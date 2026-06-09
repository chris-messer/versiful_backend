"""
Prayer Reminder scheduled worker (COMPANION_SPEC.md §7, §15.2).

Triggered by EventBridge Scheduler every 15 minutes. Each run:
  1. Finds prayers with reminders enabled (`reminderCadence` in {"daily","weekly"})
     and status='active'. A filtered Scan is used (the prayers table has no reminder
     GSI and the sibling workers — daily_verse_worker, reading_plan_delivery — scan
     their candidate tables at current scale; see the design note below).
  2. Verifies the owning user is still premium (`isSubscribed`, mirroring
     daily_verse_worker) and has a usable phone number before sending.
  3. For a prayer whose `nextReminderAt` is due (<= now UTC), atomically claims the
     send by advancing `nextReminderAt` to the next local window BEFORE sending (the
     double-send guard — an overlapping/retried run can't win the same claim), then
     sends an SMS reminder referencing the prayer in the Versiful "we" voice.
  4. For a daily/weekly prayer whose `nextReminderAt` is null/empty (the REST + chat
     write paths persist the cadence but never initialize the timestamp), the first
     run INITIALIZES `nextReminderAt` to the next local delivery window WITHOUT
     sending — so the first real reminder lands at the user's preferred local time
     rather than at whatever odd hour the bootstrap run happened to fire.

Cadence math: daily = +1 day, weekly = +7 days, anchored to the user's local
timezone at `PRAYER_REMINDER_TIME` (default 09:00 local; falls back to the user's
`dailyVerseTime` if set), consistent with how daily_verse_worker / reading_plan_delivery
schedule per-user local windows.

DESIGN NOTE — why a Scan and not a GSI:
  The prayers table is keyed (userId, prayerId) with no GSI (terraform
  _companion_tables.tf documents the access pattern as "Query PK=userId, filter by
  status in-app — no status GSI needed"). A sparse GSI on `nextReminderAt` would
  EXCLUDE every prayer whose `nextReminderAt` is still null — and that attribute is
  never initialized by any current writer — so a GSI would silently never fire and
  the feature would stay inert. A filtered Scan correctly surfaces both due and
  un-initialized prayers and matches the established sibling-worker convention.

Resilience (hard requirement):
  - A failure on one prayer/user is logged and the batch continues to the next.
  - The send path is import-guarded so the worker still runs (degraded) if the SMS
    layer is unavailable.
  - A hard per-run send cap (PRAYER_REMINDER_MAX_SENDS_PER_RUN) bounds fan-out, like
    the checkin_dispatcher's CHECKIN_MAX_SENDS_PER_RUN.
"""
import logging
import os
from datetime import datetime, timezone, timedelta

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

# SMS send path (shared modules vendored into the langchain layer; twilio in sms_layer).
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
PRAYERS_TABLE = os.environ.get("PRAYERS_TABLE", f"{ENVIRONMENT}-{PROJECT_NAME}-prayers")

# Fallback timezone when a user has no `timezone` attribute (IANA name).
DEFAULT_TIMEZONE = os.environ.get("DEFAULT_TIMEZONE", "America/New_York")
# Local time-of-day at which prayer reminders land (HH:MM in the user's timezone).
DEFAULT_REMINDER_TIME = os.environ.get("PRAYER_REMINDER_TIME", "09:00")
# Safety ceiling: never fan out more than this many sends in a single run.
MAX_SENDS_PER_RUN = int(os.environ.get("PRAYER_REMINDER_MAX_SENDS_PER_RUN", "100"))

REMINDER_CADENCES = ("daily", "weekly")
CADENCE_DAYS = {"daily": 1, "weekly": 7}

_dynamodb = None


def _resource():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb


def _prayers_table():
    return _resource().Table(PRAYERS_TABLE)


def _users_table():
    return _resource().Table(USERS_TABLE)


# ---------------------------------------------------------------------------
# Timezone / scheduling helpers
# ---------------------------------------------------------------------------
def _resolve_tz(tz_name):
    """Return a tzinfo for the IANA name, falling back to UTC if unresolved."""
    name = tz_name or DEFAULT_TIMEZONE
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        logger.info("Could not resolve timezone %r; using UTC.", name)
        return timezone.utc


def _parse_hhmm(value, default=(9, 0)):
    try:
        hh, mm = str(value).strip().split(":")
        h, m = int(hh), int(mm)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except (ValueError, AttributeError):
        pass
    return default


def _reminder_hhmm(user):
    """Local send time: PRAYER_REMINDER_TIME default, else the user's dailyVerseTime."""
    default = _parse_hhmm(DEFAULT_REMINDER_TIME, default=(9, 0))
    return _parse_hhmm((user or {}).get("dailyVerseTime"), default=default)


def _to_iso(dt):
    """Serialize an aware datetime to UTC ISO-8601 with a trailing Z."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value):
    """Parse an ISO-8601 string to an aware UTC datetime, or None if unparseable."""
    if not value:
        return None
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _at_local_time(local_date, tz, hhmm):
    """Build an aware datetime for `local_date` at hh:mm in `tz`."""
    return datetime(local_date.year, local_date.month, local_date.day,
                    hhmm[0], hhmm[1], 0, 0, tzinfo=tz)


def next_initial_reminder(now_utc, tz, hhmm):
    """Bootstrap anchor: the next occurrence of hh:mm local (today if still ahead,
    else tomorrow). Returned as a UTC ISO string."""
    local_now = now_utc.astimezone(tz)
    target_today = _at_local_time(local_now.date(), tz, hhmm)
    if local_now < target_today:
        return _to_iso(target_today)
    return _to_iso(_at_local_time(local_now.date() + timedelta(days=1), tz, hhmm))


def advance_reminder(now_utc, tz, hhmm, cadence):
    """Recurring anchor after a send: hh:mm local on (today + cadence step). UTC ISO."""
    step = CADENCE_DAYS.get(cadence, 1)
    local_now = now_utc.astimezone(tz)
    next_date = local_now.date() + timedelta(days=step)
    return _to_iso(_at_local_time(next_date, tz, hhmm))


# ---------------------------------------------------------------------------
# DynamoDB reads
# ---------------------------------------------------------------------------
def scan_reminder_prayers():
    """Scan for active prayers with a daily/weekly reminder cadence.

    Filtered Scan (no reminder GSI exists; see module design note). Small table at
    current scale, mirroring daily_verse_worker._enabled_users / reading_plan scan.
    """
    table = _prayers_table()
    items = []
    kwargs = {
        "FilterExpression": Attr("reminderCadence").is_in(list(REMINDER_CADENCES)),
    }
    try:
        while True:
            resp = table.scan(**kwargs)
            items.extend(resp.get("Items", []))
            lek = resp.get("LastEvaluatedKey")
            if not lek:
                break
            kwargs["ExclusiveStartKey"] = lek
    except ClientError as e:
        logger.error("Failed to scan prayers for reminders: %s", str(e))
    return items


def load_user(user_id):
    try:
        return _users_table().get_item(Key={"userId": user_id}).get("Item")
    except ClientError as e:
        logger.warning("Could not load user %s: %s", user_id, str(e))
        return None


# ---------------------------------------------------------------------------
# DynamoDB writes (atomic claims)
# ---------------------------------------------------------------------------
def _initialize_next(user_id, prayer_id, new_next):
    """Set nextReminderAt for a prayer that has never been scheduled.

    Conditional on the attribute being absent or NULL so a concurrent run can't
    double-initialize. Returns True if this run set it.
    """
    try:
        _prayers_table().update_item(
            Key={"userId": user_id, "prayerId": prayer_id},
            UpdateExpression="SET nextReminderAt = :new, updatedAt = :now",
            ConditionExpression=(
                Attr("nextReminderAt").not_exists() | Attr("nextReminderAt").eq(None)
            ),
            ExpressionAttributeValues={":new": new_next, ":now": _to_iso(datetime.now(timezone.utc))},
        )
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        logger.error("Failed to initialize reminder for %s/%s: %s", user_id, prayer_id, str(e))
        return False


def _claim_due(user_id, prayer_id, old_next, new_next):
    """Atomically claim a due reminder by advancing nextReminderAt BEFORE sending.

    Conditional on nextReminderAt still equalling the due value we read. Returns True
    if this run won the claim (proceed to send); False if another run already advanced
    it (skip — the double-send guard).
    """
    now_iso = _to_iso(datetime.now(timezone.utc))
    try:
        _prayers_table().update_item(
            Key={"userId": user_id, "prayerId": prayer_id},
            UpdateExpression="SET nextReminderAt = :new, lastReminderAt = :now, updatedAt = :now",
            ConditionExpression=Attr("nextReminderAt").eq(old_next),
            ExpressionAttributeValues={":new": new_next, ":now": now_iso},
        )
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        logger.error("Failed to claim reminder for %s/%s: %s", user_id, prayer_id, str(e))
        return False


# ---------------------------------------------------------------------------
# Message composition (Versiful "we" voice — no first-person singular "I")
# ---------------------------------------------------------------------------
def compose_reminder(prayer):
    title = (prayer.get("title") or "your prayer request").strip()
    people = prayer.get("people") or []
    body = prayer.get("body")

    lines = ["\U0001F64F A gentle reminder from Versiful", "",
             f"Take a moment to pray over: {title}."]
    if isinstance(people, list) and people:
        names = ", ".join(str(p) for p in people[:5])
        lines.append(f"We're lifting up {names} alongside you.")
    if body:
        snippet = str(body).strip()
        if snippet:
            lines.append("")
            lines.append(snippet[:200])
    lines.append("")
    lines.append("Reply anytime to let us know how it's going and we'll keep it in your journal.")
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Per-prayer processing
# ---------------------------------------------------------------------------
def process_prayer(prayer, now_utc):
    """Process a single prayer. Returns one of:
    'sent' | 'initialized' | 'skipped' | 'error'.
    """
    user_id = prayer.get("userId")
    prayer_id = prayer.get("prayerId")
    if not user_id or not prayer_id:
        return "skipped"

    cadence = (prayer.get("reminderCadence") or "none").lower()
    if cadence not in REMINDER_CADENCES:
        return "skipped"
    if (prayer.get("status") or "active") != "active":
        return "skipped"

    user = load_user(user_id)
    # Premium gating mirrors daily_verse_worker exactly (reminders are a paid feature).
    if not user or not user.get("isSubscribed", False):
        return "skipped"

    phone_number = user.get("phoneNumber")
    if not phone_number:
        logger.info("User %s has reminder prayer %s but no phone; skipping", user_id, prayer_id)
        return "skipped"

    tz = _resolve_tz(user.get("timezone"))
    hhmm = _reminder_hhmm(user)

    old_next = prayer.get("nextReminderAt")
    due_at = _parse_iso(old_next)

    # Bootstrap: cadence set but never scheduled -> initialize to the next local
    # window without sending (avoids an odd-hour first reminder).
    if due_at is None:
        new_next = next_initial_reminder(now_utc, tz, hhmm)
        if _initialize_next(user_id, prayer_id, new_next):
            logger.info("Initialized reminder for %s/%s -> %s", user_id, prayer_id, new_next)
            return "initialized"
        return "skipped"

    if due_at > now_utc:
        return "skipped"  # not due yet

    # Due: claim (advance nextReminderAt) BEFORE sending so we never double-send.
    new_next = advance_reminder(now_utc, tz, hhmm, cadence)
    if not _claim_due(user_id, prayer_id, old_next, new_next):
        return "skipped"

    if send_sms is None:
        logger.error("send_sms unavailable; cannot deliver reminder to %s", user_id)
        return "error"

    message = compose_reminder(prayer)
    sid = send_sms(phone_number, message)
    if not sid:
        logger.error("Reminder SMS send failed for %s/%s (rescheduled to %s)",
                     user_id, prayer_id, new_next)
        return "error"

    logger.info("Prayer reminder sent to %s for %s (next=%s)", user_id, prayer_id, new_next)
    return "sent"


def handler(event, context):
    now_utc = datetime.now(timezone.utc)
    prayers = scan_reminder_prayers()
    logger.info("prayer_reminder: %d reminder-enabled prayers to evaluate", len(prayers))

    sent = skipped = errors = initialized = 0
    for prayer in prayers:
        if sent >= MAX_SENDS_PER_RUN:
            logger.warning("send cap (%d) reached; deferring remaining prayers", MAX_SENDS_PER_RUN)
            skipped += 1
            continue
        try:
            outcome = process_prayer(prayer, now_utc)
        except Exception as e:  # never let one prayer crash the batch
            errors += 1
            logger.error("Error processing prayer %s/%s: %s",
                         prayer.get("userId"), prayer.get("prayerId"), str(e), exc_info=True)
            continue
        if outcome == "sent":
            sent += 1
        elif outcome == "error":
            errors += 1
        elif outcome == "initialized":
            initialized += 1
        else:
            skipped += 1

    summary = {
        "evaluated": len(prayers),
        "sent": sent,
        "skipped": skipped,
        "errors": errors,
        "initialized": initialized,
    }
    logger.info("prayer_reminder summary: %s", summary)
    return {"status": "ok", "worker": "prayer_reminder", **summary}
