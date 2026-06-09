"""
Personalized, non-duplicative verse selection for the Daily Verse feature.

This module is the shared core used by BOTH the `daily_verse` REST handler
(GET /daily-verse) and the `daily_verse_worker` scheduled worker. An identical
copy ships in each lambda dir (the two lambdas are packaged separately, so they
can't share a private import). Keep the two copies in sync.

What it does (spec §6.2):
  1. Builds per-user context from long-term memory (Neon `user_memories` via the
     shared `memory_retrieval`/`memory_store` modules) plus the user's recent
     `verse_history` (DynamoDB) as a do-NOT-repeat exclusion list.
  2. Asks the LLM (OpenAI, gpt-4o-mini by default) for ONE verse + a 1-2 sentence
     reflection in the user's translation, excluding recent references.
  3. Records what was served into the `verse_history` DynamoDB table with
     `context='daily_verse'` so future selections stay non-duplicative.

Degradation (hard requirement for the worker, spec §6.3 / §7):
  - If Neon is unavailable, the memory block / exclusion list are simply empty
    and selection still works (just less personalized).
  - If the LLM call fails, we fall back to a curated rotation of verses that
    avoids the exclusion list. Selection NEVER raises.

All shared-layer imports use BARE names (`import memory_store`) because they ship
in the `shared_dependencies` layer at /opt/python. They are import-guarded so the
module still loads (degraded) during local unit tests.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()

# --- shared-layer modules (bare names; guarded for local/degraded use) ----------
try:
    import memory_retrieval  # build_companion_context()
except Exception:  # pragma: no cover - only on degraded/local imports
    memory_retrieval = None

try:
    import memory_store  # fetch_active_memories(), etc.
except Exception:  # pragma: no cover
    memory_store = None

try:
    from secrets_helper import get_openai_api_key
except Exception:  # pragma: no cover
    def get_openai_api_key():
        return os.environ.get("OPENAI_API_KEY")

# Model used for verse selection. gpt-4o-mini keeps the per-send cost low and the
# output to ~1-2 SMS segments (spec §16.1 cost guardrail).
VERSE_MODEL = os.environ.get("VERSE_MODEL", "gpt-4o-mini")
DEFAULT_TRANSLATION = "NIV"
MAX_EXCLUSION_REFS = 25

_dynamodb = None


# ---------------------------------------------------------------------------
# OpenAI key + client
# ---------------------------------------------------------------------------
def ensure_openai_key() -> Optional[str]:
    """
    Make sure OPENAI_API_KEY is set in the environment from the secret.

    The worker must "set OPENAI_API_KEY from the secret at runtime"; the embeddings
    client (shared layer) reads the env var, so do this once per cold start.
    Returns the key (or None) and never raises.
    """
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    try:
        key = get_openai_api_key()
    except Exception as e:  # pragma: no cover - secrets failure
        logger.warning("Could not resolve OpenAI key: %s", str(e))
        key = None
    if key:
        os.environ["OPENAI_API_KEY"] = key
    return key


def _openai_client():
    """Return an OpenAI client or None (never raises)."""
    try:
        from openai import OpenAI
    except Exception as e:  # pragma: no cover
        logger.warning("openai SDK unavailable: %s", str(e))
        return None
    key = ensure_openai_key()
    try:
        return OpenAI(api_key=key) if key else OpenAI()
    except Exception as e:  # pragma: no cover
        logger.warning("Failed to init OpenAI client: %s", str(e))
        return None


# ---------------------------------------------------------------------------
# verse_history (DynamoDB) helpers
# ---------------------------------------------------------------------------
def _verse_history_table():
    """Return the verse_history Table resource, or None if not configured."""
    global _dynamodb
    name = os.environ.get("VERSE_HISTORY_TABLE")
    if not name:
        return None
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb.Table(name)


def recent_verse_references(user_id: str, limit: int = MAX_EXCLUSION_REFS) -> List[str]:
    """
    Best-effort do-not-repeat list: the user's most recent verse references.

    Reads `verse_history` (PK=userId, newest first). Returns [] on any failure or
    if the table isn't wired yet.
    """
    table = _verse_history_table()
    if not table or not user_id:
        return []
    try:
        resp = table.query(
            KeyConditionExpression="userId = :uid",
            ExpressionAttributeValues={":uid": user_id},
            ScanIndexForward=False,
            Limit=limit,
        )
        refs = []
        for item in resp.get("Items", []):
            ref = item.get("displayRef") or item.get("reference")
            if ref and ref not in refs:
                refs.append(ref)
        return refs
    except Exception as e:
        logger.info("verse_history query failed (degrading): %s", str(e))
        return []


def todays_daily_verse(user_id: str, local_date: str) -> Optional[Dict[str, Any]]:
    """
    Return today's already-sent daily verse for this user, if any.

    `local_date` is a YYYY-MM-DD string (the user's local date). We scan the most
    recent verse_history items and match the first `context='daily_verse'` item
    whose `sentAt` date (UTC) equals `local_date`. At one-per-day cadence the most
    recent daily_verse item is effectively "today's". Returns None on any failure.
    """
    table = _verse_history_table()
    if not table or not user_id:
        return None
    try:
        resp = table.query(
            KeyConditionExpression="userId = :uid",
            ExpressionAttributeValues={":uid": user_id},
            ScanIndexForward=False,
            Limit=10,
        )
        for item in resp.get("Items", []):
            if item.get("context") != "daily_verse":
                continue
            sent_at = item.get("sentAt", "")
            if sent_at[:10] == local_date:
                return item
            # Items are newest-first; once we pass today's date we can stop.
            return None
    except Exception as e:
        logger.info("todays_daily_verse lookup failed: %s", str(e))
    return None


def record_verse_history(
    user_id: str,
    verse: Dict[str, Any],
    phone_number: Optional[str] = None,
    context_kind: str = "daily_verse",
    channel: str = "sms",
    source_msg_id: Optional[str] = None,
) -> Optional[str]:
    """
    Persist a served verse to `verse_history` (spec §4.3). Returns the sentAt key
    (sort key) on success, or None on failure. Never raises.
    """
    table = _verse_history_table()
    if not table or not user_id:
        return None
    sent_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    item = {
        "userId": user_id,
        "sentAt": sent_at,
        "reference": verse.get("reference") or verse.get("displayRef"),
        "displayRef": verse.get("displayRef") or verse.get("reference"),
        "translation": verse.get("translation") or DEFAULT_TRANSLATION,
        "themes": verse.get("themes") or [],
        "context": context_kind,
        "channel": channel,
    }
    if phone_number:
        item["phoneNumber"] = phone_number
    if source_msg_id:
        item["sourceMsgId"] = source_msg_id
    # Carry the human-facing message so the web card can render exactly what was sent.
    if verse.get("reflection"):
        item["reflection"] = verse["reflection"]
    if verse.get("message"):
        item["message"] = verse["message"]
    try:
        table.put_item(Item={k: v for k, v in item.items() if v is not None})
        return sent_at
    except ClientError as e:
        logger.error("Failed to write verse_history for %s: %s", user_id, str(e))
        return None


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------
def build_context_block(user_id: str, first_name: Optional[str]) -> str:
    """
    The 'WHAT YOU REMEMBER ABOUT {name}' companion block (spec §5.1), reused for
    verse personalization. Returns '' if memory is unavailable. Never raises.
    """
    if not memory_retrieval or not user_id:
        return ""
    try:
        # current_message is empty here: we want salience-ordered structured recall,
        # not similarity to a live message.
        return memory_retrieval.build_companion_context(user_id, "", first_name) or ""
    except Exception as e:
        logger.info("companion context unavailable (degrading): %s", str(e))
        return ""


# ---------------------------------------------------------------------------
# Verse selection
# ---------------------------------------------------------------------------
# Curated fallback pool (used only when the LLM is unavailable). Broad, comforting
# references across themes so we can avoid the exclusion list and still send.
FALLBACK_VERSES: List[Dict[str, Any]] = [
    {"reference": "Isaiah 41:10", "displayRef": "Isaiah 41:10", "themes": ["fear", "comfort"],
     "reflection": "God promises to strengthen and uphold you — you are not alone today."},
    {"reference": "Philippians 4:6-7", "displayRef": "Philippians 4:6-7", "themes": ["anxiety", "peace"],
     "reflection": "Bring your worries to God in prayer, and his peace will guard your heart."},
    {"reference": "Psalm 23:1-3", "displayRef": "Psalm 23:1-3", "themes": ["rest", "provision"],
     "reflection": "The Lord is your shepherd; he leads you to rest and restores your soul."},
    {"reference": "Matthew 11:28", "displayRef": "Matthew 11:28", "themes": ["rest", "weariness"],
     "reflection": "Come to Jesus when you're weary — he offers real rest for your soul."},
    {"reference": "Joshua 1:9", "displayRef": "Joshua 1:9", "themes": ["courage", "presence"],
     "reflection": "Be strong and courageous; the Lord your God is with you wherever you go."},
    {"reference": "Lamentations 3:22-23", "displayRef": "Lamentations 3:22-23", "themes": ["hope", "mercy"],
     "reflection": "His mercies are new every morning — today holds fresh grace for you."},
    {"reference": "Romans 8:28", "displayRef": "Romans 8:28", "themes": ["hope", "purpose"],
     "reflection": "God is at work weaving even hard things toward good for those who love him."},
    {"reference": "Psalm 46:1", "displayRef": "Psalm 46:1", "themes": ["refuge", "strength"],
     "reflection": "God is your refuge and strength, a very present help in trouble."},
]


def _fallback_verse(translation: str, exclusion_refs: List[str], first_name: Optional[str]) -> Dict[str, Any]:
    excluded = set(exclusion_refs or [])
    pick = next((v for v in FALLBACK_VERSES if v["displayRef"] not in excluded), FALLBACK_VERSES[0])
    verse = dict(pick)
    verse["translation"] = translation
    verse["message"] = compose_message(first_name, verse["reflection"], verse["displayRef"], translation)
    verse["fallback"] = True
    return verse


def compose_message(
    first_name: Optional[str], reflection: str, display_ref: str, translation: str
) -> str:
    """Compose the human-facing daily-verse message (kept short ~1-2 SMS segments)."""
    greeting = f"Morning, {first_name}. " if first_name else "Good morning. "
    return f"{greeting}{reflection} — {display_ref} ({translation})".strip()


def _selection_prompt(
    first_name: Optional[str],
    translation: str,
    context_block: str,
    exclusion_refs: List[str],
) -> List[Dict[str, str]]:
    name = first_name or "this person"
    excl = ", ".join(exclusion_refs) if exclusion_refs else "(none yet)"
    system = (
        "You are Versiful, a warm Bible companion choosing ONE personalized verse for "
        "someone's morning. You know Scripture deeply and speak like a caring friend, "
        "never a preacher. Personalize to what this person is walking through. Keep it "
        "short enough for a text message (about 1-2 sentences of reflection)."
    )
    user = (
        f"Choose ONE Bible verse and write a 1-2 sentence reflection personalized to "
        f"{name}, quoting from the {translation} translation.\n\n"
        f"CONTEXT ABOUT {name} (use naturally; do not list it back):\n"
        f"{context_block or '(no specific context known yet — choose an encouraging verse)'}\n\n"
        f"Do NOT use any of these recently-sent references: {excl}\n\n"
        "Respond with STRICT JSON only, no prose, in this exact shape:\n"
        '{"reference": "Book Chapter:Verse", "displayRef": "Book Chapter:Verse", '
        '"translation": "' + translation + '", "themes": ["theme1", "theme2"], '
        '"reflection": "1-2 sentence personalized reflection (do NOT include the reference here)"}'
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _parse_verse_json(raw: str, translation: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    ref = (data.get("displayRef") or data.get("reference") or "").strip()
    reflection = (data.get("reflection") or "").strip()
    if not ref or not reflection:
        return None
    themes = data.get("themes") or []
    if not isinstance(themes, list):
        themes = []
    return {
        "reference": (data.get("reference") or ref).strip(),
        "displayRef": ref,
        "translation": (data.get("translation") or translation).strip() or translation,
        "themes": [str(t) for t in themes][:5],
        "reflection": reflection,
    }


def select_personalized_verse(
    user_id: Optional[str],
    bible_version: Optional[str] = None,
    first_name: Optional[str] = None,
    exclusion_refs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Select ONE personalized, non-duplicative verse for the user.

    Returns a dict: {reference, displayRef, translation, themes, reflection, message,
    fallback?}. NEVER raises — on any failure it returns a curated fallback verse.
    """
    translation = (bible_version or DEFAULT_TRANSLATION).strip() or DEFAULT_TRANSLATION
    if exclusion_refs is None:
        exclusion_refs = recent_verse_references(user_id) if user_id else []

    context_block = build_context_block(user_id, first_name) if user_id else ""

    client = _openai_client()
    if client is None:
        logger.info("LLM unavailable; using fallback verse for %s", user_id)
        return _fallback_verse(translation, exclusion_refs, first_name)

    messages = _selection_prompt(first_name, translation, context_block, exclusion_refs)
    try:
        resp = client.chat.completions.create(
            model=VERSE_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=300,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content
    except Exception as e:
        logger.warning("Verse LLM call failed (%s); using fallback: %s", VERSE_MODEL, str(e))
        return _fallback_verse(translation, exclusion_refs, first_name)

    verse = _parse_verse_json(raw, translation)
    if not verse:
        logger.warning("Could not parse verse JSON; using fallback. raw=%r", raw)
        return _fallback_verse(translation, exclusion_refs, first_name)

    # Guard against the model ignoring the exclusion list.
    if verse["displayRef"] in set(exclusion_refs or []):
        logger.info("Model returned an excluded ref (%s); using fallback", verse["displayRef"])
        return _fallback_verse(translation, exclusion_refs, first_name)

    verse["message"] = compose_message(
        first_name, verse["reflection"], verse["displayRef"], verse["translation"]
    )
    return verse
