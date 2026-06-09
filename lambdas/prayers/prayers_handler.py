"""
Companion Prayer Journal REST API (DynamoDB-backed).

Implements the prayer endpoints from COMPANION_SPEC.md §7 / §14 following
COMPANION_API_CONVENTIONS.md (envelope, JWT auth, 402 gating, ownership→404,
cursor pagination):

    GET    /prayers                 list (paginated, ?status=active|answered|archived)
    POST   /prayers                 create
    PUT    /prayers/{id}            edit (title/body/category/people/eventDate/cadence)
    POST   /prayers/{id}/answered   mark answered (capture answer note + date)
    DELETE /prayers/{id}            delete

Data store: DynamoDB table `${env}-${project}-prayers` (PK `userId`, SK `prayerId`),
camelCase attributes (ADR-1). Every query/mutation is scoped to the caller's id
derived from the authorizer (never trusted from the body) — a prayer owned by
another user reads as 404.

Gating (conventions §3, spec §16): free users may keep up to 3 prayers (a 4th
create → 402 limit_reached); reminders are premium, so a free user's
`reminderCadence` is coerced to `none`. Premium users are unlimited.

When a prayer is marked answered we additionally write a best-effort gratitude
reflection to Neon via the shared `memory_store` (spec §7.1). That write degrades
gracefully: if Neon/psycopg is unavailable (this lambda does not mount the
langchain layer by default — see the integration spec) it simply no-ops and the
DynamoDB answer is still authoritative (conventions §7).
"""
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

import api_common as api

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
PROJECT_NAME = os.environ.get("PROJECT_NAME", "versiful")

PRAYERS_TABLE = os.environ.get("PRAYERS_TABLE", f"{ENVIRONMENT}-{PROJECT_NAME}-prayers")
USERS_TABLE = os.environ.get("USERS_TABLE", f"{ENVIRONMENT}-{PROJECT_NAME}-users")

_dynamodb = boto3.resource("dynamodb")
prayers_table = _dynamodb.Table(PRAYERS_TABLE)
users_table = _dynamodb.Table(USERS_TABLE)

FREE_PRAYER_LIMIT = 3
VALID_CADENCES = {"none", "daily", "weekly"}
VALID_STATUSES = {"active", "answered", "archived"}
EDITABLE_FIELDS = ("title", "body", "category", "people", "eventDate", "reminderCadence", "status")

MAX_TITLE_LEN = 200
MAX_BODY_LEN = 5000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_user(user_id: str):
    try:
        resp = users_table.get_item(Key={"userId": user_id})
        return resp.get("Item")
    except ClientError as e:
        logger.error("Error loading user %s: %s", user_id, str(e))
        return None


def _serialize(item: dict) -> dict:
    """Shape a DynamoDB prayer item for the wire (expose both id and prayerId)."""
    out = api.to_native(dict(item))
    out["id"] = out.get("prayerId")
    return out


def _get_prayer(user_id: str, prayer_id: str):
    try:
        resp = prayers_table.get_item(Key={"userId": user_id, "prayerId": prayer_id})
        return resp.get("Item")
    except ClientError as e:
        logger.error("Error fetching prayer %s: %s", prayer_id, str(e))
        return None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def _validate_create(body: dict):
    """Return (clean_fields, error_response)."""
    title = body.get("title")
    if not title or not str(title).strip():
        return None, api.validation_error("`title` is required.", ["title"])
    title = str(title).strip()
    if len(title) > MAX_TITLE_LEN:
        return None, api.validation_error("`title` is too long.", ["title"])

    fields = {"title": title}

    bdy = body.get("body")
    if bdy is not None:
        if not isinstance(bdy, str) or len(bdy) > MAX_BODY_LEN:
            return None, api.validation_error("`body` must be a string.", ["body"])
        fields["body"] = bdy.strip() or None

    if body.get("category") is not None:
        fields["category"] = str(body["category"]).strip() or None

    fields["people"] = api.coerce_str_list(body.get("people"))

    event_date = body.get("eventDate")
    if event_date is not None:
        if not api.is_iso_date(event_date):
            return None, api.validation_error("`eventDate` must be YYYY-MM-DD.", ["eventDate"])
        fields["eventDate"] = event_date

    cadence = body.get("reminderCadence", "none")
    cadence = str(cadence).strip().lower() if cadence else "none"
    if cadence not in VALID_CADENCES:
        return None, api.validation_error(
            f"`reminderCadence` must be one of {sorted(VALID_CADENCES)}.", ["reminderCadence"]
        )
    fields["reminderCadence"] = cadence

    return fields, None


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
def handle_list(event, user_id, user_item):
    query = api.get_query_params(event)
    status_filter = (query.get("status") or "").strip().lower() or None
    if status_filter and status_filter not in VALID_STATUSES:
        return api.validation_error(
            f"`status` must be one of {sorted(VALID_STATUSES)}.", ["status"]
        )

    limit = api.clamp_limit(query)
    start_key = api.decode_cursor(query.get("cursor"))

    kwargs = {
        "KeyConditionExpression": Key("userId").eq(user_id),
        "Limit": limit,
        "ScanIndexForward": False,  # newest prayerIds first-ish; sorted below anyway
    }
    if status_filter:
        # status is a non-key attribute -> in-app filter (per-user counts are small).
        kwargs["FilterExpression"] = Attr("status").eq(status_filter)
    if isinstance(start_key, dict):
        kwargs["ExclusiveStartKey"] = start_key

    try:
        resp = prayers_table.query(**kwargs)
    except ClientError as e:
        logger.error("Error listing prayers for %s: %s", user_id, str(e))
        return api.internal_error()

    items = [_serialize(i) for i in resp.get("Items", [])]
    # Stable newest-first ordering by createdAt for the UI.
    items.sort(key=lambda p: p.get("createdAt") or "", reverse=True)
    next_cursor = api.encode_cursor(resp.get("LastEvaluatedKey"))
    return api.collection(items, next_cursor)


def handle_create(event, user_id, user_item):
    body, err = api.parse_body(event)
    if err:
        return err

    fields, verr = _validate_create(body)
    if verr:
        return verr

    premium = api.is_premium(user_item)
    if not premium:
        # Count existing prayers; free users keep at most FREE_PRAYER_LIMIT.
        try:
            count_resp = prayers_table.query(
                KeyConditionExpression=Key("userId").eq(user_id),
                Select="COUNT",
            )
            current = count_resp.get("Count", 0)
        except ClientError as e:
            logger.error("Error counting prayers: %s", str(e))
            return api.internal_error()
        if current >= FREE_PRAYER_LIMIT:
            return api.limit_reached(
                f"Free plan allows up to {FREE_PRAYER_LIMIT} prayers. Upgrade for unlimited.",
                FREE_PRAYER_LIMIT,
                current,
            )
        # Reminders are premium-only: coerce free cadence to none.
        if fields.get("reminderCadence") != "none":
            logger.info("Coercing reminderCadence to 'none' for free user %s", user_id)
            fields["reminderCadence"] = "none"

    now = _now()
    source = str(body.get("source") or "web").strip().lower()
    if source not in ("web", "chat", "sms"):
        source = "web"

    item = {
        "userId": user_id,
        "prayerId": str(uuid.uuid4()),
        "title": fields["title"],
        "body": fields.get("body"),
        "category": fields.get("category"),
        "people": fields.get("people", []),
        "status": "active",
        "eventDate": fields.get("eventDate"),
        "reminderCadence": fields.get("reminderCadence", "none"),
        "nextReminderAt": None,
        "lastPrayedAt": None,
        "prayCount": 0,
        "answerNote": None,
        "answeredAt": None,
        "source": source,
        "createdAt": now,
        "updatedAt": now,
    }
    try:
        prayers_table.put_item(Item=item)
    except ClientError as e:
        logger.error("Error creating prayer: %s", str(e))
        return api.internal_error()

    return api.created(_serialize(item))


def handle_update(event, user_id, user_item, prayer_id):
    existing = _get_prayer(user_id, prayer_id)
    if not existing:
        return api.not_found("Prayer not found.")

    body, err = api.parse_body(event)
    if err:
        return err

    updates = {}
    # title
    if "title" in body:
        title = body.get("title")
        if not title or not str(title).strip() or len(str(title).strip()) > MAX_TITLE_LEN:
            return api.validation_error("`title` must be a non-empty string.", ["title"])
        updates["title"] = str(title).strip()
    if "body" in body:
        bdy = body.get("body")
        if bdy is not None and (not isinstance(bdy, str) or len(bdy) > MAX_BODY_LEN):
            return api.validation_error("`body` must be a string.", ["body"])
        updates["body"] = (bdy.strip() or None) if isinstance(bdy, str) else None
    if "category" in body:
        cat = body.get("category")
        updates["category"] = (str(cat).strip() or None) if cat is not None else None
    if "people" in body:
        updates["people"] = api.coerce_str_list(body.get("people"))
    if "eventDate" in body:
        ed = body.get("eventDate")
        if ed is not None and not api.is_iso_date(ed):
            return api.validation_error("`eventDate` must be YYYY-MM-DD.", ["eventDate"])
        updates["eventDate"] = ed
    if "reminderCadence" in body:
        cadence = str(body.get("reminderCadence") or "none").strip().lower()
        if cadence not in VALID_CADENCES:
            return api.validation_error(
                f"`reminderCadence` must be one of {sorted(VALID_CADENCES)}.", ["reminderCadence"]
            )
        if cadence != "none" and not api.is_premium(user_item):
            cadence = "none"  # reminders premium-only
        updates["reminderCadence"] = cadence
    if "status" in body:
        st = str(body.get("status") or "").strip().lower()
        if st not in VALID_STATUSES:
            return api.validation_error(
                f"`status` must be one of {sorted(VALID_STATUSES)}.", ["status"]
            )
        updates["status"] = st

    if not updates:
        return api.validation_error("No editable fields supplied.", list(EDITABLE_FIELDS))

    updates["updatedAt"] = _now()
    updated = _apply_updates(user_id, prayer_id, updates)
    if updated is None:
        return api.internal_error()
    return api.ok(_serialize(updated))


def handle_answered(event, user_id, user_item, prayer_id):
    existing = _get_prayer(user_id, prayer_id)
    if not existing:
        return api.not_found("Prayer not found.")

    body, err = api.parse_body(event)
    if err:
        return err

    note = body.get("note")
    if note is not None:
        note = str(note).strip() or None

    answered_at = body.get("answeredAt") or body.get("date")
    if answered_at and api.is_iso_date(answered_at):
        # accept a plain calendar date; store as-is
        pass
    else:
        answered_at = _now()

    updates = {
        "status": "answered",
        "answerNote": note,
        "answeredAt": answered_at,
        "updatedAt": _now(),
    }
    updated = _apply_updates(user_id, prayer_id, updates)
    if updated is None:
        return api.internal_error()

    # Best-effort gratitude reflection to Neon (spec §7.1). Never fails the request.
    _write_answered_reflection(user_id, updated, note)

    return api.ok(_serialize(updated))


def handle_delete(event, user_id, user_item, prayer_id):
    existing = _get_prayer(user_id, prayer_id)
    if not existing:
        return api.not_found("Prayer not found.")
    try:
        prayers_table.delete_item(Key={"userId": user_id, "prayerId": prayer_id})
    except ClientError as e:
        logger.error("Error deleting prayer %s: %s", prayer_id, str(e))
        return api.internal_error()
    return api.deleted(prayer_id)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------
def _apply_updates(user_id: str, prayer_id: str, updates: dict):
    set_parts, names, values = [], {}, {}
    for k, v in updates.items():
        set_parts.append(f"#{k} = :{k}")
        names[f"#{k}"] = k
        values[f":{k}"] = v
    try:
        resp = prayers_table.update_item(
            Key={"userId": user_id, "prayerId": prayer_id},
            UpdateExpression="SET " + ", ".join(set_parts),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ReturnValues="ALL_NEW",
        )
        return resp.get("Attributes")
    except ClientError as e:
        logger.error("Error updating prayer %s: %s", prayer_id, str(e))
        return None


def _write_answered_reflection(user_id: str, prayer: dict, note):
    """Write a gratitude reflection capturing an answered prayer (best-effort)."""
    try:
        import memory_store  # shipped in the shared_dependencies layer
    except Exception:
        return
    title = prayer.get("title") or "a prayer"
    content = f"Answered prayer: {title}."
    if note:
        content += f" {note}"
    try:
        ref_id = memory_store.insert_reflection(
            user_id=user_id,
            content=content,
            source="auto_summary",
            verse_reference=None,
        )
        if ref_id:
            logger.info("Logged answered-prayer reflection %s", ref_id)
    except Exception as e:  # memory_store already degrades; belt-and-suspenders
        logger.info("Answered-prayer reflection skipped (Neon unavailable): %s", str(e))


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
def handler(event, context):
    method = api.get_method(event)
    route_key = api.get_route_key(event)
    logger.info("prayers invoked: %s", route_key)

    if method == "OPTIONS":
        return api.options_response()

    user_id = api.get_user_id(event)
    if not user_id:
        return api.unauthorized()

    path_params = api.get_path_params(event)
    prayer_id = path_params.get("id")

    try:
        user_item = _load_user(user_id)

        if route_key == "GET /prayers" or (method == "GET" and not prayer_id):
            return handle_list(event, user_id, user_item)
        if route_key == "POST /prayers" or (method == "POST" and not prayer_id):
            return handle_create(event, user_id, user_item)
        if "/answered" in route_key or (method == "POST" and prayer_id and api.get_path(event).endswith("/answered")):
            if not prayer_id:
                return api.validation_error("Prayer id is required.", ["id"])
            return handle_answered(event, user_id, user_item, prayer_id)
        if method == "PUT":
            if not prayer_id:
                return api.validation_error("Prayer id is required.", ["id"])
            return handle_update(event, user_id, user_item, prayer_id)
        if method == "DELETE":
            if not prayer_id:
                return api.validation_error("Prayer id is required.", ["id"])
            return handle_delete(event, user_id, user_item, prayer_id)

        return api.not_found("Unknown route.")
    except Exception as e:  # never leak internals
        logger.error("Unhandled error in prayers handler: %s", str(e), exc_info=True)
        return api.internal_error()
