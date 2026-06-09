"""
Unit tests for the check-in dispatcher.

Heavy coverage of the pure, compliance-sensitive logic (checkin_logic) plus moto-backed
integration tests of the two passes with SMS / Neon / LLM mocked. Run from this dir:
    pytest lambdas/checkin_dispatcher/test_checkin_dispatcher.py
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ["ENVIRONMENT"] = "test"
os.environ["PROJECT_NAME"] = "versiful"

import checkin_logic
import checkin_composer

NOW = datetime(2026, 6, 9, 16, 0, tzinfo=timezone.utc)  # 12:00 ET -> within send window


def _iso(dt):
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------
def test_parse_iso_handles_z_and_offsets():
    assert checkin_logic.parse_iso("2026-06-09T16:00:00Z").hour == 16
    assert checkin_logic.parse_iso(None) is None
    assert checkin_logic.parse_iso("not-a-date") is None


def test_days_between():
    earlier = NOW - timedelta(days=5)
    assert round(checkin_logic.days_between(earlier, NOW)) == 5
    assert checkin_logic.days_between(None, NOW) is None


def test_quiet_hours_blocks_overnight_local():
    # 06:00 UTC == 02:00 America/New_York -> quiet.
    early = datetime(2026, 6, 9, 6, 0, tzinfo=timezone.utc)
    assert checkin_logic.in_quiet_hours(early, "America/New_York") is True
    # 16:00 UTC == 12:00 ET -> allowed.
    assert checkin_logic.in_quiet_hours(NOW, "America/New_York") is False


# ---------------------------------------------------------------------------
# Cooldown / frequency cap
# ---------------------------------------------------------------------------
def test_cooldown_days_mapping():
    assert checkin_logic.cooldown_days("weekly") == 7
    assert checkin_logic.cooldown_days("biweekly") == 14
    assert checkin_logic.cooldown_days("off") is None
    assert checkin_logic.cooldown_days(None) == 7  # default weekly


def test_outside_cooldown_respects_last_checkin():
    user = {"checkinFrequency": "weekly", "lastCheckinAt": _iso(NOW - timedelta(days=3))}
    assert checkin_logic.outside_cooldown(user, NOW) is False  # only 3 days < 7
    user["lastCheckinAt"] = _iso(NOW - timedelta(days=8))
    assert checkin_logic.outside_cooldown(user, NOW) is True
    # Never checked in -> allowed.
    assert checkin_logic.outside_cooldown({"checkinFrequency": "weekly"}, NOW) is True
    # off -> never.
    assert checkin_logic.outside_cooldown({"checkinFrequency": "off"}, NOW) is False


# ---------------------------------------------------------------------------
# Inactivity eligibility
# ---------------------------------------------------------------------------
def _base_user(**over):
    user = {
        "userId": "u1",
        "checkinEnabled": True,
        "optedOut": False,
        "checkinFrequency": "weekly",
        "checkinInactivityDays": 4,
        "phoneNumber": "+15555550100",
        "timezone": "America/New_York",
        "lastMessageAt": _iso(NOW - timedelta(days=6)),
    }
    user.update(over)
    return user


def test_eligible_for_inactivity_happy_path():
    ok, reason = checkin_logic.eligible_for_inactivity(_base_user(), NOW)
    assert ok is True and reason == "eligible"


@pytest.mark.parametrize("over,expected_reason", [
    ({"checkinEnabled": False}, "not_opted_in"),
    ({"optedOut": True}, "opted_out"),
    ({"checkinFrequency": "off"}, "frequency_off"),
    ({"phoneNumber": None}, "no_phone"),
    ({"lastMessageAt": None}, "no_last_message"),
    ({"lastMessageAt": _iso(NOW - timedelta(days=1))}, "still_active"),
    ({"lastCheckinAt": _iso(NOW - timedelta(days=2))}, "in_cooldown"),
])
def test_eligible_for_inactivity_rejections(over, expected_reason):
    ok, reason = checkin_logic.eligible_for_inactivity(_base_user(**over), NOW)
    assert ok is False
    assert reason == expected_reason


def test_inactivity_respects_custom_threshold():
    # 3 days silent, but threshold is 7 -> still active.
    user = _base_user(checkinInactivityDays=7, lastMessageAt=_iso(NOW - timedelta(days=3)))
    ok, reason = checkin_logic.eligible_for_inactivity(user, NOW)
    assert ok is False and reason == "still_active"


def test_quiet_hours_blocks_eligibility():
    early = datetime(2026, 6, 9, 6, 0, tzinfo=timezone.utc)  # 02:00 ET
    ok, reason = checkin_logic.eligible_for_inactivity(_base_user(), early)
    assert ok is False and reason == "quiet_hours"


# ---------------------------------------------------------------------------
# Selector ranking (spec §10.3)
# ---------------------------------------------------------------------------
def test_selector_prefers_dated_prayer():
    prayers = [{"prayerId": "p1", "status": "active", "title": "Mom's surgery",
                "people": ["mom"], "eventDate": (NOW.date() + timedelta(days=1)).isoformat()}]
    memories = [{"id": "m1", "kind": "struggle", "status": "active", "summary": "anxiety", "salience": 0.9}]
    ctx = checkin_logic.select_context(memories, prayers, None, NOW)
    assert ctx["selector"] == "prayer_followup"
    assert ctx["ref"] == "p1"


def test_selector_event_memory_when_no_prayer():
    memories = [{"id": "m1", "kind": "life_event", "status": "active", "summary": "job interview",
                 "event_date": NOW.date().isoformat()}]
    ctx = checkin_logic.select_context(memories, [], None, NOW)
    assert ctx["selector"] == "event_followup"


def test_selector_struggle_then_plan_then_general():
    struggle = [{"id": "m1", "kind": "struggle", "status": "active", "summary": "work anxiety", "salience": 0.7}]
    assert checkin_logic.select_context(struggle, [], None, NOW)["selector"] == "struggle_followup"

    plan = {"planId": "anxiety-7", "status": "active", "title": "Finding Peace",
            "lastDeliveredAt": _iso(NOW - timedelta(days=3))}
    assert checkin_logic.select_context([], [], plan, NOW)["selector"] == "plan_nudge"

    assert checkin_logic.select_context([], [], None, NOW)["selector"] == "general"


def test_selector_ignores_far_off_dates():
    prayers = [{"prayerId": "p1", "status": "active", "title": "Trip",
                "eventDate": (NOW.date() + timedelta(days=30)).isoformat()}]
    ctx = checkin_logic.select_context([], prayers, None, NOW)
    assert ctx["selector"] == "general"


# ---------------------------------------------------------------------------
# Composer voice rules ("we"/Versiful, never first-person human "I")
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("selector", [
    "prayer_followup", "event_followup", "struggle_followup", "plan_nudge", "general",
])
def test_fallback_voice_never_first_person_human(selector):
    ctx = {"selector": selector, "title": "Mom's surgery", "summary": "anxiety"}
    msg = checkin_composer._fallback(ctx, "Chris")
    assert msg
    # Must not use a standalone first-person human "I".
    tokens = msg.replace(",", " ").replace(".", " ").split()
    assert "I" not in tokens
    assert "we" in msg.lower() or "versiful" in msg.lower()


def test_compose_message_returns_string_even_without_llm():
    user = {"firstName": "Chris"}
    ctx = {"selector": "general"}
    # Force the LLM path to fail so we exercise the deterministic fallback.
    with patch("checkin_composer.ChatOpenAI", create=True, side_effect=Exception("no llm")):
        msg = checkin_composer.compose_message(user, ctx, api_key=None)
    assert isinstance(msg, str) and msg


# ---------------------------------------------------------------------------
# Integration: the two passes with moto + mocked SMS/Neon/LLM
# ---------------------------------------------------------------------------
@pytest.fixture
def dynamo_tables():
    moto = pytest.importorskip("moto")
    import boto3
    with moto.mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="test-versiful-users",
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        ddb.create_table(
            TableName="test-versiful-checkins",
            KeySchema=[
                {"AttributeName": "userId", "KeyType": "HASH"},
                {"AttributeName": "checkinId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "checkinId", "AttributeType": "S"},
                {"AttributeName": "status", "AttributeType": "S"},
                {"AttributeName": "scheduledFor", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[{
                "IndexName": "checkins_by_status",
                "KeySchema": [
                    {"AttributeName": "status", "KeyType": "HASH"},
                    {"AttributeName": "scheduledFor", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }],
            BillingMode="PAY_PER_REQUEST",
        )
        for name, sk in [("prayers", "prayerId"), ("user-reading-plans", "planId")]:
            ddb.create_table(
                TableName=f"test-versiful-{name}",
                KeySchema=[
                    {"AttributeName": "userId", "KeyType": "HASH"},
                    {"AttributeName": sk, "KeyType": "RANGE"},
                ],
                AttributeDefinitions=[
                    {"AttributeName": "userId", "AttributeType": "S"},
                    {"AttributeName": sk, "AttributeType": "S"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )
        yield ddb


def _import_handler():
    import importlib
    import checkin_dispatcher_handler as h
    importlib.reload(h)
    return h


def test_inactivity_pass_sends_and_is_idempotent(dynamo_tables):
    h = _import_handler()
    users = dynamo_tables.Table("test-versiful-users")
    users.put_item(Item=_base_user())

    sent = []
    with patch.object(h, "_send_sms", side_effect=lambda p, m: sent.append((p, m)) or "SM123"), \
         patch.object(h, "_fetch_memories", return_value=[]), \
         patch.object(h.checkin_composer, "compose_message", return_value="Hi Chris, thinking of you."):
        stats1 = h.run_inactivity_pass(NOW, api_key=None, budget=100)

    assert stats1["sent"] == 1
    assert len(sent) == 1
    # A checkins row was logged + lastCheckinAt stamped.
    ci = dynamo_tables.Table("test-versiful-checkins").scan()["Items"]
    assert len(ci) == 1 and ci[0]["status"] == "sent" and ci[0]["trigger"] == "inactivity"
    u = users.get_item(Key={"userId": "u1"})["Item"]
    assert "lastCheckinAt" in u

    # Immediate re-run must NOT double-send (cooldown via lastCheckinAt).
    with patch.object(h, "_send_sms", side_effect=lambda p, m: "SM999"), \
         patch.object(h, "_fetch_memories", return_value=[]), \
         patch.object(h.checkin_composer, "compose_message", return_value="x"):
        stats2 = h.run_inactivity_pass(NOW, api_key=None, budget=100)
    assert stats2["sent"] == 0


def test_inactivity_pass_skips_opted_out(dynamo_tables):
    h = _import_handler()
    dynamo_tables.Table("test-versiful-users").put_item(Item=_base_user(checkinEnabled=False))
    with patch.object(h, "_send_sms", return_value="SM1"), \
         patch.object(h, "_fetch_memories", return_value=[]):
        stats = h.run_inactivity_pass(NOW, api_key=None, budget=100)
    # Not opted in -> not even a candidate from the scan filter.
    assert stats["sent"] == 0


def test_due_date_pass_claims_then_sends_once(dynamo_tables):
    h = _import_handler()
    users = dynamo_tables.Table("test-versiful-users")
    users.put_item(Item=_base_user(lastMessageAt=_iso(NOW - timedelta(days=1))))  # active is fine for time-sensitive
    checkins = dynamo_tables.Table("test-versiful-checkins")
    checkins.put_item(Item={
        "userId": "u1", "checkinId": "c1", "status": "scheduled",
        "scheduledFor": _iso(NOW - timedelta(hours=1)),
        "contextSelector": "prayer_followup", "triggerRef": "p1",
        "trigger": "time_sensitive", "createdAt": _iso(NOW - timedelta(days=1)),
    })

    sent = []
    with patch.object(h, "_send_sms", side_effect=lambda p, m: sent.append(m) or "SMX"), \
         patch.object(h.checkin_composer, "compose_message", return_value="How did it go?"):
        stats1 = h.run_due_date_pass(NOW, api_key=None, budget=100)
    assert stats1["sent"] == 1
    row = checkins.get_item(Key={"userId": "u1", "checkinId": "c1"})["Item"]
    assert row["status"] == "sent"

    # Second run: row is no longer 'scheduled' -> nothing due.
    with patch.object(h, "_send_sms", side_effect=lambda p, m: "SMY"), \
         patch.object(h.checkin_composer, "compose_message", return_value="x"):
        stats2 = h.run_due_date_pass(NOW, api_key=None, budget=100)
    assert stats2["sent"] == 0


def test_handler_returns_stats(dynamo_tables):
    h = _import_handler()
    with patch.object(h, "_send_sms", return_value=None), \
         patch.object(h, "_fetch_memories", return_value=[]), \
         patch.object(h, "_openai_key", return_value=None):
        result = h.handler({}, None)
    assert result["status"] == "ok"
    assert "inactivity" in result and "timeSensitive" in result
