"""Unit tests for the Reading Plan delivery worker.

DynamoDB access and the SMS send path are mocked; no AWS/Twilio calls are made.
The optional LLM expansion is disabled (use_llm=False) for deterministic messages.
Run:  pytest lambdas/reading_plan_delivery/test_reading_plan_delivery.py
"""
import os
import sys
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("PROJECT_NAME", "versiful")
os.environ.setdefault("SECRET_ARN", "arn:aws:secretsmanager:us-east-1:000000000000:secret:test")

import delivery  # noqa: E402

NOW = datetime(2026, 6, 9, 9, 0, tzinfo=timezone.utc)  # 09:00 UTC
USER_UTC = {"userId": "u1", "phoneNumber": "+15555550123", "timezone": "UTC",
            "bibleVersion": "NIV"}
PLAN = {"slug": "anxiety-7", "title": "Finding Peace in Anxiety", "dayCount": 7}
DAY1 = {"slug": "anxiety-7", "dayNumber": 1, "passageRef": "Philippians 4:6-7",
        "theme": "Bring it to God", "prompt": "What worry can you hand to God?"}


def _enr(**over):
    base = {"userId": "u1", "planId": "anxiety-7", "status": "active",
            "deliveryTime": "08:00", "deliveryChannel": "sms",
            "lastDeliveredDay": 0, "lastDeliveredAt": None}
    base.update(over)
    return base


# --------------------------------------------------------------------------- window
def test_is_due_before_window():
    early = datetime(2026, 6, 9, 7, 0, tzinfo=timezone.utc)
    assert delivery.is_due(_enr(), USER_UTC, now_utc=early) is False


def test_is_due_due_when_after_window():
    assert delivery.is_due(_enr(), USER_UTC, now_utc=NOW) is True


def test_is_due_already_delivered_today():
    enr = _enr(lastDeliveredDay=1, lastDeliveredAt="2026-06-09T08:30:00Z")
    assert delivery.is_due(enr, USER_UTC, now_utc=NOW) is False


def test_is_due_paused_is_false():
    assert delivery.is_due(_enr(status="paused"), USER_UTC, now_utc=NOW) is False


def test_next_day_number():
    assert delivery.next_day_number(_enr(lastDeliveredDay=0)) == 1
    assert delivery.next_day_number(_enr(lastDeliveredDay=3)) == 4


# --------------------------------------------------------------------------- deliver_one
def test_deliver_one_sends_and_records():
    with patch.object(delivery, "get_user", return_value=USER_UTC), \
         patch.object(delivery, "get_plan", return_value=PLAN), \
         patch.object(delivery, "get_plan_day", return_value=DAY1), \
         patch.object(delivery, "send_sms", return_value="SMxxx") as send, \
         patch.object(delivery, "mark_delivered") as mark, \
         patch.object(delivery, "record_verse_history") as vh:
        out = delivery.deliver_one(_enr(), now_utc=NOW, use_llm=False)
    assert out["status"] == "sent"
    assert out["dayNumber"] == 1
    send.assert_called_once()
    # message includes the passage ref + prompt (deterministic, no LLM)
    body = send.call_args.args[1]
    assert "Philippians 4:6-7" in body
    assert "Day 1 of 7" in body
    mark.assert_called_once()
    vh.assert_called_once()


def test_deliver_one_skips_when_not_due():
    early = datetime(2026, 6, 9, 7, 0, tzinfo=timezone.utc)
    with patch.object(delivery, "get_user", return_value=USER_UTC):
        out = delivery.deliver_one(_enr(), now_utc=early, use_llm=False)
    assert out["status"] == "skipped"


def test_deliver_one_no_phone():
    user = dict(USER_UTC)
    user.pop("phoneNumber")
    with patch.object(delivery, "get_user", return_value=user), \
         patch.object(delivery, "get_plan", return_value=PLAN), \
         patch.object(delivery, "get_plan_day", return_value=DAY1):
        out = delivery.deliver_one(_enr(), now_utc=NOW, use_llm=False)
    assert out["status"] == "no_phone"


def test_deliver_one_send_failure_does_not_advance():
    with patch.object(delivery, "get_user", return_value=USER_UTC), \
         patch.object(delivery, "get_plan", return_value=PLAN), \
         patch.object(delivery, "get_plan_day", return_value=DAY1), \
         patch.object(delivery, "send_sms", return_value=None), \
         patch.object(delivery, "mark_delivered") as mark, \
         patch.object(delivery, "record_verse_history"):
        out = delivery.deliver_one(_enr(), now_utc=NOW, use_llm=False)
    assert out["status"] == "send_failed"
    mark.assert_not_called()


def test_deliver_one_finished_marks_complete():
    enr = _enr(lastDeliveredDay=7)
    with patch.object(delivery, "get_user", return_value=USER_UTC), \
         patch.object(delivery, "get_plan", return_value=PLAN), \
         patch.object(delivery, "mark_delivered") as mark:
        out = delivery.deliver_one(enr, now_utc=NOW, use_llm=False)
    assert out["status"] == "finished"
    mark.assert_called_once()
    assert mark.call_args.kwargs.get("plan_completed") is True


def test_deliver_one_final_day_completes_plan():
    enr = _enr(lastDeliveredDay=6)  # next day = 7 = dayCount
    with patch.object(delivery, "get_user", return_value=USER_UTC), \
         patch.object(delivery, "get_plan", return_value=PLAN), \
         patch.object(delivery, "get_plan_day", return_value=dict(DAY1, dayNumber=7)), \
         patch.object(delivery, "send_sms", return_value="SMxxx"), \
         patch.object(delivery, "mark_delivered") as mark, \
         patch.object(delivery, "record_verse_history"):
        out = delivery.deliver_one(enr, now_utc=NOW, use_llm=False)
    assert out["status"] == "sent"
    assert out["completed"] is True
    assert mark.call_args.kwargs.get("plan_completed") is True


def test_deliver_one_isolates_errors():
    with patch.object(delivery, "get_user", side_effect=RuntimeError("boom")):
        out = delivery.deliver_one(_enr(), now_utc=NOW, use_llm=False)
    assert out["status"] == "error"


# --------------------------------------------------------------------------- batch
def test_run_batch_aggregates_counts():
    enrs = [_enr(), _enr(planId="grief-14")]
    outcomes = [{"status": "sent", "userId": "u1", "planId": "anxiety-7"},
                {"status": "skipped", "userId": "u1", "planId": "grief-14"}]
    with patch.object(delivery, "scan_active_enrollments", return_value=enrs), \
         patch.object(delivery, "deliver_one", side_effect=outcomes):
        result = delivery.run_batch(now_utc=NOW, use_llm=False)
    assert result["scanned"] == 2
    assert result["counts"]["sent"] == 1
    assert result["counts"]["skipped"] == 1


def test_handler_returns_ok():
    import reading_plan_delivery_handler as worker
    with patch.object(worker.delivery, "run_batch",
                      return_value={"scanned": 0, "counts": {}, "outcomes": []}):
        resp = worker.handler({}, None)
    assert resp["status"] == "ok"
    assert resp["worker"] == "reading_plan_delivery"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
