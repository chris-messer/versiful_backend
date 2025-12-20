import base64
import json
import logging
import sys
from datetime import datetime, timezone

try:
    from helpers import (
        send_message,
        generate_response,
        parse_url_string,
        get_sms_usage,
        consume_message_if_allowed,
        increment_nudge,
        get_user_by_id,
        current_period_key,
        FREE_MONTHLY_LIMIT,
        NUDGE_LIMIT,
        normalize_phone_number,
    )
except Exception:
    from lambdas.sms.helpers import (
        send_message,
        generate_response,
        parse_url_string,
        get_sms_usage,
        consume_message_if_allowed,
        increment_nudge,
        get_user_by_id,
        current_period_key,
        FREE_MONTHLY_LIMIT,
        NUDGE_LIMIT,
        normalize_phone_number,
    )
from twilio.twiml.messaging_response import MessagingResponse  # noqa: F401

logger = logging.getLogger()
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)


SUBSCRIPTION_INACTIVE_MESSAGE = (
    "Your Versiful subscription is inactive. Please visit https://versiful.io to renew "
    "and continue receiving guidance."
)


def _next_period_reset(period_key: str) -> str:
    """Return the ISO date string for the start of the next period."""
    year, month = [int(x) for x in period_key.split("-")]
    first_of_month = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        next_month = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return next_month.date().isoformat()


def _free_credits_exhausted_message(period_key: str, limit: int) -> str:
    reset_on = _next_period_reset(period_key)
    return (
        f"You've used your {limit} free messages for this month. "
        f"Your credits reset on {reset_on}. Register at https://versiful.io "
        "for unlimited guidance."
    )


def _evaluate_usage(phone_number: str):
    """
    Centralized if-then decision making for usage gating.
    Returns dict with keys:
    - allowed (bool)
    - limit (int or None)
    - usage (dict)
    - user_profile (dict or None)
    - reason (str)
    """
    usage = get_sms_usage(phone_number)
    user_id = usage.get("userId")
    user_profile = get_user_by_id(user_id) if user_id else None

    if user_profile and user_profile.get("isSubscribed"):
        return {
            "allowed": True,
            "limit": None,
            "usage": usage,
            "user_profile": user_profile,
            "reason": "subscribed",
        }

    if user_profile and user_profile.get("plan_monthly_cap") is not None:
        limit = int(user_profile["plan_monthly_cap"])
    else:
        limit = FREE_MONTHLY_LIMIT

    updated = consume_message_if_allowed(phone_number, limit, user_id=user_id)
    if updated:
        return {
            "allowed": True,
            "limit": limit,
            "usage": updated,
            "user_profile": user_profile,
            "reason": "within_cap",
        }

    usage = get_sms_usage(phone_number, user_id=user_id)
    return {
        "allowed": False,
        "limit": limit,
        "usage": usage,
        "user_profile": user_profile,
        "reason": "quota_exceeded",
    }


def _should_nudge(usage: dict) -> bool:
    return usage.get("nudges_sent", 0) < NUDGE_LIMIT


def _success_response():
    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "OPTIONS,POST",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
        },
    }


def handler(event, context):
    logger.info("Received event: %s", event)
    if event.get("isBase64Encoded", False):
        params = parse_url_string(base64.b64decode(event["body"]))
        params = {key.decode("utf-8"): value.decode("utf-8") for key, value in params.items()}
    else:
        params = parse_url_string(event["body"])

    body = params.get("Body", None)
    from_num = params.get("From", None)
    from_num_normalized = normalize_phone_number(from_num)

    logger.info("Message body retrieved: %s", body)

    if body is None:
        logger.info("Body was none, exiting")
        return _success_response()

    if not from_num_normalized:
        logger.info("Could not normalize phone number: %s", from_num)
        return _success_response()

    logger.info("Message body found!")
    try:
        decision = _evaluate_usage(from_num_normalized)
        logger.info("Usage decision: %s", decision["reason"])

        if not decision["allowed"]:
            period_key = decision["usage"].get("periodKey", current_period_key())
            limit = decision["limit"] or FREE_MONTHLY_LIMIT
            if _should_nudge(decision["usage"]):
                increment_nudge(from_num_normalized)
                send_message(from_num_normalized, _free_credits_exhausted_message(period_key, limit))
            else:
                logger.info("Nudge limit reached for %s", from_num_normalized)
            return _success_response()

        logger.info("Fetching from GPT")
        gpt_response = generate_response(body)
        error_msg = None
        if isinstance(gpt_response, dict) and gpt_response.get("error"):
            error_msg = gpt_response["error"]
        elif isinstance(gpt_response, str) and gpt_response.lower().startswith("error"):
            error_msg = gpt_response

        if error_msg:
            logger.info("GPT Error: %s", error_msg)
            return {
                "statusCode": 500,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "OPTIONS,POST",
                    "Access-Control-Allow-Headers": "Content-Type,Authorization",
                },
                "body": json.dumps({"error": str(error_msg)}),
            }

        logger.info("Sending Message...")
        send_message(from_num_normalized, gpt_response)

        return _success_response()

    except Exception as E:
        logger.info("Error: %s", E)
        return {
            "statusCode": 500,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "OPTIONS,POST",
                "Access-Control-Allow-Headers": "Content-Type,Authorization",
            },
            "body": json.dumps({"error": str(E)}),
        }
