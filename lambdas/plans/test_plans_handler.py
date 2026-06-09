"""Unit tests for the Reading Plans REST handler.

DynamoDB access (the `plans_repo` module) and the Neon reflection write are mocked;
no AWS calls are made. Run from repo root:  pytest lambdas/plans/test_plans_handler.py
"""
import json
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("PROJECT_NAME", "versiful")
os.environ.setdefault("SECRET_ARN", "arn:aws:secretsmanager:us-east-1:000000000000:secret:test")

import plans_handler as ph  # noqa: E402


# --------------------------------------------------------------------------- helpers
def _event(route_key, *, user_id=None, path_params=None, body=None, query=None):
    evt = {
        "routeKey": route_key,
        "pathParameters": path_params or {},
        "queryStringParameters": query or {},
        "requestContext": {"http": {"method": route_key.split(" ")[0]}},
    }
    if body is not None:
        evt["body"] = json.dumps(body) if not isinstance(body, str) else body
    if user_id:
        evt["requestContext"]["authorizer"] = {"lambda": {"userId": user_id}}
    return evt


def _body(resp):
    return json.loads(resp["body"])


PLAN = {"slug": "anxiety-7", "title": "Finding Peace in Anxiety", "topic": "anxiety",
        "dayCount": 7, "emoji": "🌊", "description": "desc", "isActive": True}


# --------------------------------------------------------------------------- catalog
def test_list_catalog_public():
    with patch.object(ph.repo, "list_active_plans", return_value=[PLAN]):
        resp = ph.handler(_event("GET /plans"), None)
    assert resp["statusCode"] == 200
    data = _body(resp)
    assert data["meta"]["count"] == 1
    assert data["data"]["items"][0]["slug"] == "anxiety-7"


def test_catalog_detail_includes_days():
    days = [{"dayNumber": 1, "passageRef": "Phil 4:6-7", "theme": "t", "prompt": "p"}]
    with patch.object(ph.repo, "get_plan", return_value=PLAN), \
         patch.object(ph.repo, "get_plan_days", return_value=days):
        resp = ph.handler(_event("GET /plans/{slug}", path_params={"slug": "anxiety-7"}), None)
    assert resp["statusCode"] == 200
    data = _body(resp)["data"]
    assert data["dayCount"] == 7
    assert data["days"][0]["passageRef"] == "Phil 4:6-7"


def test_catalog_detail_not_found():
    with patch.object(ph.repo, "get_plan", return_value=None):
        resp = ph.handler(_event("GET /plans/{slug}", path_params={"slug": "nope"}), None)
    assert resp["statusCode"] == 404
    assert _body(resp)["error"]["code"] == "not_found"


# --------------------------------------------------------------------------- enroll
def test_enroll_requires_auth():
    resp = ph.handler(_event("POST /plans/{slug}/enroll", path_params={"slug": "anxiety-7"}), None)
    assert resp["statusCode"] == 401
    assert _body(resp)["error"]["code"] == "unauthorized"


def test_enroll_unknown_plan_404():
    with patch.object(ph.repo, "get_plan", return_value=None):
        resp = ph.handler(
            _event("POST /plans/{slug}/enroll", user_id="u1", path_params={"slug": "x"}), None
        )
    assert resp["statusCode"] == 404


def test_enroll_success_premium_201():
    enr = {"userId": "u1", "planId": "anxiety-7", "status": "active", "currentDay": 1,
           "deliveryTime": "08:00", "deliveryChannel": "sms", "lastDeliveredDay": 0,
           "startedAt": "2026-06-09T08:00:00Z"}
    with patch.object(ph.repo, "get_plan", return_value=PLAN), \
         patch.object(ph.repo, "get_enrollment", return_value=None), \
         patch.object(ph.repo, "get_user", return_value={"isSubscribed": True}), \
         patch.object(ph.repo, "create_enrollment", return_value=(enr, True)) as mk:
        resp = ph.handler(
            _event("POST /plans/{slug}/enroll", user_id="u1",
                   path_params={"slug": "anxiety-7"}, body={}), None
        )
    assert resp["statusCode"] == 201
    assert mk.called
    assert _body(resp)["data"]["planId"] == "anxiety-7"


def test_enroll_free_limit_402():
    with patch.object(ph.repo, "get_plan", return_value=PLAN), \
         patch.object(ph.repo, "get_enrollment", return_value=None), \
         patch.object(ph.repo, "get_user", return_value={"isSubscribed": False}), \
         patch.object(ph.repo, "list_enrollments", return_value=[{"planId": "grief-14"}]):
        resp = ph.handler(
            _event("POST /plans/{slug}/enroll", user_id="u1",
                   path_params={"slug": "anxiety-7"}, body={}), None
        )
    assert resp["statusCode"] == 402
    err = _body(resp)["error"]
    assert err["code"] == "limit_reached"
    assert err["details"]["limit"] == 1


def test_enroll_idempotent_existing_200():
    enr = {"userId": "u1", "planId": "anxiety-7", "status": "active", "currentDay": 2,
           "deliveryTime": "08:00", "startedAt": "2026-06-09T08:00:00Z"}
    with patch.object(ph.repo, "get_plan", return_value=PLAN), \
         patch.object(ph.repo, "get_enrollment", return_value=enr), \
         patch.object(ph.repo, "completed_day_numbers", return_value=[1]), \
         patch.object(ph.repo, "create_enrollment") as mk:
        resp = ph.handler(
            _event("POST /plans/{slug}/enroll", user_id="u1",
                   path_params={"slug": "anxiety-7"}, body={}), None
        )
    assert resp["statusCode"] == 200
    assert not mk.called  # did not re-create


def test_enroll_invalid_delivery_time_400():
    with patch.object(ph.repo, "get_plan", return_value=PLAN), \
         patch.object(ph.repo, "get_enrollment", return_value=None), \
         patch.object(ph.repo, "get_user", return_value={"isSubscribed": True}):
        resp = ph.handler(
            _event("POST /plans/{slug}/enroll", user_id="u1",
                   path_params={"slug": "anxiety-7"}, body={"deliveryTime": "9am"}), None
        )
    assert resp["statusCode"] == 400
    assert _body(resp)["error"]["code"] == "validation_error"


# --------------------------------------------------------------------------- enrolled list
def test_list_enrolled():
    enr = {"userId": "u1", "planId": "anxiety-7", "status": "active", "currentDay": 3,
           "startedAt": "2026-06-09T08:00:00Z", "deliveryTime": "08:00"}
    with patch.object(ph.repo, "list_enrollments", return_value=[enr]), \
         patch.object(ph.repo, "get_plan", return_value=PLAN), \
         patch.object(ph.repo, "completed_day_numbers", return_value=[1, 2]):
        resp = ph.handler(_event("GET /plans/enrolled", user_id="u1"), None)
    assert resp["statusCode"] == 200
    data = _body(resp)["data"]
    assert data["items"][0]["completedDays"] == [1, 2]
    assert data["items"][0]["title"] == PLAN["title"]


# --------------------------------------------------------------------------- complete-day
def test_complete_day_ownership_404():
    with patch.object(ph.repo, "get_enrollment", return_value=None):
        resp = ph.handler(
            _event("POST /plans/enrolled/{id}/complete-day", user_id="u1",
                   path_params={"id": "anxiety-7"}, body={"dayNumber": 1}), None
        )
    assert resp["statusCode"] == 404


def test_complete_day_advances_and_saves_reflection():
    enr = {"userId": "u1", "planId": "anxiety-7", "status": "active", "currentDay": 2}
    updated = dict(enr, currentDay=3)
    with patch.object(ph.repo, "get_enrollment", return_value=enr), \
         patch.object(ph.repo, "get_plan", return_value=PLAN), \
         patch.object(ph.repo, "record_progress") as rec, \
         patch.object(ph.repo, "advance_current_day", return_value=updated) as adv, \
         patch.object(ph.repo, "completed_day_numbers", return_value=[1, 2]), \
         patch.object(ph, "_save_reflection", return_value="ref-123") as save:
        resp = ph.handler(
            _event("POST /plans/enrolled/{id}/complete-day", user_id="u1",
                   path_params={"id": "anxiety-7"},
                   body={"dayNumber": 2, "reflection": "trusting God today"}), None
        )
    assert resp["statusCode"] == 200
    data = _body(resp)["data"]
    assert data["completedDay"] == 2
    assert data["reflectionId"] == "ref-123"
    rec.assert_called_once_with("u1", "anxiety-7", 2, reflection_id="ref-123")
    adv.assert_called_once()
    save.assert_called_once()


def test_complete_day_invalid_day_400():
    enr = {"userId": "u1", "planId": "anxiety-7", "status": "active", "currentDay": 1}
    with patch.object(ph.repo, "get_enrollment", return_value=enr), \
         patch.object(ph.repo, "get_plan", return_value=PLAN):
        resp = ph.handler(
            _event("POST /plans/enrolled/{id}/complete-day", user_id="u1",
                   path_params={"id": "anxiety-7"}, body={"dayNumber": 99}), None
        )
    assert resp["statusCode"] == 400


def test_complete_final_day_marks_completed():
    enr = {"userId": "u1", "planId": "anxiety-7", "status": "active", "currentDay": 7}
    with patch.object(ph.repo, "get_enrollment", return_value=enr), \
         patch.object(ph.repo, "get_plan", return_value=PLAN), \
         patch.object(ph.repo, "record_progress"), \
         patch.object(ph.repo, "advance_current_day", return_value=dict(enr, status="completed")) as adv, \
         patch.object(ph.repo, "completed_day_numbers", return_value=list(range(1, 8))):
        resp = ph.handler(
            _event("POST /plans/enrolled/{id}/complete-day", user_id="u1",
                   path_params={"id": "anxiety-7"}, body={"dayNumber": 7}), None
        )
    assert resp["statusCode"] == 200
    # completed flag passed to advance_current_day
    assert adv.call_args.kwargs.get("completed") is True


# --------------------------------------------------------------------------- pause
def test_pause_toggles_status():
    enr = {"userId": "u1", "planId": "anxiety-7", "status": "active"}
    with patch.object(ph.repo, "get_enrollment", return_value=enr), \
         patch.object(ph.repo, "set_enrollment_status", return_value=dict(enr, status="paused")) as setst, \
         patch.object(ph.repo, "get_plan", return_value=PLAN), \
         patch.object(ph.repo, "completed_day_numbers", return_value=[]):
        resp = ph.handler(
            _event("POST /plans/enrolled/{id}/pause", user_id="u1",
                   path_params={"id": "anxiety-7"}, body={}), None
        )
    assert resp["statusCode"] == 200
    setst.assert_called_once_with("u1", "anxiety-7", "paused")
    assert _body(resp)["data"]["status"] == "paused"


def test_pause_explicit_resume():
    enr = {"userId": "u1", "planId": "anxiety-7", "status": "paused"}
    with patch.object(ph.repo, "get_enrollment", return_value=enr), \
         patch.object(ph.repo, "set_enrollment_status", return_value=dict(enr, status="active")) as setst, \
         patch.object(ph.repo, "get_plan", return_value=PLAN), \
         patch.object(ph.repo, "completed_day_numbers", return_value=[]):
        resp = ph.handler(
            _event("POST /plans/enrolled/{id}/pause", user_id="u1",
                   path_params={"id": "anxiety-7"}, body={"status": "active"}), None
        )
    assert resp["statusCode"] == 200
    setst.assert_called_once_with("u1", "anxiety-7", "active")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
