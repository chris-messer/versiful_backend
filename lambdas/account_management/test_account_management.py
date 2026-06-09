"""
Unit tests for the account-management lambda: preferences validation/apply, the
REST handler, and the in-chat account tools. DynamoDB is mocked throughout.

Run: conda run -n versiful_backend python -m pytest lambdas/account_management/test_account_management.py
"""
import json
import os
import sys
from unittest.mock import MagicMock, patch

THIS_DIR = os.path.dirname(__file__)
# preferences.py + account_tools.py were promoted to the shared layer (lambdas/shared),
# which the account-management lambda mounts at runtime via /opt/python. Add it here
# so the bare `import preferences` / `import account_tools` resolve under local tests.
SHARED_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", "shared"))

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("PROJECT_NAME", "versiful")
os.environ.setdefault("USERS_TABLE", "test-versiful-users")

for _m in ("preferences", "account_tools", "account_management_handler"):
    sys.modules.pop(_m, None)
sys.path.insert(0, SHARED_DIR)
sys.path.insert(0, THIS_DIR)

import preferences  # noqa: E402
import account_tools  # noqa: E402
import account_management_handler as handler  # noqa: E402


# ---------------------------------------------------------------------------
# validate_and_normalize
# ---------------------------------------------------------------------------
def test_validate_accepts_known_fields():
    clean, errors = preferences.validate_and_normalize({
        "dailyVerseEnabled": True,
        "dailyVerseTime": "7:5",
        "checkinFrequency": "WEEKLY",
        "bibleVersion": "esv",
        "responseStyle": {"tone": "Warm", "length": "short"},
    })
    assert errors == []
    assert clean["dailyVerseTime"] == "07:05"
    assert clean["checkinFrequency"] == "weekly"
    assert clean["bibleVersion"] == "ESV"
    assert clean["responseStyle"] == {"tone": "warm", "length": "short"}


def test_validate_rejects_unknown_and_bad_fields():
    clean, errors = preferences.validate_and_normalize({
        "isSubscribed": True,           # not writable -> rejected
        "dailyVerseTime": "25:00",      # invalid
        "checkinInactivityDays": 99,    # out of range
    })
    fields = {e["field"] for e in errors}
    assert "isSubscribed" in fields
    assert "dailyVerseTime" in fields
    assert "checkinInactivityDays" in fields
    assert clean == {}


def test_validate_ignores_nulls():
    clean, errors = preferences.validate_and_normalize({"dailyVerseEnabled": None})
    assert errors == []
    assert clean == {}


# ---------------------------------------------------------------------------
# read_preferences / apply_preferences (mocked table)
# ---------------------------------------------------------------------------
def test_read_preferences_fills_defaults():
    fake_table = MagicMock()
    fake_table.get_item.return_value = {"Item": {"userId": "u1", "dailyVerseEnabled": True}}
    with patch.object(preferences, "_users_table", return_value=fake_table):
        prefs = preferences.read_preferences("u1")
    assert prefs["dailyVerseEnabled"] is True
    assert prefs["checkinFrequency"] == "weekly"  # default filled
    assert prefs["primaryChannel"] == "sms"


def test_apply_preferences_writes_audit_for_changes():
    fake_table = MagicMock()
    # get_user called: once before update, once inside read_preferences after.
    fake_table.get_item.side_effect = [
        {"Item": {"userId": "u1", "dailyVerseEnabled": False}},   # before
        {"Item": {"userId": "u1", "dailyVerseEnabled": True}},    # after (read_preferences)
    ]
    with patch.object(preferences, "_users_table", return_value=fake_table):
        preferences.apply_preferences("u1", {"dailyVerseEnabled": True}, source="web")
    kwargs = fake_table.update_item.call_args.kwargs
    assert "list_append" in kwargs["UpdateExpression"]
    audit = kwargs["ExpressionAttributeValues"][":audit"]
    assert audit[0]["field"] == "dailyVerseEnabled"
    assert audit[0]["source"] == "web"
    assert audit[0]["old"] is False and audit[0]["new"] is True


# ---------------------------------------------------------------------------
# REST handler
# ---------------------------------------------------------------------------
def _event(method, body=None, user_id="u1"):
    ctx = {"authorizer": {"userId": user_id}} if user_id else {}
    e = {"httpMethod": method, "path": "/users/preferences", "requestContext": ctx}
    if body is not None:
        e["body"] = json.dumps(body)
    return e


def test_handler_get_returns_prefs():
    with patch.object(preferences, "read_preferences", return_value={"dailyVerseEnabled": True}):
        resp = handler.handler(_event("GET"), None)
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["data"]["dailyVerseEnabled"] is True


def test_handler_put_valid():
    with patch.object(preferences, "apply_preferences", return_value={"dailyVerseEnabled": True}) as ap:
        resp = handler.handler(_event("PUT", {"dailyVerseEnabled": True}), None)
    assert resp["statusCode"] == 200
    ap.assert_called_once()
    assert ap.call_args.kwargs.get("source") == "web" or ap.call_args[0][-1] == "web"


def test_handler_put_invalid_returns_400():
    resp = handler.handler(_event("PUT", {"dailyVerseTime": "99:99"}), None)
    assert resp["statusCode"] == 400
    err = json.loads(resp["body"])["error"]
    assert err["code"] == "validation_error"
    assert "fields" in err["details"]


def test_handler_missing_auth_401():
    resp = handler.handler(_event("GET", user_id=None), None)
    assert resp["statusCode"] == 401


# ---------------------------------------------------------------------------
# account tools
# ---------------------------------------------------------------------------
def test_set_daily_verse_on_with_time():
    with patch.object(account_tools.preferences, "apply_preferences", return_value={}) as ap:
        msg = account_tools.set_daily_verse("u1", True, "07:30")
    clean = ap.call_args[0][1]
    assert clean["dailyVerseEnabled"] is True
    assert clean["dailyVerseTime"] == "07:30"
    assert "07:30" in msg


def test_set_daily_verse_bad_time_no_write():
    with patch.object(account_tools.preferences, "apply_preferences") as ap:
        msg = account_tools.set_daily_verse("u1", True, "nope")
    ap.assert_not_called()
    assert "didn't look right" in msg or "24-hour" in msg


def test_set_checkin_frequency_off():
    with patch.object(account_tools.preferences, "apply_preferences", return_value={}) as ap:
        msg = account_tools.set_checkin_frequency("u1", "off")
    clean = ap.call_args[0][1]
    assert clean["checkinEnabled"] is False
    assert "won't send" in msg.lower() or "off" in msg.lower()


def test_set_checkin_frequency_less_often_maps_biweekly():
    with patch.object(account_tools.preferences, "apply_preferences", return_value={}) as ap:
        account_tools.set_checkin_frequency("u1", "less often")
    clean = ap.call_args[0][1]
    assert clean["checkinEnabled"] is True
    assert clean["checkinFrequency"] == "biweekly"
    assert clean["checkinInactivityDays"] == 7


def test_update_bible_version_invalid():
    with patch.object(account_tools.preferences, "apply_preferences") as ap:
        msg = account_tools.update_bible_version("u1", "klingon")
    ap.assert_not_called()
    assert "don't recognize" in msg.lower()


def test_set_response_style_partial():
    with patch.object(account_tools.preferences, "apply_preferences", return_value={}) as ap:
        account_tools.set_response_style("u1", tone="concise")
    clean = ap.call_args[0][1]
    assert clean["responseStyle"] == {"tone": "concise"}


def test_pause_reading_plan_active():
    plans = [{"userId": "u1", "planId": "anxiety-7", "status": "active"}]
    with patch.object(account_tools, "_list_user_plans", return_value=plans), \
         patch.object(account_tools, "_set_plan_status", return_value=True) as sp:
        msg = account_tools.pause_reading_plan("u1")
    sp.assert_called_once_with("u1", "anxiety-7", "paused")
    assert "paused" in msg.lower()


def test_resume_reading_plan_none_paused():
    with patch.object(account_tools, "_list_user_plans", return_value=[]):
        msg = account_tools.resume_reading_plan("u1")
    assert "paused reading plan" in msg.lower()


def test_get_account_status_reads_back():
    user = {"userId": "u1", "isSubscribed": True, "phoneNumber": "+15555550123"}
    prefs = dict(preferences.PREFERENCE_DEFAULTS)
    prefs["dailyVerseEnabled"] = True
    prefs["bibleVersion"] = "ESV"
    with patch.object(account_tools.preferences, "read_preferences", return_value=prefs), \
         patch.object(account_tools.preferences, "get_user", return_value=user), \
         patch.object(account_tools, "_active_prayer_count", return_value=3), \
         patch.object(account_tools, "_list_user_plans", return_value=[]):
        msg = account_tools.get_account_status("u1")
    assert "Premium" in msg
    assert "unlimited" in msg
    assert "Active prayers: 3" in msg
