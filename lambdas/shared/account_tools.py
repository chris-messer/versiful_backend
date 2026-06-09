"""
In-chat account-management tool implementations (spec §5.4).

These are the underlying CALLABLE functions behind the agent tools
`set_daily_verse`, `set_checkin_frequency`, `update_bible_version`,
`set_response_style`, `pause_reading_plan`, `resume_reading_plan`, and
`get_account_status`. They are NOT decorated here — the chat integration agent
registers them as LangChain `@tool`s (resolving the current user_id from its
request context) so this module stays free of any agent/LLM dependency.

Design (spec §5.4 guardrails):
  - Every mutation goes through `preferences.apply_preferences(..., source="chat")`,
    so chat and web write the SAME `users` attributes and every change is audited.
  - Confirm-then-apply: each function returns a short plain-language read-back of
    what changed and how to reverse it. Turning things OFF is always safe; turning
    them ON is allowed (the user already consented to SMS) and audited.
  - Billing stays OUT of chat: nothing here touches Stripe; plan changes/cancellation
    are pointed elsewhere (portal link / STOP) by the agent, never mutated here.
  - Idempotent: re-issuing an already-applied change is a no-op that still confirms.
"""
import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

try:
    import preferences
except ImportError:  # local test / non-layer context
    from lambdas.shared import preferences

logger = logging.getLogger()

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
PROJECT_NAME = os.environ.get("PROJECT_NAME", "versiful")
USER_READING_PLANS_TABLE = os.environ.get(
    "USER_READING_PLANS_TABLE", f"{ENVIRONMENT}-{PROJECT_NAME}-user-reading-plans"
)
PRAYERS_TABLE = os.environ.get("PRAYERS_TABLE", f"{ENVIRONMENT}-{PROJECT_NAME}-prayers")
SMS_USAGE_TABLE = os.environ.get("SMS_USAGE_TABLE", f"{ENVIRONMENT}-{PROJECT_NAME}-sms-usage")

FREE_SMS_LIMIT = 5  # spec §16 (free tier SMS/mo)

_dynamodb = None


def _table(name):
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb.Table(name)


# ---------------------------------------------------------------------------
# Preference tools
# ---------------------------------------------------------------------------
def set_daily_verse(user_id, enabled, time=None):
    """Turn the daily verse on/off; optionally set the delivery time (HH:MM)."""
    if not user_id:
        return "I couldn't identify your account, so I didn't change anything."
    body = {"dailyVerseEnabled": bool(enabled)}
    if time is not None:
        body["dailyVerseTime"] = time
    clean, errors = preferences.validate_and_normalize(body)
    if errors:
        if any(e["field"] == "dailyVerseTime" for e in errors):
            return ("That time didn't look right — please give me a 24-hour time like "
                    "07:30. I haven't changed anything yet.")
        return "I couldn't apply that change. Please try again."
    preferences.apply_preferences(user_id, clean, source="chat")
    if not enabled:
        return ("Done — I've turned off your daily verse. Just say \"turn my morning "
                "verse back on\" anytime to resume it.")
    when = clean.get("dailyVerseTime", "your usual time")
    return (f"Done — you'll get a personalized verse each morning at {when}. "
            "Say \"turn off my daily verse\" whenever you'd like to stop.")


def set_checkin_frequency(user_id, level):
    """
    Reduce/increase/disable inactivity check-ins from a natural-language level.

    Maps: 'off' -> disabled; 'weekly'/'more often' -> weekly (4d window);
    'biweekly'/'less often' -> biweekly (7d window).
    """
    if not user_id:
        return "I couldn't identify your account, so I didn't change anything."
    raw = str(level or "").strip().lower()
    mapping = {
        "off": ("off", False),
        "none": ("off", False),
        "never": ("off", False),
        "stop": ("off", False),
        "less": ("biweekly", True),
        "less often": ("biweekly", True),
        "biweekly": ("biweekly", True),
        "occasionally": ("biweekly", True),
        "weekly": ("weekly", True),
        "more": ("weekly", True),
        "more often": ("weekly", True),
    }
    if raw not in mapping:
        return ("I can set check-ins to off, weekly, or biweekly (less often). "
                "Which would you like? I haven't changed anything yet.")
    frequency, enabled = mapping[raw]
    body = {"checkinEnabled": enabled}
    if enabled:
        body["checkinFrequency"] = frequency
        body["checkinInactivityDays"] = preferences.CHECKIN_FREQUENCY_DAYS.get(frequency, 4)
    clean, errors = preferences.validate_and_normalize(body)
    if errors:
        return "I couldn't apply that check-in setting. Please try again."
    preferences.apply_preferences(user_id, clean, source="chat")
    if not enabled:
        return ("Done — I won't send proactive check-ins anymore. Say \"check in on me "
                "weekly\" if you'd like them back.")
    cadence = "about once a week" if frequency == "weekly" else "about every couple of weeks"
    return (f"Done — I'll gently check in {cadence} if you go quiet. "
            "Say \"check in less often\" or \"turn off check-ins\" to change this.")


def update_bible_version(user_id, version):
    """Change the preferred Bible translation (NIV / ESV / KJV / ...)."""
    if not user_id:
        return "I couldn't identify your account, so I didn't change anything."
    clean, errors = preferences.validate_and_normalize({"bibleVersion": version})
    if errors:
        supported = ", ".join(sorted(preferences.VALID_BIBLE_VERSIONS))
        return (f"I don't recognize that translation. I can use: {supported}. "
                "I haven't changed anything yet.")
    preferences.apply_preferences(user_id, clean, source="chat")
    return (f"Done — I'll quote Scripture in the {clean['bibleVersion']} from now on. "
            "Tell me another version anytime to switch again.")


def set_response_style(user_id, tone=None, length=None):
    """Set tone (warm / pastoral / concise) and/or length (short / fuller)."""
    if not user_id:
        return "I couldn't identify your account, so I didn't change anything."
    if tone is None and length is None:
        return ("Tell me how you'd like me to respond — tone (warm, pastoral, or "
                "concise) and/or length (short or fuller).")
    style = {}
    if tone is not None:
        style["tone"] = tone
    if length is not None:
        style["length"] = length
    clean, errors = preferences.validate_and_normalize({"responseStyle": style})
    if errors:
        return ("I can set tone to warm, pastoral, or concise, and length to short or "
                "fuller. I haven't changed anything yet.")
    preferences.apply_preferences(user_id, clean, source="chat")
    applied = clean["responseStyle"]
    bits = []
    if applied.get("tone"):
        bits.append(f"a {applied['tone']} tone")
    if applied.get("length"):
        bits.append(f"{applied['length']} responses")
    return (f"Done — I'll use {' and '.join(bits)}. Just tell me if you'd like me to "
            "adjust how I respond.")


# ---------------------------------------------------------------------------
# Reading-plan pause/resume (status on the user's active plan)
# ---------------------------------------------------------------------------
def _list_user_plans(user_id):
    try:
        resp = _table(USER_READING_PLANS_TABLE).query(
            KeyConditionExpression="userId = :uid",
            ExpressionAttributeValues={":uid": user_id},
        )
        return resp.get("Items", [])
    except ClientError as e:
        logger.error("Failed to list reading plans for %s: %s", user_id, str(e))
        return []


def _set_plan_status(user_id, plan_id, status):
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        _table(USER_READING_PLANS_TABLE).update_item(
            Key={"userId": user_id, "planId": plan_id},
            UpdateExpression="SET #s = :s, updatedAt = :ts",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": status, ":ts": now_iso},
        )
        return True
    except ClientError as e:
        logger.error("Failed to set plan %s status for %s: %s", plan_id, user_id, str(e))
        return False


def pause_reading_plan(user_id):
    """Pause delivery of the user's currently active reading plan."""
    if not user_id:
        return "I couldn't identify your account, so I didn't change anything."
    plans = _list_user_plans(user_id)
    active = [p for p in plans if p.get("status") == "active"]
    if not active:
        if any(p.get("status") == "paused" for p in plans):
            return "Your reading plan is already paused. Say \"resume my plan\" to pick it back up."
        return "You don't have an active reading plan right now, so there's nothing to pause."
    plan = active[0]
    if _set_plan_status(user_id, plan["planId"], "paused"):
        return ("Done — I've paused your reading plan; you won't get daily plan messages "
                "until you say \"resume my plan.\" No progress is lost.")
    return "I ran into a problem pausing your plan. Please try again in a moment."


def resume_reading_plan(user_id):
    """Resume delivery of the user's paused reading plan."""
    if not user_id:
        return "I couldn't identify your account, so I didn't change anything."
    plans = _list_user_plans(user_id)
    paused = [p for p in plans if p.get("status") == "paused"]
    if not paused:
        if any(p.get("status") == "active" for p in plans):
            return "Your reading plan is already active — you're all set."
        return "You don't have a paused reading plan to resume right now."
    plan = paused[0]
    if _set_plan_status(user_id, plan["planId"], "active"):
        return ("Done — your reading plan is active again. I'll pick up right where you "
                "left off. Say \"pause my plan\" anytime.")
    return "I ran into a problem resuming your plan. Please try again in a moment."


# ---------------------------------------------------------------------------
# get_account_status (read-only cross-table snapshot)
# ---------------------------------------------------------------------------
def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _active_prayer_count(user_id):
    try:
        resp = _table(PRAYERS_TABLE).query(
            KeyConditionExpression="userId = :uid",
            ExpressionAttributeValues={":uid": user_id},
        )
        return sum(1 for p in resp.get("Items", []) if p.get("status", "active") == "active")
    except ClientError:
        return 0


def _sms_remaining(user, phone_number):
    """Remaining free SMS this period, or None for unlimited (subscribed)."""
    if user.get("isSubscribed"):
        return None
    if not phone_number:
        return FREE_SMS_LIMIT
    try:
        resp = _table(SMS_USAGE_TABLE).get_item(Key={"phoneNumber": phone_number})
        usage = resp.get("Item") or {}
        sent = _to_int(usage.get("plan_messages_sent", 0))
        return max(0, FREE_SMS_LIMIT - sent)
    except ClientError:
        return FREE_SMS_LIMIT


def get_account_status(user_id):
    """
    Read-back only: plan, SMS usage remaining, key preferences, active-prayer count,
    and current reading-plan progress — kept concise (spec §5.4). No mutation.
    """
    if not user_id:
        return "I couldn't identify your account."
    prefs = preferences.read_preferences(user_id)
    if prefs is None:
        return "I couldn't find your account details just now."
    user = preferences.get_user(user_id) or {}

    plan_label = "Premium" if user.get("isSubscribed") else "Free"
    remaining = _sms_remaining(user, user.get("phoneNumber"))
    sms_line = "unlimited messages" if remaining is None else f"{remaining} free message(s) left this month"

    dv = "on" if prefs.get("dailyVerseEnabled") else "off"
    dv_time = prefs.get("dailyVerseTime", "08:00")
    checkins = "off" if not prefs.get("checkinEnabled") else prefs.get("checkinFrequency", "weekly")
    bible = prefs.get("bibleVersion", "your default translation")

    prayer_count = _active_prayer_count(user_id)

    plans = _list_user_plans(user_id)
    active_plans = [p for p in plans if p.get("status") == "active"]
    if active_plans:
        p = active_plans[0]
        plan_progress = (f"\"{p.get('planId')}\" — day {_to_int(p.get('currentDay', 1), 1)}"
                         f" of {_to_int(p.get('dayCount', 0), 0) or '?'}")
    elif any(p.get("status") == "paused" for p in plans):
        plan_progress = "a paused plan"
    else:
        plan_progress = "no active plan"

    lines = [
        f"Here's your account:",
        f"- Plan: {plan_label} ({sms_line})",
        f"- Daily verse: {dv}" + (f" at {dv_time}" if prefs.get("dailyVerseEnabled") else ""),
        f"- Check-ins: {checkins}",
        f"- Bible version: {bible}",
        f"- Active prayers: {prayer_count}",
        f"- Reading plan: {plan_progress}",
    ]
    return "\n".join(lines)
