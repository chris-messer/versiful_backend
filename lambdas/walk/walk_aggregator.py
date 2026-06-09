"""
Aggregation helpers for the "My Walk" journey view (spec §11).

Reads across DynamoDB companion tables (prayers, verse_history, checkins,
user_reading_plans) and Neon (user_memories via the shared `memory_store`,
reflections via a guarded `neon_client` query). EVERY read degrades gracefully:
a missing table or a Neon outage contributes nothing and never raises, so the
DynamoDB-backed core of the summary always returns (conventions doc §7).

Long-term memory + reflections live ONLY in Neon, so those two reads require the
langchain layer (psycopg) on the walk lambda. Until that layer is mounted they
simply return empty — see the integration spec TF NEEDS for `walk`.
"""
import logging
import os
from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
PROJECT_NAME = os.environ.get("PROJECT_NAME", "versiful")

PRAYERS_TABLE = os.environ.get("PRAYERS_TABLE", f"{ENVIRONMENT}-{PROJECT_NAME}-prayers")
VERSE_HISTORY_TABLE = os.environ.get("VERSE_HISTORY_TABLE", f"{ENVIRONMENT}-{PROJECT_NAME}-verse-history")
CHECKINS_TABLE = os.environ.get("CHECKINS_TABLE", f"{ENVIRONMENT}-{PROJECT_NAME}-checkins")
USER_READING_PLANS_TABLE = os.environ.get(
    "USER_READING_PLANS_TABLE", f"{ENVIRONMENT}-{PROJECT_NAME}-user-reading-plans"
)

RECENT_LIMIT = 3
MAX_THEMES = 12

_dynamodb = boto3.resource("dynamodb")


def _table(name: str):
    return _dynamodb.Table(name)


def _query_all(table_name: str, user_id: str) -> List[Dict[str, Any]]:
    """Query every item for a user (per-user counts are small). [] on any failure."""
    try:
        table = _table(table_name)
        items: List[Dict[str, Any]] = []
        kwargs = {"KeyConditionExpression": Key("userId").eq(user_id)}
        while True:
            resp = table.query(**kwargs)
            items.extend(resp.get("Items", []))
            last = resp.get("LastEvaluatedKey")
            if not last:
                break
            kwargs["ExclusiveStartKey"] = last
        return items
    except Exception as e:
        logger.info("Query of %s degraded (ok if table absent): %s", table_name, str(e))
        return []


def _date_only(ts: Optional[str]) -> Optional[str]:
    if not ts:
        return None
    return str(ts)[:10] or None


# ---------------------------------------------------------------------------
# DynamoDB-backed sections
# ---------------------------------------------------------------------------
def prayers_summary(user_id: str) -> Dict[str, Any]:
    items = _query_all(PRAYERS_TABLE, user_id)
    active = [p for p in items if (p.get("status") or "active") == "active"]
    answered = [p for p in items if p.get("status") == "answered"]
    answered.sort(key=lambda p: p.get("answeredAt") or p.get("updatedAt") or "", reverse=True)
    recent_answered = [
        {
            "id": p.get("prayerId"),
            "title": p.get("title"),
            "answerNote": p.get("answerNote"),
            "answeredAt": p.get("answeredAt"),
        }
        for p in answered[:RECENT_LIMIT]
    ]
    return {
        "active": len(active),
        "answered": len(answered),
        "recentAnswered": recent_answered,
        "_items": items,  # internal: reused for theme + streak aggregation
    }


def verses_summary(user_id: str) -> Dict[str, Any]:
    items = _query_all(VERSE_HISTORY_TABLE, user_id)
    items.sort(key=lambda v: v.get("sentAt") or "", reverse=True)
    recent_refs: List[str] = []
    for v in items[:5]:
        ref = v.get("displayRef") or v.get("reference")
        if ref:
            recent_refs.append(ref)
    return {
        "count": len(items),
        "recent": recent_refs,
        "_items": items,  # internal: reused for theme + streak aggregation
    }


def reading_plan_summary(user_id: str) -> Optional[Dict[str, Any]]:
    items = _query_all(USER_READING_PLANS_TABLE, user_id)
    active = [p for p in items if (p.get("status") or "active") == "active"]
    if not active:
        return None
    # Prefer the most recently started/updated active plan.
    active.sort(key=lambda p: p.get("startedAt") or p.get("updatedAt") or "", reverse=True)
    plan = active[0]
    return {
        "slug": plan.get("planId"),
        "title": plan.get("title") or plan.get("planId"),
        "currentDay": _as_int(plan.get("currentDay")),
        "dayCount": _as_int(plan.get("dayCount")),
        "status": plan.get("status") or "active",
        "lastDeliveredDay": _as_int(plan.get("lastDeliveredDay")),
    }


def upcoming_checkins(user_id: str) -> List[Dict[str, Any]]:
    items = _query_all(CHECKINS_TABLE, user_id)
    now = datetime.now(timezone.utc).isoformat()
    upcoming = [
        c for c in items
        if c.get("status") == "scheduled" and (c.get("scheduledFor") or "") >= now
    ]
    upcoming.sort(key=lambda c: c.get("scheduledFor") or "")
    return [
        {
            "checkinId": c.get("checkinId"),
            "scheduledFor": c.get("scheduledFor"),
            "contextSelector": c.get("contextSelector"),
        }
        for c in upcoming[:RECENT_LIMIT]
    ]


# ---------------------------------------------------------------------------
# Neon-backed sections (degrade to empty when Neon/psycopg unavailable)
# ---------------------------------------------------------------------------
def memories_summary(user_id: str) -> Dict[str, Any]:
    """Count + kind histogram from Neon user_memories (via shared memory_store)."""
    try:
        import memory_store
        rows = memory_store.list_memories(user_id) or []
    except Exception as e:
        logger.info("memories_summary degraded: %s", str(e))
        rows = []
    kinds = Counter((m.get("kind") or "note") for m in rows)
    return {"count": len(rows), "byKind": dict(kinds), "_items": rows}


def reflections_summary(user_id: str) -> Dict[str, Any]:
    """Count + recent reflections from Neon (guarded direct query)."""
    recent: List[Dict[str, Any]] = []
    count = 0
    try:
        import neon_client
        if neon_client.is_available():
            cnt = neon_client.execute(
                "SELECT count(*) FROM reflections WHERE user_id = %s",
                (user_id,),
                fetch="one",
            )
            count = int(cnt[0]) if cnt else 0
            rows = neon_client.execute(
                """
                SELECT id, content, verse_reference, mood, created_at
                  FROM reflections
                 WHERE user_id = %s
                 ORDER BY created_at DESC
                 LIMIT %s
                """,
                (user_id, RECENT_LIMIT),
                fetch="all",
            )
            for r in (rows or []):
                recent.append({
                    "id": str(r[0]),
                    "content": r[1],
                    "verseReference": r[2],
                    "mood": r[3],
                    "createdAt": r[4].isoformat() if r[4] else None,
                })
    except Exception as e:
        logger.info("reflections_summary degraded: %s", str(e))
    return {"count": count, "recent": recent}


# ---------------------------------------------------------------------------
# Derived: themes, streak, milestones, gentle prompt
# ---------------------------------------------------------------------------
def build_themes(verse_items: List[Dict[str, Any]], memory_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    counter: Counter = Counter()
    for v in verse_items:
        for theme in (v.get("themes") or []):
            label = str(theme).strip().lower()
            if label:
                counter[label] += 1
    for m in memory_rows:
        kind = (m.get("kind") or "").strip()
        if kind in ("struggle", "goal", "spiritual_state"):
            # Surface the memory's own topical flavor via its kind as a coarse theme.
            counter[kind.replace("_", " ")] += 1
    return [{"label": label, "count": n} for label, n in counter.most_common(MAX_THEMES)]


def compute_streak(activity_dates: set) -> int:
    """Current consecutive-day streak ending today or yesterday."""
    if not activity_dates:
        return 0
    today = datetime.now(timezone.utc).date()
    # Allow the streak to "hold" if they were active yesterday but not yet today.
    start = today if today.isoformat() in activity_dates else today - timedelta(days=1)
    if start.isoformat() not in activity_dates:
        return 0
    streak = 0
    cursor = start
    while cursor.isoformat() in activity_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def collect_activity_dates(
    prayer_items: List[Dict[str, Any]],
    verse_items: List[Dict[str, Any]],
    reflection_recent: List[Dict[str, Any]],
) -> set:
    dates = set()
    for p in prayer_items:
        for key in ("createdAt", "answeredAt", "lastPrayedAt"):
            d = _date_only(p.get(key))
            if d:
                dates.add(d)
    for v in verse_items:
        d = _date_only(v.get("sentAt"))
        if d:
            dates.add(d)
    for r in reflection_recent:
        d = _date_only(r.get("createdAt"))
        if d:
            dates.add(d)
    return dates


def build_milestones(
    prayers: Dict[str, Any],
    plan: Optional[Dict[str, Any]],
    reflections: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """A small auto-generated highlight reel (derived on read, not materialized)."""
    milestones: List[Dict[str, Any]] = []
    for p in prayers.get("recentAnswered", []):
        milestones.append({
            "type": "prayer_answered",
            "label": f"Prayer answered: {p.get('title')}",
            "at": p.get("answeredAt"),
        })
    if plan and plan.get("slug"):
        milestones.append({
            "type": "reading_plan",
            "label": f"Reading plan in progress: {plan.get('title')}",
            "at": None,
        })
    for r in reflections.get("recent", [])[:1]:
        milestones.append({
            "type": "reflection",
            "label": "Saved a reflection",
            "at": r.get("createdAt"),
        })
    # Newest first where we have timestamps; undated milestones sink to the end.
    milestones.sort(key=lambda m: m.get("at") or "", reverse=True)
    return milestones[:5]


def build_gentle_prompt(themes: List[Dict[str, Any]], plan: Optional[Dict[str, Any]]) -> Optional[str]:
    """A single, warm, non-pushy nudge in the Versiful 'we' voice."""
    explored = {t["label"] for t in themes}
    if "gratitude" not in explored and explored:
        return ("You've spent time with some heavy themes lately. "
                "When you're ready, we'd love to walk through gratitude with you.")
    if not plan:
        return "Whenever you're ready, a guided reading plan can give the week a gentle rhythm."
    return None


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Top-level assembly
# ---------------------------------------------------------------------------
def build_summary(user_id: str, is_premium: bool) -> Dict[str, Any]:
    """
    Assemble the full journey summary. For free users we return a TEASER: headline
    counts only, with detailed lists withheld behind the premium upgrade (spec §16,
    conventions §3 — premium reads degrade to a teaser rather than erroring).
    """
    prayers = prayers_summary(user_id)
    verses = verses_summary(user_id)
    memories = memories_summary(user_id)
    reflections = reflections_summary(user_id)
    plan = reading_plan_summary(user_id)

    activity_dates = collect_activity_dates(prayers["_items"], verses["_items"], reflections["recent"])
    themes = build_themes(verses["_items"], memories["_items"])

    base = {
        "isPremium": is_premium,
        "streak": compute_streak(activity_dates),
        "daysActive": len(activity_dates),
        "prayers": {"active": prayers["active"], "answered": prayers["answered"]},
        "reflections": {"count": reflections["count"]},
        "memories": {"count": memories["count"]},
        "verses": {"count": verses["count"]},
    }

    if not is_premium:
        base["teaser"] = True
        base["themes"] = themes[:3]
        base["upgradeMessage"] = (
            "Subscribe to see your full walk: themes, milestones, answered prayers, "
            "and everything Versiful remembers."
        )
        return base

    base["teaser"] = False
    base["themes"] = themes
    base["prayers"]["recentAnswered"] = prayers["recentAnswered"]
    base["reflections"]["recent"] = reflections["recent"]
    base["memories"]["byKind"] = memories["byKind"]
    base["verses"]["recent"] = verses["recent"]
    base["readingPlan"] = plan
    base["upcomingCheckins"] = upcoming_checkins(user_id)
    base["milestones"] = build_milestones(prayers, plan, reflections)
    base["gentlePrompt"] = build_gentle_prompt(themes, plan)
    return base
