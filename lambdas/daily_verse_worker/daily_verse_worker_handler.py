"""
Daily Verse scheduled worker (spec §6, §15.2).

Triggered by EventBridge Scheduler every 15 minutes. Each run:
  1. Finds users with daily verse enabled (`dailyVerseEnabled = true`) who are
     premium subscribers (daily verse is a premium capability, spec §16).
  2. Determines whose local send-time window (`dailyVerseTime` in the user's
     `timezone`) has arrived and who hasn't already received today's verse
     (`lastDailyVerseDate` guard — an atomic conditional write prevents double-sends
     across overlapping runs).
  3. Selects a personalized, non-duplicative verse (long-term memory + the
     `verse_history` do-not-repeat list), sends it over SMS, and records it to
     `verse_history` with context='daily_verse'.

Resilience (hard requirement):
  - OPENAI_API_KEY is set from the secret at runtime.
  - Neon unavailable -> selection degrades to a curated fallback verse; the batch
    never crashes.
  - A failure on one user is logged and the batch continues to the next user.
"""
import logging
import os
from datetime import datetime, timezone, timedelta

import boto3
from botocore.exceptions import ClientError

try:
    import verse_engine
except ImportError:  # local test / non-layer context
    from lambdas.daily_verse_worker import verse_engine

# SMS send path (shared_dependencies layer).
try:
    from sms_notifications import send_sms
except ImportError:  # pragma: no cover - local fallback
    try:
        from lambdas.shared.sms_notifications import send_sms
    except ImportError:
        send_sms = None

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
PROJECT_NAME = os.environ.get("PROJECT_NAME", "versiful")
USERS_TABLE = os.environ.get("USERS_TABLE", f"{ENVIRONMENT}-{PROJECT_NAME}-users")

# Fallback timezone when a user has no `timezone` attribute (IANA name).
DEFAULT_TIMEZONE = os.environ.get("DEFAULT_TIMEZONE", "America/New_York")
DEFAULT_VERSE_TIME = "08:00"
# Don't send if we're already this many minutes past the target (avoids a very late
# send when a user is found long after their window for the first time that day).
SEND_GRACE_MINUTES = int(os.environ.get("DAILY_VERSE_GRACE_MINUTES", "180"))

_dynamodb = None


def _users_table():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb.Table(USERS_TABLE)


# ---------------------------------------------------------------------------
# Timezone / due-window logic
# ---------------------------------------------------------------------------
def _user_local_now(user, now_utc):
    """Return (local_datetime, tz_name). Falls back to DEFAULT_TIMEZONE / UTC."""
    tz_name = user.get("timezone") or DEFAULT_TIMEZONE
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name)
    except Exception as e:
        logger.info("Unknown timezone %r (%s); using UTC", tz_name, str(e))
        tz = timezone.utc
        tz_name = "UTC"
    return now_utc.astimezone(tz), tz_name


def _parse_hhmm(value):
    """Parse 'HH:MM' -> (hour, minute), or None if invalid."""
    try:
        hh, mm = str(value).strip().split(":")
        h, m = int(hh), int(mm)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except (ValueError, AttributeError):
        pass
    return None


def is_due(user, now_utc):
    """
    Decide whether this user should receive their daily verse now.

    Due when (in the user's local time) the current moment is at/after the chosen
    `dailyVerseTime`, within the grace window, AND we haven't already sent today.
    Returns (due: bool, local_date: str).
    """
    local_now, _tz = _user_local_now(user, now_utc)
    local_date = local_now.date().isoformat()

    hhmm = _parse_hhmm(user.get("dailyVerseTime") or DEFAULT_VERSE_TIME) or _parse_hhmm(DEFAULT_VERSE_TIME)
    target = local_now.replace(hour=hhmm[0], minute=hhmm[1], second=0, microsecond=0)

    if local_now < target:
        return False, local_date  # before their time today
    if local_now - target > timedelta(minutes=SEND_GRACE_MINUTES):
        return False, local_date  # missed the window for today
    if user.get("lastDailyVerseDate") == local_date:
        return False, local_date  # already sent today
    return True, local_date


def _claim_send_lock(user_id, local_date):
    """
    Atomically claim today's send via a conditional UpdateItem on `lastDailyVerseDate`.

    Returns True if we won the claim (proceed to send), False if another run already
    claimed it (skip). This is the double-send guard (spec §6.2).
    """
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        _users_table().update_item(
            Key={"userId": user_id},
            UpdateExpression="SET lastDailyVerseDate = :d, lastDailyVerseAt = :ts",
            ConditionExpression="attribute_not_exists(lastDailyVerseDate) OR lastDailyVerseDate <> :d",
            ExpressionAttributeValues={":d": local_date, ":ts": now_iso},
        )
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        logger.error("Lock claim failed for %s: %s", user_id, str(e))
        return False


# ---------------------------------------------------------------------------
# Candidate selection
# ---------------------------------------------------------------------------
def _enabled_users():
    """
    Scan for users with daily verse enabled. At current scale (~2k users) a filtered
    Scan is cheap; revisit with a sparse GSI if the base grows (spec §15 open Q1).
    """
    table = _users_table()
    users = []
    kwargs = {
        "FilterExpression": "dailyVerseEnabled = :true",
        "ExpressionAttributeValues": {":true": True},
    }
    try:
        while True:
            resp = table.scan(**kwargs)
            users.extend(resp.get("Items", []))
            lek = resp.get("LastEvaluatedKey")
            if not lek:
                break
            kwargs["ExclusiveStartKey"] = lek
    except ClientError as e:
        logger.error("Failed to scan users for daily verse: %s", str(e))
    return users


# ---------------------------------------------------------------------------
# Per-user processing
# ---------------------------------------------------------------------------
def process_user(user, now_utc):
    """
    Process a single due user. Returns one of: 'sent', 'skipped', 'error'.
    Raises nothing the caller can't tolerate — the handler also wraps this.
    """
    user_id = user.get("userId")
    if not user_id:
        return "skipped"

    # Premium gating: daily verse is a paid capability (spec §16).
    if not user.get("isSubscribed", False):
        return "skipped"

    due, local_date = is_due(user, now_utc)
    if not due:
        return "skipped"

    channel = (user.get("dailyVerseChannel") or "sms").lower()
    phone_number = user.get("phoneNumber")
    if channel == "sms" and not phone_number:
        logger.info("User %s has SMS daily verse but no phone; skipping", user_id)
        return "skipped"

    # Win the atomic lock BEFORE sending so overlapping runs can't double-send.
    if not _claim_send_lock(user_id, local_date):
        return "skipped"

    verse = verse_engine.select_personalized_verse(
        user_id=user_id,
        bible_version=user.get("bibleVersion"),
        first_name=user.get("firstName"),
    )

    message_sid = None
    if channel == "sms":
        if send_sms is None:
            logger.error("send_sms unavailable; cannot deliver to %s", user_id)
        else:
            message_sid = send_sms(phone_number, verse["message"])
            if not message_sid:
                logger.error("SMS send failed for %s (verse still recorded)", user_id)

    verse_engine.record_verse_history(
        user_id=user_id,
        verse=verse,
        phone_number=phone_number,
        context_kind="daily_verse",
        channel=channel,
        source_msg_id=message_sid,
    )
    return "sent"


def handler(event, context):
    verse_engine.ensure_openai_key()
    now_utc = datetime.now(timezone.utc)

    users = _enabled_users()
    logger.info("daily_verse_worker: %d daily-verse-enabled users to evaluate", len(users))

    sent = skipped = errors = 0
    for user in users:
        try:
            outcome = process_user(user, now_utc)
        except Exception as e:  # never let one user crash the batch
            errors += 1
            logger.error("Error processing user %s: %s", user.get("userId"), str(e), exc_info=True)
            continue
        if outcome == "sent":
            sent += 1
        elif outcome == "error":
            errors += 1
        else:
            skipped += 1

    summary = {"evaluated": len(users), "sent": sent, "skipped": skipped, "errors": errors}
    logger.info("daily_verse_worker summary: %s", summary)
    return {"status": "ok", "worker": "daily_verse_worker", **summary}
