"""
Compose the single, warm re-engagement SMS for a check-in (spec §10.2–§10.3).

Voice rules (non-negotiable): the assistant speaks as "we" / "Versiful", NEVER as a
first-person human "I". Tone is gentle, brief (1–2 short sentences, ideally one SMS
segment to control cost — §16.1), no marketing, no pressure. The message is
personalized by exactly one context selector chosen upstream.

A best-effort LLM (gpt-4o-mini) writes the copy; if the model or key is unavailable
we fall back to a deterministic template so a send never depends on the LLM. STOP
handling is inherent to the SMS channel and is not re-appended here.
"""
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger()

MODEL = "gpt-4o-mini"
MAX_TOKENS = 120

_SYSTEM_PROMPT = (
    "You are Versiful, a warm Christian companion that checks in on people by text. "
    "Always refer to yourself as 'we' or 'Versiful' — NEVER use a first-person human "
    "'I', and never imply you are a human. Write ONE gentle re-engagement text "
    "message (1-2 short sentences, ideally under 160 characters). It should feel "
    "personal and caring, reference the given context naturally, invite a reply "
    "without pressure, and contain nothing salesy or markety. Do not add quotes, "
    "signatures, or a Bible verse unless it flows naturally and stays short. Return "
    "only the message text."
)


def _first_name(user: Dict[str, Any]) -> str:
    return (user.get("firstName") or "").strip()


def _context_brief(ctx: Dict[str, Any]) -> str:
    """A compact natural-language description of the chosen selector for the LLM."""
    selector = ctx.get("selector")
    people = ", ".join(ctx.get("people") or []) if ctx.get("people") else ""
    if selector == "prayer_followup":
        bits = [f"a prayer they shared titled '{ctx.get('title')}'"]
        if people:
            bits.append(f"about {people}")
        if ctx.get("eventDate"):
            bits.append(f"with a date of {ctx.get('eventDate')}")
        return ("They have been quiet for a few days. Gently follow up on "
                + " ".join(bits) + ". Ask how it went / how they are.")
    if selector == "event_followup":
        return ("They have been quiet for a few days. Gently follow up on something "
                f"going on in their life: '{ctx.get('summary')}'"
                + (f" (involving {people})" if people else "")
                + (f", dated {ctx.get('eventDate')}" if ctx.get('eventDate') else "")
                + ". Let them know we're thinking of them.")
    if selector == "struggle_followup":
        return ("They have been quiet for a few days. Gently check in on a struggle "
                f"they keep returning to: '{ctx.get('summary')}'. Ask how their heart is.")
    if selector == "plan_nudge":
        return ("They have been quiet for a few days and have an active reading plan "
                f"'{ctx.get('title')}' they've fallen behind on. Offer a no-pressure "
                "nudge that it's waiting whenever they're ready.")
    return ("They have been quiet for a few days and nothing specific is pending. "
            "Send a simple, caring 'thinking of you, how are you?' check-in.")


# Deterministic fallbacks (used when the LLM is unavailable). All in the 'we' voice.
def _fallback(ctx: Dict[str, Any], name: str) -> str:
    hi = f"Hi {name}, " if name else "Hi, "
    selector = ctx.get("selector")
    if selector == "prayer_followup":
        title = ctx.get("title") or "what you asked us to pray for"
        return f"{hi}we've been praying about {title}. How are you doing with it? We're here whenever you'd like to talk."
    if selector == "event_followup":
        return f"{hi}we've been thinking of you and what you've been walking through. How are you? We're here if you want to share."
    if selector == "struggle_followup":
        return f"{hi}it's been a few days and we've had you on our heart. How is your heart today? We're here for you."
    if selector == "plan_nudge":
        title = ctx.get("title") or "your reading plan"
        return f"{hi}{title} is here whenever you're ready — no pressure at all. We'd love to pick back up with you."
    return f"{hi}it's been a few days and we've been thinking of you. How are you doing? We're always here when you want to talk."


def compose_message(
    user: Dict[str, Any],
    ctx: Dict[str, Any],
    api_key: Optional[str] = None,
) -> str:
    """
    Return the check-in SMS text. Tries the LLM; always returns a usable message
    (falls back to a deterministic template). Never raises.
    """
    name = _first_name(user)
    fallback = _fallback(ctx, name)
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage

        kwargs = {"model": MODEL, "temperature": 0.6, "max_tokens": MAX_TOKENS}
        if api_key:
            kwargs["api_key"] = api_key
        llm = ChatOpenAI(**kwargs)

        who = f"The person's first name is {name}. " if name else ""
        human = who + _context_brief(ctx)
        resp = llm.invoke([SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=human)])
        text = (resp.content or "").strip().strip('"').strip()
        if not text:
            return fallback
        # Keep SMS tight; hard cap so we never blow up segment cost.
        if len(text) > 320:
            text = text[:317].rstrip() + "..."
        return text
    except Exception as e:
        logger.warning("Check-in LLM compose failed, using fallback: %s", str(e))
        return fallback
