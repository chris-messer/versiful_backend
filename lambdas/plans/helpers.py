"""Shared helpers for the Reading Plans REST lambda.

Implements the COMPANION_API_CONVENTIONS.md contract: the success/error envelope,
JWT auth extraction (HTTP API v2 custom authorizer), subscription gating, route
parsing, and small validation utilities. Kept dependency-light (boto3 + stdlib) so
the handler stays readable and unit-testable with DynamoDB mocked.
"""
import json
import logging
import os
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# JSON / Decimal handling (DynamoDB returns Decimals)
# ---------------------------------------------------------------------------
def _to_native(obj):
    """Recursively convert DynamoDB Decimals to int/float for JSON serialization."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_native(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
def cors_headers():
    """CORS headers echoed on every response (preflight handled by the cors lambda).

    Reuses the existing pattern: echo the configured origin. Allow-Credentials is
    only sent for a concrete origin (the wildcard + credentials combo is invalid).
    """
    origin = os.environ.get("CORS_ORIGIN") or os.environ.get("ALLOWED_CORS_ORIGINS", "*")
    if "," in origin:
        origin = origin.split(",")[0].strip()
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
    }
    if origin != "*":
        headers["Access-Control-Allow-Credentials"] = "true"
    return headers


# ---------------------------------------------------------------------------
# Response envelope (COMPANION_API_CONVENTIONS.md §4)
# ---------------------------------------------------------------------------
def success(data, status_code=200, meta=None):
    """Success envelope: {"data": ..., "meta"?: ...}."""
    body = {"data": _to_native(data)}
    if meta is not None:
        body["meta"] = _to_native(meta)
    return {
        "statusCode": status_code,
        "headers": cors_headers(),
        "body": json.dumps(body),
    }


def error(code, message, status_code, details=None):
    """Error envelope: {"error": {"code", "message", "details"?}}."""
    err = {"code": code, "message": message}
    if details is not None:
        err["details"] = _to_native(details)
    return {
        "statusCode": status_code,
        "headers": cors_headers(),
        "body": json.dumps({"error": err}),
    }


# Convenience wrappers for the standard status codes (§4).
def unauthorized(message="Missing or invalid authentication."):
    return error("unauthorized", message, 401)


def forbidden(message="You are not allowed to perform this action."):
    return error("forbidden", message, 403)


def not_found(message="Resource not found."):
    return error("not_found", message, 404)


def validation_error(message, fields=None):
    details = {"fields": fields} if fields else None
    return error("validation_error", message, 400, details)


def subscription_required(message="This feature requires a premium subscription."):
    return error("subscription_required", message, 402)


def limit_reached(message, details):
    return error("limit_reached", message, 402, details)


def conflict(message="Conflict."):
    return error("conflict", message, 409)


def internal_error(message="An unexpected error occurred."):
    # Never leak internals to the client (§4).
    return error("internal_error", message, 500)


# ---------------------------------------------------------------------------
# Request parsing
# ---------------------------------------------------------------------------
def get_route(event):
    """Return the normalized "METHOD /path" route key for both HTTP API v2 and v1.

    HTTP API v2 supplies `routeKey` (e.g. "POST /plans/{slug}/enroll"). Falls back to
    composing from method + path for direct invokes / REST v1.
    """
    route = event.get("routeKey")
    if route and route != "$default":
        return route
    method = (
        event.get("httpMethod")
        or event.get("requestContext", {}).get("http", {}).get("method", "")
    )
    path = event.get("path") or event.get("rawPath") or ""
    return f"{method} {path}".strip()


def get_method(event):
    rc_http = event.get("requestContext", {}).get("http", {})
    return event.get("httpMethod") or rc_http.get("method") or ""


def get_path_param(event, name):
    return (event.get("pathParameters") or {}).get(name)


def get_query_params(event):
    return event.get("queryStringParameters") or {}


def parse_body(event):
    """Parse the JSON body. Returns (parsed_dict, None) or (None, error_response)."""
    raw = event.get("body")
    if raw is None or raw == "":
        return {}, None
    if isinstance(raw, (dict, list)):
        return raw, None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None, validation_error("Request body must be valid JSON.")
    if not isinstance(parsed, dict):
        return None, validation_error("Request body must be a JSON object.")
    return parsed, None


# ---------------------------------------------------------------------------
# Auth (COMPANION_API_CONVENTIONS.md §2)
# ---------------------------------------------------------------------------
def get_user_id(event):
    """Resolve the caller's Cognito sub from the authorizer context.

    Supports the HTTP API v2 simple-response Lambda authorizer (context under
    `authorizer.lambda`), the older direct `authorizer.userId`, and the native JWT
    authorizer (`authorizer.jwt.claims.sub`). Never trusts body/query (§2).
    """
    authorizer = event.get("requestContext", {}).get("authorizer", {}) or {}
    lam = authorizer.get("lambda") or {}
    if lam.get("userId"):
        return lam["userId"]
    if authorizer.get("userId"):
        return authorizer["userId"]
    jwt_claims = (authorizer.get("jwt") or {}).get("claims") or {}
    if jwt_claims.get("sub"):
        return jwt_claims["sub"]
    claims = authorizer.get("claims") or {}
    if claims.get("sub"):
        return claims["sub"]
    return None
