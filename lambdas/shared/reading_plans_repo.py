"""DynamoDB access for the Reading Plans feature.

Tables (camelCase attrs, ADR-1; names from env vars set by Terraform):
    reading_plans               PK slug                       -- catalog
    reading_plan_days           PK slug, SK dayNumber [N]      -- catalog day content
    user_reading_plans          PK userId, SK planId           -- enrollment
    user_reading_plan_progress  PK userId, SK dayKey           -- progress (dayKey = "planId#dayNumber")
    users                       PK userId                      -- subscription/prefs/timezone

Every read degrades to a safe default ([] / None) on a client error; writes raise so
the handler can map them to a 500. Access patterns are simple Query-on-PK with in-app
filtering (per-user counts are tiny — spec §4.3).
"""
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

logger = logging.getLogger()

_ENV = os.environ.get("ENVIRONMENT", "dev")
_PROJECT = os.environ.get("PROJECT_NAME", "versiful")


def _table_name(env_var, suffix):
    return os.environ.get(env_var, f"{_ENV}-{_PROJECT}-{suffix}")


READING_PLANS_TABLE = _table_name("READING_PLANS_TABLE", "reading-plans")
READING_PLAN_DAYS_TABLE = _table_name("READING_PLAN_DAYS_TABLE", "reading-plan-days")
USER_READING_PLANS_TABLE = _table_name("USER_READING_PLANS_TABLE", "user-reading-plans")
USER_READING_PLAN_PROGRESS_TABLE = _table_name(
    "USER_READING_PLAN_PROGRESS_TABLE", "user-reading-plan-progress"
)
USERS_TABLE = _table_name("USERS_TABLE", "users")

_dynamodb = boto3.resource("dynamodb")


def _t(name):
    return _dynamodb.Table(name)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def day_key(plan_id, day_number):
    return f"{plan_id}#{int(day_number)}"


# ---------------------------------------------------------------------------
# Catalog (public reads)
# ---------------------------------------------------------------------------
def list_active_plans():
    """Return all active catalog plans (small table → Scan is fine)."""
    try:
        resp = _t(READING_PLANS_TABLE).scan()
    except ClientError as e:
        logger.error("list_active_plans failed: %s", e)
        return []
    items = resp.get("Items", [])
    active = [p for p in items if p.get("isActive", True)]
    active.sort(key=lambda p: p.get("title", ""))
    return active


def get_plan(slug):
    """Return a single catalog plan item, or None."""
    try:
        resp = _t(READING_PLANS_TABLE).get_item(Key={"slug": slug})
    except ClientError as e:
        logger.error("get_plan(%s) failed: %s", slug, e)
        return None
    return resp.get("Item")


def get_plan_days(slug):
    """Return the ordered day list for a plan ([] if none)."""
    try:
        resp = _t(READING_PLAN_DAYS_TABLE).query(
            KeyConditionExpression=Key("slug").eq(slug),
            ScanIndexForward=True,
        )
    except ClientError as e:
        logger.error("get_plan_days(%s) failed: %s", slug, e)
        return []
    days = resp.get("Items", [])
    days.sort(key=lambda d: int(d.get("dayNumber", 0)))
    return days


def get_plan_day(slug, day_number):
    try:
        resp = _t(READING_PLAN_DAYS_TABLE).get_item(
            Key={"slug": slug, "dayNumber": Decimal(int(day_number))}
        )
    except ClientError as e:
        logger.error("get_plan_day(%s,%s) failed: %s", slug, day_number, e)
        return None
    return resp.get("Item")


# ---------------------------------------------------------------------------
# Users (subscription / prefs / timezone)
# ---------------------------------------------------------------------------
def get_user(user_id):
    try:
        resp = _t(USERS_TABLE).get_item(Key={"userId": user_id})
    except ClientError as e:
        logger.error("get_user(%s) failed: %s", user_id, e)
        return None
    return resp.get("Item")


def is_subscribed(user):
    if not user:
        return False
    return bool(user.get("isSubscribed", False))


# ---------------------------------------------------------------------------
# Enrollment (user_reading_plans)
# ---------------------------------------------------------------------------
def list_enrollments(user_id):
    try:
        resp = _t(USER_READING_PLANS_TABLE).query(
            KeyConditionExpression=Key("userId").eq(user_id)
        )
    except ClientError as e:
        logger.error("list_enrollments(%s) failed: %s", user_id, e)
        return []
    return resp.get("Items", [])


def get_enrollment(user_id, plan_id):
    try:
        resp = _t(USER_READING_PLANS_TABLE).get_item(
            Key={"userId": user_id, "planId": plan_id}
        )
    except ClientError as e:
        logger.error("get_enrollment(%s,%s) failed: %s", user_id, plan_id, e)
        return None
    return resp.get("Item")


def create_enrollment(user_id, plan_id, delivery_channel="sms", delivery_time="08:00"):
    """Create a new enrollment. Returns (item, created_bool).

    Idempotent: if an enrollment already exists it is returned unchanged with
    created=False (a conditional PutItem guards against clobbering progress).
    """
    now = now_iso()
    item = {
        "userId": user_id,
        "planId": plan_id,
        "status": "active",
        "currentDay": Decimal(1),
        "deliveryChannel": delivery_channel,
        "deliveryTime": delivery_time,
        "lastDeliveredDay": Decimal(0),
        "lastDeliveredAt": None,
        "startedAt": now,
        "completedAt": None,
        "createdAt": now,
        "updatedAt": now,
    }
    try:
        _t(USER_READING_PLANS_TABLE).put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(userId) AND attribute_not_exists(planId)",
        )
        return item, True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            existing = get_enrollment(user_id, plan_id)
            return existing, False
        raise


def set_enrollment_status(user_id, plan_id, status):
    """Set status (active|paused|completed) on an enrollment. Returns updated item."""
    resp = _t(USER_READING_PLANS_TABLE).update_item(
        Key={"userId": user_id, "planId": plan_id},
        UpdateExpression="SET #s = :s, updatedAt = :now",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": status, ":now": now_iso()},
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes")


def advance_current_day(user_id, plan_id, new_current_day, completed=False):
    """Advance currentDay (monotonic) and optionally mark the plan completed."""
    expr = "SET currentDay = :d, updatedAt = :now"
    values = {":d": Decimal(int(new_current_day)), ":now": now_iso()}
    if completed:
        expr += ", #s = :s, completedAt = :ca"
        values[":s"] = "completed"
        values[":ca"] = now_iso()
        names = {"#s": "status"}
    else:
        names = None
    kwargs = dict(
        Key={"userId": user_id, "planId": plan_id},
        UpdateExpression=expr,
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )
    if names:
        kwargs["ExpressionAttributeNames"] = names
    resp = _t(USER_READING_PLANS_TABLE).update_item(**kwargs)
    return resp.get("Attributes")


def mark_delivered(user_id, plan_id, day_number):
    """Record that a plan day was delivered (idempotency guard for the worker)."""
    resp = _t(USER_READING_PLANS_TABLE).update_item(
        Key={"userId": user_id, "planId": plan_id},
        UpdateExpression=(
            "SET lastDeliveredDay = :d, lastDeliveredAt = :now, "
            "currentDay = :cd, updatedAt = :now"
        ),
        ExpressionAttributeValues={
            ":d": Decimal(int(day_number)),
            ":cd": Decimal(int(day_number)),
            ":now": now_iso(),
        },
        ReturnValues="ALL_NEW",
    )
    return resp.get("Attributes")


# ---------------------------------------------------------------------------
# Progress (user_reading_plan_progress)
# ---------------------------------------------------------------------------
def list_progress(user_id, plan_id):
    """Return progress rows for one plan (dayKey begins with 'planId#')."""
    try:
        resp = _t(USER_READING_PLAN_PROGRESS_TABLE).query(
            KeyConditionExpression=Key("userId").eq(user_id)
            & Key("dayKey").begins_with(f"{plan_id}#")
        )
    except ClientError as e:
        logger.error("list_progress(%s,%s) failed: %s", user_id, plan_id, e)
        return []
    return resp.get("Items", [])


def get_progress(user_id, plan_id, day_number):
    try:
        resp = _t(USER_READING_PLAN_PROGRESS_TABLE).get_item(
            Key={"userId": user_id, "dayKey": day_key(plan_id, day_number)}
        )
    except ClientError as e:
        logger.error("get_progress failed: %s", e)
        return None
    return resp.get("Item")


def record_progress(user_id, plan_id, day_number, reflection_id=None):
    """Upsert a completed-day progress row (idempotent on dayKey)."""
    item = {
        "userId": user_id,
        "dayKey": day_key(plan_id, day_number),
        "planId": plan_id,
        "dayNumber": Decimal(int(day_number)),
        "completedAt": now_iso(),
    }
    if reflection_id:
        item["reflectionId"] = reflection_id
    _t(USER_READING_PLAN_PROGRESS_TABLE).put_item(Item=item)
    return item


def completed_day_numbers(user_id, plan_id):
    """Return a sorted list of completed day numbers for a plan."""
    rows = list_progress(user_id, plan_id)
    return sorted(int(r.get("dayNumber", 0)) for r in rows if r.get("completedAt"))
