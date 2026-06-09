"""Reading Plan delivery scheduled worker (COMPANION_SPEC.md §9.2, §15.2).

Triggered by EventBridge Scheduler every 15 min (timezone-bucketed selection happens
inside the worker). For each active enrollment whose local delivery window matches now,
sends that day's reading via the existing SMS path and records progress. Idempotent
(one day per enrollment per local calendar day) and fault-isolated (one user's failure
never aborts the batch). See delivery.py for the full semantics.
"""
import json
import logging
import sys

sys.path.append("/opt/python")

try:
    import delivery
except ImportError:  # pragma: no cover - package-style import for tests
    from lambdas.reading_plan_delivery import delivery

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    logger.info("reading_plan_delivery invoked: %s", json.dumps(event) if event else "{}")
    # Allow a test/dry-run flag to skip the optional LLM expansion.
    use_llm = not bool((event or {}).get("disable_llm"))
    try:
        result = delivery.run_batch(use_llm=use_llm)
        return {"status": "ok", "worker": "reading_plan_delivery", **result}
    except Exception as e:  # pragma: no cover - run_batch already guards
        logger.error("reading_plan_delivery batch failed: %s", e, exc_info=True)
        return {"status": "error", "worker": "reading_plan_delivery", "error": str(e)}
