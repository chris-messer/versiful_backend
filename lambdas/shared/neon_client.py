"""
Neon (Postgres + pgvector) connection layer for the companion memory system.

Design goals (spec §3, §5; build plan F9):
- Use the Neon POOLED endpoint (PgBouncer-backed) with `sslmode=require`.
- Reuse a module-level connection across warm Lambda invocations; reconnect on
  failure. The pooled endpoint handles server-side pooling, so a single short-lived
  connection per warm container is the right Lambda pattern.
- **Graceful degradation is a hard requirement.** Nothing in this module raises to
  callers. If Neon is unreachable (cold start, suspension, error) or the driver/secret
  is missing, every function returns a safe default (None / []) and logs. A short
  circuit-breaker avoids hammering a suspended/unreachable Neon on every turn.

pgvector note: embeddings are sent to Postgres as `'[f1,f2,...]'::vector` text
literals (see `vector_literal`), so we do not depend on the `pgvector` python adapter.
"""
import logging
import threading
import time
from typing import Any, List, Optional, Sequence

logger = logging.getLogger()

# psycopg may be absent if the langchain layer hasn't been rebuilt yet. Importing
# defensively means the chat lambda still answers (memory simply stays disabled).
try:
    import psycopg
    _PSYCOPG_AVAILABLE = True
except Exception as _e:  # pragma: no cover - import-time guard
    psycopg = None
    _PSYCOPG_AVAILABLE = False
    logging.getLogger().warning("psycopg not available; Neon memory disabled: %s", _e)

# This module is shared across lambdas via the shared_dependencies layer
# (/opt/python). The canonical Neon-URL resolver is `secrets_helper` (shipped in
# that same layer and used by the workers + REST lambdas). The chat lambda carries a
# self-contained mirror named `helpers`, so fall back to it when `secrets_helper`
# isn't on the path. Both expose an identical `get_neon_database_url()` contract.
try:
    from secrets_helper import get_neon_database_url
except ImportError:  # chat-lambda context: no shared layer mounting secrets_helper
    from helpers import get_neon_database_url

# How long to stop trying after a failed connect, to avoid per-turn latency hits
# while Neon is suspended/unreachable.
_FAILURE_COOLDOWN_SECONDS = 60
# Bound connection + query latency so a slow Neon never blocks the core chat reply.
_CONNECT_TIMEOUT_SECONDS = 3
_STATEMENT_TIMEOUT_MS = 4000

_conn = None
_conn_lock = threading.Lock()
_last_failure_at = 0.0


def _normalize_conninfo(url: str) -> str:
    """Ensure TLS is required on the pooled endpoint."""
    if not url:
        return url
    if "sslmode=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url


def is_available() -> bool:
    """True if the driver is importable and a Neon URL is configured."""
    return _PSYCOPG_AVAILABLE and bool(get_neon_database_url())


def _in_cooldown() -> bool:
    return (time.time() - _last_failure_at) < _FAILURE_COOLDOWN_SECONDS


def _mark_failure():
    global _last_failure_at, _conn
    _last_failure_at = time.time()
    if _conn is not None:
        try:
            _conn.close()
        except Exception:
            pass
        _conn = None


def get_connection():
    """
    Return a live psycopg connection, or None if Neon is unavailable.

    Reuses a module-level connection across warm invocations; transparently
    reconnects if the cached connection has gone stale. Never raises.
    """
    global _conn
    if not _PSYCOPG_AVAILABLE:
        return None
    if _in_cooldown():
        return None

    url = get_neon_database_url()
    if not url:
        return None

    with _conn_lock:
        # Reuse a healthy connection.
        if _conn is not None:
            try:
                if not _conn.closed:
                    return _conn
            except Exception:
                pass
            _conn = None

        try:
            conn = psycopg.connect(
                _normalize_conninfo(url),
                connect_timeout=_CONNECT_TIMEOUT_SECONDS,
                autocommit=True,
                # PgBouncer transaction pooling is incompatible with server-side
                # prepared statements; disable them.
                prepare_threshold=None,
                options=f"-c statement_timeout={_STATEMENT_TIMEOUT_MS}",
            )
            _conn = conn
            logger.info("Neon connection established")
            return _conn
        except Exception as e:
            logger.warning("Neon connect failed (entering %ds cooldown): %s",
                           _FAILURE_COOLDOWN_SECONDS, str(e))
            _mark_failure()
            return None


def execute(
    query: str,
    params: Optional[Sequence[Any]] = None,
    fetch: str = "all",
) -> Optional[Any]:
    """
    Execute a statement with graceful degradation.

    Args:
        query: SQL with %s placeholders.
        params: parameter sequence.
        fetch: "all" -> list[tuple], "one" -> tuple|None, "none" -> rowcount(int).

    Returns:
        Result per `fetch`, or None on ANY failure (caller treats None as "Neon down").
    """
    conn = get_connection()
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            if fetch == "one":
                return cur.fetchone()
            if fetch == "none":
                return cur.rowcount
            return cur.fetchall()
    except Exception as e:
        logger.warning("Neon query failed: %s", str(e))
        # A broken connection should be dropped so the next turn reconnects.
        _mark_failure()
        return None


def vector_literal(embedding: Optional[List[float]]) -> Optional[str]:
    """
    Format an embedding as a pgvector text literal: '[f1,f2,...]'.

    Returns None if embedding is falsy, so callers can store NULL embeddings
    (embedding-failure policy, spec §15.1a).
    """
    if not embedding:
        return None
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"
