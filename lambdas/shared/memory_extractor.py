"""
Memory extraction (the `extract` + `persist` graph nodes), spec §5.2 / §15.

After a turn, a cheap GPT-4o-mini call distills the exchange into structured JSON,
which is then upserted into Neon (`user_memories`, `reflections`) using the dedup /
salience rules in `memory_store`. Verses / prayers / check-in suggestions are part of
the contract too, but their DynamoDB destinations (`verse_history`, `prayers`,
`checkins`) arrive in later phases — those writes are guarded and no-op until the
tables exist. Memory + reflection persistence (Neon) is live in Phase 1.

============================ EXTRACTION JSON CONTRACT ============================
The model MUST return a single JSON object (no prose, no code fences):

{
  "memories": [
    {
      "kind": "life_event|struggle|relationship|preference|spiritual_state|goal",
      "summary": "concise factual statement about the user (<= 200 chars)",
      "detail": "optional extra context, or null",
      "people": ["dad", "wife Sarah"],          // [] if none
      "event_date": "YYYY-MM-DD" | null,         // only if a concrete date is implied
      "salience": 0.0-1.0,                        // how central/important to remember
      "status": "active" | "resolved"
    }
  ],
  "reflections": [
    { "content": "one-line takeaway", "verse_reference": "Isaiah 41:10" | null, "mood": null }
  ],
  "prayers": [
    { "title": "Mom's surgery", "body": null, "people": ["mom"],
      "event_date": "YYYY-MM-DD" | null, "cadence": "none|daily|weekly" }
  ],
  "verses": [
    { "display_ref": "Isaiah 41:10", "reference": null, "themes": ["fear","comfort"] }
  ],
  "suggest_checkin": {
      "time_sensitive": true|false,
      "event_date": "YYYY-MM-DD" | null,
      "context": "prayer_followup|event_followup|struggle_followup|plan_nudge|general"
  }
}

Rules the prompt enforces and the parser re-validates:
- Extract ONLY durable facts the user actually stated. Do NOT invent or infer beyond
  the text. Empty arrays are correct and expected for small talk.
- `summary` is about the USER (not the assistant), phrased so it is useful weeks later.
- `salience`: 0.8-1.0 = major life events (diagnosis, death, job loss, marriage),
  0.5-0.7 = recurring struggles / meaningful preferences, 0.2-0.4 = minor/incidental.
- Only set `suggest_checkin.time_sensitive=true` with a concrete `event_date`.
=================================================================================
"""
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import memory_store

logger = logging.getLogger()

EXTRACTION_MODEL = "gpt-4o-mini"
MAX_MEMORIES_PER_TURN = 5
MAX_REFLECTIONS_PER_TURN = 2

_VALID_CHECKIN_CONTEXTS = {
    "prayer_followup", "event_followup", "struggle_followup", "plan_nudge", "general",
}

_extraction_llm = None


def _get_llm():
    global _extraction_llm
    if _extraction_llm is None:
        from langchain_openai import ChatOpenAI
        _extraction_llm = ChatOpenAI(
            model=EXTRACTION_MODEL,
            temperature=0,
            max_tokens=700,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
    return _extraction_llm


_SYSTEM_PROMPT = (
    "You extract durable, long-term memory from a spiritual-guidance conversation. "
    "Return ONLY a single JSON object matching the schema the user describes. "
    "Extract only facts the user actually stated about themselves or their life; never "
    "invent details. Prefer empty arrays over speculation. Summaries describe the USER "
    "and must stay useful weeks later."
)

_USER_TEMPLATE = """Conversation turn to analyze.

Recent context:
{context}

User said: {user_message}
Assistant replied: {assistant_response}

Return a JSON object with keys: memories, reflections, prayers, verses, suggest_checkin.
Schema:
- memories[]: {{kind(one of life_event|struggle|relationship|preference|spiritual_state|goal), summary, detail|null, people[], event_date(YYYY-MM-DD)|null, salience(0..1), status(active|resolved)}}
- reflections[]: {{content, verse_reference|null, mood|null}}
- prayers[]: {{title, body|null, people[], event_date|null, cadence(none|daily|weekly)}}
- verses[]: {{display_ref, reference|null, themes[]}}
- suggest_checkin: {{time_sensitive(bool), event_date|null, context(prayer_followup|event_followup|struggle_followup|plan_nudge|general)}}

Use [] / null / false when nothing applies."""


# ---------------------------------------------------------------------------
# Public entrypoints
# ---------------------------------------------------------------------------
def extract_only(
    user_message: str,
    assistant_response: str,
    recent_history: Optional[List[Dict[str, str]]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Run JUST the extraction LLM + parse (the `extract` graph node).

    Returns the validated contract dict, or None if extraction failed (caller skips
    persistence). Never raises.
    """
    try:
        return _call_and_parse(user_message, assistant_response, recent_history)
    except Exception as e:
        logger.warning("Extraction LLM/parse failed, skipping: %s", str(e))
        return None


def persist_extraction(
    user_id: Optional[str],
    channel: str,
    parsed: Optional[Dict[str, Any]],
    source_msg_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Persist a parsed extraction to Neon (memories + reflections) — the `persist` node.

    Best-effort and per-item guarded; a single bad item never aborts the rest, and
    Neon being down simply persists nothing. Never raises.
    """
    result = {"persisted_memories": 0, "persisted_reflections": 0}
    if not user_id or not parsed:
        return result

    source = "sms" if channel == "sms" else "chat"

    for mem in parsed.get("memories", [])[:MAX_MEMORIES_PER_TURN]:
        try:
            mid = memory_store.upsert_memory(
                user_id=user_id,
                kind=mem.get("kind"),
                summary=mem.get("summary"),
                detail=mem.get("detail"),
                people=mem.get("people"),
                event_date=mem.get("event_date"),
                salience=mem.get("salience"),
                status=mem.get("status", "active"),
                source=source,
                source_msg_id=source_msg_id,
            )
            if mid:
                result["persisted_memories"] += 1
        except Exception as e:
            logger.warning("upsert_memory failed for one item: %s", str(e))

    for ref in parsed.get("reflections", [])[:MAX_REFLECTIONS_PER_TURN]:
        try:
            rid = memory_store.insert_reflection(
                user_id=user_id,
                content=ref.get("content"),
                source="auto_summary",
                session_id=session_id,
                verse_reference=ref.get("verse_reference"),
                mood=ref.get("mood"),
            )
            if rid:
                result["persisted_reflections"] += 1
        except Exception as e:
            logger.warning("insert_reflection failed for one item: %s", str(e))

    # verses / prayers / suggest_checkin -> DynamoDB destinations land in later phases.
    _record_verses_if_possible(user_id, parsed.get("verses", []))
    return result


def run_extraction(
    user_id: Optional[str],
    channel: str,
    user_message: str,
    assistant_response: str,
    recent_history: Optional[List[Dict[str, str]]] = None,
    source_msg_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Distill one turn AND persist (extract + persist combined). Best-effort.

    Used by the async worker entrypoint and the inline fallback. Never raises.
    """
    result = {"persisted_memories": 0, "persisted_reflections": 0, "raw": None}
    if not user_id:
        # No registered user => nothing to attach long-term memory to (spec scope).
        return result
    parsed = extract_only(user_message, assistant_response, recent_history)
    result["raw"] = parsed
    counts = persist_extraction(user_id, channel, parsed, source_msg_id, session_id)
    result.update(counts)
    return result


def handle_extraction_event(event: Dict[str, Any], context=None) -> Dict[str, Any]:
    """
    Lambda entrypoint for ASYNC extraction (spec §5.2 "async for SMS").

    Infra can route SMS extraction to this by invoking the chat lambda (or a dedicated
    `memory_extractor` lambda) with InvocationType='Event' and a payload of:
        {"task": "extract", "user_id", "channel", "user_message",
         "assistant_response", "recent_history", "source_msg_id", "session_id"}
    Until that wiring exists, the chat path runs extraction inline (see chat_handler).
    """
    return run_extraction(
        user_id=event.get("user_id"),
        channel=event.get("channel", "web"),
        user_message=event.get("user_message", ""),
        assistant_response=event.get("assistant_response", ""),
        recent_history=event.get("recent_history"),
        source_msg_id=event.get("source_msg_id"),
        session_id=event.get("session_id"),
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------
def _call_and_parse(
    user_message: str, assistant_response: str, recent_history: Optional[List[Dict[str, str]]]
) -> Dict[str, Any]:
    from langchain_core.messages import SystemMessage, HumanMessage

    context_lines = []
    for msg in (recent_history or [])[-6:]:
        role = msg.get("role", "user")
        content = (msg.get("content") or "")[:300]
        context_lines.append(f"{role}: {content}")
    context = "\n".join(context_lines) if context_lines else "(none)"

    prompt = _USER_TEMPLATE.format(
        context=context,
        user_message=user_message[:2000],
        assistant_response=assistant_response[:2000],
    )
    llm = _get_llm()
    resp = llm.invoke([SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)])
    return _coerce(_loads(resp.content))


def _loads(raw: str) -> Dict[str, Any]:
    if not raw:
        return {}
    text = raw.strip()
    # Strip ```json fences if the model added them despite json_object mode.
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Last resort: grab the first {...} block.
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return {}
        return {}


def _coerce(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate/normalize model output into the strict contract shape."""
    if not isinstance(data, dict):
        return _empty()

    out = _empty()
    for mem in _as_list(data.get("memories")):
        if not isinstance(mem, dict):
            continue
        summary = (mem.get("summary") or "").strip()
        if not summary:
            continue
        # Drop memories whose kind isn't in the enum (store layer guards too).
        if mem.get("kind") not in memory_store.VALID_KINDS:
            continue
        out["memories"].append({
            "kind": mem.get("kind"),
            "summary": summary[:200],
            "detail": _clean_str(mem.get("detail")),
            "people": _as_str_list(mem.get("people")),
            "event_date": _clean_date(mem.get("event_date")),
            "salience": mem.get("salience"),
            "status": mem.get("status") if mem.get("status") in ("active", "resolved") else "active",
        })

    for ref in _as_list(data.get("reflections")):
        if not isinstance(ref, dict):
            continue
        content = (ref.get("content") or "").strip()
        if not content:
            continue
        out["reflections"].append({
            "content": content,
            "verse_reference": _clean_str(ref.get("verse_reference")),
            "mood": _clean_str(ref.get("mood")),
        })

    for pr in _as_list(data.get("prayers")):
        if not isinstance(pr, dict):
            continue
        title = (pr.get("title") or "").strip()
        if not title:
            continue
        cadence = pr.get("cadence")
        out["prayers"].append({
            "title": title,
            "body": _clean_str(pr.get("body")),
            "people": _as_str_list(pr.get("people")),
            "event_date": _clean_date(pr.get("event_date")),
            "cadence": cadence if cadence in ("none", "daily", "weekly") else "none",
        })

    for v in _as_list(data.get("verses")):
        if not isinstance(v, dict):
            continue
        ref = (v.get("display_ref") or v.get("reference") or "").strip()
        if not ref:
            continue
        out["verses"].append({
            "display_ref": ref,
            "reference": _clean_str(v.get("reference")),
            "themes": _as_str_list(v.get("themes")),
        })

    sc = data.get("suggest_checkin")
    if isinstance(sc, dict):
        ctx = sc.get("context")
        out["suggest_checkin"] = {
            "time_sensitive": bool(sc.get("time_sensitive")),
            "event_date": _clean_date(sc.get("event_date")),
            "context": ctx if ctx in _VALID_CHECKIN_CONTEXTS else "general",
        }
    return out


def _empty() -> Dict[str, Any]:
    return {
        "memories": [], "reflections": [], "prayers": [], "verses": [],
        "suggest_checkin": {"time_sensitive": False, "event_date": None, "context": "general"},
    }


def _as_list(v):
    return v if isinstance(v, list) else []


def _as_str_list(v):
    if not isinstance(v, list):
        return []
    return [str(x).strip() for x in v if x and str(x).strip()]


def _clean_str(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _clean_date(v):
    """Accept only YYYY-MM-DD; otherwise None."""
    if not v:
        return None
    s = str(v).strip()
    return s if re.match(r"^\d{4}-\d{2}-\d{2}$", s) else None


def _record_verses_if_possible(user_id: str, verses: List[Dict[str, Any]]):
    """
    Write surfaced verses to the DynamoDB `verse_history` table if it's wired.

    No-op until Phase 2 provisions the table + VERSE_HISTORY_TABLE env var.
    """
    table_name = os.environ.get("VERSE_HISTORY_TABLE")
    if not table_name or not verses:
        return
    try:
        import boto3
        from datetime import datetime, timezone

        table = boto3.resource("dynamodb").Table(table_name)
        for v in verses:
            now = datetime.now(timezone.utc).isoformat()
            table.put_item(Item={
                "userId": user_id,
                "sentAt": now,
                "displayRef": v.get("display_ref"),
                "reference": v.get("reference"),
                "themes": v.get("themes") or [],
                "context": "chat",
            })
    except Exception as e:
        logger.info("verse_history write skipped (ok pre-Phase-2): %s", str(e))
