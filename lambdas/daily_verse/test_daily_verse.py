"""
Unit tests for the daily_verse REST handler (GET /daily-verse).

Run: conda run -n versiful_backend python -m pytest lambdas/daily_verse/test_daily_verse.py
"""
import json
import os
import sys
from unittest.mock import patch

THIS_DIR = os.path.dirname(__file__)

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("PROJECT_NAME", "versiful")
os.environ.setdefault("USERS_TABLE", "test-versiful-users")
os.environ.setdefault("VERSE_HISTORY_TABLE", "test-versiful-verse-history")

# Make sure this dir's `verse_engine` wins over the worker's same-named module.
for _m in ("verse_engine", "daily_verse_handler", "daily_verse_worker_handler"):
    sys.modules.pop(_m, None)
sys.path.insert(0, THIS_DIR)

import daily_verse_handler as dv  # noqa: E402


def _event(method="GET", user_id="u1"):
    ctx = {}
    if user_id is not None:
        ctx = {"authorizer": {"userId": user_id}}
    return {"httpMethod": method, "path": "/daily-verse", "requestContext": ctx}


def test_missing_auth_returns_401():
    resp = dv.handler(_event(user_id=None), None)
    assert resp["statusCode"] == 401
    assert json.loads(resp["body"])["error"]["code"] == "unauthorized"


def test_free_user_gets_402():
    with patch.object(dv, "_get_user", return_value={"userId": "u1", "isSubscribed": False}):
        resp = dv.handler(_event(), None)
    assert resp["statusCode"] == 402
    assert json.loads(resp["body"])["error"]["code"] == "subscription_required"


def test_returns_existing_todays_verse_idempotent():
    existing = {
        "displayRef": "Psalm 23", "reference": "Psalm 23", "translation": "NIV",
        "themes": ["rest"], "reflection": "He restores", "message": "msg",
        "context": "daily_verse", "sentAt": "2026-06-09T08:00:00Z",
    }
    with patch.object(dv, "_get_user", return_value={"userId": "u1", "isSubscribed": True}), \
         patch.object(dv.verse_engine, "todays_daily_verse", return_value=existing), \
         patch.object(dv.verse_engine, "select_personalized_verse") as sel:
        resp = dv.handler(_event(), None)
    assert resp["statusCode"] == 200
    data = json.loads(resp["body"])["data"]
    assert data["displayRef"] == "Psalm 23"
    sel.assert_not_called()  # idempotent: no new selection


def test_generates_and_records_when_absent():
    verse = {"displayRef": "John 14:27", "reference": "John 14:27", "translation": "NIV",
             "themes": ["peace"], "reflection": "peace", "message": "Good morning"}
    with patch.object(dv, "_get_user", return_value={"userId": "u1", "isSubscribed": True, "firstName": "Chris"}), \
         patch.object(dv.verse_engine, "todays_daily_verse", return_value=None), \
         patch.object(dv.verse_engine, "select_personalized_verse", return_value=verse) as sel, \
         patch.object(dv.verse_engine, "record_verse_history", return_value="2026-06-09T08:00:00Z") as rec:
        resp = dv.handler(_event(), None)
    assert resp["statusCode"] == 200
    data = json.loads(resp["body"])["data"]
    assert data["displayRef"] == "John 14:27"
    assert data["context"] == "daily_verse"
    sel.assert_called_once()
    rec.assert_called_once()


def test_options_preflight():
    resp = dv.handler({"httpMethod": "OPTIONS"}, None)
    assert resp["statusCode"] == 200
