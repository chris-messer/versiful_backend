"""Unit tests for the My Walk endpoints (moto for DynamoDB; Neon/memory mocked)."""
import json
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

import walk_handler as wh
import walk_aggregator as wa


def _event(method, path, user_id="u1", qs=None, path_params=None):
    return {
        "httpMethod": method,
        "path": path,
        "requestContext": {"authorizer": {"userId": user_id}},
        "queryStringParameters": qs,
        "pathParameters": path_params,
    }


def _iso(dt):
    return dt.isoformat()


@pytest.fixture
def tables():
    moto = pytest.importorskip("moto")
    import boto3
    import importlib
    with moto.mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="test-versiful-users",
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        ddb.create_table(
            TableName="test-versiful-verse-history",
            KeySchema=[
                {"AttributeName": "userId", "KeyType": "HASH"},
                {"AttributeName": "sentAt", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "sentAt", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        for name, sk in [("prayers", "prayerId"), ("checkins", "checkinId"),
                         ("user-reading-plans", "planId")]:
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
        # Rebind module-level DynamoDB resources under the active moto mock.
        importlib.reload(wa)
        importlib.reload(wh)
        yield ddb


def _seed_user(ddb, subscribed=True):
    ddb.Table("test-versiful-users").put_item(
        Item={"userId": "u1", "isSubscribed": subscribed, "plan": "premium" if subscribed else "free"}
    )


def _seed_activity(ddb):
    today = datetime.now(timezone.utc)
    ddb.Table("test-versiful-prayers").put_item(Item={
        "userId": "u1", "prayerId": "p1", "title": "Mom", "status": "answered",
        "answerNote": "She's well", "answeredAt": _iso(today), "createdAt": _iso(today - timedelta(days=1)),
    })
    ddb.Table("test-versiful-prayers").put_item(Item={
        "userId": "u1", "prayerId": "p2", "title": "Job", "status": "active",
        "createdAt": _iso(today),
    })
    ddb.Table("test-versiful-verse-history").put_item(Item={
        "userId": "u1", "sentAt": _iso(today), "displayRef": "Isaiah 41:10",
        "themes": ["fear", "comfort"], "context": "daily_verse",
    })


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def test_unauthorized():
    resp = wh.handler({"httpMethod": "GET", "path": "/walk/summary", "requestContext": {}}, None)
    assert resp["statusCode"] == 401


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
def test_summary_premium(tables):
    _seed_user(tables, subscribed=True)
    _seed_activity(tables)
    with patch.object(wa, "memories_summary", return_value={"count": 2, "byKind": {"struggle": 2}, "_items": [{"kind": "struggle"}]}), \
         patch.object(wa, "reflections_summary", return_value={"count": 1, "recent": []}):
        resp = wh.handler(_event("GET", "/walk/summary"), None)
    assert resp["statusCode"] == 200
    data = json.loads(resp["body"])["data"]
    assert data["isPremium"] is True and data["teaser"] is False
    assert data["prayers"]["active"] == 1 and data["prayers"]["answered"] == 1
    assert "recentAnswered" in data["prayers"]
    assert data["verses"]["count"] == 1
    assert "milestones" in data and "themes" in data


def test_summary_free_is_teaser(tables):
    _seed_user(tables, subscribed=False)
    _seed_activity(tables)
    with patch.object(wa, "memories_summary", return_value={"count": 0, "byKind": {}, "_items": []}), \
         patch.object(wa, "reflections_summary", return_value={"count": 0, "recent": []}):
        resp = wh.handler(_event("GET", "/walk/summary"), None)
    data = json.loads(resp["body"])["data"]
    assert data["isPremium"] is False and data["teaser"] is True
    assert "upgradeMessage" in data
    # Detailed lists are withheld in the teaser.
    assert "recentAnswered" not in data["prayers"]
    assert "milestones" not in data


# ---------------------------------------------------------------------------
# Memories list / delete / clear
# ---------------------------------------------------------------------------
def test_list_memories_503_when_neon_down(tables):
    with patch.object(wh, "_neon_available", return_value=False):
        resp = wh.handler(_event("GET", "/walk/memories"), None)
    assert resp["statusCode"] == 503
    assert json.loads(resp["body"])["error"]["code"] == "service_unavailable"


def test_list_memories_ok(tables):
    fake = [{"id": "m1", "kind": "struggle", "summary": "anxiety", "people": [],
             "event_date": None, "status": "active", "created_at": "2026-06-01T00:00:00Z",
             "last_referenced_at": None, "detail": None}]
    with patch.object(wh, "_neon_available", return_value=True), \
         patch("memory_store.list_memories", return_value=fake):
        resp = wh.handler(_event("GET", "/walk/memories"), None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["data"]["items"][0]["id"] == "m1"
    assert body["data"]["items"][0]["eventDate"] is None
    assert body["meta"]["count"] == 1


def test_delete_one_memory_found(tables):
    with patch.object(wh, "_neon_available", return_value=True), \
         patch("memory_store.delete_memory", return_value=True):
        resp = wh.handler(_event("DELETE", "/walk/memories/m1", path_params={"id": "m1"}), None)
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["data"] == {"deleted": True, "id": "m1"}


def test_delete_one_memory_not_found_is_404(tables):
    with patch.object(wh, "_neon_available", return_value=True), \
         patch("memory_store.delete_memory", return_value=False):
        resp = wh.handler(_event("DELETE", "/walk/memories/missing", path_params={"id": "missing"}), None)
    assert resp["statusCode"] == 404
    assert json.loads(resp["body"])["error"]["code"] == "not_found"


def test_delete_one_memory_503_when_neon_down(tables):
    with patch.object(wh, "_neon_available", return_value=False):
        resp = wh.handler(_event("DELETE", "/walk/memories/m1", path_params={"id": "m1"}), None)
    assert resp["statusCode"] == 503


def test_clear_all_memories(tables):
    with patch.object(wh, "_neon_available", return_value=True), \
         patch("memory_store.delete_all_memories", return_value=4):
        resp = wh.handler(_event("DELETE", "/walk/memories"), None)
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["data"] == {"deleted": True, "count": 4}
