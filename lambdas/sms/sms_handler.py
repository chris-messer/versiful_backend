import base64
import json
import logging
import sys
import os
from datetime import datetime, timezone

try:
    from helpers import (
        send_message,
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

import boto3
from twilio.twiml.messaging_response import MessagingResponse  # noqa: F401

logger = logging.getLogger()
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)

# Lambda client for invoking chat handler
lambda_client = boto3.client('lambda')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'versiful')
CHAT_FUNCTION_NAME = os.environ.get(
    'CHAT_FUNCTION_NAME',
    f'{ENVIRONMENT}-{PROJECT_NAME}-chat'
)

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


def _invoke_chat_handler(thread_id: str, message: str, user_id: str = None, phone_number: str = None):
    """
    Invoke the chat Lambda function
    
    Args:
        thread_id: Thread identifier (phone number for SMS)
        message: User's message
        user_id: Optional user ID
        phone_number: Phone number
        
    Returns:
        Response from chat handler
    """
    payload = {
        'thread_id': thread_id,
        'message': message,
        'channel': 'sms',
        'user_id': user_id,
        'phone_number': phone_number
    }
    
    logger.info("Invoking chat handler with thread_id: %s", thread_id)
    
    try:
        response = lambda_client.invoke(
            FunctionName=CHAT_FUNCTION_NAME,
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        response_payload = json.loads(response['Payload'].read())
        logger.info("Chat handler response: %s", response_payload)
        
        # Parse the response body
        if response_payload.get('statusCode') == 200:
            body = json.loads(response_payload.get('body', '{}'))
            return body
        else:
            logger.error("Chat handler returned error: %s", response_payload)
            return {'success': False, 'error': 'Chat handler error'}
            
    except Exception as e:
        logger.error("Error invoking chat handler: %s", str(e))
        return {'success': False, 'error': str(e)}


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

        # Get user_id if available
        user_id = decision.get("user_profile", {}).get("userId") if decision.get("user_profile") else None

        # Invoke chat handler with phone number as thread_id
        logger.info("Invoking chat handler for SMS")
        chat_result = _invoke_chat_handler(
            thread_id=from_num_normalized,  # Phone number is the thread ID for SMS
            message=body,
            user_id=user_id,
            phone_number=from_num_normalized
        )

        if not chat_result.get('success', False):
            error_msg = chat_result.get('error', 'Unknown error')
            logger.error("Chat handler error: %s", error_msg)
            # Send a user-friendly error message
            send_message(
                from_num_normalized,
                "I apologize, but I encountered an error processing your message. Please try again in a moment."
            )
            return {
                "statusCode": 500,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "OPTIONS,POST",
                    "Access-Control-Allow-Headers": "Content-Type,Authorization",
                },
                "body": json.dumps({"error": error_msg}),
            }

        gpt_response = chat_result.get('response', '')
        
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
