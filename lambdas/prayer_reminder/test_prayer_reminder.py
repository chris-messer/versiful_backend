"""
Unit tests for the prayer_reminder worker.

All external services are mocked: boto3 (DynamoDB) and the SMS send path.
Run: conda run -n versiful_backend python -m pytest lambdas/prayer_reminder/test_prayer_reminder.py
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

THIS_DIR = os.path.dirname(__file__)

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("PROJECT_NAME", "versiful")
os.environ.setdefault("USERS_TABLE", "test-versiful-users")
os.environ.setdefault("PRAYERS_TABLE", "test-versiful-prayers")
os.environ.setdefault("DEFAULT_TIMEZONE", "UTC")
os.environ.setdefault("PRAYER_REMINDER_TIME", "09:00")

sys.modules.pop("prayer_reminder_handler", None)
sys.path.insert(0, THIS_DIR)

import prayer_reminder_handler as worker  # noqa: E402


PREMIUM_USER = {
    "userId": "u1", "isSubscribed": True, "timezone": "UTC",
    "phoneNumber": "+15555550123", "firstName": "Chris",
}


# ---------------------------------------------------------------------------
# Scheduling math
# ---------------------------------------------------------------------------
def test_next_initial_reminder_today_when_before_window():
    now = datetime(2026, 6, 9, 7, 0, tzinfo=timezone.utc)
    tz = worker._resolve_tz("UTC")
    assert worker.next_initial_reminder(now, tz, (9, 0)) == "2026-06-09T09:00:00Z"


def test_next_initial_reminder_tomorrow_when_past_window():
    now = datetime(2026, 6, 9, 10, 0, tzinfo=timezone.utc)
    tz = worker._resolve_tz("UTC")
    assert worker.next_initial_reminder(now, tz, (9, 0)) == "2026-06-10T09:00:00Z"


def test_advance_reminder_daily_and_weekly():
    now = datetime(2026, 6, 9, 9, 5, tzinfo=timezone.utc)
    tz = worker._resolve_tz("UTC")
    assert worker.advance_reminder(now, tz, (9, 0), "daily") == "2026-06-10T09:00:00Z"
    assert worker.advance_reminder(now, tz, (9, 0), "weekly") == "2026-06-16T09:00:00Z"


def test_parse_iso_roundtrip():
    dt = worker._parse_iso("2026-06-09T09:00:00Z")
    assert dt == datetime(2026, 6, 9, 9, 0, tzinfo=timezone.utc)
    assert worker._parse_iso(None) is None
    assert worker._parse_iso("garbage") is None


# ---------------------------------------------------------------------------
# Message copy — must avoid first-person singular "I"
# ---------------------------------------------------------------------------
def test_compose_reminder_references_prayer_and_uses_we_voice():
    msg = worker.compose_reminder({"title": "Mom's surgery", "people": ["Mom"], "body": "Pray for peace"})
    assert "Mom's surgery" in msg
    assert "Versiful" in msg
    assert "Mom" in msg
    # No standalone first-person singular pronoun.
    assert " I " not in f" {msg} "
    assert "I'll" not in msg and "I've" not in msg and "I'm" not in msg


# ---------------------------------------------------------------------------
# process_prayer
# ---------------------------------------------------------------------------
def test_process_prayer_skips_non_reminder_cadence():
    prayer = {"userId": "u1", "prayerId": "p1", "reminderCadence": "none"}
    assert worker.process_prayer(prayer, datetime.now(timezone.utc)) == "skipped"


def test_process_prayer_skips_non_active_status():
    prayer = {"userId": "u1", "prayerId": "p1", "reminderCadence": "daily", "status": "answered"}
    assert worker.process_prayer(prayer, datetime.now(timezone.utc)) == "skipped"


def test_process_prayer_skips_free_user():
    prayer = {"userId": "u1", "prayerId": "p1", "reminderCadence": "daily",
              "status": "active", "nextReminderAt": "2020-01-01T09:00:00Z"}
    free = {"userId": "u1", "isSubscribed": False, "phoneNumber": "+15555550123"}
    with patch.object(worker, "load_user", return_value=free):
        assert worker.process_prayer(prayer, datetime.now(timezone.utc)) == "skipped"


def test_process_prayer_skips_user_without_phone():
    prayer = {"userId": "u1", "prayerId": "p1", "reminderCadence": "daily",
              "status": "active", "nextReminderAt": "2020-01-01T09:00:00Z"}
    no_phone = {"userId": "u1", "isSubscribed": True}
    with patch.object(worker, "load_user", return_value=no_phone):
        assert worker.process_prayer(prayer, datetime.now(timezone.utc)) == "skipped"


def test_process_prayer_initializes_when_next_is_null():
    prayer = {"userId": "u1", "prayerId": "p1", "reminderCadence": "daily",
              "status": "active", "nextReminderAt": None}
    now = datetime(2026, 6, 9, 7, 0, tzinfo=timezone.utc)
    with patch.object(worker, "load_user", return_value=PREMIUM_USER), \
         patch.object(worker, "_initialize_next", return_value=True) as init, \
         patch.object(worker, "send_sms") as send:
        assert worker.process_prayer(prayer, now) == "initialized"
    init.assert_called_once_with("u1", "p1", "2026-06-09T09:00:00Z")
    send.assert_not_called()


def test_process_prayer_skips_when_not_due():
    future = "2099-01-01T09:00:00Z"
    prayer = {"userId": "u1", "prayerId": "p1", "reminderCadence": "daily",
              "status": "active", "nextReminderAt": future}
    with patch.object(worker, "load_user", return_value=PREMIUM_USER), \
         patch.object(worker, "send_sms") as send:
        assert worker.process_prayer(prayer, datetime.now(timezone.utc)) == "skipped"
    send.assert_not_called()


def test_process_prayer_sends_when_due_and_claimed():
    prayer = {"userId": "u1", "prayerId": "p1", "reminderCadence": "daily",
              "status": "active", "nextReminderAt": "2020-01-01T09:00:00Z",
              "title": "Job interview"}
    now = datetime(2026, 6, 9, 9, 5, tzinfo=timezone.utc)
    with patch.object(worker, "load_user", return_value=PREMIUM_USER), \
         patch.object(worker, "_claim_due", return_value=True) as claim, \
         patch.object(worker, "send_sms", return_value="SM123") as send:
        assert worker.process_prayer(prayer, now) == "sent"
    claim.assert_called_once()
    send.assert_called_once()
    assert send.call_args.args[0] == "+15555550123"


def test_process_prayer_skips_when_claim_lost():
    prayer = {"userId": "u1", "prayerId": "p1", "reminderCadence": "daily",
              "status": "active", "nextReminderAt": "2020-01-01T09:00:00Z"}
    now = datetime(2026, 6, 9, 9, 5, tzinfo=timezone.utc)
    with patch.object(worker, "load_user", return_value=PREMIUM_USER), \
         patch.object(worker, "_claim_due", return_value=False), \
         patch.object(worker, "send_sms") as send:
        assert worker.process_prayer(prayer, now) == "skipped"
    send.assert_not_called()


def test_process_prayer_error_on_send_failure():
    prayer = {"userId": "u1", "prayerId": "p1", "reminderCadence": "daily",
              "status": "active", "nextReminderAt": "2020-01-01T09:00:00Z", "title": "x"}
    now = datetime(2026, 6, 9, 9, 5, tzinfo=timezone.utc)
    with patch.object(worker, "load_user", return_value=PREMIUM_USER), \
         patch.object(worker, "_claim_due", return_value=True), \
         patch.object(worker, "send_sms", return_value=None):
        assert worker.process_prayer(prayer, now) == "error"


# ---------------------------------------------------------------------------
# handler batch resilience
# ---------------------------------------------------------------------------
def test_handler_continues_when_one_prayer_errors():
    prayers = [{"userId": "good", "prayerId": "1"},
               {"userId": "bad", "prayerId": "2"},
               {"userId": "good2", "prayerId": "3"}]

    def fake_process(prayer, now):
        if prayer["userId"] == "bad":
            raise RuntimeError("boom")
        return "sent"

    with patch.object(worker, "scan_reminder_prayers", return_value=prayers), \
         patch.object(worker, "process_prayer", side_effect=fake_process):
        result = worker.handler({}, None)
    assert result["evaluated"] == 3
    assert result["sent"] == 2
    assert result["errors"] == 1


def test_handler_respects_send_cap():
    prayers = [{"userId": f"u{i}", "prayerId": str(i)} for i in range(5)]
    with patch.object(worker, "scan_reminder_prayers", return_value=prayers), \
         patch.object(worker, "process_prayer", return_value="sent"), \
         patch.object(worker, "MAX_SENDS_PER_RUN", 2):
        result = worker.handler({}, None)
    assert result["sent"] == 2
    assert result["skipped"] == 3
