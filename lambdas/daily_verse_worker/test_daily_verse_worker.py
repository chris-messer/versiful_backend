"""
Unit tests for the daily_verse_worker (and its verse_engine copy).

All external services are mocked: boto3 (DynamoDB), OpenAI, and the SMS send path.
Run: conda run -n versiful_backend python -m pytest lambdas/daily_verse_worker/test_daily_verse_worker.py
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

THIS_DIR = os.path.dirname(__file__)

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("PROJECT_NAME", "versiful")
os.environ.setdefault("USERS_TABLE", "test-versiful-users")
os.environ.setdefault("VERSE_HISTORY_TABLE", "test-versiful-verse-history")
os.environ.setdefault("DEFAULT_TIMEZONE", "UTC")

# Ensure THIS lambda's modules win over a sibling lambda's same-named module
# (both daily_verse and daily_verse_worker ship a `verse_engine`).
for _m in ("verse_engine", "daily_verse_worker_handler", "daily_verse_handler"):
    sys.modules.pop(_m, None)
sys.path.insert(0, THIS_DIR)

import verse_engine  # noqa: E402
import daily_verse_worker_handler as worker  # noqa: E402


# ---------------------------------------------------------------------------
# verse_engine
# ---------------------------------------------------------------------------
def test_fallback_verse_avoids_exclusions():
    with patch.object(verse_engine, "_openai_client", return_value=None):
        verse = verse_engine.select_personalized_verse(
            user_id="u1", bible_version="ESV", first_name="Chris",
            exclusion_refs=["Isaiah 41:10", "Philippians 4:6-7"],
        )
    assert verse["fallback"] is True
    assert verse["displayRef"] not in {"Isaiah 41:10", "Philippians 4:6-7"}
    assert verse["translation"] == "ESV"
    assert "Chris" in verse["message"]


def test_select_parses_llm_json():
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content=(
            '{"reference":"John 14:27","displayRef":"John 14:27",'
            '"translation":"NIV","themes":["peace"],'
            '"reflection":"Jesus leaves you his peace; let not your heart be troubled."}'
        )))
    ]
    with patch.object(verse_engine, "_openai_client", return_value=fake_client):
        verse = verse_engine.select_personalized_verse(
            user_id="u1", bible_version="NIV", first_name="Sam", exclusion_refs=[],
        )
    assert verse["displayRef"] == "John 14:27"
    assert verse.get("fallback") is not True
    assert "John 14:27" in verse["message"]


def test_select_falls_back_on_bad_json():
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content="not json at all"))
    ]
    with patch.object(verse_engine, "_openai_client", return_value=fake_client):
        verse = verse_engine.select_personalized_verse(
            user_id="u1", bible_version="NIV", exclusion_refs=[],
        )
    assert verse["fallback"] is True


def test_record_verse_history_writes_item():
    fake_table = MagicMock()
    with patch.object(verse_engine, "_verse_history_table", return_value=fake_table):
        sent_at = verse_engine.record_verse_history(
            user_id="u1",
            verse={"displayRef": "Psalm 23", "translation": "NIV", "themes": ["rest"],
                   "reflection": "He restores", "message": "msg"},
            phone_number="+15555550123",
        )
    assert sent_at is not None
    item = fake_table.put_item.call_args.kwargs["Item"]
    assert item["userId"] == "u1"
    assert item["context"] == "daily_verse"
    assert item["phoneNumber"] == "+15555550123"


def test_recent_verse_references_dedups():
    fake_table = MagicMock()
    fake_table.query.return_value = {"Items": [
        {"displayRef": "Psalm 23"}, {"displayRef": "Psalm 23"}, {"reference": "John 3:16"},
    ]}
    with patch.object(verse_engine, "_verse_history_table", return_value=fake_table):
        refs = verse_engine.recent_verse_references("u1")
    assert refs == ["Psalm 23", "John 3:16"]


# ---------------------------------------------------------------------------
# is_due window logic
# ---------------------------------------------------------------------------
def test_is_due_true_after_time_and_not_sent():
    now = datetime(2026, 6, 9, 8, 5, tzinfo=timezone.utc)
    user = {"timezone": "UTC", "dailyVerseTime": "08:00"}
    due, local_date = worker.is_due(user, now)
    assert due is True
    assert local_date == "2026-06-09"


def test_is_due_false_before_time():
    now = datetime(2026, 6, 9, 7, 55, tzinfo=timezone.utc)
    user = {"timezone": "UTC", "dailyVerseTime": "08:00"}
    due, _ = worker.is_due(user, now)
    assert due is False


def test_is_due_false_already_sent_today():
    now = datetime(2026, 6, 9, 8, 5, tzinfo=timezone.utc)
    user = {"timezone": "UTC", "dailyVerseTime": "08:00", "lastDailyVerseDate": "2026-06-09"}
    due, _ = worker.is_due(user, now)
    assert due is False


def test_is_due_false_past_grace_window():
    now = datetime(2026, 6, 9, 23, 0, tzinfo=timezone.utc)
    user = {"timezone": "UTC", "dailyVerseTime": "08:00"}
    due, _ = worker.is_due(user, now)
    assert due is False


# ---------------------------------------------------------------------------
# process_user
# ---------------------------------------------------------------------------
def test_process_user_skips_free_user():
    now = datetime(2026, 6, 9, 8, 5, tzinfo=timezone.utc)
    user = {"userId": "u1", "isSubscribed": False, "timezone": "UTC", "dailyVerseTime": "08:00"}
    assert worker.process_user(user, now) == "skipped"


def test_process_user_sends_and_records():
    now = datetime(2026, 6, 9, 8, 5, tzinfo=timezone.utc)
    user = {
        "userId": "u1", "isSubscribed": True, "timezone": "UTC",
        "dailyVerseTime": "08:00", "phoneNumber": "+15555550123", "firstName": "Chris",
    }
    verse = {"displayRef": "Psalm 23", "translation": "NIV", "message": "hello", "reflection": "r", "themes": []}
    with patch.object(worker, "_claim_send_lock", return_value=True) as claim, \
         patch.object(worker.verse_engine, "select_personalized_verse", return_value=verse), \
         patch.object(worker.verse_engine, "record_verse_history", return_value="2026-06-09T08:05:00Z") as rec, \
         patch.object(worker, "send_sms", return_value="SM123") as send:
        outcome = worker.process_user(user, now)
    assert outcome == "sent"
    claim.assert_called_once()
    send.assert_called_once_with("+15555550123", "hello")
    rec.assert_called_once()


def test_process_user_skips_when_lock_lost():
    now = datetime(2026, 6, 9, 8, 5, tzinfo=timezone.utc)
    user = {"userId": "u1", "isSubscribed": True, "timezone": "UTC",
            "dailyVerseTime": "08:00", "phoneNumber": "+15555550123"}
    with patch.object(worker, "_claim_send_lock", return_value=False):
        assert worker.process_user(user, now) == "skipped"


def test_process_user_skips_sms_without_phone():
    now = datetime(2026, 6, 9, 8, 5, tzinfo=timezone.utc)
    user = {"userId": "u1", "isSubscribed": True, "timezone": "UTC",
            "dailyVerseTime": "08:00", "dailyVerseChannel": "sms"}
    assert worker.process_user(user, now) == "skipped"


# ---------------------------------------------------------------------------
# handler batch resilience
# ---------------------------------------------------------------------------
def test_handler_continues_when_one_user_errors():
    users = [{"userId": "good"}, {"userId": "bad"}, {"userId": "good2"}]

    def fake_process(user, now):
        if user["userId"] == "bad":
            raise RuntimeError("boom")
        return "sent"

    with patch.object(worker.verse_engine, "ensure_openai_key", return_value="k"), \
         patch.object(worker, "_enabled_users", return_value=users), \
         patch.object(worker, "process_user", side_effect=fake_process):
        result = worker.handler({}, None)
    assert result["evaluated"] == 3
    assert result["sent"] == 2
    assert result["errors"] == 1
