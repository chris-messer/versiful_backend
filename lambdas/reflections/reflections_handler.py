"""
Companion Reflection Log REST API (Neon-backed).

Implements the reflection endpoints from COMPANION_SPEC.md §8 / §14 following
COMPANION_API_CONVENTIONS.md:

    GET    /reflections     list newest-first (paginated); ?q= vector search,
                            ?source=auto_summary|manual|reading_plan filter
    POST   /reflections     create (writes to Neon via memory_store; embedding
                            generated on write, NEVER fails the write if embedding
                            fails)
    DELETE /reflections/{id} delete (ownership-checked; single-store Neon op)

Reflections live ONLY in Neon (`reflections` table, snake_case columns, pgvector
`embedding`). Reflection log is a Premium feature (spec §16) so all endpoints are
subscription-gated (free → 402). Every Neon interaction degrades gracefully: if
Neon/psycopg is unavailable this returns a clean 503 (`service_unavailable`) and
NEVER a 500 crash (conventions §7).

IMPORTANT (recorded in the integration spec): this lambda must mount the
`langchain_layer` (for psycopg) in addition to `shared_dependencies` to actually
reach Neon — until then `neon_client.is_available()` is False and these endpoints
correctly return 503.
"""
import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

import api_common as api
import reflections_store as store

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
PROJECT_NAME = os.environ.get("PROJECT_NAME", "versiful")
USERS_TABLE = os.environ.get("USERS_TABLE", f"{ENVIRONMENT}-{PROJECT_NAME}-users")

_dynamodb = boto3.resource("dynamodb")
users_table = _dynamodb.Table(USERS_TABLE)

MAX_CONTENT_LEN = 5000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_user(user_id: str):
    try:
        resp = users_table.get_item(Key={"userId": user_id})
        return resp.get("Item")
    except ClientError as e:
        logger.error("Error loading user %s: %s", user_id, str(e))
        return None


def _require_premium(user_item):
    """Return a 402 response if the caller is not premium, else None."""
    if api.is_premium(user_item):
        return None
    return api.subscription_required(
        "The reflection journal is a premium feature. Upgrade to save and search reflections."
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
def handle_list(event, user_id, user_item):
    gate = _require_premium(user_item)
    if gate:
        return gate

    if not store.available():
        return api.service_unavailable("The journal is temporarily unavailable. Please try again shortly.")

    query = api.get_query_params(event)
    source = (query.get("source") or "").strip().lower() or None
    if source and source not in store.VALID_SOURCES:
        return api.validation_error(
            f"`source` must be one of {sorted(store.VALID_SOURCES)}.", ["source"]
        )
    limit = api.clamp_limit(query)
    q = (query.get("q") or "").strip()

    if q:
        # Vector similarity search (conventions §5). Embed the query best-effort.
        embedding = None
        try:
            import embeddings
            embedding = embeddings.embed_text(q)
        except Exception as e:
            logger.info("Query embedding unavailable, falling back to recency: %s", str(e))
        result = store.search_reflections(user_id, embedding, source=source, limit=limit)
    else:
        cursor = api.decode_cursor(query.get("cursor"))
        result = store.list_reflections(user_id, source=source, limit=limit, cursor=cursor)

    if not result.get("available"):
        return api.service_unavailable()

    next_cursor = api.encode_cursor(result.get("nextCursor"))
    return api.collection(result.get("items", []), next_cursor)


def handle_create(event, user_id, user_item):
    gate = _require_premium(user_item)
    if gate:
        return gate

    body, err = api.parse_body(event)
    if err:
        return err

    content = body.get("content")
    if not content or not str(content).strip():
        return api.validation_error("`content` is required.", ["content"])
    content = str(content).strip()
    if len(content) > MAX_CONTENT_LEN:
        return api.validation_error("`content` is too long.", ["content"])

    source = str(body.get("source") or "manual").strip().lower()
    if source not in store.VALID_SOURCES:
        return api.validation_error(
            f"`source` must be one of {sorted(store.VALID_SOURCES)}.", ["source"]
        )

    verse_reference = body.get("verseReference")
    if verse_reference is not None:
        verse_reference = str(verse_reference).strip() or None
    mood = body.get("mood")
    if mood is not None:
        mood = str(mood).strip() or None
    session_id = body.get("sessionId")
    if session_id is not None:
        session_id = str(session_id).strip() or None

    if not store.available():
        return api.service_unavailable("Couldn't save your reflection just now. Please try again shortly.")

    try:
        import memory_store  # shared_dependencies layer (write + embedding-on-write)
        reflection_id = memory_store.insert_reflection(
            user_id=user_id,
            content=content,
            source=source,
            session_id=session_id,
            verse_reference=verse_reference,
            mood=mood,
        )
    except Exception as e:
        logger.error("insert_reflection error: %s", str(e))
        reflection_id = None

    if not reflection_id:
        # Neon write failed despite being "available" -> treat as transient outage.
        return api.service_unavailable("Couldn't save your reflection just now. Please try again shortly.")

    # Return the created resource (fetch back for the DB-assigned createdAt).
    fetched = store.get_reflection(user_id, reflection_id)
    resource = fetched.get("item") if fetched.get("available") else None
    if not resource:
        resource = {
            "id": reflection_id,
            "content": content,
            "source": source,
            "verseReference": verse_reference,
            "mood": mood,
            "sessionId": session_id,
            "createdAt": _now(),
        }
    return api.created(resource)


def handle_delete(event, user_id, user_item, reflection_id):
    gate = _require_premium(user_item)
    if gate:
        return gate

    if not store.available():
        return api.service_unavailable()

    result = store.delete_reflection(user_id, reflection_id)
    if not result.get("available"):
        return api.service_unavailable()
    if not result.get("deleted"):
        return api.not_found("Reflection not found.")
    return api.deleted(reflection_id)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
def handler(event, context):
    method = api.get_method(event)
    route_key = api.get_route_key(event)
    logger.info("reflections invoked: %s", route_key)

    if method == "OPTIONS":
        return api.options_response("GET,POST,DELETE,OPTIONS")

    user_id = api.get_user_id(event)
    if not user_id:
        return api.unauthorized()

    reflection_id = api.get_path_params(event).get("id")

    try:
        user_item = _load_user(user_id)

        if route_key == "GET /reflections" or (method == "GET" and not reflection_id):
            return handle_list(event, user_id, user_item)
        if route_key == "POST /reflections" or (method == "POST" and not reflection_id):
            return handle_create(event, user_id, user_item)
        if method == "DELETE":
            if not reflection_id:
                return api.validation_error("Reflection id is required.", ["id"])
            return handle_delete(event, user_id, user_item, reflection_id)

        return api.not_found("Unknown route.")
    except Exception as e:
        logger.error("Unhandled error in reflections handler: %s", str(e), exc_info=True)
        return api.internal_error()
