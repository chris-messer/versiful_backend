"""
SMS Notification Helper
Provides functions to send lifecycle SMS notifications to users
"""
import os
import json
import logging
from twilio.rest import Client

logger = logging.getLogger()

# Import secrets helper
try:
    from secrets_helper import get_secret, get_secrets
except ImportError:
    # Fallback for local testing
    from lambdas.shared.secrets_helper import get_secret, get_secrets


VERSIFUL_PHONE = "+18336811158"
VERSIFUL_DOMAIN = "versiful.io"


def get_twilio_client():
    """Initialize and return Twilio client"""
    secrets = get_secrets()
    account_sid = secrets.get("twilio_account_sid")
    auth_token = secrets.get("twilio_auth")
    
    if not account_sid or not auth_token:
        raise ValueError("Twilio credentials not found in secrets")
    
    return Client(account_sid, auth_token)


def generate_vcard():
    """
    Generate a vCard contact card for Versiful
    This allows users to easily add Versiful to their contacts
    """
    vcard = """BEGIN:VCARD
VERSION:3.0
FN:Versiful
ORG:Versiful
TEL;TYPE=CELL:+18336811158
URL:https://versiful.io
NOTE:Biblical guidance and wisdom via text message
END:VCARD"""
    return vcard


def send_sms(phone_number: str, message: str, media_url: str = None):
    """
    Send an SMS message to a phone number
    
    Args:
        phone_number: E.164 formatted phone number (e.g. +1##########)
        message: Message body
        media_url: Optional media URL (for MMS with vCard)
    
    Returns:
        message_sid on success, None on failure
    """
    try:
        client = get_twilio_client()
        
        kwargs = {
            "from_": VERSIFUL_PHONE,
            "body": message,
            "to": phone_number
        }
        
        if media_url:
            kwargs["media_url"] = [media_url]
        
        twilio_message = client.messages.create(**kwargs)
        logger.info(f"SMS sent to {phone_number}: {twilio_message.sid}")
        return twilio_message.sid
        
    except Exception as e:
        logger.error(f"Failed to send SMS to {phone_number}: {str(e)}")
        return None


def send_welcome_sms(phone_number: str):
    """
    Send welcome message when user first registers their phone number
    Includes information about free tier and link to subscribe
    """
    message = (
        f"Welcome to Versiful! 🙏\n\n"
        f"You have 5 free messages per month. Text us anytime for biblical guidance and wisdom.\n\n"
        f"Want unlimited messages? Subscribe at https://{VERSIFUL_DOMAIN}\n\n"
        f"Save this number to your contacts for easy access!"
    )
    
    logger.info(f"Sending welcome SMS to {phone_number}")
    return send_sms(phone_number, message)


def send_subscription_confirmation_sms(phone_number: str):
    """
    Send confirmation message when user subscribes to paid plan
    """
    message = (
        f"Thank you for subscribing to Versiful! 🎉\n\n"
        f"You now have unlimited messages. Text us anytime for guidance, wisdom, and comfort from Scripture.\n\n"
        f"We're honored to walk with you on your spiritual journey."
    )
    
    logger.info(f"Sending subscription confirmation SMS to {phone_number}")
    return send_sms(phone_number, message)


def send_cancellation_sms(phone_number: str):
    """
    Send message when user cancels their subscription
    Informs them they've been moved back to free tier
    """
    message = (
        f"We're sorry to see you go! 😢\n\n"
        f"Your subscription has been canceled and you've been moved back to our free plan with 5 messages per month.\n\n"
        f"You're always welcome back. Text us anytime or resubscribe at https://{VERSIFUL_DOMAIN}\n\n"
        f"Blessings on your journey! 🙏"
    )
    
    logger.info(f"Sending cancellation SMS to {phone_number}")
    return send_sms(phone_number, message)

