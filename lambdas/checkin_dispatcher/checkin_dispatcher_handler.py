"""
Check-in dispatcher — EventBridge Scheduler worker (hourly). Spec §10, §15.2.

Two passes, both opt-in / STOP / quiet-hours / frequency-cap gated:

  1. INACTIVITY SCAN (primary): find opted-in users whose `lastMessageAt` is older
     than their `checkinInactivityDays` and who are outside their frequency-cap
     cooldown. For each, pick ONE context selector (prayer/event/struggle/plan/general),
     compose a single warm, memory-informed message in the Versiful "we" voice, send it
     via the existing SMS path, log a `checkins` row (status='sent'), and stamp
     `lastCheckinAt` on the user (this is the idempotency + cooldown guard — never
     double-send).

  2. DUE-DATE PASS (secondary, capped): query the `checkins_by_status` GSI for
     status='scheduled' AND scheduledFor <= now (the time-sensitive exceptions written
     by extraction). Claim each row with a conditional status flip (scheduled->sent)
     BEFORE sending so concurrent/retried runs can't double-send.

Cost posture (§16.1): conservative by default — one re-engagement message per quiet
stretch, hard weekly/biweekly cap. Degrades gracefully: a Neon outage just means the
message is composed from less context, never a crash; an SMS failure is logged and
the row is marked 'failed' rather than silently retried.

Scope: only REGISTERED users with a `users` item, opt-in, and a phone number are
reachable (unregistered SMS texters have no users item — spec build-plan note #6).
"""
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Attr, Key

import checkin_logic
import checkin_composer

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
PROJECT_NAME = os.environ.get("PROJECT_NAME", "versiful")

USERS_TABLE = os.environ.get("USERS_TABLE", f"{ENVIRONMENT}-{PROJECT_NAME}-users")
CHECKINS_TABLE = os.environ.get("CHECKINS_TABLE", f"{ENVIRONMENT}-{PROJECT_NAME}-checkins")
PRAYERS_TABLE = os.environ.get("PRAYERS_TABLE", f"{ENVIRONMENT}-{PROJECT_NAME}-prayers")
USER_READING_PLANS_TABLE = os.environ.get(
    "USER_READING_PLANS_TABLE", f"{ENVIRONMENT}-{PROJECT_NAME}-user-reading-plans"
)
CHECKINS_BY_STATUS_INDEX = "checkins_by_status"

# Safety ceiling: never fan out more than this many sends in a single hourly run.
MAX_SENDS_PER_RUN = int(os.environ.get("CHECKIN_MAX_SENDS_PER_RUN", "100"))

_dynamodb = boto3.resource("dynamodb")


# ---------------------------------------------------------------------------
# Lazy shared-layer deps (import guarded so the worker still runs degraded)
# ---------------------------------------------------------------------------
def _send_sms(phone_number: str, message: str) -> Optional[str]:
    try:
        from sms_notifications import send_sms
        return send_sms(phone_number, message)
    except Exception as e:
        logger.error("SMS send path unavailable: %s", str(e))
        return None


def _fetch_memories(user_id: str) -> List[Dict[str, Any]]:
    try:
        import memory_store
        return memory_store.fetch_active_memories(user_id, limit=12) or []
    except Exception as e:
        logger.info("memory fetch degraded for %s: %s", user_id, str(e))
        return []


def _openai_key() -> Optional[str]:
    try:
        from secrets_helper import get_openai_api_key
        return get_openai_api_key()
    except Exception as e:
        logger.info("OpenAI key unavailable (composer will fall back): %s", str(e))
        return None


# ---------------------------------------------------------------------------
# DynamoDB reads
# ---------------------------------------------------------------------------
def _scan_opted_in_users() -> List[Dict[str, Any]]:
    """
    Candidate set for the inactivity scan: users with checkinEnabled = true.

    A filtered Scan is correct at current scale (spec §10.6); finer per-attribute
    eligibility (inactivity, cooldown, quiet hours) is applied in checkin_logic.
    """
    table = _dynamodb.Table(USERS_TABLE)
    users: List[Dict[str, Any]] = []
    kwargs = {"FilterExpression": Attr("checkinEnabled").eq(True)}
    while True:
        resp = table.scan(**kwargs)
        users.extend(resp.get("Items", []))
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    return users


def _active_prayers(user_id: str) -> List[Dict[str, Any]]:
    try:
        resp = _dynamodb.Table(PRAYERS_TABLE).query(
            KeyConditionExpression=Key("userId").eq(user_id)
        )
        return [p for p in resp.get("Items", []) if (p.get("status") or "active") == "active"]
    except Exception as e:
        logger.info("prayers read degraded for %s: %s", user_id, str(e))
        return []


def _active_plan(user_id: str) -> Optional[Dict[str, Any]]:
    try:
        resp = _dynamodb.Table(USER_READING_PLANS_TABLE).query(
            KeyConditionExpression=Key("userId").eq(user_id)
        )
        active = [p for p in resp.get("Items", []) if (p.get("status") or "active") == "active"]
        return active[0] if active else None
    except Exception as e:
        logger.info("plan read degraded for %s: %s", user_id, str(e))
        return None


def _load_user(user_id: str) -> Optional[Dict[str, Any]]:
    try:
        return _dynamodb.Table(USERS_TABLE).get_item(Key={"userId": user_id}).get("Item")
    except Exception as e:
        logger.warning("could not load user %s: %s", user_id, str(e))
        return None


def _load_prayer(user_id: str, prayer_id: str) -> Optional[Dict[str, Any]]:
    try:
        return _dynamodb.Table(PRAYERS_TABLE).get_item(
            Key={"userId": user_id, "prayerId": prayer_id}
        ).get("Item")
    except Exception as e:
        logger.info("could not load prayer %s: %s", prayer_id, str(e))
        return None


# ---------------------------------------------------------------------------
# DynamoDB writes
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_checkin_sent(user_id: str, trigger: str, ctx: Dict[str, Any], message: str) -> None:
    now = _now_iso()
    item = {
        "userId": user_id,
        "checkinId": str(uuid.uuid4()),
        "trigger": trigger,
        "contextSelector": ctx.get("selector"),
        "channel": "sms",
        "status": "sent",
        "messageSent": message,
        "createdAt": now,
        "sentAt": now,
    }
    if ctx.get("ref"):
        item["triggerRef"] = ctx["ref"]
    try:
        _dynamodb.Table(CHECKINS_TABLE).put_item(Item=item)
    except Exception as e:
        logger.error("failed to log checkin row for %s: %s", user_id, str(e))


def _stamp_last_checkin(user_id: str) -> None:
    """Record the send time; this drives the frequency-cap cooldown + idempotency."""
    try:
        _dynamodb.Table(USERS_TABLE).update_item(
            Key={"userId": user_id},
            UpdateExpression="SET lastCheckinAt = :now",
            ExpressionAttributeValues={":now": _now_iso()},
        )
    except Exception as e:
        logger.error("failed to stamp lastCheckinAt for %s: %s", user_id, str(e))


def _claim_scheduled_row(user_id: str, checkin_id: str) -> bool:
    """
    Atomically flip a scheduled row to 'sent' (idempotent claim before sending).

    Returns True if THIS run won the claim (status was 'scheduled'); False if it was
    already taken (prevents double-send across overlapping/retried runs).
    """
    try:
        _dynamodb.Table(CHECKINS_TABLE).update_item(
            Key={"userId": user_id, "checkinId": checkin_id},
            UpdateExpression="SET #s = :sent, sentAt = :now",
            ConditionExpression=Attr("status").eq("scheduled"),
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":sent": "sent", ":now": _now_iso()},
        )
        return True
    except _dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        return False
    except Exception as e:
        logger.error("claim of checkin %s failed: %s", checkin_id, str(e))
        return False


def _mark_row_status(user_id: str, checkin_id: str, status: str) -> None:
    try:
        _dynamodb.Table(CHECKINS_TABLE).update_item(
            Key={"userId": user_id, "checkinId": checkin_id},
            UpdateExpression="SET #s = :st",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":st": status},
        )
    except Exception as e:
        logger.error("could not mark checkin %s as %s: %s", checkin_id, status, str(e))


# ---------------------------------------------------------------------------
# Passes
# ---------------------------------------------------------------------------
def run_inactivity_pass(now: datetime, api_key: Optional[str], budget: int) -> Dict[str, int]:
    stats = {"candidates": 0, "eligible": 0, "sent": 0, "failed": 0, "skipped": 0}
    try:
        users = _scan_opted_in_users()
    except Exception as e:
        logger.error("inactivity scan failed: %s", str(e))
        return stats

    stats["candidates"] = len(users)
    for user in users:
        if stats["sent"] >= budget:
            logger.warning("send budget (%d) reached; deferring remaining users", budget)
            break

        eligible, reason = checkin_logic.eligible_for_inactivity(user, now)
        if not eligible:
            stats["skipped"] += 1
            logger.info("skip user %s: %s", user.get("userId"), reason)
            continue
        stats["eligible"] += 1

        user_id = user["userId"]
        ctx = checkin_logic.select_context(
            memories=_fetch_memories(user_id),
            prayers=_active_prayers(user_id),
            active_plan=_active_plan(user_id),
            now=now,
        )
        message = checkin_composer.compose_message(user, ctx, api_key=api_key)
        sid = _send_sms(user["phoneNumber"], message)
        if sid:
            _log_checkin_sent(user_id, "inactivity", ctx, message)
            _stamp_last_checkin(user_id)
            stats["sent"] += 1
            logger.info("inactivity check-in sent to %s (selector=%s)", user_id, ctx.get("selector"))
        else:
            stats["failed"] += 1
            logger.error("inactivity check-in send failed for %s", user_id)
    return stats


def _ctx_from_scheduled_row(user_id: str, row: Dict[str, Any]) -> Dict[str, Any]:
    """Rebuild a composer context from a stored scheduled row (best-effort enrich)."""
    selector = row.get("contextSelector") or "general"
    ref = row.get("triggerRef")
    ctx: Dict[str, Any] = {"selector": selector, "ref": ref}
    if selector == "prayer_followup" and ref:
        prayer = _load_prayer(user_id, ref)
        if prayer:
            ctx["title"] = prayer.get("title")
            ctx["people"] = prayer.get("people") or []
            ctx["eventDate"] = prayer.get("eventDate")
    return ctx


def run_due_date_pass(now: datetime, api_key: Optional[str], budget: int) -> Dict[str, int]:
    stats = {"due": 0, "sent": 0, "failed": 0, "skipped": 0}
    now_iso = now.isoformat()
    try:
        resp = _dynamodb.Table(CHECKINS_TABLE).query(
            IndexName=CHECKINS_BY_STATUS_INDEX,
            KeyConditionExpression=Key("status").eq("scheduled") & Key("scheduledFor").lte(now_iso),
        )
        rows = resp.get("Items", [])
    except Exception as e:
        logger.error("due-date GSI query failed: %s", str(e))
        return stats

    stats["due"] = len(rows)
    for row in rows:
        if stats["sent"] >= budget:
            break
        user_id = row.get("userId")
        checkin_id = row.get("checkinId")
        if not user_id or not checkin_id:
            continue

        user = _load_user(user_id)
        if not user:
            _mark_row_status(user_id, checkin_id, "skipped")
            stats["skipped"] += 1
            continue

        eligible, reason = checkin_logic.eligible_for_time_sensitive(user, now)
        if not eligible:
            stats["skipped"] += 1
            logger.info("skip scheduled checkin %s: %s", checkin_id, reason)
            continue

        # Claim BEFORE sending so a retry/overlap can't double-send.
        if not _claim_scheduled_row(user_id, checkin_id):
            stats["skipped"] += 1
            continue

        ctx = _ctx_from_scheduled_row(user_id, row)
        message = checkin_composer.compose_message(user, ctx, api_key=api_key)
        sid = _send_sms(user["phoneNumber"], message)
        if sid:
            _stamp_last_checkin(user_id)
            stats["sent"] += 1
            logger.info("time-sensitive check-in sent to %s (selector=%s)", user_id, ctx.get("selector"))
        else:
            _mark_row_status(user_id, checkin_id, "failed")
            stats["failed"] += 1
    return stats


def handler(event, context):
    now = datetime.now(timezone.utc)
    api_key = _openai_key()
    logger.info("checkin_dispatcher run starting at %s", now.isoformat())

    inactivity = run_inactivity_pass(now, api_key, budget=MAX_SENDS_PER_RUN)
    remaining = max(0, MAX_SENDS_PER_RUN - inactivity.get("sent", 0))
    due_date = run_due_date_pass(now, api_key, budget=remaining)

    result = {
        "status": "ok",
        "ranAt": now.isoformat(),
        "inactivity": inactivity,
        "timeSensitive": due_date,
    }
    logger.info("checkin_dispatcher run complete: %s", result)
    return result
