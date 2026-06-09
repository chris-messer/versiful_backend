"""
In-chat agent tool for the Prayer Journal: `save_prayer`.

Produced by the prayers feature team; WIRED by the integration/agent team into the
chat LangGraph (spec §5.3, §7.1). This module is intentionally self-contained and
depends only on things available in BOTH the prayers REST lambda and the chat
lambda (stdlib + boto3 + the shared_dependencies layer), so the integration team
can register it from the chat agent without a cross-lambda import.

Two integration surfaces are exported:

1. `save_prayer(user_id, ...)` — the pure callable (testable, no LangChain dep).
   Writes a prayer to the same DynamoDB table + shape as the REST `POST /prayers`
   (source="chat"). Returns a small result dict; never raises.

2. `make_save_prayer_tool(resolve_user_id)` — a factory that returns a LangChain
   `@tool`. The agent team passes a `resolve_user_id` callable (e.g.
   `lambda: agent_tools.current_user_id.get()`) so the model never supplies the
   user id. The tool string return is what the model sees.

NOTE: a free-tier user is capped at 3 prayers by the REST API; the chat tool does
NOT re-enforce that cap here (the agent path is premium-centric and the cap is a
web/UX guardrail). If desired, the integration team can gate tool registration on
entitlement. Documented in the integration spec.
"""
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Callable, List, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()

_ENV = os.environ.get("ENVIRONMENT", "dev")
_PROJECT = os.environ.get("PROJECT_NAME", "versiful")
_PRAYERS_TABLE = os.environ.get("PRAYERS_TABLE", f"{_ENV}-{_PROJECT}-prayers")

VALID_CADENCES = {"none", "daily", "weekly"}

_dynamodb = None


def _table():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb.Table(_PRAYERS_TABLE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _norm_people(people) -> List[str]:
    if not people or not isinstance(people, list):
        return []
    seen, out = set(), []
    for p in people:
        if p is None:
            continue
        s = str(p).strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out


def save_prayer(
    user_id: str,
    title: str,
    body: Optional[str] = None,
    people: Optional[List[str]] = None,
    event_date: Optional[str] = None,
    cadence: str = "none",
    category: Optional[str] = None,
    source: str = "chat",
) -> dict:
    """
    Create a prayer for `user_id`. Pure callable — returns
    {"ok": bool, "prayerId": str|None, "title": str, "error": str|None}.
    Never raises.
    """
    if not user_id:
        return {"ok": False, "prayerId": None, "title": title, "error": "no_user"}
    if not title or not str(title).strip():
        return {"ok": False, "prayerId": None, "title": title, "error": "missing_title"}

    cadence = (str(cadence).strip().lower() if cadence else "none")
    if cadence not in VALID_CADENCES:
        cadence = "none"

    now = _now()
    prayer_id = str(uuid.uuid4())
    item = {
        "userId": user_id,
        "prayerId": prayer_id,
        "title": str(title).strip()[:200],
        "body": (str(body).strip() or None) if body else None,
        "category": (str(category).strip() or None) if category else None,
        "people": _norm_people(people),
        "status": "active",
        "eventDate": event_date if (event_date and len(str(event_date)) == 10) else None,
        "reminderCadence": cadence,
        "nextReminderAt": None,
        "lastPrayedAt": None,
        "prayCount": 0,
        "answerNote": None,
        "answeredAt": None,
        "source": source if source in ("chat", "sms", "web") else "chat",
        "createdAt": now,
        "updatedAt": now,
    }
    try:
        _table().put_item(Item=item)
        logger.info("save_prayer created %s for %s", prayer_id, user_id)
        return {"ok": True, "prayerId": prayer_id, "title": item["title"], "error": None}
    except ClientError as e:
        logger.error("save_prayer failed: %s", str(e))
        return {"ok": False, "prayerId": None, "title": title, "error": "write_failed"}


# ---------------------------------------------------------------------------
# LangChain tool factory (used by the chat agent; LangChain import is guarded so
# this module still imports/compiles in the REST lambda which has no langchain).
# ---------------------------------------------------------------------------
def make_save_prayer_tool(resolve_user_id: Callable[[], Optional[str]]):
    """
    Return a LangChain @tool `save_prayer` bound to a user-id resolver.

    Example wiring in the chat agent:
        from prayer_tools import make_save_prayer_tool
        import agent_tools
        tool = make_save_prayer_tool(lambda: agent_tools.current_user_id.get())
        tools.append(tool)
    """
    from langchain_core.tools import tool

    @tool
    def save_prayer(
        title: str,
        body: Optional[str] = None,
        people: Optional[List[str]] = None,
        event_date: Optional[str] = None,
        cadence: str = "none",
    ) -> str:
        """Add a request to the user's prayer journal so it can be prayed over and
        followed up on later. Use when the user asks you to pray for something or
        shares a clear prayer request. `title` is a short label (e.g. "Mom's
        surgery"). Optional: `body` (a longer note), `people` (names involved),
        `event_date` (YYYY-MM-DD if there's a specific date like a surgery), and
        `cadence` ("none", "daily", or "weekly") for reminders.
        """
        user_id = resolve_user_id()
        if not user_id:
            return "I couldn't access your account to save that prayer."
        result = save_prayer_callable(
            user_id, title, body=body, people=people,
            event_date=event_date, cadence=cadence, source="chat",
        )
        if result.get("ok"):
            return f"Added '{result['title']}' to your prayer list. I'll be praying with you."
        if result.get("error") == "missing_title":
            return "I need a short description of what to pray for."
        return "I wasn't able to save that prayer just now, but I'm still here with you."

    return save_prayer


# Alias so the factory's inner closure can call the pure function unambiguously.
save_prayer_callable = save_prayer
