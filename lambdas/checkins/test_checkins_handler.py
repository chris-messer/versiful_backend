"""Unit tests for the GET /checkins transparency endpoint (moto-backed)."""
import json
import os
import sys
from datetime import datetime, timezone, timedelta

import pytest

sys.path.insert(0, os.path.dirname(__file__))

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ["ENVIRONMENT"] = "test"
os.environ["PROJECT_NAME"] = "versiful"

import checkins_handler as ch


def _event(user_id="u1", qs=None):
    return {
        "routeKey": "GET /checkins",
        "requestContext": {"authorizer": {"userId": user_id}},
        "queryStringParameters": qs,
    }


def _iso(dt):
    return dt.isoformat()


@pytest.fixture
def checkins_table():
    moto = pytest.importorskip("moto")
    import boto3
    import importlib
    with moto.mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="test-versiful-checkins",
            KeySchema=[
                {"AttributeName": "userId", "KeyType": "HASH"},
                {"AttributeName": "checkinId", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "checkinId", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        # Rebind the handler's module-level resource under the active moto mock.
        importlib.reload(ch)
        yield ddb.Table("test-versiful-checkins")


def _seed(table, user_id, count, status="sent", base=None):
    base = base or datetime(2026, 6, 1, tzinfo=timezone.utc)
    for i in range(count):
        table.put_item(Item={
            "userId": user_id,
            "checkinId": f"{user_id}-c{i}",
            "trigger": "inactivity",
            "contextSelector": "general",
            "status": status,
            "channel": "sms",
            "messageSent": f"msg {i}",
            "createdAt": _iso(base + timedelta(hours=i)),
            "sentAt": _iso(base + timedelta(hours=i)),
        })


def test_unauthorized_without_user():
    resp = ch.handler({"routeKey": "GET /checkins", "requestContext": {}}, None)
    assert resp["statusCode"] == 401
    assert json.loads(resp["body"])["error"]["code"] == "unauthorized"


def test_returns_envelope_newest_first(checkins_table):
    _seed(checkins_table, "u1", 3)
    resp = ch.handler(_event(), None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    items = body["data"]["items"]
    assert len(items) == 3
    # Newest-first by createdAt.
    assert items[0]["createdAt"] > items[-1]["createdAt"]
    assert body["meta"]["count"] == 3
    assert body["meta"]["nextCursor"] is None


def test_ownership_scoped(checkins_table):
    _seed(checkins_table, "u1", 2)
    _seed(checkins_table, "other", 5)
    resp = ch.handler(_event(user_id="u1"), None)
    items = json.loads(resp["body"])["data"]["items"]
    assert len(items) == 2  # never sees 'other' rows


def test_status_filter_validation(checkins_table):
    resp = ch.handler(_event(qs={"status": "bogus"}), None)
    assert resp["statusCode"] == 400
    assert json.loads(resp["body"])["error"]["code"] == "validation_error"


def test_status_filter_applies(checkins_table):
    _seed(checkins_table, "u1", 2, status="sent")
    _seed(checkins_table, "u1", 1, status="scheduled",
          base=datetime(2026, 7, 1, tzinfo=timezone.utc))
    resp = ch.handler(_event(qs={"status": "scheduled"}), None)
    items = json.loads(resp["body"])["data"]["items"]
    assert len(items) == 1 and items[0]["status"] == "scheduled"


def test_pagination_cursor(checkins_table):
    _seed(checkins_table, "u1", 30)
    resp = ch.handler(_event(qs={"limit": "25"}), None)
    body = json.loads(resp["body"])
    assert body["meta"]["count"] == 25
    cursor = body["meta"]["nextCursor"]
    assert cursor

    resp2 = ch.handler(_event(qs={"limit": "25", "cursor": cursor}), None)
    body2 = json.loads(resp2["body"])
    assert body2["meta"]["count"] == 5
    assert body2["meta"]["nextCursor"] is None
