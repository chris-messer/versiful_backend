"""
SMS Notification Helper
Provides functions to send lifecycle SMS notifications to users
"""
import os
import logging

logger = logging.getLogger()

# Import SMS operations (unified module)
try:
    from sms_operations import send_sms as send_sms_operation
except ImportError:
    # Fallback for different import contexts
    import sys
    sys.path.append(os.path.dirname(__file__))
    from sms_operations import send_sms as send_sms_operation


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


def send_welcome_sms(phone_number: str, first_name: str = None, user_id: str = None):
    """
    Send welcome message when user first registers their phone number
    Includes information about free tier, link to subscribe, and vCard to save contact
    
    Args:
        phone_number: E.164 formatted phone number
        first_name: Optional first name to personalize the message
        user_id: Optional user ID for tracking
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
    message_id, twilio_sid = send_sms_operation(
        to_number=phone_number,
        message=message,
        user_id=user_id,
        message_type='welcome',
        media_url=vcard_url
    )
    return twilio_sid


def send_subscription_confirmation_sms(phone_number: str, user_id: str = None):
    """
    Send confirmation message when user subscribes to paid plan
    """
    message = (
        f"Thank you for subscribing to Versiful! 🎉\n\n"
        f"You now have unlimited messages. Text us anytime for guidance, wisdom, and comfort from Scripture.\n\n"
        f"We're honored to walk with you on your spiritual journey."
    )
    
    logger.info(f"Sending subscription confirmation SMS to {phone_number}")
    message_id, twilio_sid = send_sms_operation(
        to_number=phone_number,
        message=message,
        user_id=user_id,
        message_type='subscription'
    )
    return twilio_sid


def send_cancellation_sms(phone_number: str, user_id: str = None):
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
    message_id, twilio_sid = send_sms_operation(
        to_number=phone_number,
        message=message,
        user_id=user_id,
        message_type='cancellation'
    )
    return twilio_sid


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
    message_id, twilio_sid = send_sms_operation(
        to_number=phone_number,
        message=message,
        message_type='welcome'
    )
    return twilio_sid

