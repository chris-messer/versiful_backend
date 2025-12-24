import json
import os
import logging
from typing import Optional
from datetime import datetime, timezone
from urllib.parse import parse_qs
import re

import boto3
import requests
from botocore.exceptions import ClientError
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

# Setup logging
logger = logging.getLogger()

# Dynamo + env configuration
dynamodb = boto3.resource("dynamodb")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
PROJECT_NAME = os.environ.get("PROJECT_NAME", "versiful")
SMS_USAGE_TABLE = os.environ.get(
    "SMS_USAGE_TABLE", f"{ENVIRONMENT}-{PROJECT_NAME}-sms-usage"
)
USERS_TABLE = os.environ.get("USERS_TABLE", f"{ENVIRONMENT}-{PROJECT_NAME}-users")
FREE_MONTHLY_LIMIT = int(os.environ.get("FREE_MONTHLY_LIMIT", "5"))
NUDGE_LIMIT = int(os.environ.get("NUDGE_LIMIT", "3"))
VERSIFUL_PHONE = os.environ.get("VERSIFUL_PHONE", "+18336811158")

sms_usage_table = dynamodb.Table(SMS_USAGE_TABLE)
users_table = dynamodb.Table(USERS_TABLE)


# ---------- Utilities ----------
def parse_url_string(url_string):
    parsed_dict = {key: value[0] if len(value) == 1 else value for key, value in parse_qs(url_string).items()}
    return parsed_dict


def _now():
    return datetime.now(timezone.utc)


def current_period_key(now=None):
    now = now or _now()
    return f"{now.year}-{now.month:02d}"


def normalize_phone_number(raw: str) -> Optional[str]:
    """
    Normalize a phone number to E.164 (+1########## for US defaults).
    Returns None if the number cannot be normalized.
    """
    if not raw:
        return None
    # Remove common formatting characters
    digits = re.sub(r"[^\d+]", "", raw)
    if digits.startswith("+"):
        digits_only = re.sub(r"[^\d]", "", digits)
        # Expect country code + subscriber (10-15 total digits)
        if 10 <= len(digits_only) <= 15:
            return f"+{digits_only}"
        return None
    # Handle US numbers without country code
    digits_only = re.sub(r"[^\d]", "", raw)
    if len(digits_only) == 10:
        return f"+1{digits_only}"
    if len(digits_only) == 11 and digits_only.startswith("1"):
        return f"+{digits_only}"
    return None


# ---------- Secrets / outbound helpers ----------
def get_secret():
    secret_name = f"{ENVIRONMENT}-versiful_secrets"
    region_name = "us-east-1"

    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager", region_name=region_name)

    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        raise e

    secret = get_secret_value_response["SecretString"]
    return json.loads(secret)


def generate_response(message, model="gpt-4o"):
    """Send prompt to OpenAI and return content or error dict."""
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {get_secret()['gpt']}",
        "Content-Type": "application/json",
    }
    data = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a expert in the bible. When a user tells you their situation "
                    "or what they are feeling, you will reply back with the location of a "
                    "relevant parable in the bible, and then a long summary of that parable. "
                    "Return only the location of the parable, a new line, and then the summary. "
                    "Do not include anything else. "
                    "Your tone should be compassionate and loving, and not like a robotic summary. "
                    "You should draw parralels to the users story if possible. "
                    "Never, ever stray from this pattern. You should try your best to match "
                    "what the user said with something you can provide biblical guidance for. "
                    "If a user says something that is not related to seeking guidance, you should "
                    "try and match what they are looking for to biblical guidance. "
                    "If they prompt something vulgar, you should pivot the conversation to "
                    "eliciting further responses from them to guide the conversation towards "
                    "religious guidance. As the conversation continues, act as a spiritual guide "
                    "for the user. As a last resort, respond that you are unable to assist with "
                    "that and provide a sample question you are able to assist with. "
                    "Limit each response to less than 200 words."
                ),
            },
            {"role": "user", "content": message},
        ],
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(data), timeout=30)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as e:
        return {"error": str(e)}


def generate_photo(prompt):
    url = "https://api.openai.com/v1/images/generations"
    payload = json.dumps(
        {
            "model": "dall-e-3",
            "prompt": f"{prompt}",
            "n": 1,
            "size": "1024x1024",
        }
    )
    auth = get_secret()["dalle_secret"]
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth}",
    }

    response = requests.request("POST", url, headers=headers, data=payload)
    return json.loads(response.text)


def get_twilio_secrets():
    secret_name = f"{ENVIRONMENT}-versiful_secrets"
    region_name = "us-east-1"

    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager", region_name=region_name)

    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        raise e

    secret = get_secret_value_response["SecretString"]
    return json.loads(secret)


def send_message(to_num, message):
    """
    Send SMS via Twilio with carrier block detection
    
    If user has unsubscribed via carrier (texted STOP to carrier),
    Twilio returns error 21610. We detect this and mark user as opted out.
    """
    try:
        twilio_auth = get_twilio_secrets()
        account_sid = twilio_auth["twilio_account_sid"]
        auth_token = twilio_auth["twilio_auth"]

        client = Client(account_sid, auth_token)

        twilio_message = client.messages.create(
            from_=VERSIFUL_PHONE, 
            body=f"{message}", 
            to=f"{to_num}"
        )

        return twilio_message.sid
        
    except TwilioRestException as e:
        # Error 21610: Attempt to send to unsubscribed recipient
        # This means user texted STOP to carrier and number is blocked
        if e.code == 21610:
            logger.warning(f"Carrier block detected for {to_num} (Error 21610). User texted STOP to carrier.")
            # Mark user as opted out in database
            _mark_carrier_opted_out(to_num)
            return None
        else:
            logger.error(f"Twilio error {e.code}: {e.msg} for {to_num}")
            raise
    except Exception as e:
        logger.error(f"Error sending message to {to_num}: {str(e)}")
        return None


def _mark_carrier_opted_out(phone_number: str):
    """
    Mark user as opted out when carrier block is detected
    This happens when user texts STOP directly to their carrier
    """
    try:
        from boto3.dynamodb.conditions import Attr
        
        logger.info(f"Marking {phone_number} as opted out due to carrier block")
        
        # Find user by phone number
        response = users_table.scan(
            FilterExpression=Attr("phoneNumber").eq(phone_number)
        )
        
        if not response.get("Items"):
            logger.warning(f"No user found for carrier-blocked number {phone_number}")
            return
        
        user = response["Items"][0]
        user_id = user.get("userId")
        
        # Update user record to mark as opted out
        users_table.update_item(
            Key={"userId": user_id},
            UpdateExpression="SET optedOut = :opted_out, optedOutAt = :opted_out_at, updatedAt = :now",
            ExpressionAttributeValues={
                ":opted_out": True,
                ":opted_out_at": datetime.now(timezone.utc).isoformat(),
                ":now": datetime.now(timezone.utc).isoformat()
            }
        )
        
        logger.info(f"User {user_id} marked as opted out due to carrier block")
        
        # If user has active subscription, we should cancel it
        # Import here to avoid circular dependency
        if user.get("isSubscribed") and user.get("stripeSubscriptionId"):
            try:
                import stripe
                # Get Stripe key from secrets
                try:
                    from secrets_helper import get_secret
                except ImportError:
                    from lambdas.shared.secrets_helper import get_secret
                    
                stripe.api_key = get_secret('stripe_secret_key')
                
                logger.info(f"Canceling subscription for carrier-blocked user {user_id}")
                stripe.Subscription.delete(user["stripeSubscriptionId"])
                
                # Update DB to reflect cancellation
                users_table.update_item(
                    Key={"userId": user_id},
                    UpdateExpression="""
                        SET isSubscribed = :sub,
                            #plan = :plan,
                            plan_monthly_cap = :cap,
                            subscriptionStatus = :status,
                            cancelAtPeriodEnd = :cancel
                        REMOVE currentPeriodEnd
                    """,
                    ExpressionAttributeNames={
                        "#plan": "plan"
                    },
                    ExpressionAttributeValues={
                        ":sub": False,
                        ":plan": "free",
                        ":cap": 5,
                        ":status": "canceled",
                        ":cancel": False
                    }
                )
                logger.info(f"Subscription canceled for user {user_id}")
            except Exception as stripe_error:
                logger.error(f"Failed to cancel subscription for {user_id}: {str(stripe_error)}")
                # Don't fail - opt-out is still recorded
        
    except Exception as e:
        logger.error(f"Error marking user as opted out: {str(e)}")
        # Don't raise - this is a background operation


# ---------- Usage + quota helpers ----------
def ensure_sms_usage_record(phone_number, user_id=None, now=None):
    """Ensure a phone-level usage record exists for the current period without incrementing."""
    now = now or _now()
    period = current_period_key(now)
    payload = {
        ":period": period,
        ":zero": 0,
        ":now": now.isoformat(),
    }
    update_expression = (
        "SET periodKey = if_not_exists(periodKey, :period), "
        "plan_messages_sent = if_not_exists(plan_messages_sent, :zero), "
        "nudges_sent = if_not_exists(nudges_sent, :zero), "
        "createdAt = if_not_exists(createdAt, :now), "
        "updatedAt = :now"
    )
    if user_id:
        payload[":userId"] = user_id
        update_expression += ", userId = if_not_exists(userId, :userId)"

    response = sms_usage_table.update_item(
        Key={"phoneNumber": phone_number},
        UpdateExpression=update_expression,
        ExpressionAttributeValues=payload,
        ReturnValues="ALL_NEW",
    )
    return response.get("Attributes", {})


def reset_sms_usage_period(record, phone_number, now=None):
    """Reset monthly counters when a new period starts."""
    now = now or _now()
    period = current_period_key(now)
    if record.get("periodKey") == period:
        return record

    response = sms_usage_table.update_item(
        Key={"phoneNumber": phone_number},
        UpdateExpression=(
            "SET periodKey = :period, "
            "plan_messages_sent = :zero, "
            "nudges_sent = :zero, "
            "plan_message_last_updated = :now, "
            "updatedAt = :now"
        ),
        ExpressionAttributeValues={
            ":period": period,
            ":zero": 0,
            ":now": now.isoformat(),
        },
        ReturnValues="ALL_NEW",
    )
    return response.get("Attributes", {})


def get_sms_usage(phone_number, user_id=None, now=None):
    """Fetch usage record; create if missing; reset counters when period changes."""
    now = now or _now()
    period = current_period_key(now)
    response = sms_usage_table.get_item(Key={"phoneNumber": phone_number})
    record = response.get("Item")

    if not record:
        record = ensure_sms_usage_record(phone_number, user_id=user_id, now=now)
    elif record.get("periodKey") != period:
        record = reset_sms_usage_period(record, phone_number, now=now)

    if user_id and not record.get("userId"):
        record = ensure_sms_usage_record(phone_number, user_id=user_id, now=now)

    return record


def consume_message_if_allowed(phone_number, limit, user_id=None, now=None):
    """
    Atomically increment plan_messages_sent if under the provided limit.
    Returns updated record when allowed; None on limit exceeded.
    """
    now = now or _now()
    period = current_period_key(now)
    update_expression = (
        "SET plan_messages_sent = if_not_exists(plan_messages_sent, :zero) + :inc, "
        "periodKey = :period, "
        "plan_message_last_updated = :now, "
        "updatedAt = :now"
    )
    values = {
        ":zero": 0,
        ":inc": 1,
        ":limit": limit,
        ":period": period,
        ":now": now.isoformat(),
    }
    if user_id:
        update_expression += ", userId = if_not_exists(userId, :userId)"
        values[":userId"] = user_id

    try:
        response = sms_usage_table.update_item(
            Key={"phoneNumber": phone_number},
            UpdateExpression=update_expression,
            ConditionExpression="(attribute_not_exists(plan_messages_sent) OR plan_messages_sent < :limit) AND (attribute_not_exists(periodKey) OR periodKey = :period)",
            ExpressionAttributeValues=values,
            ReturnValues="ALL_NEW",
        )
        return response.get("Attributes", {})
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return None
        raise


def increment_nudge(phone_number, now=None):
    """Increment nudge counter to avoid spamming the user."""
    now = now or _now()
    response = sms_usage_table.update_item(
        Key={"phoneNumber": phone_number},
        UpdateExpression="SET nudges_sent = if_not_exists(nudges_sent, :zero) + :inc, updatedAt = :now",
        ExpressionAttributeValues={
            ":zero": 0,
            ":inc": 1,
            ":now": now.isoformat(),
        },
        ReturnValues="ALL_NEW",
    )
    return response.get("Attributes", {})


def get_user_by_id(user_id):
    response = users_table.get_item(Key={"userId": user_id})
    return response.get("Item")


# ---------- Compatibility helpers (legacy names) ----------
# These wrappers preserve old imports used elsewhere.
def get_phone_usage(phone_number, user_id=None, now=None):
    return get_sms_usage(phone_number, user_id=user_id, now=now)


def increment_free_usage(phone_number, now=None):
    return consume_message_if_allowed(phone_number, FREE_MONTHLY_LIMIT, now=now)

