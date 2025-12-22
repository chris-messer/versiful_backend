"""
Chat Lambda Handler - Channel-agnostic message processing
Handles message persistence, history retrieval, and agent interaction
"""
import os
import json
import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

try:
    from agent_service import get_agent_service
    from helpers import get_secret
except ImportError:
    from lambdas.chat.agent_service import get_agent_service
    from lambdas.sms.helpers import get_secret

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
CHAT_SESSIONS_TABLE = os.environ.get(
    'CHAT_SESSIONS_TABLE',
    f'{ENVIRONMENT}-{PROJECT_NAME}-chat-sessions'
)

messages_table = dynamodb.Table(CHAT_MESSAGES_TABLE)
sessions_table = dynamodb.Table(CHAT_SESSIONS_TABLE)

# Global agent service instance (reused across invocations)
_agent_service = None


def get_agent() -> Any:
    """Get or initialize agent service with API key from secrets"""
    global _agent_service
    if _agent_service is None:
        try:
            secrets = get_secret()
            api_key = secrets.get('gpt') or secrets.get('openai_api_key')
            if not api_key:
                raise ValueError("OpenAI API key not found in secrets")
            _agent_service = get_agent_service(api_key=api_key)
            logger.info("Agent service initialized")
        except Exception as e:
            logger.error("Failed to initialize agent service: %s", str(e))
            raise
    return _agent_service


def get_message_history(
    thread_id: str,
    limit: int = 20,
    before_timestamp: str = None
) -> List[Dict[str, Any]]:
    """
    Retrieve message history for a thread
    
    Args:
        thread_id: Thread identifier
        limit: Maximum number of messages to retrieve
        before_timestamp: Optional timestamp to paginate before
        
    Returns:
        List of messages sorted by timestamp (oldest first)
    """
    try:
        query_params = {
            'KeyConditionExpression': 'threadId = :tid',
            'ExpressionAttributeValues': {':tid': thread_id},
            'ScanIndexForward': False,  # Most recent first
            'Limit': limit
        }
        
        if before_timestamp:
            query_params['KeyConditionExpression'] += ' AND #ts < :before'
            query_params['ExpressionAttributeNames'] = {'#ts': 'timestamp'}
            query_params['ExpressionAttributeValues'][':before'] = before_timestamp
        
        response = messages_table.query(**query_params)
        messages = response.get('Items', [])
        
        # Convert Decimal to native types and reverse to chronological order
        messages = [_deserialize_message(m) for m in reversed(messages)]
        
        logger.info("Retrieved %d messages for thread: %s", len(messages), thread_id)
        return messages
    except ClientError as e:
        logger.error("Error retrieving messages: %s", str(e))
        return []


def save_message(
    thread_id: str,
    role: str,
    content: str,
    channel: str,
    user_id: str = None,
    phone_number: str = None,
    metadata: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Save a message to DynamoDB
    
    Args:
        thread_id: Thread identifier
        role: "user" or "assistant"
        content: Message content
        channel: "sms" or "web"
        user_id: Optional user ID
        phone_number: Optional phone number (for SMS)
        metadata: Optional metadata dict
        
    Returns:
        Saved message dict
    """
    now = datetime.utcnow()
    timestamp = now.isoformat() + 'Z'
    
    message = {
        'threadId': thread_id,
        'timestamp': timestamp,
        'messageId': str(uuid.uuid4()),
        'role': role,
        'content': content,
        'channel': channel,
        'createdAt': timestamp,
        'updatedAt': timestamp
    }
    
    if user_id:
        message['userId'] = user_id
    if phone_number:
        message['phoneNumber'] = phone_number
    if metadata:
        message['metadata'] = metadata
    
    try:
        messages_table.put_item(Item=message)
        logger.info("Saved %s message to thread: %s", role, thread_id)
        return message
    except ClientError as e:
        logger.error("Error saving message: %s", str(e))
        raise


def update_session_metadata(
    user_id: str,
    session_id: str,
    title: str = None,
    increment_count: bool = False
) -> None:
    """
    Update session metadata (message count, last message time, title)
    
    Args:
        user_id: User ID
        session_id: Session ID
        title: Optional title to set
        increment_count: Whether to increment message count
    """
    now = datetime.utcnow().isoformat() + 'Z'
    
    try:
        update_expr = 'SET lastMessageAt = :now, updatedAt = :now'
        expr_values = {':now': now}
        
        if increment_count:
            update_expr += ', messageCount = if_not_exists(messageCount, :zero) + :inc'
            expr_values[':zero'] = 0
            expr_values[':inc'] = 1
        
        if title:
            update_expr += ', title = :title'
            expr_values[':title'] = title
        
        sessions_table.update_item(
            Key={'userId': user_id, 'sessionId': session_id},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values
        )
        logger.info("Updated session metadata: %s/%s", user_id, session_id)
    except ClientError as e:
        logger.error("Error updating session: %s", str(e))


def process_chat_message(
    thread_id: str,
    message: str,
    channel: str,
    user_id: str = None,
    phone_number: str = None,
    session_id: str = None
) -> Dict[str, Any]:
    """
    Main function to process a chat message
    
    Args:
        thread_id: Thread identifier (phone for SMS, userId#sessionId for web)
        message: User's message
        channel: "sms" or "web"
        user_id: Optional user ID
        phone_number: Optional phone number
        session_id: Optional session ID (for web)
        
    Returns:
        Dict with response and metadata
    """
    logger.info("Processing chat message - thread: %s, channel: %s", thread_id, channel)
    
    try:
        # Get message history
        history = get_message_history(thread_id, limit=20)
        
        # Convert to format expected by agent
        agent_history = [
            {'role': msg['role'], 'content': msg['content']}
            for msg in history
        ]
        
        # Get agent and process
        agent = get_agent()
        result = agent.process_message(
            thread_id=thread_id,
            message=message,
            channel=channel,
            history=agent_history,
            user_id=user_id
        )
        
        assistant_response = result.get('response', '')
        
        # Save user message
        save_message(
            thread_id=thread_id,
            role='user',
            content=message,
            channel=channel,
            user_id=user_id,
            phone_number=phone_number
        )
        
        # Save assistant response
        save_message(
            thread_id=thread_id,
            role='assistant',
            content=assistant_response,
            channel=channel,
            user_id=user_id,
            metadata={'model': 'gpt-4o'}  # Could get from config
        )
        
        # Update session metadata if web channel
        if channel == 'web' and user_id and session_id:
            # Generate title if this is first message
            if len(history) == 0:
                title = agent.get_conversation_title([
                    {'role': 'user', 'content': message}
                ])
                update_session_metadata(user_id, session_id, title=title, increment_count=True)
            else:
                update_session_metadata(user_id, session_id, increment_count=True)
        
        return {
            'success': True,
            'response': assistant_response,
            'thread_id': thread_id,
            'channel': channel,
            'needs_crisis_intervention': result.get('needs_crisis_intervention', False)
        }
        
    except Exception as e:
        logger.error("Error processing chat message: %s", str(e))
        return {
            'success': False,
            'error': str(e),
            'response': 'I apologize, but I encountered an error processing your message. Please try again.'
        }


def _deserialize_message(item: Dict[str, Any]) -> Dict[str, Any]:
    """Convert DynamoDB Decimal types to native Python types"""
    return json.loads(json.dumps(item, default=str))


def handler(event, context):
    """
    Lambda handler for direct invocation (used by SMS and Web lambdas)
    
    Event should contain:
    {
        "thread_id": "...",
        "message": "...",
        "channel": "sms" or "web",
        "user_id": "..." (optional),
        "phone_number": "..." (optional),
        "session_id": "..." (optional)
    }
    """
    logger.info("Chat handler invoked: %s", json.dumps(event))
    
    try:
        # Extract parameters
        thread_id = event.get('thread_id')
        message = event.get('message')
        channel = event.get('channel', 'web')
        user_id = event.get('user_id')
        phone_number = event.get('phone_number')
        session_id = event.get('session_id')
        
        # Validate required fields
        if not thread_id or not message:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'thread_id and message are required'})
            }
        
        # Process message
        result = process_chat_message(
            thread_id=thread_id,
            message=message,
            channel=channel,
            user_id=user_id,
            phone_number=phone_number,
            session_id=session_id
        )
        
        return {
            'statusCode': 200 if result.get('success') else 500,
            'body': json.dumps(result)
        }
        
    except Exception as e:
        logger.error("Error in chat handler: %s", str(e))
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'success': False
            })
        }

