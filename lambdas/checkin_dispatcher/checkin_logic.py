"""
Pure (AWS-free) decision logic for the check-in dispatcher.

Everything compliance- and cost-sensitive about check-ins lives here so it can be
unit-tested without DynamoDB/Neon/Twilio: inactivity eligibility, the frequency-cap
cooldown, quiet hours, and the single-selector ranking (spec §10).

Design posture (spec §10, §16.1): SMS is expensive, so the dispatcher is
CONSERVATIVE by default — one re-engagement message after a quiet stretch, hard
weekly/biweekly cap, opt-in only, quiet hours, STOP respected. The frequency cap is
a ceiling, not a target.
"""
import logging
from datetime import datetime, timezone, timedelta, date
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger()

# --- Tunable defaults (documented in the integration spec assumptions) ---
DEFAULT_INACTIVITY_DAYS = 4          # silence threshold before a re-engagement send
# Hard frequency cap -> minimum days between ANY two check-in sends to one user.
FREQUENCY_COOLDOWN_DAYS = {"weekly": 7, "biweekly": 14}
QUIET_START_HOUR = 8                 # inclusive: earliest local hour we may send
QUIET_END_HOUR = 21                  # exclusive: 9pm; no sends at/after this local hour
# A dated prayer/event is "near" if its date is within this window of today.
EVENT_NEAR_PAST_DAYS = 3             # just-passed window (e.g. surgery was 2 days ago)
EVENT_NEAR_FUTURE_DAYS = 2          # near-future window (e.g. interview tomorrow)
DEFAULT_TIMEZONE = "America/New_York"


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------
def parse_iso(ts: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into an aware UTC datetime. None on failure."""
    if not ts:
        return None
    s = str(ts).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def days_between(earlier: Optional[datetime], now: datetime) -> Optional[float]:
    if earlier is None:
        return None
    return (now - earlier).total_seconds() / 86400.0


def local_hour(now_utc: datetime, tz_name: Optional[str]) -> int:
    """
    Local hour (0-23) for a timezone name. Falls back to UTC if zoneinfo can't
    resolve the zone (e.g. tzdata missing) so quiet hours still apply conservatively.
    """
    name = tz_name or DEFAULT_TIMEZONE
    try:
        from zoneinfo import ZoneInfo
        return now_utc.astimezone(ZoneInfo(name)).hour
    except Exception as e:
        logger.info("tz resolve failed for %r, using UTC: %s", name, str(e))
        return now_utc.astimezone(timezone.utc).hour


def in_quiet_hours(now_utc: datetime, tz_name: Optional[str]) -> bool:
    """True if the user's LOCAL time is outside the allowed [8:00, 21:00) send window."""
    hour = local_hour(now_utc, tz_name)
    return hour < QUIET_START_HOUR or hour >= QUIET_END_HOUR


# ---------------------------------------------------------------------------
# Attribute coercion
# ---------------------------------------------------------------------------
def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return bool(value)


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def cooldown_days(frequency: Optional[str]) -> Optional[int]:
    """
    Days that must elapse between sends for the given frequency. None means
    'never send' (frequency == 'off' or unknown-as-off is handled by caller).
    """
    if not frequency:
        return FREQUENCY_COOLDOWN_DAYS["weekly"]
    freq = str(frequency).strip().lower()
    if freq == "off":
        return None
    return FREQUENCY_COOLDOWN_DAYS.get(freq, FREQUENCY_COOLDOWN_DAYS["weekly"])


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------
def outside_cooldown(user: Dict[str, Any], now: datetime) -> bool:
    """True if the user's last check-in is old enough to allow another (frequency cap)."""
    freq = user.get("checkinFrequency", "weekly")
    cd = cooldown_days(freq)
    if cd is None:
        return False  # 'off' -> never
    last = parse_iso(user.get("lastCheckinAt"))
    if last is None:
        return True
    age = days_between(last, now)
    return age is not None and age >= cd


def eligible_for_inactivity(user: Dict[str, Any], now: datetime) -> Tuple[bool, str]:
    """
    Full eligibility for a PRIMARY inactivity re-engagement send.

    Returns (eligible, reason). `reason` is a short slug for logging/metrics.
    """
    if not _as_bool(user.get("checkinEnabled")):
        return False, "not_opted_in"
    if _as_bool(user.get("optedOut")):
        return False, "opted_out"
    if str(user.get("checkinFrequency", "weekly")).strip().lower() == "off":
        return False, "frequency_off"
    if not user.get("phoneNumber"):
        return False, "no_phone"

    inactivity_days = _as_int(user.get("checkinInactivityDays"), DEFAULT_INACTIVITY_DAYS)
    silence = days_between(parse_iso(user.get("lastMessageAt")), now)
    if silence is None:
        # No recorded inbound activity -> don't cold-message; we only re-engage.
        return False, "no_last_message"
    if silence < inactivity_days:
        return False, "still_active"

    if not outside_cooldown(user, now):
        return False, "in_cooldown"

    if in_quiet_hours(now, user.get("timezone")):
        return False, "quiet_hours"

    return True, "eligible"


def eligible_for_time_sensitive(user: Dict[str, Any], now: datetime) -> Tuple[bool, str]:
    """
    Eligibility for the SECONDARY capped time-sensitive send (spec §10.4).

    Same opt-in / STOP / quiet-hours / frequency-cap guards as inactivity, but it does
    NOT require inactivity. The unified frequency cooldown (outside_cooldown) is what
    enforces the '<= 1/week' ceiling — both passes share lastCheckinAt.
    """
    if not _as_bool(user.get("checkinEnabled")):
        return False, "not_opted_in"
    if _as_bool(user.get("optedOut")):
        return False, "opted_out"
    if str(user.get("checkinFrequency", "weekly")).strip().lower() == "off":
        return False, "frequency_off"
    if not user.get("phoneNumber"):
        return False, "no_phone"
    if not outside_cooldown(user, now):
        return False, "in_cooldown"
    if in_quiet_hours(now, user.get("timezone")):
        return False, "quiet_hours"
    return True, "eligible"


# ---------------------------------------------------------------------------
# Single-selector ranking (spec §10.3): pick ONE thing the message is about.
# ---------------------------------------------------------------------------
def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _is_near(event_date: Optional[date], today: date) -> Optional[int]:
    """Return |offset in days| if the date is within the near window, else None."""
    if event_date is None:
        return None
    delta = (event_date - today).days
    if -EVENT_NEAR_PAST_DAYS <= delta <= EVENT_NEAR_FUTURE_DAYS:
        return abs(delta)
    return None


def select_context(
    memories: List[Dict[str, Any]],
    prayers: List[Dict[str, Any]],
    active_plan: Optional[Dict[str, Any]],
    now: datetime,
) -> Dict[str, Any]:
    """
    Resolve AT MOST ONE context selector to personalize the single message.

    Priority (spec §10.3): time-sensitive prayer/event date > recurring struggle >
    plan nudge > general. Returns a dict the composer turns into copy:
        {selector, ref, title?, summary?, people?, eventDate?}
    """
    today = now.date()

    # 1) Time-sensitive dated prayer (nearest date wins).
    best_prayer, best_prayer_off = None, None
    for p in prayers or []:
        if (p.get("status") or "active") != "active":
            continue
        off = _is_near(_parse_date(p.get("eventDate")), today)
        if off is not None and (best_prayer_off is None or off < best_prayer_off):
            best_prayer, best_prayer_off = p, off

    # 2) Time-sensitive dated memory.
    best_mem_evt, best_mem_off = None, None
    for m in memories or []:
        off = _is_near(_parse_date(m.get("event_date")), today)
        if off is not None and (best_mem_off is None or off < best_mem_off):
            best_mem_evt, best_mem_off = m, off

    # Prefer whichever dated item is closest to today.
    if best_prayer is not None and (best_mem_off is None or best_prayer_off <= best_mem_off):
        return {
            "selector": "prayer_followup",
            "ref": best_prayer.get("prayerId"),
            "title": best_prayer.get("title"),
            "people": best_prayer.get("people") or [],
            "eventDate": best_prayer.get("eventDate"),
        }
    if best_mem_evt is not None:
        return {
            "selector": "event_followup",
            "ref": best_mem_evt.get("id"),
            "summary": best_mem_evt.get("summary"),
            "people": best_mem_evt.get("people") or [],
            "eventDate": best_mem_evt.get("event_date"),
        }

    # 3) Most salient open struggle.
    struggles = [m for m in (memories or []) if m.get("kind") == "struggle" and m.get("status") == "active"]
    if struggles:
        struggles.sort(key=lambda m: float(m.get("salience") or 0.0), reverse=True)
        top = struggles[0]
        return {
            "selector": "struggle_followup",
            "ref": top.get("id"),
            "summary": top.get("summary"),
            "people": top.get("people") or [],
        }

    # 4) Plan nudge (active plan with a stale last delivery).
    if active_plan and (active_plan.get("status") or "active") == "active":
        last_delivered = parse_iso(active_plan.get("lastDeliveredAt"))
        stale = last_delivered is None or (days_between(last_delivered, now) or 0) >= 1
        if stale:
            return {
                "selector": "plan_nudge",
                "ref": active_plan.get("planId"),
                "title": active_plan.get("title") or active_plan.get("planId"),
            }

    # 5) Nothing pending -> a gentle general check-in.
    return {"selector": "general", "ref": None}
