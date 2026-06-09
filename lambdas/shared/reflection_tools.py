"""
In-chat agent tool for the Reflection Log: `save_reflection` (spec §5.3 `log_reflection`).

Produced by the reflections feature team; WIRED by the integration/agent team into
the chat LangGraph. Self-contained except for the shared `memory_store` module
(shipped in the `shared_dependencies` layer, which the chat lambda mounts), so the
integration team can register it from the chat agent without a cross-lambda import.

Exports:

1. `save_reflection(user_id, content, ...)` — pure callable. Writes the reflection
   to Neon via `memory_store.insert_reflection` (embedding generated on write;
   never fails the write if embedding fails). Degrades gracefully: if Neon is
   unavailable it returns {"ok": False, "error": "unavailable"} and never raises.

2. `make_save_reflection_tool(resolve_user_id)` — factory returning a LangChain
   `@tool` bound to a user-id resolver (e.g.
   `lambda: agent_tools.current_user_id.get()`), so the model never supplies the
   user id.
"""
import logging
from typing import Callable, Optional

logger = logging.getLogger()

VALID_SOURCES = {"auto_summary", "manual", "reading_plan"}


def save_reflection(
    user_id: str,
    content: str,
    verse_reference: Optional[str] = None,
    source: str = "auto_summary",
    session_id: Optional[str] = None,
    mood: Optional[str] = None,
) -> dict:
    """
    Save a reflection/takeaway for `user_id`. Returns
    {"ok": bool, "reflectionId": str|None, "error": str|None}. Never raises.

    `source` defaults to "auto_summary" (the agent saving a takeaway from a chat
    exchange); "manual" and "reading_plan" are the other valid sources.
    """
    if not user_id:
        return {"ok": False, "reflectionId": None, "error": "no_user"}
    if not content or not str(content).strip():
        return {"ok": False, "reflectionId": None, "error": "missing_content"}

    src = (str(source).strip().lower() if source else "auto_summary")
    if src not in VALID_SOURCES:
        src = "auto_summary"

    try:
        import memory_store
    except Exception as e:
        logger.warning("memory_store unavailable for save_reflection: %s", str(e))
        return {"ok": False, "reflectionId": None, "error": "unavailable"}

    try:
        reflection_id = memory_store.insert_reflection(
            user_id=user_id,
            content=str(content).strip(),
            source=src,
            session_id=session_id,
            verse_reference=(str(verse_reference).strip() or None) if verse_reference else None,
            mood=(str(mood).strip() or None) if mood else None,
        )
    except Exception as e:  # memory_store already guards; belt-and-suspenders
        logger.warning("save_reflection write error: %s", str(e))
        return {"ok": False, "reflectionId": None, "error": "write_failed"}

    if not reflection_id:
        return {"ok": False, "reflectionId": None, "error": "unavailable"}
    return {"ok": True, "reflectionId": reflection_id, "error": None}


def make_save_reflection_tool(resolve_user_id: Callable[[], Optional[str]]):
    """
    Return a LangChain @tool `save_reflection` bound to a user-id resolver.

    Example wiring in the chat agent:
        from reflection_tools import make_save_reflection_tool
        import agent_tools
        tool = make_save_reflection_tool(lambda: agent_tools.current_user_id.get())
        tools.append(tool)
    """
    from langchain_core.tools import tool

    @tool
    def save_reflection(content: str, verse_reference: Optional[str] = None) -> str:
        """Save a short reflection or takeaway to the user's journal so they can
        revisit it later. Use when the user shares a meaningful realization, or when
        they ask you to remember/save a takeaway from the conversation. `content` is
        the one or two sentence takeaway in the user's voice; `verse_reference` is an
        optional related verse (e.g. "Isaiah 41:10").
        """
        user_id = resolve_user_id()
        if not user_id:
            return "I couldn't access your account to save that reflection."
        result = save_reflection_callable(
            user_id, content, verse_reference=verse_reference, source="auto_summary",
        )
        if result.get("ok"):
            return "Saved that to your journal — you can revisit it anytime."
        if result.get("error") == "missing_content":
            return "What would you like me to save as the takeaway?"
        if result.get("error") == "unavailable":
            return "Your journal is briefly unavailable, so I couldn't save that just now."
        return "I wasn't able to save that reflection just now."

    return save_reflection


# Alias so the factory's closure can reference the pure callable unambiguously.
save_reflection_callable = save_reflection
