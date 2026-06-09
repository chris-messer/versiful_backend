"""
Companion account-management / communication-preferences REST API.

Backs GET/PUT /users/preferences (spec §4.4, §12, §14). Reads/writes the
communication-preference ATTRIBUTES on the existing `users` DynamoDB item — there
is no separate preferences table. The same attributes are written by the in-chat
account-management tools (account_tools.py), keeping chat/web in parity (§5.4).

Follows COMPANION_API_CONVENTIONS.md: JWT auth (userId from the authorizer, never
the body), success -> {"data": {...}}, error -> {"error": {code,message,details?}}.
Preference reads/writes are allowed for any authenticated user (free or premium);
the individual capabilities (daily verse, check-ins) are gated where they're
delivered (the worker / send paths), not at the preference toggle.
"""
import json
import logging
import os

try:
    import preferences
except ImportError:  # local test / non-layer context
    from lambdas.shared import preferences

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _cors_headers():
    origin = os.environ.get("CORS_ORIGIN", "http://localhost:5173")
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "GET,PUT,OPTIONS",
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
    authorizer = (event.get("requestContext") or {}).get("authorizer") or {}
    if authorizer.get("userId"):
        return authorizer["userId"]
    claims = authorizer.get("claims") or {}
    return claims.get("sub")


def handle_get_preferences(user_id):
    prefs = preferences.read_preferences(user_id)
    if prefs is None:
        # No user item yet: return the documented defaults so the UI can render.
        prefs = dict(preferences.PREFERENCE_DEFAULTS)
    return _ok(prefs)


def handle_put_preferences(event, user_id):
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _err("validation_error", "Request body must be valid JSON.", 400)

    clean, errors = preferences.validate_and_normalize(body)
    if errors:
        return _err(
            "validation_error",
            "One or more preference fields are invalid.",
            400,
            details={"fields": errors},
        )
    if not clean:
        # Nothing valid to change; return current state rather than erroring.
        return _ok(preferences.read_preferences(user_id) or dict(preferences.PREFERENCE_DEFAULTS))

    try:
        updated = preferences.apply_preferences(user_id, clean, source="web")
    except Exception as e:
        logger.error("Failed to apply preferences for %s: %s", user_id, str(e))
        return _err("internal_error", "Could not save your preferences.", 500)

    return _ok(updated)


def handler(event, context):
    method = event.get("httpMethod") or (event.get("requestContext", {}).get("http", {}) or {}).get("method", "")
    route = event.get("routeKey") or f'{method} {event.get("path", "")}'
    logger.info("account_management invoked: %s", route)

    if method == "OPTIONS":
        return {"statusCode": 200, "headers": _cors_headers(), "body": ""}

    user_id = _user_id_from_event(event)
    if not user_id:
        return _err("unauthorized", "Missing or invalid authentication.", 401)

    try:
        if method == "GET":
            return handle_get_preferences(user_id)
        if method == "PUT":
            return handle_put_preferences(event, user_id)
        return _err("not_found", "Unknown route.", 404)
    except Exception as e:
        logger.error("Unhandled error in account_management: %s", str(e), exc_info=True)
        return _err("internal_error", "An unexpected error occurred.", 500)
