"""
Communication-preference read/validate/write for the companion account-management
lambda (spec §4.4, §5.4, §12).

Preferences are ATTRIBUTES on the existing `users` DynamoDB item — there is no
separate preferences table. Both the web Settings UI (PUT /users/preferences) and
the in-chat account-management tools (account_tools.py) write the SAME attributes
through `apply_preferences()` so chat and web stay in parity (spec §5.4, §12.2).

Guardrails enforced here:
  - Only a fixed WHITELIST of preference fields may be written. Anything else
    (e.g. isSubscribed, plan, userId, phoneNumber, billing) is rejected — a user
    can never toggle a field they shouldn't via this path.
  - Every field is validated/normalized server-side (conventions §6).
  - Every applied change writes an audit-trail entry (ts, source, field, old, new)
    to `prefAuditLog` on the users item (TCPA / consent, spec §5.4).
"""
import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
PROJECT_NAME = os.environ.get("PROJECT_NAME", "versiful")
USERS_TABLE = os.environ.get("USERS_TABLE", f"{ENVIRONMENT}-{PROJECT_NAME}-users")

VALID_CHANNELS = {"sms", "web"}
VALID_CHECKIN_FREQUENCY = {"off", "weekly", "biweekly"}
VALID_TONES = {"warm", "pastoral", "concise"}
VALID_LENGTHS = {"short", "fuller"}
VALID_BIBLE_VERSIONS = {
    "NIV", "ESV", "KJV", "NLT", "NASB", "NKJV", "CSB", "MSG", "AMP", "NRSV",
}

# Natural-language -> checkinFrequency / inactivity-days mapping (spec §5.4).
CHECKIN_FREQUENCY_DAYS = {"weekly": 4, "biweekly": 7}

# Defaults per spec §4.4 (used by read_preferences for the comms-pref attrs).
PREFERENCE_DEFAULTS = {
    "primaryChannel": "sms",
    "dailyVerseEnabled": False,
    "dailyVerseTime": "08:00",
    "dailyVerseChannel": "sms",
    "checkinEnabled": False,
    "checkinFrequency": "weekly",
    "checkinInactivityDays": 4,
    "readingPlanReminders": True,
    "marketingUpdates": True,
    "encouragementTips": True,
}

# Settings-style attrs (spec §12) also writable via this path but with no §4.4 default.
SETTINGS_FIELDS = {"bibleVersion", "responseStyle", "timezone"}

_dynamodb = None


def _users_table():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb.Table(USERS_TABLE)


# ---------------------------------------------------------------------------
# Validators (each returns (normalized_value, error_message_or_None))
# ---------------------------------------------------------------------------
def _v_bool(value):
    if isinstance(value, bool):
        return value, None
    return None, "must be a boolean"


def _v_hhmm(value):
    try:
        hh, mm = str(value).strip().split(":")
        h, m = int(hh), int(mm)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return f"{h:02d}:{m:02d}", None
    except (ValueError, AttributeError):
        pass
    return None, "must be a time in HH:MM (24h) format"


def _v_channel(value):
    v = str(value).strip().lower()
    if v in VALID_CHANNELS:
        return v, None
    return None, f"must be one of {sorted(VALID_CHANNELS)}"


def _v_checkin_frequency(value):
    v = str(value).strip().lower()
    if v in VALID_CHECKIN_FREQUENCY:
        return v, None
    return None, f"must be one of {sorted(VALID_CHECKIN_FREQUENCY)}"


def _v_inactivity_days(value):
    try:
        n = int(value)
    except (ValueError, TypeError):
        return None, "must be an integer"
    if 1 <= n <= 30:
        return n, None
    return None, "must be between 1 and 30"


def _v_bible_version(value):
    v = str(value).strip().upper()
    if v in VALID_BIBLE_VERSIONS:
        return v, None
    return None, f"must be one of {sorted(VALID_BIBLE_VERSIONS)}"


def _v_response_style(value):
    if not isinstance(value, dict):
        return None, "must be an object with optional 'tone' and 'length'"
    out = {}
    if "tone" in value and value["tone"] is not None:
        tone = str(value["tone"]).strip().lower()
        if tone not in VALID_TONES:
            return None, f"tone must be one of {sorted(VALID_TONES)}"
        out["tone"] = tone
    if "length" in value and value["length"] is not None:
        length = str(value["length"]).strip().lower()
        if length not in VALID_LENGTHS:
            return None, f"length must be one of {sorted(VALID_LENGTHS)}"
        out["length"] = length
    if not out:
        return None, "must include 'tone' and/or 'length'"
    return out, None


def _v_timezone(value):
    tz = str(value).strip()
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(tz)
        return tz, None
    except Exception:
        return None, "must be a valid IANA timezone name (e.g. America/New_York)"


# field name -> validator
VALIDATORS = {
    "primaryChannel": _v_channel,
    "dailyVerseEnabled": _v_bool,
    "dailyVerseTime": _v_hhmm,
    "dailyVerseChannel": _v_channel,
    "checkinEnabled": _v_bool,
    "checkinFrequency": _v_checkin_frequency,
    "checkinInactivityDays": _v_inactivity_days,
    "readingPlanReminders": _v_bool,
    "marketingUpdates": _v_bool,
    "encouragementTips": _v_bool,
    "bibleVersion": _v_bible_version,
    "responseStyle": _v_response_style,
    "timezone": _v_timezone,
}

WRITABLE_FIELDS = set(VALIDATORS.keys())


def validate_and_normalize(body):
    """
    Validate an incoming preferences body.

    Returns (clean: dict, errors: list[{field, message}]).
    Unknown / non-writable keys are reported as errors (the guardrail against
    toggling fields the user shouldn't).
    """
    if not isinstance(body, dict):
        return {}, [{"field": "_body", "message": "request body must be a JSON object"}]

    clean, errors = {}, []
    for key, value in body.items():
        if key not in WRITABLE_FIELDS:
            errors.append({"field": key, "message": "unknown or non-writable preference"})
            continue
        if value is None:
            continue  # null = "leave unchanged"
        normalized, err = VALIDATORS[key](value)
        if err:
            errors.append({"field": key, "message": err})
        else:
            clean[key] = normalized
    return clean, errors


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------
def get_user(user_id):
    try:
        resp = _users_table().get_item(Key={"userId": user_id})
        return resp.get("Item")
    except ClientError as e:
        logger.error("Failed to load user %s: %s", user_id, str(e))
        return None


def read_preferences(user_id):
    """
    Return the user's communication preferences, with §4.4 defaults filled in.
    Returns None if the user item doesn't exist.
    """
    user = get_user(user_id)
    if user is None:
        return None
    prefs = dict(PREFERENCE_DEFAULTS)
    for key in PREFERENCE_DEFAULTS:
        if key in user and user[key] is not None:
            prefs[key] = user[key]
    for key in SETTINGS_FIELDS:
        if key in user and user[key] is not None:
            prefs[key] = user[key]
    return prefs


def _audit_entries(user, clean, source):
    """Build audit-trail entries for fields whose value actually changes."""
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    entries = []
    for field, new_value in clean.items():
        old_value = user.get(field) if user else None
        if old_value == new_value:
            continue
        entries.append({
            "ts": now_iso,
            "source": source,
            "field": field,
            "old": old_value,
            "new": new_value,
        })
    return entries


def apply_preferences(user_id, clean, source="web"):
    """
    Write validated preference attributes onto the users item + append audit entries.

    `clean` must already be validated/normalized (see validate_and_normalize).
    `source` is 'web' (REST) or 'chat' (agent tools). Returns the updated prefs dict.
    Creates the user item if missing (parity with users/helpers.update_user_settings).
    """
    table = _users_table()
    user = get_user(user_id)
    if user is None:
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        try:
            table.put_item(Item={"userId": user_id, "createdAt": now_iso})
        except ClientError as e:
            logger.error("Failed to create user item %s: %s", user_id, str(e))
        user = {"userId": user_id}

    if not clean:
        return read_preferences(user_id)

    audit = _audit_entries(user, clean, source)

    set_parts = []
    names = {}
    values = {}
    for i, (field, value) in enumerate(clean.items()):
        names[f"#f{i}"] = field
        values[f":v{i}"] = value
        set_parts.append(f"#f{i} = :v{i}")

    update_expr = "SET " + ", ".join(set_parts)
    if audit:
        names["#audit"] = "prefAuditLog"
        values[":audit"] = audit
        values[":empty"] = []
        update_expr += ", #audit = list_append(if_not_exists(#audit, :empty), :audit)"

    try:
        table.update_item(
            Key={"userId": user_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
    except ClientError as e:
        logger.error("Failed to update preferences for %s: %s", user_id, str(e))
        raise

    return read_preferences(user_id)
