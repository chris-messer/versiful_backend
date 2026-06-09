"""
Neon data-access for the companion memory system: `user_memories` + `reflections`.

This module owns the WRITE rules (dedup / upsert / salience / embedding-failure) and
the READ rules (structured-primary + vector-secondary retrieval, on-demand recall)
described in spec §5 and finalized in the build plan (F9). All Neon access goes
through `neon_client`, so every function degrades gracefully (returns [] / None) when
Neon is unavailable — a Neon problem never breaks the core chat reply.

----------------------------------------------------------------------------------
DEDUP / UPSERT / SALIENCE RULES (the build plan flagged these as only "sketched")
----------------------------------------------------------------------------------
A newly-extracted memory is considered a DUPLICATE of an existing active memory of
the same `kind` when EITHER:
  * vector match:  cosine_distance(new, existing) <= COSINE_DISTANCE_DUP_THRESHOLD
                   (i.e. cosine similarity >= 0.88), computed in pgvector; OR
  * fuzzy match:   difflib ratio(new.summary, existing.summary) >= FUZZY_RATIO
                   (dependency-free; also the only path when embeddings are missing).

On a duplicate hit we UPDATE the existing row instead of inserting:
  * salience   = min(1.0, max(old_salience, extracted_salience) + SALIENCE_BUMP)
  * people     = union(old, new)
  * event_date = filled in if it was NULL and the new memory supplies one
  * status     = promoted to 'resolved' if the new memory says so
  * last_referenced_at / updated_at = now()
  (the existing embedding is kept; we don't re-embed on every mention)

On no match we INSERT a new row (embedding computed on write; NULL-tolerant).

SALIENCE: initial value comes from the extractor (clamped to [0,1]); defaults to 0.5.
Re-mentions bump it by SALIENCE_BUMP (capped at 1.0). Time-decay is intentionally NOT
applied on write; retrieval orders by salience with a recency tiebreak, and a future
nightly job can decay stale rows (documented, not required for v1).

EMBEDDING-FAILURE POLICY (spec §15.1a): if embedding fails, the row is still written
with a NULL embedding (usable immediately for structured retrieval) and can be
backfilled later via `backfill_missing_embeddings()`. Writes never fail on embeddings.
"""
import json
import logging
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

import neon_client
from neon_client import vector_literal
from embeddings import embed_text

logger = logging.getLogger()

# --- Tunable rules (documented above) ---
COSINE_DISTANCE_DUP_THRESHOLD = 0.12   # cosine similarity >= 0.88
FUZZY_RATIO = 0.85
SALIENCE_BUMP = 0.10
SALIENCE_DEFAULT = 0.5

VALID_KINDS = {
    "life_event", "struggle", "relationship",
    "preference", "spiritual_state", "goal",
}
VALID_STATUSES = {"active", "resolved", "archived"}


def _clamp_salience(value: Any) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return SALIENCE_DEFAULT
    return max(0.0, min(1.0, v))


def _norm_people(people: Optional[List[str]]) -> List[str]:
    if not people:
        return []
    seen, out = set(), []
    for p in people:
        if not p:
            continue
        key = str(p).strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(str(p).strip())
    return out


# ---------------------------------------------------------------------------
# Retrieval (read)
# ---------------------------------------------------------------------------
def fetch_active_memories(user_id: str, limit: int = 12) -> List[Dict[str, Any]]:
    """
    STRUCTURED-PRIMARY retrieval: top active memories by salience, recency tiebreak.

    Returns [] on Neon failure. `limit` is intentionally a bit larger than the final
    cap so the caller can vector-rerank the candidate set (spec §5.1).
    """
    if not user_id:
        return []
    rows = neon_client.execute(
        """
        SELECT id, kind, summary, detail, people, salience, status, event_date,
               last_referenced_at, created_at
          FROM user_memories
         WHERE user_id = %s AND status = 'active'
         ORDER BY salience DESC, last_referenced_at DESC NULLS LAST, created_at DESC
         LIMIT %s
        """,
        (user_id, limit),
        fetch="all",
    )
    if not rows:
        return []
    return [_memory_row_to_dict(r) for r in rows]


def rerank_by_similarity(
    user_id: str, query_text: str, candidates: List[Dict[str, Any]], top_k: int = 6
) -> List[Dict[str, Any]]:
    """
    VECTOR-SECONDARY rerank of already-fetched candidates.

    Blends structured salience with cosine similarity to the current message:
        score = 0.7 * salience + 0.3 * cosine_similarity
    If embeddings are unavailable (no key / Neon down), falls back to the structured
    order (first `top_k`). Never raises.
    """
    if not candidates:
        return []
    if len(candidates) <= top_k or not query_text:
        return candidates[:top_k]

    q_emb = embed_text(query_text)
    if not q_emb:
        return candidates[:top_k]
    q_lit = vector_literal(q_emb)

    ids = [c["id"] for c in candidates]
    rows = neon_client.execute(
        """
        SELECT id, 1 - (embedding <=> %s::vector) AS similarity
          FROM user_memories
         WHERE id = ANY(%s) AND embedding IS NOT NULL
        """,
        (q_lit, ids),
        fetch="all",
    )
    if not rows:
        return candidates[:top_k]

    sim_by_id = {str(r[0]): float(r[1]) for r in rows}
    for c in candidates:
        sim = sim_by_id.get(str(c["id"]), 0.0)
        c["_score"] = 0.7 * float(c.get("salience", 0.0)) + 0.3 * sim
    ranked = sorted(candidates, key=lambda c: c.get("_score", 0.0), reverse=True)
    return ranked[:top_k]


def recall(user_id: str, query_text: str, k: int = 5) -> Dict[str, List[Dict[str, Any]]]:
    """
    On-demand semantic recall over BOTH memories and reflections (the `recall` tool).

    Pure vector search. Returns {"memories": [...], "reflections": [...]} (possibly
    empty) and never raises.
    """
    out: Dict[str, List[Dict[str, Any]]] = {"memories": [], "reflections": []}
    if not user_id or not query_text:
        return out
    q_emb = embed_text(query_text)
    if not q_emb:
        return out
    q_lit = vector_literal(q_emb)

    mem_rows = neon_client.execute(
        """
        SELECT id, kind, summary, detail, people, salience, status, event_date,
               last_referenced_at, created_at
          FROM user_memories
         WHERE user_id = %s AND status <> 'archived' AND embedding IS NOT NULL
         ORDER BY embedding <=> %s::vector
         LIMIT %s
        """,
        (user_id, q_lit, k),
        fetch="all",
    )
    if mem_rows:
        out["memories"] = [_memory_row_to_dict(r) for r in mem_rows]

    ref_rows = neon_client.execute(
        """
        SELECT id, content, source, verse_reference, mood, created_at
          FROM reflections
         WHERE user_id = %s AND embedding IS NOT NULL
         ORDER BY embedding <=> %s::vector
         LIMIT %s
        """,
        (user_id, q_lit, k),
        fetch="all",
    )
    if ref_rows:
        out["reflections"] = [
            {
                "id": str(r[0]), "content": r[1], "source": r[2],
                "verse_reference": r[3], "mood": r[4],
                "created_at": r[5].isoformat() if r[5] else None,
            }
            for r in ref_rows
        ]
    return out


def list_memories(user_id: str) -> List[Dict[str, Any]]:
    """List all non-archived memories for a user (foundation for GET /walk/memories)."""
    if not user_id:
        return []
    rows = neon_client.execute(
        """
        SELECT id, kind, summary, detail, people, salience, status, event_date,
               last_referenced_at, created_at
          FROM user_memories
         WHERE user_id = %s AND status <> 'archived'
         ORDER BY created_at DESC
        """,
        (user_id,),
        fetch="all",
    )
    return [_memory_row_to_dict(r) for r in rows] if rows else []


def delete_memory(user_id: str, memory_id: str) -> bool:
    """Delete one memory (drops its pgvector row too). Returns True if a row was removed."""
    rc = neon_client.execute(
        "DELETE FROM user_memories WHERE user_id = %s AND id = %s",
        (user_id, memory_id),
        fetch="none",
    )
    return bool(rc)


def delete_all_memories(user_id: str) -> Optional[int]:
    """Clear all memories for a user (right-to-be-forgotten). Returns count or None."""
    return neon_client.execute(
        "DELETE FROM user_memories WHERE user_id = %s",
        (user_id,),
        fetch="none",
    )


# ---------------------------------------------------------------------------
# Write (extraction-time upsert)
# ---------------------------------------------------------------------------
def upsert_memory(
    user_id: str,
    kind: str,
    summary: str,
    detail: Optional[str] = None,
    people: Optional[List[str]] = None,
    event_date: Optional[str] = None,
    salience: Any = None,
    status: str = "active",
    source: Optional[str] = None,
    source_msg_id: Optional[str] = None,
) -> Optional[str]:
    """
    Insert a memory or merge into an existing duplicate (see module docstring).

    Returns the memory id (str) on success, or None on failure / invalid input.
    Never raises.
    """
    if not user_id or not summary or not summary.strip():
        return None
    if kind not in VALID_KINDS:
        logger.info("Dropping memory with invalid kind=%r", kind)
        return None
    if status not in VALID_STATUSES:
        status = "active"

    summary = summary.strip()
    people = _norm_people(people)
    sal = _clamp_salience(salience)

    embedding = embed_text(f"{summary}\n{detail}" if detail else summary)
    emb_lit = vector_literal(embedding)

    existing = _find_duplicate(user_id, kind, summary, emb_lit)
    if existing:
        return _merge_into_existing(existing, people, event_date, sal, status)

    new_id = neon_client.execute(
        """
        INSERT INTO user_memories
            (user_id, kind, summary, detail, people, embedding, salience,
             status, source, source_msg_id, event_date, last_referenced_at)
        VALUES
            (%s, %s, %s, %s, %s::jsonb, {emb}, %s, %s, %s, %s, %s, now())
        RETURNING id
        """.format(emb="%s::vector" if emb_lit else "NULL"),
        _insert_params(user_id, kind, summary, detail, people, emb_lit, sal,
                       status, source, source_msg_id, event_date),
        fetch="one",
    )
    if new_id:
        logger.info("Inserted memory %s (kind=%s) for %s", new_id[0], kind, user_id)
        return str(new_id[0])
    return None


def insert_reflection(
    user_id: str,
    content: str,
    source: str = "auto_summary",
    session_id: Optional[str] = None,
    verse_reference: Optional[str] = None,
    mood: Optional[str] = None,
) -> Optional[str]:
    """Insert a reflection (embedded on write; NULL-tolerant). Returns id or None."""
    if not user_id or not content or not content.strip():
        return None
    content = content.strip()
    emb_lit = vector_literal(embed_text(content))

    row = neon_client.execute(
        """
        INSERT INTO reflections
            (user_id, content, embedding, source, session_id, verse_reference, mood)
        VALUES
            (%s, %s, {emb}, %s, %s, %s, %s)
        RETURNING id
        """.format(emb="%s::vector" if emb_lit else "NULL"),
        ([user_id, content] + ([emb_lit] if emb_lit else [])
         + [source, session_id, verse_reference, mood]),
        fetch="one",
    )
    return str(row[0]) if row else None


def backfill_missing_embeddings(user_id: Optional[str] = None, limit: int = 100) -> int:
    """
    Compute embeddings for rows written with NULL embedding (embedding-failure retry).

    Returns the number of rows successfully backfilled. Safe to call repeatedly.
    """
    fixed = 0
    where = "embedding IS NULL"
    params: List[Any] = []
    if user_id:
        where += " AND user_id = %s"
        params.append(user_id)

    rows = neon_client.execute(
        f"SELECT id, summary, detail FROM user_memories WHERE {where} LIMIT %s",
        tuple(params + [limit]),
        fetch="all",
    )
    for r in (rows or []):
        mem_id, summary, detail = r[0], r[1], r[2]
        emb_lit = vector_literal(embed_text(f"{summary}\n{detail}" if detail else summary))
        if not emb_lit:
            continue
        rc = neon_client.execute(
            "UPDATE user_memories SET embedding = %s::vector, updated_at = now() WHERE id = %s",
            (emb_lit, mem_id),
            fetch="none",
        )
        if rc:
            fixed += 1
    return fixed


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------
def _insert_params(user_id, kind, summary, detail, people, emb_lit, sal,
                   status, source, source_msg_id, event_date):
    base = [user_id, kind, summary, detail, json.dumps(people)]
    if emb_lit:
        base.append(emb_lit)
    base += [sal, status, source, source_msg_id, event_date or None]
    return base


def _find_duplicate(
    user_id: str, kind: str, summary: str, emb_lit: Optional[str]
) -> Optional[Dict[str, Any]]:
    """Return the best-matching existing memory dict, or None."""
    # 1) Vector nearest-neighbor within same user+kind.
    if emb_lit:
        vrow = neon_client.execute(
            """
            SELECT id, summary, people, salience, status, event_date,
                   (embedding <=> %s::vector) AS dist
              FROM user_memories
             WHERE user_id = %s AND kind = %s AND status <> 'archived'
                   AND embedding IS NOT NULL
             ORDER BY embedding <=> %s::vector
             LIMIT 1
            """,
            (emb_lit, user_id, kind, emb_lit),
            fetch="one",
        )
        if vrow and vrow[6] is not None and float(vrow[6]) <= COSINE_DISTANCE_DUP_THRESHOLD:
            return {
                "id": vrow[0], "summary": vrow[1], "people": vrow[2] or [],
                "salience": vrow[3], "status": vrow[4], "event_date": vrow[5],
            }

    # 2) Fuzzy summary match over the (small) active set for this user+kind.
    cands = neon_client.execute(
        """
        SELECT id, summary, people, salience, status, event_date
          FROM user_memories
         WHERE user_id = %s AND kind = %s AND status <> 'archived'
        """,
        (user_id, kind),
        fetch="all",
    )
    best, best_ratio = None, 0.0
    target = summary.lower()
    for r in (cands or []):
        ratio = SequenceMatcher(None, target, (r[1] or "").lower()).ratio()
        if ratio > best_ratio:
            best, best_ratio = r, ratio
    if best and best_ratio >= FUZZY_RATIO:
        return {
            "id": best[0], "summary": best[1], "people": best[2] or [],
            "salience": best[3], "status": best[4], "event_date": best[5],
        }
    return None


def _merge_into_existing(
    existing: Dict[str, Any],
    new_people: List[str],
    new_event_date: Optional[str],
    new_salience: float,
    new_status: str,
) -> Optional[str]:
    old_salience = float(existing.get("salience") or SALIENCE_DEFAULT)
    bumped = min(1.0, max(old_salience, new_salience) + SALIENCE_BUMP)
    merged_people = _norm_people(list(existing.get("people") or []) + (new_people or []))

    # Only promote to 'resolved'; never silently un-resolve.
    status = "resolved" if new_status == "resolved" else existing.get("status", "active")

    rc = neon_client.execute(
        """
        UPDATE user_memories
           SET salience = %s,
               people = %s::jsonb,
               status = %s,
               event_date = COALESCE(event_date, %s),
               last_referenced_at = now(),
               updated_at = now()
         WHERE id = %s
        """,
        (bumped, json.dumps(merged_people), status, new_event_date or None, existing["id"]),
        fetch="none",
    )
    if rc:
        logger.info("Merged duplicate into memory %s (salience %.2f -> %.2f)",
                    existing["id"], old_salience, bumped)
        return str(existing["id"])
    return None


def _memory_row_to_dict(r) -> Dict[str, Any]:
    return {
        "id": str(r[0]),
        "kind": r[1],
        "summary": r[2],
        "detail": r[3],
        "people": r[4] or [],
        "salience": float(r[5]) if r[5] is not None else None,
        "status": r[6],
        "event_date": r[7].isoformat() if r[7] else None,
        "last_referenced_at": r[8].isoformat() if r[8] else None,
        "created_at": r[9].isoformat() if r[9] else None,
    }
