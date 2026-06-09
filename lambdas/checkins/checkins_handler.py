"""
Companion Check-ins REST API — GET /checkins.

The user-facing transparency view (spec §10.7, §11.2a "upcoming check-ins"): the
caller's upcoming (scheduled) and recent (sent/responded) proactive check-ins.
Proactive *sending* is owned by the checkin_dispatcher worker; this endpoint is a
read-only window into what we've done / plan to do, which builds trust.

Conventions (docs/COMPANION_API_CONVENTIONS.md):
- JWT required; caller resolved from the authorizer context only.
- Ownership is implicit: we Query PK=userId, so rows can only ever be the caller's.
- Envelope {"data": {"items": [...]}, "meta": {count, nextCursor}}.
- Cursor-based opaque pagination (limit default 25, max 100).
- Optional ?status=scheduled|sent|responded filter.
"""
import logging
import os
from typing import Any, Dict, List

import boto3
from boto3.dynamodb.conditions import Key

import companion_http as http

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
PROJECT_NAME = os.environ.get("PROJECT_NAME", "versiful")
CHECKINS_TABLE = os.environ.get("CHECKINS_TABLE", f"{ENVIRONMENT}-{PROJECT_NAME}-checkins")

# Statuses a caller is allowed to filter on.
_FILTERABLE_STATUSES = {"scheduled", "sent", "responded", "skipped", "failed"}

# Fields surfaced to the client (camelCase already; internal-only fields omitted).
_PUBLIC_FIELDS = (
    "checkinId", "trigger", "contextSelector", "status", "channel",
    "messageSent", "scheduledFor", "createdAt", "sentAt", "respondedAt",
)

_dynamodb = boto3.resource("dynamodb")


def _checkins_table():
    return _dynamodb.Table(CHECKINS_TABLE)


def _to_public(item: Dict[str, Any]) -> Dict[str, Any]:
    return {k: item.get(k) for k in _PUBLIC_FIELDS if item.get(k) is not None}


def _query_user_checkins(user_id: str) -> List[Dict[str, Any]]:
    """All check-in rows for a user (per-user counts are tiny). Sorted newest-first."""
    table = _checkins_table()
    items: List[Dict[str, Any]] = []
    kwargs = {"KeyConditionExpression": Key("userId").eq(user_id)}
    while True:
        resp = table.query(**kwargs)
        items.extend(resp.get("Items", []))
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    # SK is checkinId (a UUID, not time-ordered), so sort in-app by createdAt desc.
    items.sort(key=lambda x: x.get("createdAt") or "", reverse=True)
    return items


def handle_get_checkins(event: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    status_filter = http.get_query_param(event, "status")
    if status_filter is not None:
        status_filter = status_filter.strip().lower()
        if status_filter not in _FILTERABLE_STATUSES:
            return http.validation_error(
                "Invalid status filter.",
                {"fields": {"status": f"must be one of {sorted(_FILTERABLE_STATUSES)}"}},
            )

    try:
        items = _query_user_checkins(user_id)
    except Exception as e:
        logger.error("Failed to query check-ins for %s: %s", user_id, str(e))
        return http.internal_error("Could not load check-ins.")

    if status_filter:
        items = [i for i in items if (i.get("status") or "").lower() == status_filter]

    public = [_to_public(i) for i in items]
    page, meta = http.paginate_offset(public, event)
    return http.success({"items": page}, meta=meta)


def handler(event, context):
    if event.get("httpMethod") == "OPTIONS" or event.get("requestContext", {}).get("http", {}).get("method") == "OPTIONS":
        return {"statusCode": 200, "headers": http.cors_headers(), "body": ""}

    user_id = http.get_user_id_from_event(event)
    if not user_id:
        return http.unauthorized()

    route = http.route_key(event)
    logger.info("checkins request: %s (user=%s)", route, user_id)

    try:
        # Only GET /checkins is exposed by this lambda.
        if route.startswith("GET"):
            return handle_get_checkins(event, user_id)
        return http.not_found("Unknown route.")
    except Exception as e:
        logger.error("Unhandled error in checkins handler: %s", str(e), exc_info=True)
        return http.internal_error()
