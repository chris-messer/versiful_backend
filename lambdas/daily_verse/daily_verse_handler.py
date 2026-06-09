"""
Companion Daily Verse REST API — GET /daily-verse (spec §6, §14).

Returns today's personalized, non-duplicative verse for the authenticated user.
Backs the web DailyVerseCard. Daily verse is a PREMIUM capability (spec §16), so a
free user gets a 402 per COMPANION_API_CONVENTIONS.md §3.

Behavior:
  - If today's daily verse was already produced (sent by the worker or a prior GET),
    return it from `verse_history` (idempotent — repeated GETs return the same verse).
  - Otherwise select a fresh personalized verse (leveraging long-term memory + the
    do-not-repeat list) and record it to `verse_history` with context='daily_verse'.

Follows the shared envelope: success -> {"data": {...}}, error -> {"error": {...}}.
"""
import json
import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

try:
    import verse_engine
except ImportError:  # local test / non-layer context
    from lambdas.daily_verse import verse_engine

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
PROJECT_NAME = os.environ.get("PROJECT_NAME", "versiful")
USERS_TABLE = os.environ.get("USERS_TABLE", f"{ENVIRONMENT}-{PROJECT_NAME}-users")

_dynamodb = None


def _users_table():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb.Table(USERS_TABLE)


# ---------------------------------------------------------------------------
# HTTP helpers (shared conventions, COMPANION_API_CONVENTIONS.md §1, §4)
# ---------------------------------------------------------------------------
def _cors_headers():
    origin = os.environ.get("CORS_ORIGIN", "http://localhost:5173")
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "GET,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Credentials": "true",
    }


def _ok(data, status=200, meta=None):
    body = {"data": data}
    if meta is not None:
        body["meta"] = meta
    return {"statusCode": status, "headers": _cors_headers(), "body": json.dumps(body)}


def _err(code, message, status, details=None):
    error = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"statusCode": status, "headers": _cors_headers(), "body": json.dumps({"error": error})}


def _user_id_from_event(event):
    """Resolve the caller from the JWT authorizer context. Never trust the body."""
    authorizer = (event.get("requestContext") or {}).get("authorizer") or {}
    if authorizer.get("userId"):
        return authorizer["userId"]
    claims = authorizer.get("claims") or {}
    return claims.get("sub")


def _get_user(user_id):
    try:
        resp = _users_table().get_item(Key={"userId": user_id})
        return resp.get("Item") or {}
    except ClientError as e:
        logger.error("Failed to load user %s: %s", user_id, str(e))
        return {}


def _verse_payload(verse, sent_at):
    """Shape a verse (from selection or verse_history) into the API response."""
    return {
        "reference": verse.get("reference") or verse.get("displayRef"),
        "displayRef": verse.get("displayRef") or verse.get("reference"),
        "translation": verse.get("translation"),
        "themes": verse.get("themes") or [],
        "reflection": verse.get("reflection"),
        "message": verse.get("message"),
        "context": verse.get("context", "daily_verse"),
        "sentAt": sent_at,
    }


def handle_get_daily_verse(event):
    user_id = _user_id_from_event(event)
    if not user_id:
        return _err("unauthorized", "Missing or invalid authentication.", 401)

    user = _get_user(user_id)

    # Subscription gating: daily verse is premium (spec §16, conventions §3).
    is_subscribed = bool(user.get("isSubscribed", False))
    if not is_subscribed:
        return _err(
            "subscription_required",
            "Daily verse is a premium feature. Upgrade to receive a personalized verse each day.",
            402,
        )

    first_name = user.get("firstName")
    bible_version = user.get("bibleVersion")
    local_date = datetime.now(timezone.utc).date().isoformat()

    # Idempotent: return today's verse if we already produced it.
    existing = verse_engine.todays_daily_verse(user_id, local_date)
    if existing:
        return _ok(_verse_payload(existing, existing.get("sentAt")))

    # Otherwise select + record a fresh personalized verse.
    verse = verse_engine.select_personalized_verse(
        user_id=user_id,
        bible_version=bible_version,
        first_name=first_name,
    )
    sent_at = verse_engine.record_verse_history(
        user_id=user_id,
        verse=verse,
        phone_number=user.get("phoneNumber"),
        context_kind="daily_verse",
        channel="web",
    )
    if not sent_at:
        sent_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    payload = _verse_payload(verse, sent_at)
    payload["context"] = "daily_verse"
    return _ok(payload)


def handler(event, context):
    method = event.get("httpMethod") or (event.get("requestContext", {}).get("http", {}) or {}).get("method", "")
    route = event.get("routeKey") or f'{method} {event.get("path", "")}'
    logger.info("daily_verse invoked: %s", route)

    if method == "OPTIONS":
        return {"statusCode": 200, "headers": _cors_headers(), "body": ""}

    try:
        if method == "GET":
            return handle_get_daily_verse(event)
        return _err("not_found", "Unknown route.", 404)
    except Exception as e:
        logger.error("Unhandled error in daily_verse: %s", str(e), exc_info=True)
        return _err("internal_error", "An unexpected error occurred.", 500)
