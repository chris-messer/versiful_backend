import base64
import json
import logging
import sys
import os
import re
import stripe
from uuid import uuid4
from datetime import datetime, timezone
from posthog import Posthog

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
        sms_usage_table,
    )
except ImportError:
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
        sms_usage_table,
    )

# Import secrets helper and SMS notifications
try:
    from secrets_helper import get_secret
    from sms_notifications import send_cancellation_sms, send_first_time_texter_welcome_sms
except ImportError:
    from lambdas.shared.secrets_helper import get_secret
    from lambdas.shared.sms_notifications import send_cancellation_sms, send_first_time_texter_welcome_sms

import boto3
from boto3.dynamodb.conditions import Attr
from twilio.twiml.messaging_response import MessagingResponse  # noqa: F401

logger = logging.getLogger()
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)

# Initialize Stripe
stripe.api_key = get_secret('stripe_secret_key')

# DynamoDB setup
dynamodb = boto3.resource("dynamodb")
env = os.environ.get('ENVIRONMENT', 'dev')
project_name = os.environ.get('PROJECT_NAME', 'versiful')
table_name = f"{env}-{project_name}-users"
table = dynamodb.Table(table_name)

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

# Initialize PostHog for user identification
try:
    posthog = Posthog(
        os.environ.get('POSTHOG_API_KEY'),
        host='https://us.i.posthog.com'
    )
    logger.info("PostHog initialized successfully in sms_handler")
except Exception as e:
    logger.error(f"Failed to initialize PostHog: {str(e)}")
    posthog = None


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
        # -1 means unlimited (same as isSubscribed)
        if limit == -1:
            return {
                "allowed": True,
                "limit": None,
                "usage": usage,
                "user_profile": user_profile,
                "reason": "unlimited_cap",
            }
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


def _handle_stop_keyword(phone_number: str):
    """
    Handle STOP, END, CANCEL, UNSUBSCRIBE, QUIT keywords
    Cancels subscription (if any) and opts user out of messages
    
    IMPORTANT: This MUST cancel Stripe subscriptions to avoid charging users
    for a service they're not receiving. This is required for consumer protection.
    """
    logger.info(f"Processing STOP request from {phone_number}")
    
    try:
        # Find user by phone number
        response = table.scan(
            FilterExpression=Attr("phoneNumber").eq(phone_number)
        )
        
        if not response.get("Items"):
            logger.info(f"No user found for phone {phone_number}")
            # Still send opt-out confirmation
            send_message(
                phone_number,
                "You have been unsubscribed from Versiful messages. "
                "Reply START to resubscribe anytime."
            )
            return
        
        user = response["Items"][0]
        user_id = user.get("userId")
        logger.info(f"Found user {user_id} for STOP request")
        
        # Check if user has an active subscription
        has_subscription = user.get("isSubscribed", False)
        stripe_subscription_id = user.get("stripeSubscriptionId")
        
        # CRITICAL: Cancel Stripe subscription to stop billing
        if has_subscription and stripe_subscription_id:
            logger.info(f"User {user_id} has active subscription {stripe_subscription_id}, canceling immediately")
            try:
                # Cancel the Stripe subscription immediately (not at period end)
                # This is REQUIRED to avoid charging users for service they're not receiving
                stripe.Subscription.delete(stripe_subscription_id)
                logger.info(f"Successfully canceled Stripe subscription {stripe_subscription_id}")
            except Exception as stripe_error:
                logger.error(f"CRITICAL ERROR canceling Stripe subscription: {str(stripe_error)}")
                # Continue with opt-out even if Stripe fails - user shouldn't receive messages
                # but we should alert about the billing issue
        
        # Update DynamoDB - revert to free plan and mark as opted out
        update_expression = """
            SET isSubscribed = :sub,
                #plan = :plan,
                plan_monthly_cap = :cap,
                subscriptionStatus = :status,
                cancelAtPeriodEnd = :cancel,
                optedOut = :opted_out,
                optedOutAt = :opted_out_at,
                updatedAt = :now
            REMOVE currentPeriodEnd
        """
        
        table.update_item(
            Key={"userId": user_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames={
                "#plan": "plan"
            },
            ExpressionAttributeValues={
                ":sub": False,
                ":plan": "free",
                ":cap": 5,  # Revert to free tier limit
                ":status": "canceled",
                ":cancel": False,
                ":opted_out": True,
                ":opted_out_at": datetime.now(timezone.utc).isoformat(),
                ":now": datetime.now(timezone.utc).isoformat()
            }
        )
        
        logger.info(f"Updated user {user_id}: subscription canceled, opted out, reverted to free plan")
        
        # Send cancellation confirmation
        if has_subscription:
            # User had subscription - send full cancellation message
            send_cancellation_sms(phone_number)
        else:
            # User was free tier - just opt-out confirmation
            send_message(
                phone_number,
                "You have been unsubscribed from Versiful messages. "
                "Reply START to resubscribe anytime."
            )
        
    except Exception as e:
        logger.error(f"Error processing STOP request: {str(e)}", exc_info=True)
        # Still send basic opt-out confirmation
        send_message(
            phone_number,
            "You have been unsubscribed. Reply START to resubscribe."
        )


def _handle_start_keyword(phone_number: str):
    """
    Handle START, UNSTOP keywords
    Opts user back in to receive messages
    """
    logger.info(f"Processing START request from {phone_number}")
    
    try:
        # Find user by phone number
        response = table.scan(
            FilterExpression=Attr("phoneNumber").eq(phone_number)
        )
        
        if not response.get("Items"):
            logger.info(f"No user found for phone {phone_number}, sending welcome message")
            send_message(
                phone_number,
                "Welcome back to Versiful! 🙏\n\n"
                "Text us your questions or what you're facing, and we'll respond with "
                "biblical wisdom and guidance.\n\n"
                "Register at https://versiful.io for unlimited messages and saved conversations."
            )
            return
        
        user = response["Items"][0]
        user_id = user.get("userId")
        
        # Update opt-out status
        table.update_item(
            Key={"userId": user_id},
            UpdateExpression="SET optedOut = :opted_out, updatedAt = :now REMOVE optedOutAt",
            ExpressionAttributeValues={
                ":opted_out": False,
                ":now": datetime.now(timezone.utc).isoformat()
            }
        )
        
        logger.info(f"User {user_id} opted back in")
        
        # Send welcome back message
        first_name = user.get("firstName", "")
        greeting = f"Welcome back, {first_name}!" if first_name else "Welcome back to Versiful!"
        
        send_message(
            phone_number,
            f"{greeting} 🙏\n\n"
            f"You're now subscribed to receive messages again. Text us anytime for "
            f"guidance and wisdom from Scripture.\n\n"
            f"Visit https://versiful.io to manage your account."
        )
        
    except Exception as e:
        logger.error(f"Error processing START request: {str(e)}", exc_info=True)
        send_message(
            phone_number,
            "Welcome back! You're now subscribed to Versiful messages."
        )


def _handle_help_keyword(phone_number: str):
    """
    Handle HELP keyword
    Provides support information and commands
    """
    logger.info(f"Processing HELP request from {phone_number}")
    
    help_message = (
        "VERSIFUL HELP 📖\n\n"
        "Text us your questions or what you're facing, and we'll respond with "
        "biblical guidance.\n\n"
        "COMMANDS:\n"
        "• STOP - Unsubscribe from messages\n"
        "• START - Resubscribe to messages\n"
        "• HELP - Show this help message\n\n"
        "SUPPORT:\n"
        "Visit: https://versiful.io\n"
        "Email: support@versiful.com\n"
        "Text: 833-681-1158\n\n"
        "Message & data rates may apply."
    )
    
    send_message(phone_number, help_message)


def _is_keyword_command(body: str) -> tuple[bool, str]:
    """
    Check if message is a keyword command (STOP, START, HELP, etc.)
    Returns (is_keyword, keyword_type)
    """
    if not body:
        return (False, None)
    
    normalized = body.strip().upper()
    
    # STOP variants (TCPA required)
    if normalized in ["STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"]:
        return (True, "STOP")
    
    # START variants (TCPA required)
    if normalized in ["START", "UNSTOP"]:
        return (True, "START")
    
    # HELP (TCPA required)
    if normalized in ["HELP", "INFO"]:
        return (True, "HELP")
    
    return (False, None)


def _get_or_create_posthog_id(phone_number: str) -> str:
    """
    Get or create a PostHog anonymous ID for unregistered SMS user.
    Stores mapping in sms-usage table for later linking when user registers.
    
    Args:
        phone_number: Normalized phone number (e.g., "+15551234567")
        
    Returns:
        PostHog distinct_id (UUID string)
    """
    # Check if we already have a PostHog ID for this phone
    usage = get_sms_usage(phone_number)
    
    if usage and usage.get('posthogAnonymousId'):
        logger.info(f"Found existing PostHog anonymous ID for {phone_number}")
        return usage['posthogAnonymousId']
    
    # Generate new UUID for PostHog
    anonymous_id = str(uuid4())
    
    try:
        # Store in sms-usage table
        sms_usage_table.update_item(
            Key={'phoneNumber': phone_number},
            UpdateExpression='SET posthogAnonymousId = :id, updatedAt = :now',
            ExpressionAttributeValues={
                ':id': anonymous_id,
                ':now': datetime.now(timezone.utc).isoformat()
            }
        )
        logger.info(f"Created PostHog anonymous ID for {phone_number}: {anonymous_id}")
    except Exception as e:
        logger.error(f"Failed to store PostHog anonymous ID: {str(e)}")
    
    return anonymous_id


def _identify_sms_user(phone_number: str, user_id: str = None, user_profile: dict = None) -> str:
    """
    Identify user in PostHog for SMS activity.
    
    For registered users: Use their userId as distinct_id
    For unregistered users: Get/create anonymous UUID and use as distinct_id
    
    Args:
        phone_number: Full phone number (e.g., "+15551234567")
        user_id: DynamoDB userId if registered
        user_profile: Full user profile from DynamoDB
    
    Returns:
        distinct_id to use for PostHog events
    """
    if not posthog:
        logger.warning("PostHog not initialized, skipping identification")
        # Can't use regex in f-string, compute separately
        phone_digits = re.sub(r'\D', '', phone_number)
        return user_id if user_id else f"fallback_{phone_digits}"
    
    if user_id and user_profile:
        # REGISTERED USER - Use real userId
        distinct_id = user_id
        
        properties = {
            'email': user_profile.get('email'),
            'phone_number': phone_number,
            'first_name': user_profile.get('firstName'),
            'last_name': user_profile.get('lastName'),
            'plan': user_profile.get('plan', 'free'),
            'is_subscribed': user_profile.get('isSubscribed', False),
            'bible_version': user_profile.get('bibleVersion'),
            'registration_status': 'registered',
            'channel': 'sms',
        }
        
        logger.info(f"Identifying registered SMS user: {user_id}")
    else:
        # UNREGISTERED USER - Get/create anonymous ID
        distinct_id = _get_or_create_posthog_id(phone_number)
        
        properties = {
            'phone_number': phone_number,
            'registration_status': 'unregistered',
            'channel': 'sms',
            'first_seen_at': datetime.utcnow().isoformat(),
        }
        
        logger.info(f"Identifying unregistered SMS user: {distinct_id}")
    
    # Identify in PostHog
    try:
        posthog.identify(
            distinct_id=distinct_id,
            properties=properties
        )
    except Exception as e:
        logger.error(f"Failed to identify user in PostHog: {str(e)}")
    
    return distinct_id


def _invoke_chat_handler(thread_id: str, message: str, user_id: str = None, phone_number: str = None, posthog_distinct_id: str = None):
    """
    Invoke the chat Lambda function
    
    Args:
        thread_id: Thread identifier (phone number for SMS)
        message: User's message
        user_id: Optional user ID
        phone_number: Phone number
        posthog_distinct_id: PostHog distinct_id for event tracking
        
    Returns:
        Response from chat handler
    """
    payload = {
        'thread_id': thread_id,
        'message': message,
        'channel': 'sms',
        'user_id': user_id,
        'phone_number': phone_number,
        'posthog_distinct_id': posthog_distinct_id
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

    # Check if message is a keyword command (STOP, START, HELP)
    is_keyword, keyword_type = _is_keyword_command(body)
    
    if is_keyword:
        logger.info(f"Processing keyword command: {keyword_type}")
        
        if keyword_type == "STOP":
            _handle_stop_keyword(from_num_normalized)
        elif keyword_type == "START":
            _handle_start_keyword(from_num_normalized)
        elif keyword_type == "HELP":
            _handle_help_keyword(from_num_normalized)
        
        return _success_response()

    # Check if user is opted out
    try:
        response = table.scan(
            FilterExpression=Attr("phoneNumber").eq(from_num_normalized)
        )
        
        if response.get("Items"):
            user = response["Items"][0]
            if user.get("optedOut", False):
                logger.info(f"User {from_num_normalized} is opted out, ignoring message")
                # Don't respond to opted-out users (except for START/HELP)
                return _success_response()
    except Exception as e:
        logger.warning(f"Error checking opt-out status: {str(e)}")
        # Continue processing if we can't check opt-out status

    logger.info("Message body found!")
    try:
        # Check if this is a first-time texter (no sms_usage record exists)
        # We check BEFORE _evaluate_usage creates the record
        existing_usage = sms_usage_table.get_item(Key={"phoneNumber": from_num_normalized}).get("Item")
        
        is_first_time_texter = existing_usage is None
        
        # If first-time texter, send welcome message
        if is_first_time_texter:
            logger.info(f"First-time texter detected: {from_num_normalized}")
            send_first_time_texter_welcome_sms(from_num_normalized)
        
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

        # Get user_id and profile if available
        user_id = decision.get("user_profile", {}).get("userId") if decision.get("user_profile") else None
        user_profile = decision.get("user_profile")

        # Identify user in PostHog (registered or anonymous)
        posthog_distinct_id = _identify_sms_user(from_num_normalized, user_id, user_profile)

        # Invoke chat handler with phone number as thread_id
        logger.info("Invoking chat handler for SMS with PostHog distinct_id: %s", posthog_distinct_id)
        chat_result = _invoke_chat_handler(
            thread_id=from_num_normalized,  # Phone number is the thread ID for SMS
            message=body,
            user_id=user_id,
            phone_number=from_num_normalized,
            posthog_distinct_id=posthog_distinct_id
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
