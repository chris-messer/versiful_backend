"""Reading Plans REST API (COMPANION_SPEC.md §9, §14; conventions in
COMPANION_API_CONVENTIONS.md).

Routes (HTTP API v2 / AWS_PROXY):
    GET  /plans                              PUBLIC  catalog list
    GET  /plans/{slug}                        PUBLIC  plan detail incl. days
    POST /plans/{slug}/enroll                 JWT     enroll (free = 1 trial plan)
    GET  /plans/enrolled                       JWT     caller's enrollments + progress
    POST /plans/enrolled/{id}/complete-day     JWT     record/advance progress (+ reflection)
    POST /plans/enrolled/{id}/pause            JWT     pause / resume delivery

Conventions enforced: success/error envelope (§4), JWT on enrolled actions (§2),
ownership = 404 (§4), subscription gating for reading plans (§3: free = 1 trial plan),
camelCase on the wire (§1). The enrollment id ({id}) is the planId.
"""
import logging
import sys

# Shared layer (/opt/python) provides memory_store/neon_client at runtime; the
# package-local fallbacks keep imports working for unit tests.
sys.path.append("/opt/python")

try:
    import helpers as h
    import reading_plans_repo as repo
except ImportError:  # pragma: no cover - package-style import for tests
    from lambdas.plans import helpers as h
    from lambdas.shared import reading_plans_repo as repo

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Free tier may enroll in a single trial plan (COMPANION_API_CONVENTIONS.md §3).
FREE_PLAN_LIMIT = 1


# ---------------------------------------------------------------------------
# Serializers (DynamoDB item -> wire shape, camelCase)
# ---------------------------------------------------------------------------
def _serialize_catalog(plan):
    return {
        "slug": plan.get("slug"),
        "title": plan.get("title"),
        "description": plan.get("description"),
        "topic": plan.get("topic"),
        "dayCount": plan.get("dayCount"),
        "emoji": plan.get("emoji"),
        "isActive": plan.get("isActive", True),
    }


def _serialize_day(day):
    return {
        "dayNumber": day.get("dayNumber"),
        "passageRef": day.get("passageRef"),
        "theme": day.get("theme"),
        "prompt": day.get("prompt"),
    }


def _serialize_enrollment(enr, plan=None, completed_days=None):
    out = {
        "planId": enr.get("planId"),
        "slug": enr.get("planId"),
        "status": enr.get("status"),
        "currentDay": enr.get("currentDay"),
        "deliveryChannel": enr.get("deliveryChannel"),
        "deliveryTime": enr.get("deliveryTime"),
        "lastDeliveredDay": enr.get("lastDeliveredDay"),
        "lastDeliveredAt": enr.get("lastDeliveredAt"),
        "startedAt": enr.get("startedAt"),
        "completedAt": enr.get("completedAt"),
        "completedDays": completed_days if completed_days is not None else [],
    }
    if plan:
        out["title"] = plan.get("title")
        out["emoji"] = plan.get("emoji")
        out["topic"] = plan.get("topic")
        out["dayCount"] = plan.get("dayCount")
        out["description"] = plan.get("description")
    return out


# ---------------------------------------------------------------------------
# Catalog endpoints (public)
# ---------------------------------------------------------------------------
def list_catalog(event):
    plans = repo.list_active_plans()
    items = [_serialize_catalog(p) for p in plans]
    return h.success({"items": items}, meta={"count": len(items)})


def get_catalog_detail(event):
    slug = h.get_path_param(event, "slug")
    if not slug:
        return h.validation_error("Missing plan slug.")
    plan = repo.get_plan(slug)
    if not plan or not plan.get("isActive", True):
        return h.not_found("Reading plan not found.")
    days = [_serialize_day(d) for d in repo.get_plan_days(slug)]
    detail = _serialize_catalog(plan)
    detail["days"] = days
    # dayCount falls back to the authored day count if the catalog row omits it.
    if detail.get("dayCount") is None:
        detail["dayCount"] = len(days)
    return h.success(detail)


# ---------------------------------------------------------------------------
# Enrolled endpoints (authed)
# ---------------------------------------------------------------------------
def enroll(event, user_id):
    slug = h.get_path_param(event, "slug")
    if not slug:
        return h.validation_error("Missing plan slug.")

    plan = repo.get_plan(slug)
    if not plan or not plan.get("isActive", True):
        return h.not_found("Reading plan not found.")

    body, err = h.parse_body(event)
    if err:
        return err

    existing = repo.get_enrollment(user_id, slug)
    if existing:
        # Idempotent: already enrolled in this plan -> return it unchanged.
        completed = repo.completed_day_numbers(user_id, slug)
        return h.success(_serialize_enrollment(existing, plan, completed), status_code=200)

    # Subscription gating: free tier capped at FREE_PLAN_LIMIT enrolled plans.
    user = repo.get_user(user_id)
    if not repo.is_subscribed(user):
        current = len(repo.list_enrollments(user_id))
        if current >= FREE_PLAN_LIMIT:
            return h.limit_reached(
                "Free plan allows 1 reading plan. Upgrade for all plans.",
                {"limit": FREE_PLAN_LIMIT, "current": current},
            )

    # Delivery prefs: body overrides, else user defaults, else system defaults.
    user = user if user is not None else {}
    delivery_time = (body.get("deliveryTime") or user.get("dailyVerseTime") or "08:00")
    delivery_channel = (
        body.get("deliveryChannel") or user.get("primaryChannel") or "sms"
    )
    if not _valid_hhmm(delivery_time):
        return h.validation_error("deliveryTime must be HH:MM (24h).", ["deliveryTime"])

    enr, _created = repo.create_enrollment(
        user_id, slug, delivery_channel=delivery_channel, delivery_time=delivery_time
    )
    return h.success(_serialize_enrollment(enr, plan, []), status_code=201)


def list_enrolled(event, user_id):
    enrollments = repo.list_enrollments(user_id)
    items = []
    for enr in enrollments:
        plan = repo.get_plan(enr.get("planId"))
        completed = repo.completed_day_numbers(user_id, enr.get("planId"))
        items.append(_serialize_enrollment(enr, plan, completed))
    items.sort(key=lambda e: e.get("startedAt") or "", reverse=True)
    return h.success({"items": items}, meta={"count": len(items)})


def complete_day(event, user_id):
    plan_id = h.get_path_param(event, "id")
    if not plan_id:
        return h.validation_error("Missing enrollment id.")

    enr = repo.get_enrollment(user_id, plan_id)
    if not enr:
        return h.not_found("Enrollment not found.")  # ownership scoped -> 404 (§4)

    body, err = h.parse_body(event)
    if err:
        return err

    plan = repo.get_plan(plan_id)
    day_count = int(plan.get("dayCount") or 0) if plan else 0

    # day_number: explicit, else the enrollment's currentDay.
    raw_day = body.get("dayNumber", body.get("day_number"))
    if raw_day is None:
        day_number = int(enr.get("currentDay") or 1)
    else:
        try:
            day_number = int(raw_day)
        except (TypeError, ValueError):
            return h.validation_error("dayNumber must be an integer.", ["dayNumber"])

    if day_number < 1 or (day_count and day_number > day_count):
        return h.validation_error(
            f"dayNumber must be between 1 and {day_count}.", ["dayNumber"]
        )

    # Best-effort reflection write to Neon (DynamoDB stays authoritative — §7 conv).
    reflection_id = None
    reflection_text = (body.get("reflection") or "").strip()
    if reflection_text:
        reflection_id = _save_reflection(user_id, plan_id, day_number, reflection_text)

    repo.record_progress(user_id, plan_id, day_number, reflection_id=reflection_id)

    # Advance currentDay monotonically; complete the plan if the last day is done.
    new_current = max(int(enr.get("currentDay") or 1), day_number + 1)
    completed_plan = bool(day_count) and day_number >= day_count
    if completed_plan:
        new_current = day_count
    updated = repo.advance_current_day(
        user_id, plan_id, new_current, completed=completed_plan
    )

    completed_days = repo.completed_day_numbers(user_id, plan_id)
    result = _serialize_enrollment(updated or enr, plan, completed_days)
    result["completedDay"] = day_number
    if reflection_id:
        result["reflectionId"] = reflection_id
    return h.success(result)


def pause(event, user_id):
    plan_id = h.get_path_param(event, "id")
    if not plan_id:
        return h.validation_error("Missing enrollment id.")

    enr = repo.get_enrollment(user_id, plan_id)
    if not enr:
        return h.not_found("Enrollment not found.")

    body, err = h.parse_body(event)
    if err:
        return err

    # Accept explicit {status} or {paused: bool}; default toggles active<->paused.
    current_status = enr.get("status", "active")
    if "status" in body:
        new_status = str(body["status"]).lower()
        if new_status not in ("active", "paused"):
            return h.validation_error("status must be 'active' or 'paused'.", ["status"])
    elif "paused" in body:
        new_status = "paused" if body.get("paused") else "active"
    else:
        new_status = "active" if current_status == "paused" else "paused"

    updated = repo.set_enrollment_status(user_id, plan_id, new_status)
    plan = repo.get_plan(plan_id)
    completed = repo.completed_day_numbers(user_id, plan_id)
    return h.success(_serialize_enrollment(updated or enr, plan, completed))


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------
def _valid_hhmm(value):
    try:
        hh, mm = str(value).split(":")
        return 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59
    except (ValueError, AttributeError):
        return False


def _save_reflection(user_id, plan_id, day_number, content):
    """Best-effort Neon reflection write. Returns reflection id or None; never raises."""
    try:
        import memory_store
    except ImportError:
        try:
            from lambdas.shared import memory_store
        except ImportError:
            logger.info("memory_store unavailable; skipping reflection persistence.")
            return None
    try:
        day = repo.get_plan_day(plan_id, day_number)
        verse_ref = day.get("passageRef") if day else None
        return memory_store.insert_reflection(
            user_id,
            content,
            source="reading_plan",
            verse_reference=verse_ref,
        )
    except Exception as e:  # pragma: no cover - defensive; Neon best-effort
        logger.warning("Reflection persistence failed (non-fatal): %s", e)
        return None


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
# Catalog routes are public; the rest require JWT.
_PUBLIC_ROUTES = {"GET /plans", "GET /plans/{slug}"}


def handler(event, context):
    route = h.get_route(event)
    logger.info("plans invoked: %s", route)

    if h.get_method(event) == "OPTIONS":
        return {"statusCode": 200, "headers": h.cors_headers(), "body": ""}

    try:
        # Public catalog.
        if route == "GET /plans":
            return list_catalog(event)
        if route == "GET /plans/enrolled":
            # Must match BEFORE the {slug} catalog route (exact route wins in API GW,
            # but guard here too for direct invokes).
            user_id = h.get_user_id(event)
            if not user_id:
                return h.unauthorized()
            return list_enrolled(event, user_id)
        if route == "GET /plans/{slug}":
            slug = h.get_path_param(event, "slug")
            if slug == "enrolled":
                user_id = h.get_user_id(event)
                if not user_id:
                    return h.unauthorized()
                return list_enrolled(event, user_id)
            return get_catalog_detail(event)

        # Authed actions.
        user_id = h.get_user_id(event)
        if not user_id:
            return h.unauthorized()

        if route == "POST /plans/{slug}/enroll":
            return enroll(event, user_id)
        if route == "POST /plans/enrolled/{id}/complete-day":
            return complete_day(event, user_id)
        if route == "POST /plans/enrolled/{id}/pause":
            return pause(event, user_id)

        return h.not_found(f"No route for {route}.")
    except Exception as e:
        logger.error("Unhandled error in plans handler: %s", e, exc_info=True)
        return h.internal_error()
