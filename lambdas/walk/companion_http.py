"""
Shared HTTP helpers for the companion REST lambdas (envelope, auth, pagination).

Implements the contract in docs/COMPANION_API_CONVENTIONS.md:
- success -> {"data": ..., "meta"?: ...}; error -> {"error": {code, message, details?}}
- camelCase on the wire; ISO-8601 UTC timestamps with trailing Z
- JWT resolved from the authorizer context only (never the body/query)
- cursor-based, opaque base64 pagination (limit default 25, max 100)

This module is duplicated per REST lambda dir on purpose: each lambda is zipped
from its own directory and only mounts the shared layers, so a per-feature copy of
this tiny helper keeps packaging self-contained (it cannot live in lambdas/shared
without being owned by the foundation layer).
"""
import base64
import json
import logging
import os
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEFAULT_LIMIT = 25
MAX_LIMIT = 100


def _decimal_to_number(obj):
    """DynamoDB returns Decimals; coerce to int/float for JSON serialization."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_number(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_number(i) for i in obj]
    return obj


def cors_headers() -> Dict[str, str]:
    origin = os.environ.get("CORS_ORIGIN", "http://localhost:5173")
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Credentials": "true",
    }


def get_user_id_from_event(event: Dict[str, Any]) -> Optional[str]:
    """Resolve the caller's Cognito sub from the authorizer context ONLY."""
    request_context = event.get("requestContext", {}) or {}
    authorizer = request_context.get("authorizer", {}) or {}
    if authorizer.get("userId"):
        return authorizer["userId"]
    claims = authorizer.get("claims", {}) or {}
    if claims.get("sub"):
        return claims["sub"]
    # HTTP API (v2) nests JWT claims under authorizer.jwt.claims
    jwt = authorizer.get("jwt", {}) or {}
    jwt_claims = jwt.get("claims", {}) or {}
    if jwt_claims.get("sub"):
        return jwt_claims["sub"]
    return None


def success(data: Any, status_code: int = 200, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    body: Dict[str, Any] = {"data": _decimal_to_number(data)}
    if meta is not None:
        body["meta"] = _decimal_to_number(meta)
    return {
        "statusCode": status_code,
        "headers": cors_headers(),
        "body": json.dumps(body),
    }


def error(code: str, message: str, status_code: int, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    err: Dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    return {
        "statusCode": status_code,
        "headers": cors_headers(),
        "body": json.dumps({"error": err}),
    }


# Common error shortcuts (stable codes per the conventions doc).
def unauthorized(message: str = "Missing or invalid authentication.") -> Dict[str, Any]:
    return error("unauthorized", message, 401)


def not_found(message: str = "Resource not found.") -> Dict[str, Any]:
    return error("not_found", message, 404)


def validation_error(message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return error("validation_error", message, 400, details)


def subscription_required(message: str = "This feature requires a premium subscription.") -> Dict[str, Any]:
    return error("subscription_required", message, 402)


def service_unavailable(message: str = "This service is temporarily unavailable.") -> Dict[str, Any]:
    return error("service_unavailable", message, 503)


def internal_error(message: str = "An unexpected error occurred.") -> Dict[str, Any]:
    return error("internal_error", message, 500)


def parse_limit(event: Dict[str, Any]) -> int:
    """Clamp the `limit` query param to [1, MAX_LIMIT], defaulting to DEFAULT_LIMIT."""
    params = event.get("queryStringParameters") or {}
    raw = params.get("limit")
    if raw is None:
        return DEFAULT_LIMIT
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return max(1, min(MAX_LIMIT, n))


def get_query_param(event: Dict[str, Any], name: str) -> Optional[str]:
    params = event.get("queryStringParameters") or {}
    return params.get(name)


def encode_cursor(payload: Dict[str, Any]) -> Optional[str]:
    """Opaque, forward-only base64 cursor. Returns None for an empty payload."""
    if not payload:
        return None
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: Optional[str]) -> Dict[str, Any]:
    """Decode an opaque cursor. Returns {} for a missing/garbage cursor."""
    if not cursor:
        return {}
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        out = json.loads(raw.decode("utf-8"))
        return out if isinstance(out, dict) else {}
    except Exception:
        logger.info("Ignoring undecodable cursor")
        return {}


def paginate_offset(items: list, event: Dict[str, Any]) -> Tuple[list, Dict[str, Any]]:
    """
    Apply opaque offset-based pagination over an in-memory list.

    Used where per-user item counts are small (checkins, memories) and we sort in
    app rather than relying on a DynamoDB sort key. Returns (page_items, meta).
    """
    limit = parse_limit(event)
    cursor = decode_cursor(get_query_param(event, "cursor"))
    offset = int(cursor.get("offset", 0) or 0)
    if offset < 0:
        offset = 0
    page = items[offset:offset + limit]
    next_offset = offset + limit
    next_cursor = encode_cursor({"offset": next_offset}) if next_offset < len(items) else None
    return page, {"count": len(page), "nextCursor": next_cursor}


def route_key(event: Dict[str, Any]) -> str:
    """Best-effort route string for both API GW v2 (routeKey) and v1 (method+path)."""
    return event.get("routeKey") or f'{event.get("httpMethod", "")} {event.get("rawPath") or event.get("path", "")}'.strip()
