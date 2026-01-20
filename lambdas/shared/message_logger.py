"""
Message Logger - Centralized logging for all messages (SMS, chat, system)
Logs to DynamoDB chat-messages table and sends events to PostHog
"""
import os
import json
import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any

import boto3
from botocore.exceptions import ClientError

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

# PostHog setup
try:
    from posthog import Posthog
    
    POSTHOG_API_KEY = os.environ.get('POSTHOG_API_KEY')
    posthog_client = None
    
    if POSTHOG_API_KEY:
        posthog_client = Posthog(
            POSTHOG_API_KEY,
            host='https://us.i.posthog.com'
        )
        logger.info("PostHog initialized for message logging")
    else:
        logger.warning("PostHog API key not found, events will not be sent")
except ImportError:
    logger.warning("PostHog not available, events will not be sent")
    posthog_client = None


def log_sms_message(
    thread_id: str,
    direction: str,  # 'inbound' or 'outbound'
    from_number: str,
    to_number: str,
    body: str,
    twilio_sid: str,
    user_id: Optional[str] = None,
    message_type: str = 'chat',  # 'chat', 'welcome', 'notification'
    num_segments: int = 1
) -> str:
    """
    Log an SMS message to DynamoDB and PostHog
    
    Args:
        thread_id: Thread identifier (phone number for SMS)
        direction: 'inbound' or 'outbound'
        from_number: Sender phone number (E.164 format)
        to_number: Recipient phone number (E.164 format)
        body: Message content
        twilio_sid: Twilio message SID
        user_id: Optional user ID
        message_type: Type of message ('chat', 'welcome', 'notification')
        num_segments: Number of SMS segments
        
    Returns:
        messageId (UUID) for tracking
    """
    now = datetime.utcnow()
    timestamp = now.isoformat() + 'Z'
    message_id = str(uuid.uuid4())
    
    # Determine role based on direction
    role = 'user' if direction == 'inbound' else 'assistant'
    
    # Build message record
    message = {
        'threadId': thread_id,
        'timestamp': timestamp,
        'messageId': message_id,
        'role': role,
        'content': body,
        'channel': 'sms',
        'createdAt': timestamp,
        'updatedAt': timestamp,
        'metadata': {
            'twilioSid': twilio_sid,
            'direction': direction,
            'messageType': message_type,
            'numSegments': num_segments
        }
    }
    
    if user_id:
        message['userId'] = user_id
    
    # Always set phoneNumber based on direction
    if direction == 'inbound':
        message['phoneNumber'] = from_number
    else:
        message['phoneNumber'] = to_number
    
    # Save to DynamoDB
    try:
        messages_table.put_item(Item=message)
        logger.info(f"Logged {direction} SMS message: {message_id} (SID: {twilio_sid})")
    except ClientError as e:
        logger.error(f"Error saving SMS message to DynamoDB: {str(e)}")
        # Don't raise - we still want to send PostHog event
    
    # Send PostHog event
    if posthog_client:
        try:
            event_name = f'sms_{direction}'
            
            # Determine distinct_id
            if user_id:
                distinct_id = user_id
            else:
                # Use phone number without symbols
                import re
                distinct_id = re.sub(r'\D', '', from_number if direction == 'inbound' else to_number)
            
            # Build properties with user_id for joining
            properties = {
                'message_uuid': message_id,
                'thread_id': thread_id,
                'from': from_number,
                'to': to_number,
                'twilio_sid': twilio_sid,
                'direction': direction,
                'message_type': message_type,
                'segments': num_segments,
                'channel': 'sms',
                'environment': ENVIRONMENT,
                'timestamp': timestamp
            }
            
            # Add user_id if available (for joining with user data)
            if user_id:
                properties['user_id'] = user_id
            
            posthog_client.capture(
                distinct_id=distinct_id,
                event=event_name,
                properties=properties
            )
            
            # Flush immediately for Lambda
            posthog_client.flush()
            
            logger.info(f"Sent {event_name} event to PostHog for message: {message_id}")
        except Exception as e:
            logger.error(f"Error sending PostHog event: {str(e)}")
    
    return message_id


def update_sms_cost(
    message_id: str,
    price: float,
    price_unit: str = 'USD',
    status: str = 'delivered',
    num_segments: int = 1
) -> bool:
    """
    Update an existing message with Twilio cost data
    Uses MessageUuidIndex GSI to find the message by UUID
    
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
                # Get user_id and distinct_id from message
                user_id = message.get('userId')
                distinct_id = user_id
                
                if not distinct_id and message.get('phoneNumber'):
                    import re
                    distinct_id = re.sub(r'\D', '', message['phoneNumber'])
                
                direction = message.get('metadata', {}).get('direction', 'unknown')
                twilio_sid = message.get('metadata', {}).get('twilioSid', 'unknown')
                thread_id = message.get('threadId')
                
                # Build properties with user_id for joining
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
                
                # Add user_id if available (for joining with user data)
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


def get_message_by_uuid(message_id: str) -> Optional[Dict[str, Any]]:
    """
    Look up a message by its UUID using the MessageUuidIndex GSI
    
    Args:
        message_id: Message UUID
        
    Returns:
        Message dict or None if not found
    """
    try:
        response = messages_table.query(
            IndexName='MessageUuidIndex',
            KeyConditionExpression='messageId = :mid',
            ExpressionAttributeValues={':mid': message_id},
            Limit=1
        )
        
        if response.get('Items'):
            return response['Items'][0]
        
        return None
        
    except ClientError as e:
        logger.error(f"Error looking up message by UUID: {str(e)}")
        return None


# For testing
if __name__ == "__main__":
    print("Message Logger Test")
    print("=" * 50)
    
    # Test logging an outbound SMS
    msg_id = log_sms_message(
        thread_id="+12345678901",
        direction="outbound",
        from_number="+19876543210",
        to_number="+12345678901",
        body="Test message",
        twilio_sid="SM_TEST123",
        message_type="chat",
        num_segments=1
    )
    
    print(f"Logged message: {msg_id}")
    
    # Test cost update
    success = update_sms_cost(
        message_id=msg_id,
        price=-0.0079,
        price_unit="USD",
        status="delivered",
        num_segments=1
    )
    
    print(f"Cost update: {'success' if success else 'failed'}")
    
    # Test lookup
    message = get_message_by_uuid(msg_id)
    if message:
        print(f"Found message: {json.dumps(message, default=str, indent=2)}")
    else:
        print("Message not found")

