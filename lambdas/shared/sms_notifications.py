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


VERSIFUL_PHONE = os.environ.get("VERSIFUL_PHONE", "+18336811158")
VERSIFUL_DOMAIN = "versiful.io"

# vCard URL - hosted in S3 (environment-specific files with correct phone numbers)
# Format: https://{env}.versiful.io/versiful-contact.vcf
def get_vcard_url(environment=None):
    """Get the vCard URL for the current environment"""
    if not environment:
        environment = os.environ.get("ENVIRONMENT", "dev")
    
    if environment == "prod":
        return f"https://{VERSIFUL_DOMAIN}/versiful-contact.vcf"
    else:
        return f"https://{environment}.{VERSIFUL_DOMAIN}/versiful-contact.vcf"


def get_twilio_client():
    """Initialize and return Twilio client"""
    secrets = get_secrets()
    account_sid = secrets.get("twilio_account_sid")
    auth_token = secrets.get("twilio_auth")
    
    if not account_sid or not auth_token:
        raise ValueError("Twilio credentials not found in secrets")
    
    return Client(account_sid, auth_token)


def send_sms(phone_number: str, message: str, media_url: str = None):
    """
    Send an SMS/MMS message to a phone number
    
    Args:
        phone_number: E.164 formatted phone number (e.g. +1##########)
        message: Message body
        media_url: Optional media URL (for MMS with vCard or images)
    
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


def send_welcome_sms(phone_number: str, first_name: str = None):
    """
    Send welcome message when user first registers their phone number
    Includes information about free tier, link to subscribe, and vCard to save contact
    
    Args:
        phone_number: E.164 formatted phone number
        first_name: Optional first name to personalize the message
    """
    # Personalize greeting if we have a first name
    greeting = f"Welcome to Versiful, {first_name}! 🙏" if first_name else "Welcome to Versiful! 🙏"
    
    message = (
        f"{greeting}\n\n"
        f"You have 5 free messages per month. Text us anytime for biblical guidance and wisdom.\n\n"
        f"Want unlimited messages? Subscribe at https://{VERSIFUL_DOMAIN}\n\n"
        f"Tap the contact card to save Versiful to your contacts!"
    )
    
    # Get vCard URL for current environment
    vcard_url = get_vcard_url()
    
    logger.info(f"Sending welcome SMS with vCard to {phone_number}")
    return send_sms(phone_number, message, media_url=vcard_url)


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


def send_first_time_texter_welcome_sms(phone_number: str):
    """
    Send welcome message to first-time texters who aren't registered users
    Prompts them to visit versiful.io for more information
    """
    message = (
        f"Welcome to Versiful! 🙏\n\n"
        f"We provide biblical guidance and wisdom through text.\n\n"
        f"Visit https://{VERSIFUL_DOMAIN} to create an account and unlock:\n"
        f"• Personalized guidance\n"
        f"• Saved conversation history\n"
        f"• Unlimited messages\n\n"
        f"Reply HELP for commands or text us your question."
    )
    
    logger.info(f"Sending first-time texter welcome SMS to {phone_number}")
    return send_sms(phone_number, message)

