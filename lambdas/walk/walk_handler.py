"""
Companion "My Walk" (Journey View) REST API.

Routes (all JWT; spec §11, §11.2a, §14; conventions doc):
- GET    /walk/summary        journey overview aggregated across DynamoDB + Neon
- GET    /walk/memories       "things Versiful remembers" — Neon user_memories, paged
- DELETE /walk/memories       clear ALL of the caller's memories (GDPR right-to-erasure)
- DELETE /walk/memories/{id}  delete one memory, ownership-checked

Memory reads/deletes are single-store Neon operations via the shared `memory_store`
(the pgvector embedding is on the same row, so a row delete removes it — §11.2a). They
degrade gracefully: if Neon is unreachable we return 503 for the Neon-only memory
routes (conventions §7) rather than masking an outage as "not found". The DynamoDB
parts of /walk/summary always succeed regardless of Neon.

Deletes are intentionally allowed for ANY authenticated caller (not premium-gated):
erasing your own data is a privacy right, not a paid feature. /walk/summary is
premium-gated and degrades to a teaser for free users (spec §16).
"""
import logging
import os
from typing import Any, Dict

import boto3

import companion_http as http
import walk_aggregator

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
PROJECT_NAME = os.environ.get("PROJECT_NAME", "versiful")
USERS_TABLE = os.environ.get("USERS_TABLE", f"{ENVIRONMENT}-{PROJECT_NAME}-users")

_dynamodb = boto3.resource("dynamodb")


def _is_premium(user_id: str) -> bool:
    """Determine entitlement from the users item (isSubscribed / plan), spec §16/§3."""
    try:
        resp = _dynamodb.Table(USERS_TABLE).get_item(Key={"userId": user_id})
        item = resp.get("Item") or {}
        if item.get("isSubscribed"):
            return True
        plan = (item.get("plan") or "").lower()
        return plan not in ("", "free")
    except Exception as e:
        logger.warning("Could not read entitlement for %s (treating as free): %s", user_id, str(e))
        return False


def _neon_available() -> bool:
    try:
        import neon_client
        return neon_client.is_available()
    except Exception as e:
        logger.info("neon_client unavailable: %s", str(e))
        return False


# ---------------------------------------------------------------------------
# GET /walk/summary
# ---------------------------------------------------------------------------
def handle_summary(event: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    try:
        summary = walk_aggregator.build_summary(user_id, is_premium=_is_premium(user_id))
        return http.success(summary)
    except Exception as e:
        logger.error("Failed to build walk summary for %s: %s", user_id, str(e), exc_info=True)
        return http.internal_error("Could not build your walk summary.")


# ---------------------------------------------------------------------------
# GET /walk/memories
# ---------------------------------------------------------------------------
def handle_list_memories(event: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    if not _neon_available():
        return http.service_unavailable("Memory storage is temporarily unavailable.")
    try:
        import memory_store
        memories = memory_store.list_memories(user_id) or []
    except Exception as e:
        logger.error("Failed to list memories for %s: %s", user_id, str(e))
        return http.service_unavailable("Memory storage is temporarily unavailable.")

    items = [_memory_to_public(m) for m in memories]
    page, meta = http.paginate_offset(items, event)
    return http.success({"items": page}, meta=meta)


def _memory_to_public(m: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": m.get("id"),
        "kind": m.get("kind"),
        "summary": m.get("summary"),
        "detail": m.get("detail"),
        "people": m.get("people") or [],
        "eventDate": m.get("event_date"),
        "status": m.get("status"),
        "createdAt": m.get("created_at"),
        "lastReferencedAt": m.get("last_referenced_at"),
    }


# ---------------------------------------------------------------------------
# DELETE /walk/memories/{id}
# ---------------------------------------------------------------------------
def handle_delete_memory(event: Dict[str, Any], user_id: str, memory_id: str) -> Dict[str, Any]:
    if not memory_id:
        return http.validation_error("A memory id is required.")
    if not _neon_available():
        return http.service_unavailable("Memory storage is temporarily unavailable.")
    try:
        import memory_store
        deleted = memory_store.delete_memory(user_id, memory_id)
    except Exception as e:
        logger.error("Failed to delete memory %s for %s: %s", memory_id, user_id, str(e))
        return http.service_unavailable("Memory storage is temporarily unavailable.")

    if not deleted:
        # Either it never existed or it belongs to someone else -> 404 (don't reveal).
        return http.not_found("Memory not found.")
    logger.info("Deleted memory %s for user %s", memory_id, user_id)
    return http.success({"deleted": True, "id": memory_id})


# ---------------------------------------------------------------------------
# DELETE /walk/memories  (clear all)
# ---------------------------------------------------------------------------
def handle_clear_memories(event: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    if not _neon_available():
        return http.service_unavailable("Memory storage is temporarily unavailable.")
    try:
        import memory_store
        count = memory_store.delete_all_memories(user_id)
    except Exception as e:
        logger.error("Failed to clear memories for %s: %s", user_id, str(e))
        return http.service_unavailable("Memory storage is temporarily unavailable.")

    if count is None:
        return http.service_unavailable("Memory storage is temporarily unavailable.")
    logger.info("Cleared %s memories for user %s (right-to-erasure)", count, user_id)
    return http.success({"deleted": True, "count": int(count)})


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------
def _path(event: Dict[str, Any]) -> str:
    return event.get("rawPath") or event.get("path") or ""


def _method(event: Dict[str, Any]) -> str:
    return (
        event.get("httpMethod")
        or event.get("requestContext", {}).get("http", {}).get("method")
        or ""
    ).upper()


def _memory_id_from_event(event: Dict[str, Any]) -> str:
    params = event.get("pathParameters") or {}
    if params.get("id"):
        return params["id"]
    # Fallback: parse the trailing path segment after /walk/memories/
    path = _path(event)
    marker = "/walk/memories/"
    if marker in path:
        return path.split(marker, 1)[1].split("/")[0]
    return ""


def handler(event, context):
    method = _method(event)
    if method == "OPTIONS":
        return {"statusCode": 200, "headers": http.cors_headers(), "body": ""}

    user_id = http.get_user_id_from_event(event)
    if not user_id:
        return http.unauthorized()

    path = _path(event)
    logger.info("walk request: %s %s (user=%s)", method, path, user_id)

    try:
        if method == "GET" and path.endswith("/walk/summary"):
            return handle_summary(event, user_id)
        if method == "GET" and path.endswith("/walk/memories"):
            return handle_list_memories(event, user_id)
        if method == "DELETE" and path.endswith("/walk/memories"):
            return handle_clear_memories(event, user_id)
        if method == "DELETE" and "/walk/memories/" in path:
            return handle_delete_memory(event, user_id, _memory_id_from_event(event))
        return http.not_found("Unknown route.")
    except Exception as e:
        logger.error("Unhandled error in walk handler: %s", str(e), exc_info=True)
        return http.internal_error()
