"""
Agent tools for the companion graph.

Phase 1 added `recall` (on-demand semantic memory lookup) alongside the existing
`get_versiful_info`. Wave 2 registers the full spec §5.3 / §5.4 tool set here:

  - save_prayer, save_reflection            (prayers / reflections feature factories)
  - set_daily_verse, set_checkin_frequency, update_bible_version, set_response_style,
    get_account_status                       (account_management `account_tools`)
  - enroll_reading_plan, get_reading_progress, pause_reading_plan,
    resume_reading_plan                      (reading-plan enrollment via reading_plans_repo)

Tools can't take hidden per-request context as arguments, so the current user_id is
passed via the `current_user_id` ContextVar, which the graph's generate node sets
before each turn. Every tool resolves the user id from it (the model never supplies a
user id) and degrades gracefully to a friendly string — a tool must never crash the turn.

The feature-team callables (prayer_tools, reflection_tools, account_tools) and the
reading-plan repo (reading_plans_repo) live in the shared layer (lambdas/shared), so
they import cleanly here without a cross-lambda dependency.
"""
import contextvars
import logging
from typing import List, Optional

from langchain_core.tools import tool

import memory_store

# Promoted feature modules (shared layer). Imported defensively so a single missing
# module only drops its own tools, never the whole tool set.
try:
    import prayer_tools
except Exception as _e:  # pragma: no cover
    prayer_tools = None
    logging.getLogger().warning("prayer_tools unavailable: %s", _e)
try:
    import reflection_tools
except Exception as _e:  # pragma: no cover
    reflection_tools = None
    logging.getLogger().warning("reflection_tools unavailable: %s", _e)
try:
    import account_tools
except Exception as _e:  # pragma: no cover
    account_tools = None
    logging.getLogger().warning("account_tools unavailable: %s", _e)
try:
    import reading_plans_repo
except Exception as _e:  # pragma: no cover
    reading_plans_repo = None
    logging.getLogger().warning("reading_plans_repo unavailable: %s", _e)

logger = logging.getLogger()

# Set by the graph's generate node so tools know whose memory to query.
current_user_id: "contextvars.ContextVar[Optional[str]]" = contextvars.ContextVar(
    "current_user_id", default=None
)


def _resolve_user_id() -> Optional[str]:
    """Resolver passed to the prayers/reflections tool factories."""
    return current_user_id.get()


@tool
def recall(query: str) -> str:
    """Recall specific things the user has shared before (life events, struggles,
    prayers, preferences, past reflections). Use this when the user references
    something from the past, asks "do you remember...", or when older context would
    make your reply more personal. Provide a short natural-language search query.
    """
    user_id = current_user_id.get()
    if not user_id:
        return "No long-term memory is available for this user."

    try:
        results = memory_store.recall(user_id, query, k=5)
    except Exception as e:  # memory_store already guards, this is belt-and-suspenders
        logger.warning("recall tool failed: %s", str(e))
        return "Long-term memory is temporarily unavailable."

    memories = results.get("memories", [])
    reflections = results.get("reflections", [])
    if not memories and not reflections:
        return "Nothing relevant found in long-term memory."

    lines = []
    for m in memories:
        line = f"- {m.get('summary', '')}"
        if m.get("event_date"):
            line += f" (date: {m['event_date']})"
        lines.append(line)
    for r in reflections:
        snippet = (r.get("content") or "")[:200]
        lines.append(f"- (reflection) {snippet}")
    return "Here is what I found:\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Account-management tools (spec §5.4) — thin @tool wrappers over account_tools
# callables. The model never passes user_id; it's resolved from the ContextVar.
# `pause_reading_plan` / `resume_reading_plan` are deliberately NOT taken from
# account_tools here — the registered versions are the enrollment-based ones below.
# ---------------------------------------------------------------------------
@tool
def set_daily_verse(enabled: bool, time: Optional[str] = None) -> str:
    """Turn the user's daily verse on or off, and optionally set the delivery time.
    `enabled` is true to turn it on, false to turn it off. `time` is an optional
    24-hour HH:MM local time (e.g. "07:30"). Use when the user asks to start, stop,
    or reschedule their morning/daily verse.
    """
    if account_tools is None:
        return "I can't change that setting right now."
    return account_tools.set_daily_verse(current_user_id.get(), enabled, time)


@tool
def set_checkin_frequency(level: str) -> str:
    """Change how often the user receives gentle proactive check-ins when they go
    quiet. `level` is a natural-language setting: "off" to stop check-ins, "weekly"
    (more often), or "biweekly"/"less often". Use when the user asks to check in
    more, less, or not at all.
    """
    if account_tools is None:
        return "I can't change that setting right now."
    return account_tools.set_checkin_frequency(current_user_id.get(), level)


@tool
def update_bible_version(version: str) -> str:
    """Change the Bible translation used when quoting Scripture (e.g. NIV, ESV, KJV,
    NLT, NASB, NKJV, CSB, MSG, AMP, NRSV). Use when the user asks to switch translations.
    """
    if account_tools is None:
        return "I can't change that setting right now."
    return account_tools.update_bible_version(current_user_id.get(), version)


@tool
def set_response_style(tone: Optional[str] = None, length: Optional[str] = None) -> str:
    """Set how the assistant responds. `tone` is one of "warm", "pastoral", or
    "concise"; `length` is "short" or "fuller". Provide either or both. Use when the
    user asks you to be warmer, more concise, shorter, more detailed, etc.
    """
    if account_tools is None:
        return "I can't change that setting right now."
    return account_tools.set_response_style(current_user_id.get(), tone=tone, length=length)


@tool
def get_account_status() -> str:
    """Read back the user's account: plan (free/premium), SMS messages remaining,
    key preferences (daily verse, check-ins, Bible version), active-prayer count, and
    current reading-plan progress. Use when the user asks about their account,
    subscription, settings, usage, or "what's my status". Read-only — changes nothing.
    """
    if account_tools is None:
        return "I can't look that up right now."
    return account_tools.get_account_status(current_user_id.get())


# ---------------------------------------------------------------------------
# Reading-plan tools (spec §5.3 / §5.4) — enrollment-based, backed by the shared
# reading_plans_repo (the plans feature's logic). These are the registered
# pause/resume tools (reconciling the account_tools duplicate).
# ---------------------------------------------------------------------------
_FREE_PLAN_LIMIT = 1  # COMPANION_API_CONVENTIONS.md §3: free tier = 1 trial plan.


def _active_or_recent_enrollment(enrollments, status=None):
    matches = [e for e in enrollments if e.get("status") == status] if status else enrollments
    if not matches:
        return None
    matches.sort(key=lambda e: e.get("startedAt") or "", reverse=True)
    return matches[0]


@tool
def enroll_reading_plan(slug: str) -> str:
    """Enroll the user in a reading plan by its slug (e.g. "anxiety-7", "grief-14").
    Use when the user agrees to start a plan you suggested or asks to begin one. Free
    users may have one active plan; premium users may enroll in any.
    """
    user_id = current_user_id.get()
    if not user_id:
        return "I couldn't access your account to start that plan."
    if reading_plans_repo is None:
        return "Reading plans are briefly unavailable, so I couldn't enroll you just now."
    try:
        plan = reading_plans_repo.get_plan(slug)
        if not plan or not plan.get("isActive", True):
            return f"I couldn't find a reading plan called '{slug}'."
        title = plan.get("title", slug)
        existing = reading_plans_repo.get_enrollment(user_id, slug)
        if existing:
            return f"You're already enrolled in \"{title}.\" Say \"where am I in my plan\" anytime."
        user = reading_plans_repo.get_user(user_id)
        if not reading_plans_repo.is_subscribed(user):
            current = len(reading_plans_repo.list_enrollments(user_id))
            if current >= _FREE_PLAN_LIMIT:
                return ("Your free plan includes one reading plan at a time. You can finish or "
                        "pause your current plan, or upgrade for all plans.")
        reading_plans_repo.create_enrollment(user_id, slug)
        return (f"Done — you're enrolled in \"{title}.\" I'll send each day's reading at your "
                "usual time. Say \"pause my plan\" anytime.")
    except Exception as e:  # never crash the turn
        logger.warning("enroll_reading_plan failed: %s", str(e))
        return "I ran into a problem starting that plan. Please try again in a moment."


@tool
def get_reading_progress() -> str:
    """Report where the user is in their reading plan(s): plan name, current day, total
    days, and how many days they've completed. Use when the user asks about their plan
    progress ("where am I in my plan", "how's my reading plan going"). Read-only.
    """
    user_id = current_user_id.get()
    if not user_id:
        return "I couldn't access your account to check your reading plan."
    if reading_plans_repo is None:
        return "Reading plans are briefly unavailable, so I couldn't check your progress."
    try:
        enrollments = reading_plans_repo.list_enrollments(user_id)
        if not enrollments:
            return "You're not enrolled in a reading plan yet. Want me to suggest one?"
        lines = []
        for enr in sorted(enrollments, key=lambda e: e.get("startedAt") or "", reverse=True):
            plan = reading_plans_repo.get_plan(enr.get("planId"))
            title = (plan or {}).get("title", enr.get("planId"))
            day_count = int((plan or {}).get("dayCount") or 0)
            current_day = int(enr.get("currentDay") or 1)
            completed = len(reading_plans_repo.completed_day_numbers(user_id, enr.get("planId")))
            status = enr.get("status", "active")
            total = f" of {day_count}" if day_count else ""
            suffix = "" if status == "active" else f" ({status})"
            lines.append(f"- \"{title}\": day {current_day}{total}, {completed} day(s) completed{suffix}")
        return "Here's your reading plan progress:\n" + "\n".join(lines)
    except Exception as e:
        logger.warning("get_reading_progress failed: %s", str(e))
        return "I couldn't pull up your reading plan progress just now."


@tool
def pause_reading_plan() -> str:
    """Pause delivery of the user's currently active reading plan (no progress is
    lost). Use when the user asks to pause, stop, or take a break from their plan.
    """
    user_id = current_user_id.get()
    if not user_id:
        return "I couldn't access your account to pause your plan."
    if reading_plans_repo is None:
        return "Reading plans are briefly unavailable, so I couldn't pause your plan."
    try:
        enrollments = reading_plans_repo.list_enrollments(user_id)
        active = _active_or_recent_enrollment(enrollments, status="active")
        if not active:
            if _active_or_recent_enrollment(enrollments, status="paused"):
                return "Your reading plan is already paused. Say \"resume my plan\" to pick it back up."
            return "You don't have an active reading plan right now, so there's nothing to pause."
        reading_plans_repo.set_enrollment_status(user_id, active["planId"], "paused")
        return ("Done — I've paused your reading plan. You won't get daily plan messages until you "
                "say \"resume my plan.\" No progress is lost.")
    except Exception as e:
        logger.warning("pause_reading_plan failed: %s", str(e))
        return "I ran into a problem pausing your plan. Please try again in a moment."


@tool
def resume_reading_plan() -> str:
    """Resume delivery of the user's paused reading plan, picking up where they left
    off. Use when the user asks to resume, restart, or continue their plan.
    """
    user_id = current_user_id.get()
    if not user_id:
        return "I couldn't access your account to resume your plan."
    if reading_plans_repo is None:
        return "Reading plans are briefly unavailable, so I couldn't resume your plan."
    try:
        enrollments = reading_plans_repo.list_enrollments(user_id)
        paused = _active_or_recent_enrollment(enrollments, status="paused")
        if not paused:
            if _active_or_recent_enrollment(enrollments, status="active"):
                return "Your reading plan is already active — you're all set."
            return "You don't have a paused reading plan to resume right now."
        reading_plans_repo.set_enrollment_status(user_id, paused["planId"], "active")
        return ("Done — your reading plan is active again. I'll pick up right where you left off. "
                "Say \"pause my plan\" anytime.")
    except Exception as e:
        logger.warning("resume_reading_plan failed: %s", str(e))
        return "I ran into a problem resuming your plan. Please try again in a moment."


# ---------------------------------------------------------------------------
# Tool registry — single source of truth for the companion tool set. Each entry is
# guarded so a missing feature module drops only its own tool(s). Names are unique.
# ---------------------------------------------------------------------------
def build_companion_tools() -> List:
    """Return the full deduped list of companion agent tools to bind to the LLM.

    Order: recall, prayers, reflections, account-management, reading plans. The chat
    agent prepends `get_versiful_info`.
    """
    tools: List = [recall]

    if prayer_tools is not None:
        try:
            tools.append(prayer_tools.make_save_prayer_tool(_resolve_user_id))
        except Exception as e:  # pragma: no cover
            logger.warning("Could not build save_prayer tool: %s", str(e))

    if reflection_tools is not None:
        try:
            tools.append(reflection_tools.make_save_reflection_tool(_resolve_user_id))
        except Exception as e:  # pragma: no cover
            logger.warning("Could not build save_reflection tool: %s", str(e))

    if account_tools is not None:
        tools.extend([
            set_daily_verse,
            set_checkin_frequency,
            update_bible_version,
            set_response_style,
            get_account_status,
        ])

    if reading_plans_repo is not None:
        tools.extend([
            enroll_reading_plan,
            get_reading_progress,
            pause_reading_plan,
            resume_reading_plan,
        ])

    return tools
