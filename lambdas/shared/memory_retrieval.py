"""
Companion-context assembly (the `retrieve_memory` graph node).

Builds the compact "WHAT YOU REMEMBER ABOUT {name}" block that gets prepended to the
system prompt before generating (spec §5.1). Strategy is **structured-primary,
vector-secondary**: top active memories by salience/recency, optionally reranked by
similarity to the current message.

Phase-1 scope: long-term memory comes from Neon `user_memories`. Supporting DynamoDB
context (active prayers, reading-plan day, verse_history do-not-repeat list) is read
here too, but only if those tables exist yet — they are added in later phases, so the
reads are guarded and silently contribute nothing until then.

Everything degrades to an empty block if Neon (or anything else) is unavailable.
"""
import logging
import os
from typing import Optional

import memory_store

logger = logging.getLogger()

MAX_MEMORIES = 6
MAX_VERSE_HISTORY = 20


def build_companion_context(
    user_id: Optional[str],
    current_message: str,
    first_name: Optional[str] = None,
) -> str:
    """
    Return the companion-context block (string), or "" if there's nothing to add or
    Neon is unavailable. Never raises.
    """
    if not user_id:
        return ""

    try:
        candidates = memory_store.fetch_active_memories(user_id, limit=MAX_MEMORIES * 2)
        memories = memory_store.rerank_by_similarity(
            user_id, current_message, candidates, top_k=MAX_MEMORIES
        )
    except Exception as e:  # defensive; memory_store already guards internally
        logger.warning("Memory retrieval failed, degrading: %s", str(e))
        memories = []

    verse_refs = _recent_verse_refs(user_id)

    if not memories and not verse_refs:
        return ""

    name = first_name or "this person"
    lines = [f"WHAT YOU REMEMBER ABOUT {name} (use naturally; do not recite as a list):"]

    for m in memories:
        bullet = f"- [{m.get('kind', 'note')}] {m.get('summary', '').strip()}"
        people = m.get("people") or []
        if people:
            bullet += f" (people: {', '.join(people)})"
        if m.get("event_date"):
            bullet += f" (date: {m['event_date']})"
        lines.append(bullet)

    if verse_refs:
        lines.append("")
        lines.append("RECENTLY SHARED VERSES (do NOT repeat unless they ask):")
        lines.append(", ".join(verse_refs))

    return "\n".join(lines)


def _recent_verse_refs(user_id: str):
    """
    Best-effort do-not-repeat list from the DynamoDB `verse_history` table.

    Returns [] if the table doesn't exist yet (added in a later phase) or on any error.
    """
    table_name = os.environ.get("VERSE_HISTORY_TABLE")
    if not table_name:
        # Table/env not wired yet (Phase 2+). Silently contribute nothing.
        return []
    try:
        import boto3
        from botocore.exceptions import ClientError

        table = boto3.resource("dynamodb").Table(table_name)
        resp = table.query(
            KeyConditionExpression="userId = :uid",
            ExpressionAttributeValues={":uid": user_id},
            ScanIndexForward=False,
            Limit=MAX_VERSE_HISTORY,
        )
        refs = []
        for item in resp.get("Items", []):
            ref = item.get("displayRef") or item.get("reference")
            if ref:
                refs.append(ref)
        return refs
    except Exception as e:  # ClientError (no table) or anything else
        logger.info("verse_history unavailable (ok pre-Phase-2): %s", str(e))
        return []
