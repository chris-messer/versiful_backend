"""
SMS Operations - Unified module for all SMS send/receive operations
This is the ONLY place where SMS messages are logged to DynamoDB and sent via Twilio.
"""
import os
import json
import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, Tuple

import boto3
from botocore.exceptions import ClientError
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

# Import secrets helper
try:
    from secrets_helper import get_secret
except ImportError:
    try:
        from lambdas.shared.secrets_helper import get_secret
    except ImportError:
        # For Lambda layer context
        import sys
        import os
        sys.path.append('/opt/python')
        from secrets_helper import get_secret

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# DynamoDB setup
dynamodb = boto3.resource('dynamodb')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'versiful')
CHAT_MESSAGES_TABLE = os.environ.get(
    'CHAT_MESSAGES_TABLE',
    f'{ENVIRONMENT}-{PROJECT_NAME}-chat-messages'
)
messages_table = dynamodb.Table(CHAT_MESSAGES_TABLE)

# Twilio setup
VERSIFUL_PHONE = os.environ.get("VERSIFUL_PHONE", "+18336811158")

# PostHog setup
try:
    from posthog import Posthog
    POSTHOG_API_KEY = os.environ.get('POSTHOG_API_KEY')
    posthog_client = None
    if POSTHOG_API_KEY:
        posthog_client = Posthog(POSTHOG_API_KEY, host='https://us.i.posthog.com')
        logger.info("PostHog initialized for SMS operations")
    else:
        logger.warning("PostHog API key not found, events will not be sent")
except ImportError:
    logger.warning("PostHog not available, events will not be sent")
    posthog_client = None


def get_twilio_secrets():
    """Get Twilio credentials from Secrets Manager"""
    return {
        'twilio_account_sid': get_secret('twilio_account_sid'),
        'twilio_auth': get_secret('twilio_auth')
    }


def receive_sms(
    from_number: str,
    to_number: str,
    body: str,
    twilio_sid: str,
    num_segments: int = 1,
    user_id: Optional[str] = None
) -> str:
    """
    Single entry point for all inbound SMS messages.
    Called ONLY by sms_handler when receiving SMS from Twilio.
    
    Args:
        from_number: Sender phone number (E.164 format)
        to_number: Recipient phone number (our number)
        body: Message content
        twilio_sid: Twilio message SID
        num_segments: Number of SMS segments
        user_id: Optional user ID if sender is registered
        
    Returns:
        message_id (UUID) for tracking
    """
    now = datetime.utcnow()
    timestamp = now.isoformat() + 'Z'
    message_id = str(uuid.uuid4())
    
    # Build message record
    message = {
        'threadId': from_number,  # For SMS, phone is the thread
        'timestamp': timestamp,
        'messageId': message_id,
        'twilioSid': twilio_sid,  # Top-level for easy querying
        'role': 'user',
        'content': body,
        'channel': 'sms',
        'phoneNumber': from_number,
        'createdAt': timestamp,
        'updatedAt': timestamp,
        'metadata': {
            'twilioSid': twilio_sid,  # Also in metadata for backwards compatibility
            'direction': 'inbound',
            'messageType': 'chat',
            'numSegments': num_segments
        }
    }
    
    if user_id:
        message['userId'] = user_id
    
    # Save to DynamoDB
    try:
        messages_table.put_item(Item=message)
        logger.info(f"Logged inbound SMS: {message_id} (SID: {twilio_sid})")
    except ClientError as e:
        logger.error(f"Error saving inbound SMS to DynamoDB: {str(e)}")
        # Don't raise - we still want to send PostHog event
    
    # Send PostHog event
    if posthog_client:
        try:
            import re
            distinct_id = user_id if user_id else re.sub(r'\D', '', from_number)
            
            properties = {
                'message_uuid': message_id,
                'thread_id': from_number,
                'from': from_number,
                'to': to_number,
                'twilio_sid': twilio_sid,
                'direction': 'inbound',
                'message_type': 'chat',
                'segments': num_segments,
                'channel': 'sms',
                'environment': ENVIRONMENT,
                'timestamp': timestamp
            }
            
            if user_id:
                properties['user_id'] = user_id
            
            posthog_client.capture(
                distinct_id=distinct_id,
                event='sms_inbound',
                properties=properties
            )
            posthog_client.flush()
            
            logger.info(f"Sent sms_inbound event to PostHog for message: {message_id}")
        except Exception as e:
            logger.error(f"Error sending PostHog event: {str(e)}")
    
    return message_id


def send_sms(
    to_number: str,
    message: str,
    message_id: Optional[str] = None,
    user_id: Optional[str] = None,
    message_type: str = 'chat',
    media_url: Optional[str] = None
) -> Tuple[Optional[str], Optional[str]]:
    """
    Single entry point for all outbound SMS messages.
    Called by: chat responses, system notifications, error messages, welcome messages, etc.
    
    If message_id is provided, updates existing message with Twilio metadata (for chat responses).
    Otherwise creates new message record (for system notifications).
    
    Args:
        to_number: Recipient phone number
        message: Message content
        message_id: Optional UUID of existing message to update (for chat responses)
        user_id: Optional user ID
        message_type: Type of message ('chat', 'welcome', 'notification', etc.)
        media_url: Optional media URL for MMS (images, vCards, etc.)
        
    Returns:
        Tuple of (message_id, twilio_sid) or (None, None) on failure
    """
    now = datetime.utcnow()
    timestamp = now.isoformat() + 'Z'
    
    # If no message_id provided, create new message record
    if not message_id:
        message_id = str(uuid.uuid4())
        
        message_record = {
            'threadId': to_number,
            'timestamp': timestamp,
            'messageId': message_id,
            'role': 'assistant',
            'content': message,
            'channel': 'sms',
            'phoneNumber': to_number,
            'createdAt': timestamp,
            'updatedAt': timestamp,
            'metadata': {
                'direction': 'outbound',
                'messageType': message_type
            }
        }
        
        if user_id:
            message_record['userId'] = user_id
        
        try:
            messages_table.put_item(Item=message_record)
            logger.info(f"Created outbound SMS record: {message_id}")
        except ClientError as e:
            logger.error(f"Error creating outbound SMS record: {str(e)}")
            # Continue - we'll still try to send
    
    # Send via Twilio
    try:
        twilio_auth = get_twilio_secrets()
        account_sid = twilio_auth["twilio_account_sid"]
        auth_token = twilio_auth["twilio_auth"]
        
        client = Client(account_sid, auth_token)
        
        # Add status callback URL with message_uuid for cost tracking  
        status_callback_url = f"https://api.{ENVIRONMENT}.versiful.io/sms/callback?message_uuid={message_id}"
        
        logger.info(f"Creating Twilio message with callback URL: {status_callback_url}")
        
        # Create message with required and optional parameters
        create_params = {
            'from_': VERSIFUL_PHONE,
            'to': to_number,
            'body': message,
            'status_callback': status_callback_url
        }
        
        # Only add media_url if provided
        if media_url:
            create_params['media_url'] = [media_url]
        
        logger.info(f"Twilio create_params (before sending): {list(create_params.keys())}")
        
        try:
            twilio_message = client.messages.create(**create_params)
            logger.info(f"Twilio message created. Checking response for status_callback...")
            # Check if Twilio response includes status_callback
            twilio_msg_dict = twilio_message.__dict__
            if '_properties' in twilio_msg_dict:
                props = twilio_msg_dict['_properties']
                logger.info(f"Twilio response status_callback: {props.get('status_callback', 'NOT FOUND')}")
        except Exception as e:
            logger.error(f"Error sending message with status_callback: {e}")
            # Try without status_callback as fallback
            create_params.pop('status_callback', None)
            logger.warning("Retrying message send without status_callback")
            twilio_message = client.messages.create(**create_params)
        
        twilio_sid = twilio_message.sid
        logger.info(f"Sent SMS via Twilio: {message_id} (SID: {twilio_sid})")
        
        # Update message with Twilio SID
        _update_message_twilio_metadata(
            message_id=message_id,
            twilio_sid=twilio_sid,
            status=twilio_message.status,
            message_type=message_type
        )
        
        # Send PostHog event
        if posthog_client:
            try:
                import re
                distinct_id = user_id if user_id else re.sub(r'\D', '', to_number)
                
                properties = {
                    'message_uuid': message_id,
                    'thread_id': to_number,
                    'from': VERSIFUL_PHONE,
                    'to': to_number,
                    'twilio_sid': twilio_sid,
                    'direction': 'outbound',
                    'message_type': message_type,
                    'channel': 'sms',
                    'environment': ENVIRONMENT,
                    'timestamp': timestamp
                }
                
                if user_id:
                    properties['user_id'] = user_id
                
                posthog_client.capture(
                    distinct_id=distinct_id,
                    event='sms_outbound',
                    properties=properties
                )
                posthog_client.flush()
                
                logger.info(f"Sent sms_outbound event to PostHog for message: {message_id}")
            except Exception as e:
                logger.error(f"Error sending PostHog event: {str(e)}")
        
        return (message_id, twilio_sid)
        
    except TwilioRestException as e:
        # Error 21610: Attempt to send to unsubscribed recipient
        if e.code == 21610:
            logger.warning(f"Carrier block detected for {to_number} (Error 21610). User texted STOP to carrier.")
            # Mark user as opted out
            _mark_carrier_opted_out(to_number)
            return (message_id, None)
        else:
            logger.error(f"Twilio error {e.code}: {e.msg} for {to_number}")
            return (message_id, None)
    except Exception as e:
        logger.error(f"Error sending SMS to {to_number}: {str(e)}")
        return (message_id, None)


def update_sms_cost(
    message_id: str,
    price: float,
    price_unit: str = 'USD',
    status: str = 'delivered',
    num_segments: int = 1
) -> bool:
    """
    Updates an existing message with Twilio cost data.
    Called ONLY by twilio_callback_handler when cost data arrives.
    
    Uses MessageUuidIndex GSI to find the message by UUID.
    
    Args:
        message_id: Message UUID
        price: Cost from Twilio (can be negative for inbound)
        price_unit: Currency unit (usually 'USD')
        status: Message status ('sent', 'delivered', 'failed', etc.)
        num_segments: Number of SMS segments
        
    Returns:
        True if updated successfully, False otherwise
    """
    try:
        # Look up message by messageId using GSI
        response = messages_table.query(
            IndexName='MessageUuidIndex',
            KeyConditionExpression='messageId = :mid',
            ExpressionAttributeValues={':mid': message_id},
            Limit=1
        )
        
        if not response.get('Items'):
            logger.warning(f"Message not found for UUID: {message_id}")
            return False
        
        message = response['Items'][0]
        thread_id = message['threadId']
        timestamp = message['timestamp']
        
        # Update with cost data
        now_timestamp = datetime.utcnow().isoformat() + 'Z'
        
        messages_table.update_item(
            Key={
                'threadId': thread_id,
                'timestamp': timestamp
            },
            UpdateExpression='SET #costs.#twilio = :twilio_costs, updatedAt = :now',
            ExpressionAttributeNames={
                '#costs': 'costs',
                '#twilio': 'twilio'
            },
            ExpressionAttributeValues={
                ':twilio_costs': {
                    'price': Decimal(str(price)),
                    'priceUnit': price_unit,
                    'status': status,
                    'numSegments': num_segments,
                    'timestamp': now_timestamp
                },
                ':now': now_timestamp
            }
        )
        
        logger.info(f"Updated SMS cost for message {message_id}: {price} {price_unit}")
        
        # Send PostHog cost update event
        if posthog_client:
            try:
                user_id = message.get('userId')
                distinct_id = user_id
                
                if not distinct_id and message.get('phoneNumber'):
                    import re
                    distinct_id = re.sub(r'\D', '', message['phoneNumber'])
                
                direction = message.get('metadata', {}).get('direction', 'unknown')
                twilio_sid = message.get('metadata', {}).get('twilioSid', 'unknown')
                
                properties = {
                    'message_uuid': message_id,
                    'twilio_sid': twilio_sid,
                    'price': float(price),
                    'price_unit': price_unit,
                    'status': status,
                    'segments': num_segments,
                    'direction': direction,
                    'thread_id': thread_id,
                    'environment': ENVIRONMENT,
                    'timestamp': now_timestamp
                }
                
                if user_id:
                    properties['user_id'] = user_id
                
                posthog_client.capture(
                    distinct_id=distinct_id,
                    event='sms_cost_update',
                    properties=properties
                )
                posthog_client.flush()
                
                logger.info(f"Sent sms_cost_update event to PostHog for message: {message_id}")
            except Exception as e:
                logger.error(f"Error sending PostHog cost update event: {str(e)}")
        
        return True
        
    except ClientError as e:
        logger.error(f"Error updating SMS cost: {str(e)}")
        return False


def _update_message_twilio_metadata(
    message_id: str,
    twilio_sid: str,
    status: str,
    message_type: str
) -> bool:
    """
    Internal helper to update message with Twilio SID and metadata.
    Updates both top-level twilioSid and metadata.twilioSid
    """
    try:
        response = messages_table.query(
            IndexName='MessageUuidIndex',
            KeyConditionExpression='messageId = :mid',
            ExpressionAttributeValues={':mid': message_id},
            Limit=1
        )
        
        if not response.get('Items'):
            logger.warning(f"Message not found for UUID: {message_id}")
            return False
        
        message = response['Items'][0]
        thread_id = message['threadId']
        timestamp = message['timestamp']
        
        messages_table.update_item(
            Key={
                'threadId': thread_id,
                'timestamp': timestamp
            },
            UpdateExpression='SET twilioSid = :sid, metadata.twilioSid = :sid, metadata.#status = :status, metadata.#direction = :direction, metadata.messageType = :msgtype',
            ExpressionAttributeNames={
                '#status': 'status',
                '#direction': 'direction'
            },
            ExpressionAttributeValues={
                ':sid': twilio_sid,
                ':status': status,
                ':direction': 'outbound',
                ':msgtype': message_type
            }
        )
        logger.info(f"Updated message {message_id} with Twilio metadata (SID: {twilio_sid})")
        return True
    except Exception as e:
        logger.error(f"Error updating Twilio metadata: {str(e)}")
        return False


def _mark_carrier_opted_out(phone_number: str):
    """
    Mark user as opted out when carrier block is detected (user texted STOP)
    """
    try:
        users_table = dynamodb.Table(f'{ENVIRONMENT}-{PROJECT_NAME}-users')
        
        # Find user by phone number
        response = users_table.scan(
            FilterExpression='phoneNumber = :phone',
            ExpressionAttributeValues={':phone': phone_number}
        )
        
        if response.get('Items'):
            user = response['Items'][0]
            user_id = user.get('userId')
            
            users_table.update_item(
                Key={'userId': user_id},
                UpdateExpression='SET carrierOptedOut = :opted_out, updatedAt = :now',
                ExpressionAttributeValues={
                    ':opted_out': True,
                    ':now': datetime.utcnow().isoformat() + 'Z'
                }
            )
            logger.info(f"Marked user {user_id} as carrier opted out")
        else:
            logger.warning(f"No user found for phone {phone_number} to mark as opted out")
    except Exception as e:
        logger.error(f"Error marking user as opted out: {str(e)}")

