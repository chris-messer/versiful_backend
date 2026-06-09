"""
Neon data-access for the Reflection Log REST API.

WRITES reuse the shared `memory_store.insert_reflection` (embedding-on-write +
NULL-tolerance live there — we do not reinvent them). The recency-list, vector
search, and ownership-delete READ paths are not exposed by `memory_store`, so they
are issued here directly through the shared `neon_client` (which degrades
gracefully — every call returns None when Neon/psycopg is unavailable).

All functions return a small result dict carrying an explicit `available` flag so
the handler can map a Neon outage to a clean 503 (conventions §7) instead of a 500.
Wire shape is camelCase (conventions §1): id, content, source, verseReference,
mood, sessionId, createdAt.

Pagination (conventions §5): recency listing is keyset paginated on
(created_at, id) DESC with an opaque cursor. Vector search (?q=) returns a single
similarity-ranked page (nextCursor=null) — documented semantics.
"""
import logging
import re
from typing import Any, Dict, List, Optional

import neon_client

logger = logging.getLogger()

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                      r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

VALID_SOURCES = {"auto_summary", "manual", "reading_plan"}


def available() -> bool:
    """True if the Neon driver + URL are configured (does not open a connection)."""
    return neon_client.is_available()


def is_uuid(value: Any) -> bool:
    return isinstance(value, str) and bool(_UUID_RE.match(value))


def _row_to_dict(r) -> Dict[str, Any]:
    return {
        "id": str(r[0]),
        "content": r[1],
        "source": r[2],
        "verseReference": r[3],
        "mood": r[4],
        "sessionId": r[5],
        "createdAt": r[6].isoformat() if r[6] else None,
    }


def list_reflections(
    user_id: str,
    source: Optional[str] = None,
    limit: int = 25,
    cursor: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """
    Recency-ordered (newest first) keyset page. Returns
    {"available": bool, "items": [...], "nextCursor": [created_at, id] | None}.
    `cursor` is the decoded [created_at_iso, id] tuple from the previous page.
    """
    where = ["user_id = %s"]
    params: List[Any] = [user_id]
    if source:
        where.append("source = %s")
        params.append(source)
    if cursor and isinstance(cursor, (list, tuple)) and len(cursor) == 2:
        where.append("(created_at, id) < (%s::timestamptz, %s::uuid)")
        params.extend([cursor[0], cursor[1]])

    sql = f"""
        SELECT id, content, source, verse_reference, mood, session_id, created_at
          FROM reflections
         WHERE {' AND '.join(where)}
         ORDER BY created_at DESC, id DESC
         LIMIT %s
    """
    # Fetch one extra to detect a following page precisely.
    params.append(limit + 1)
    rows = neon_client.execute(sql, tuple(params), fetch="all")
    if rows is None:
        return {"available": False, "items": [], "nextCursor": None}

    items = [_row_to_dict(r) for r in rows]
    next_cursor = None
    if len(items) > limit:
        items = items[:limit]
        last = rows[limit - 1]
        next_cursor = [last[6].isoformat() if last[6] else None, str(last[0])]
    return {"available": True, "items": items, "nextCursor": next_cursor}


def search_reflections(
    user_id: str,
    query_embedding: Optional[List[float]],
    source: Optional[str] = None,
    limit: int = 25,
) -> Dict[str, Any]:
    """
    Vector-similarity ranked page (?q= path). Returns the same dict shape with
    nextCursor always None. Falls back to recency if no embedding was produced.
    """
    if not query_embedding:
        return list_reflections(user_id, source=source, limit=limit)

    from neon_client import vector_literal
    q_lit = vector_literal(query_embedding)
    if not q_lit:
        return list_reflections(user_id, source=source, limit=limit)

    where = ["user_id = %s", "embedding IS NOT NULL"]
    params: List[Any] = [user_id]
    if source:
        where.append("source = %s")
        params.append(source)

    sql = f"""
        SELECT id, content, source, verse_reference, mood, session_id, created_at
          FROM reflections
         WHERE {' AND '.join(where)}
         ORDER BY embedding <=> %s::vector
         LIMIT %s
    """
    params.extend([q_lit, limit])
    rows = neon_client.execute(sql, tuple(params), fetch="all")
    if rows is None:
        return {"available": False, "items": [], "nextCursor": None}
    return {"available": True, "items": [_row_to_dict(r) for r in rows], "nextCursor": None}


def delete_reflection(user_id: str, reflection_id: str) -> Dict[str, Any]:
    """
    Ownership-scoped delete (drops the pgvector row with it). Returns
    {"available": bool, "deleted": bool}. A malformed id is reported as not-deleted
    (the handler maps that to 404) rather than treated as a Neon outage.
    """
    if not is_uuid(reflection_id):
        return {"available": True, "deleted": False}
    rc = neon_client.execute(
        "DELETE FROM reflections WHERE user_id = %s AND id = %s",
        (user_id, reflection_id),
        fetch="none",
    )
    if rc is None:
        return {"available": False, "deleted": False}
    return {"available": True, "deleted": bool(rc)}


def get_reflection(user_id: str, reflection_id: str) -> Dict[str, Any]:
    """Fetch a single reflection by id (used to return a created resource)."""
    if not is_uuid(reflection_id):
        return {"available": True, "item": None}
    row = neon_client.execute(
        """
        SELECT id, content, source, verse_reference, mood, session_id, created_at
          FROM reflections
         WHERE user_id = %s AND id = %s
        """,
        (user_id, reflection_id),
        fetch="one",
    )
    if row is None:
        return {"available": False, "item": None}
    return {"available": True, "item": _row_to_dict(row) if row else None}
