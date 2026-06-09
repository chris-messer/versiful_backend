"""
Shared REST helpers for companion feature lambdas (envelope, auth, gating,
pagination, event parsing) — implements docs/COMPANION_API_CONVENTIONS.md.

This module is intentionally self-contained (stdlib only) so it can be vendored
into each per-feature lambda dir (prayers/, reflections/) which zip separately and
do NOT share a layer for application code. Keep the prayers/ and reflections/
copies identical.

It deliberately does NOT construct any boto3 resources — each handler owns its
DynamoDB tables — so this stays trivially importable and unit-testable.
"""
import base64
import json
import logging
import os
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger()

# Pagination bounds (conventions §5).
DEFAULT_LIMIT = 25
MAX_LIMIT = 100

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------------------------------------------------------------------------
# JSON / Decimal
# ---------------------------------------------------------------------------
def _decimal_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def to_native(obj: Any) -> Any:
    """Recursively convert DynamoDB Decimals to int/float for JSON output."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: to_native(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_native(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
def cors_headers(methods: str = "GET,POST,PUT,DELETE,OPTIONS") -> Dict[str, str]:
    """Standard CORS headers (mirrors web_handler.cors_headers; conventions §1)."""
    origin = os.environ.get("CORS_ORIGIN", "http://localhost:5173")
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": methods,
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Credentials": "true",
    }


# ---------------------------------------------------------------------------
# Event parsing (HTTP API v2 with REQUEST authorizer + simple responses,
# falling back to v1.0 shapes so the handlers are payload-format agnostic)
# ---------------------------------------------------------------------------
def get_route_key(event: Dict[str, Any]) -> str:
    """Return e.g. "GET /prayers". Prefer v2 routeKey, else reconstruct."""
    rk = event.get("routeKey")
    if rk:
        return rk
    return f"{get_method(event)} {get_path(event)}"


def get_method(event: Dict[str, Any]) -> str:
    http = (event.get("requestContext") or {}).get("http") or {}
    return http.get("method") or event.get("httpMethod") or ""


def get_path(event: Dict[str, Any]) -> str:
    http = (event.get("requestContext") or {}).get("http") or {}
    return http.get("path") or event.get("rawPath") or event.get("path") or ""


def get_path_params(event: Dict[str, Any]) -> Dict[str, str]:
    return event.get("pathParameters") or {}


def get_query_params(event: Dict[str, Any]) -> Dict[str, str]:
    return event.get("queryStringParameters") or {}


def get_user_id(event: Dict[str, Any]) -> Optional[str]:
    """
    Resolve the caller's Cognito sub from the authorizer context — NEVER from the
    body/query (conventions §2).

    Our authorizer is a REQUEST authorizer with payload format 2.0 and
    enable_simple_responses=true returning context {"userId": sub}, so API Gateway
    exposes it at requestContext.authorizer.lambda.userId. We also accept the v1
    (requestContext.authorizer.userId) and native-JWT (jwt.claims.sub) shapes.
    """
    authz = (event.get("requestContext") or {}).get("authorizer") or {}
    lam = authz.get("lambda")
    if isinstance(lam, dict) and lam.get("userId"):
        return lam["userId"]
    if authz.get("userId"):
        return authz["userId"]
    claims = (authz.get("jwt") or {}).get("claims") or authz.get("claims") or {}
    if claims.get("sub"):
        return claims["sub"]
    return None


def parse_body(event: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Parse a JSON object body. Returns (data, error_response). On bad JSON or a
    non-object body, returns (None, <400 error response>).
    """
    raw = event.get("body")
    if raw is None or raw == "":
        return {}, None
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw).decode("utf-8")
        except Exception:
            return None, error("validation_error", "Malformed request body.", 400)
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None, error("validation_error", "Request body must be valid JSON.", 400)
    if not isinstance(parsed, dict):
        return None, error("validation_error", "Request body must be a JSON object.", 400)
    return parsed, None


# ---------------------------------------------------------------------------
# Responses (envelope, conventions §4)
# ---------------------------------------------------------------------------
def _response(status: int, body: Dict[str, Any], methods: str = "GET,POST,PUT,DELETE,OPTIONS") -> Dict[str, Any]:
    return {
        "statusCode": status,
        "headers": cors_headers(methods),
        "body": json.dumps(to_native(body), default=_decimal_default),
    }


def ok(data: Any, meta: Optional[Dict[str, Any]] = None, status: int = 200) -> Dict[str, Any]:
    body: Dict[str, Any] = {"data": data}
    if meta is not None:
        body["meta"] = meta
    return _response(status, body)


def created(data: Any) -> Dict[str, Any]:
    return _response(201, {"data": data})


def collection(items: List[Any], next_cursor: Optional[str]) -> Dict[str, Any]:
    return ok({"items": items}, meta={"count": len(items), "nextCursor": next_cursor})


def deleted(resource_id: str) -> Dict[str, Any]:
    return ok({"deleted": True, "id": resource_id})


def error(code: str, message: str, status: int, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    err: Dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    return _response(status, {"error": err})


def unauthorized() -> Dict[str, Any]:
    return error("unauthorized", "Missing or invalid authentication.", 401)


def not_found(message: str = "Resource not found.") -> Dict[str, Any]:
    # Ownership failures also return 404 (conventions §4: don't reveal existence).
    return error("not_found", message, 404)


def validation_error(message: str, fields: Optional[List[str]] = None) -> Dict[str, Any]:
    details = {"fields": fields} if fields else None
    return error("validation_error", message, 400, details)


def subscription_required(message: str = "This feature requires a premium subscription.") -> Dict[str, Any]:
    return error("subscription_required", message, 402)


def limit_reached(message: str, limit: int, current: int) -> Dict[str, Any]:
    return error("limit_reached", message, 402, {"limit": limit, "current": current})


def service_unavailable(message: str = "This feature is temporarily unavailable. Please try again shortly.") -> Dict[str, Any]:
    return error("service_unavailable", message, 503)


def internal_error() -> Dict[str, Any]:
    # Never leak internals (conventions §4).
    return error("internal_error", "An unexpected error occurred.", 500)


def options_response(methods: str = "GET,POST,PUT,DELETE,OPTIONS") -> Dict[str, Any]:
    return {"statusCode": 200, "headers": cors_headers(methods), "body": ""}


# ---------------------------------------------------------------------------
# Subscription gating (conventions §3) — pure helpers over the users item
# ---------------------------------------------------------------------------
def is_premium(user_item: Optional[Dict[str, Any]]) -> bool:
    """A user is premium if isSubscribed is true or plan is a paid tier."""
    if not user_item:
        return False
    if user_item.get("isSubscribed") is True:
        return True
    plan = (user_item.get("plan") or "free")
    return str(plan).lower() not in ("free", "", "none")


# ---------------------------------------------------------------------------
# Pagination cursors (opaque base64, conventions §5)
# ---------------------------------------------------------------------------
def clamp_limit(query: Dict[str, str]) -> int:
    raw = (query or {}).get("limit")
    if raw is None:
        return DEFAULT_LIMIT
    try:
        n = int(raw)
    except (ValueError, TypeError):
        return DEFAULT_LIMIT
    return max(1, min(MAX_LIMIT, n))


def encode_cursor(value: Any) -> Optional[str]:
    """Base64-encode an arbitrary JSON-serializable cursor value."""
    if value is None:
        return None
    raw = json.dumps(value, default=_decimal_default, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: Optional[str]) -> Optional[Any]:
    """Decode an opaque cursor back to its value, or None if absent/invalid."""
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        return json.loads(raw)
    except Exception:
        logger.info("Ignoring malformed pagination cursor")
        return None


# ---------------------------------------------------------------------------
# Field validation/coercion helpers (conventions §6)
# ---------------------------------------------------------------------------
def is_iso_date(value: Any) -> bool:
    return isinstance(value, str) and bool(ISO_DATE_RE.match(value))


def coerce_str_list(value: Any) -> List[str]:
    """Normalize a 'people'-style list: drop empties, trim, dedupe (case-insensitive)."""
    if not value:
        return []
    if not isinstance(value, list):
        return []
    seen, out = set(), []
    for item in value:
        if item is None:
            continue
        s = str(item).strip()
        key = s.lower()
        if s and key not in seen:
            seen.add(key)
            out.append(s)
    return out
