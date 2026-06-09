"""
Embedding client for the companion memory system.

Uses OpenAI `text-embedding-3-small` (1536-dim) — the model the Neon schema's
`vector(1536)` columns expect (spec §4.1, §15.1a). The OpenAI key is the same
`gpt` secret the agent already uses.

Failure policy (spec §15.1a): embedding is best-effort. On any error this returns
None (single) or a list with None entries (batch); callers must store the row with a
NULL embedding and rely on a later backfill, never failing the write.
"""
import logging
from typing import List, Optional

logger = logging.getLogger()

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

try:
    from openai import OpenAI
    _OPENAI_AVAILABLE = True
except Exception as _e:  # pragma: no cover
    OpenAI = None
    _OPENAI_AVAILABLE = False
    logging.getLogger().warning("openai SDK unavailable for embeddings: %s", _e)

_client = None


def _get_client(api_key: Optional[str] = None):
    global _client
    if not _OPENAI_AVAILABLE:
        return None
    if _client is None:
        try:
            _client = OpenAI(api_key=api_key) if api_key else OpenAI()
        except Exception as e:
            logger.warning("Failed to init OpenAI embeddings client: %s", str(e))
            return None
    return _client


def embed_text(text: str, api_key: Optional[str] = None) -> Optional[List[float]]:
    """Embed a single string. Returns a 1536-dim list, or None on failure."""
    if not text or not text.strip():
        return None
    results = embed_texts([text], api_key=api_key)
    return results[0] if results else None


def embed_texts(
    texts: List[str], api_key: Optional[str] = None
) -> Optional[List[Optional[List[float]]]]:
    """
    Embed a batch of strings in one API call.

    Returns a list aligned with `texts` (each item a vector or None), or None if the
    whole call fails. Never raises.
    """
    if not texts:
        return []
    client = _get_client(api_key)
    if client is None:
        return None
    try:
        resp = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=texts,
            dimensions=EMBEDDING_DIM,
        )
        # Preserve input order.
        ordered = sorted(resp.data, key=lambda d: d.index)
        return [list(d.embedding) for d in ordered]
    except Exception as e:
        logger.warning("Embedding call failed (%d texts): %s", len(texts), str(e))
        return None
