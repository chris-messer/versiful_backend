"""
Web Chat Handler - REST API for web chat interface
Provides endpoints for chat sessions and message management
"""
import os
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

from chat_handler import get_message_history, get_agent

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def decimal_to_number(obj):
    """Convert Decimal objects to int or float for JSON serialization"""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_number(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_number(i) for i in obj]
    return obj

# DynamoDB setup
dynamodb = boto3.resource('dynamodb')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'versiful')

CHAT_SESSIONS_TABLE = os.environ.get(
    'CHAT_SESSIONS_TABLE',
    f'{ENVIRONMENT}-{PROJECT_NAME}-chat-sessions'
)

sessions_table = dynamodb.Table(CHAT_SESSIONS_TABLE)

# Lambda client for invoking chat handler
lambda_client = boto3.client('lambda')
CHAT_FUNCTION_NAME = os.environ.get(
    'CHAT_FUNCTION_NAME',
    f'{ENVIRONMENT}-{PROJECT_NAME}-chat'
)


def get_user_id_from_event(event: Dict[str, Any]) -> Optional[str]:
    """Extract user ID from JWT authorizer context"""
    request_context = event.get('requestContext', {})
    authorizer = request_context.get('authorizer', {})
    
    # Check Lambda authorizer
    if 'userId' in authorizer:
        return authorizer['userId']
    
    # Check JWT authorizer claims
    claims = authorizer.get('claims', {})
    if 'sub' in claims:
        return claims['sub']
    
    return None


def cors_headers():
    """Standard CORS headers"""
    origin = os.environ.get('CORS_ORIGIN', 'http://localhost:5173')
    return {
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Credentials': 'true'
    }


def success_response(body: Dict[str, Any], status_code: int = 200):
    """Standard success response"""
    # Convert any Decimal objects to numbers
    body = decimal_to_number(body)
    return {
        'statusCode': status_code,
        'headers': cors_headers(),
        'body': json.dumps(body)
    }


def error_response(message: str, status_code: int = 400):
    """Standard error response"""
    return {
        'statusCode': status_code,
        'headers': cors_headers(),
        'body': json.dumps({'error': message})
    }


def create_session(user_id: str, title: str = None) -> Dict[str, Any]:
    """
    Create a new chat session
    
    Args:
        user_id: User ID
        title: Optional session title
        
    Returns:
        Created session dict
    """
    session_id = str(uuid.uuid4())
    thread_id = f"{user_id}#{session_id}"
    now = datetime.utcnow().isoformat() + 'Z'
    
    session = {
        'userId': user_id,
        'sessionId': session_id,
        'threadId': thread_id,
        'title': title or 'New Conversation',
        'messageCount': 0,
        'lastMessageAt': now,
        'channel': 'web',
        'createdAt': now,
        'updatedAt': now,
        'archived': False
    }
    
    try:
        sessions_table.put_item(Item=session)
        logger.info("Created session: %s for user: %s", session_id, user_id)
        return session
    except ClientError as e:
        logger.error("Error creating session: %s", str(e))
        raise


def get_user_sessions(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get all sessions for a user, ordered by most recent activity
    
    Args:
        user_id: User ID
        limit: Maximum number of sessions to return
        
    Returns:
        List of session dicts
    """
    try:
        # Query using GSI if it exists, otherwise query by userId
        response = sessions_table.query(
            KeyConditionExpression='userId = :uid',
            ExpressionAttributeValues={':uid': user_id},
            ScanIndexForward=False,  # Most recent first
            Limit=limit
        )
        
        sessions = response.get('Items', [])
        
        # Filter out archived sessions unless specifically requested
        sessions = [s for s in sessions if not s.get('archived', False)]
        
        # Sort by lastMessageAt in memory (in case GSI isn't set up yet)
        sessions.sort(key=lambda x: x.get('lastMessageAt', ''), reverse=True)
        
        logger.info("Retrieved %d sessions for user: %s", len(sessions), user_id)
        return sessions
    except ClientError as e:
        logger.error("Error retrieving sessions: %s", str(e))
        return []


def get_session(user_id: str, session_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific session
    
    Args:
        user_id: User ID
        session_id: Session ID
        
    Returns:
        Session dict or None
    """
    try:
        response = sessions_table.get_item(
            Key={'userId': user_id, 'sessionId': session_id}
        )
        session = response.get('Item')
        
        if session:
            logger.info("Retrieved session: %s", session_id)
        else:
            logger.info("Session not found: %s", session_id)
        
        return session
    except ClientError as e:
        logger.error("Error retrieving session: %s", str(e))
        return None


def archive_session(user_id: str, session_id: str) -> bool:
    """
    Archive a session (soft delete)
    
    Args:
        user_id: User ID
        session_id: Session ID
        
    Returns:
        True if successful
    """
    try:
        sessions_table.update_item(
            Key={'userId': user_id, 'sessionId': session_id},
            UpdateExpression='SET archived = :true, updatedAt = :now',
            ExpressionAttributeValues={
                ':true': True,
                ':now': datetime.utcnow().isoformat() + 'Z'
            }
        )
        logger.info("Archived session: %s", session_id)
        return True
    except ClientError as e:
        logger.error("Error archiving session: %s", str(e))
        return False


def invoke_chat_handler(
    thread_id: str,
    message: str,
    user_id: str,
    session_id: str
) -> Dict[str, Any]:
    """
    Invoke the chat Lambda function
    
    Args:
        thread_id: Full thread identifier
        message: User's message
        user_id: User ID
        session_id: Session ID
        
    Returns:
        Response from chat handler
    """
    payload = {
        'thread_id': thread_id,
        'message': message,
        'channel': 'web',
        'user_id': user_id,
        'session_id': session_id
    }
    
    logger.info("Invoking chat handler with thread_id: %s", thread_id)
    
    try:
        response = lambda_client.invoke(
            FunctionName=CHAT_FUNCTION_NAME,
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        response_payload = json.loads(response['Payload'].read())
        logger.info("Chat handler response status: %s", response_payload.get('statusCode'))
        
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


def generate_ai_title(messages: List[Dict[str, Any]], thread_id: str = None, user_id: str = None, trace_id: str = None) -> str:
    """
    Generate an AI-powered title using GPT-4o-mini
    
    Args:
        messages: List of conversation messages
        thread_id: Thread ID of the conversation being summarized (for PostHog tracing)
        user_id: User ID for PostHog tracking
        trace_id: Trace ID to group with related LLM calls
        
    Returns:
        A short, descriptive title
    """
    try:
        agent = get_agent()
        title = agent.get_conversation_title(messages, thread_id=thread_id, user_id=user_id, trace_id=trace_id)
        logger.info("Generated AI title: %s", title)
        return title
    except Exception as e:
        logger.error("Error generating AI title: %s", str(e))
        # Fallback to simple generation
        return generate_session_title(messages[0]['content'] if messages else "New Conversation")


def generate_session_title(message: str) -> str:
    """
    Generate a short title from the first user message
    
    Args:
        message: The first user message
        
    Returns:
        A short title (max 50 chars)
    """
    # Take first sentence or first 50 characters
    title = message.strip()
    
    # Remove newlines
    title = title.replace('\n', ' ').replace('\r', '')
    
    # Find first sentence
    for ending in ['. ', '! ', '? ', '\n']:
        if ending in title:
            title = title.split(ending)[0] + ending.strip()
            break
    
    # Truncate to 50 chars
    if len(title) > 50:
        title = title[:47] + '...'
    
    return title or 'New Conversation'


def update_session_title(user_id: str, session_id: str, title: str) -> bool:
    """
    Update the title of a session
    
    Args:
        user_id: User ID
        session_id: Session ID
        title: New title
        
    Returns:
        True if successful
    """
    try:
        sessions_table.update_item(
            Key={'userId': user_id, 'sessionId': session_id},
            UpdateExpression='SET title = :title, updatedAt = :now',
            ExpressionAttributeValues={
                ':title': title,
                ':now': datetime.utcnow().isoformat() + 'Z'
            }
        )
        logger.info("Updated session title: %s -> %s", session_id, title)
        return True
    except ClientError as e:
        logger.error("Error updating session title: %s", str(e))
        return False


def handle_post_message(event: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """
    POST /chat/message - Send a message and get response
    
    Body:
    {
        "message": "...",
        "sessionId": "..." (optional, creates new if not provided)
    }
    """
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return error_response('Invalid JSON body', 400)
    
    message = body.get('message')
    session_id = body.get('sessionId')
    
    if not message:
        return error_response('message is required', 400)
    
    # Create new session if not provided
    is_new_session = False
    should_generate_title = False
    if not session_id:
        session = create_session(user_id)
        session_id = session['sessionId']
        thread_id = session['threadId']
        is_new_session = True
    else:
        # Verify session exists and belongs to user
        session = get_session(user_id, session_id)
        if not session:
            return error_response('Session not found', 404)
        thread_id = session['threadId']
        # Check if this is effectively the first message (title is still default)
        if session.get('title') == 'New Conversation' and session.get('messageCount', 0) == 0:
            is_new_session = True
        # Check if we should regenerate title (after 4-6 messages, while title is still simple)
        message_count = session.get('messageCount', 0)
        current_title = session.get('title', 'New Conversation')
        # Only regenerate if current title looks like it's just the first message
        if message_count >= 3 and (current_title == 'New Conversation' or len(current_title) > 40):
            should_generate_title = True
    
    # Invoke chat handler
    result = invoke_chat_handler(
        thread_id=thread_id,
        message=message,
        user_id=user_id,
        session_id=session_id
    )
    
    if not result.get('success', False):
        return error_response(result.get('error', 'Error processing message'), 500)
    
    # Generate title for new conversations or when appropriate
    if is_new_session:
        # Simple title for first message
        title = generate_session_title(message)
        update_session_title(user_id, session_id, title)
    elif should_generate_title:
        # Generate AI-powered title after a few messages
        try:
            messages = get_message_history(thread_id, limit=10)
            if messages and len(messages) >= 4:
                # Generate NEW trace_id for title generation
                import uuid
                title_trace_id = str(uuid.uuid4())
                title = generate_ai_title(messages, thread_id=thread_id, user_id=user_id, trace_id=title_trace_id)
                update_session_title(user_id, session_id, title)
        except Exception as e:
            logger.error("Error generating AI title: %s", str(e))
    
    return success_response({
        'message': result.get('response'),
        'sessionId': session_id,
        'threadId': thread_id,
        'needsCrisisIntervention': result.get('needs_crisis_intervention', False)
    })


def handle_get_sessions(user_id: str) -> Dict[str, Any]:
    """
    GET /chat/sessions - List user's chat sessions
    """
    sessions = get_user_sessions(user_id)
    
    return success_response({
        'sessions': sessions,
        'count': len(sessions)
    })


def handle_post_session(user_id: str) -> Dict[str, Any]:
    """
    POST /chat/sessions - Create a new session
    """
    session = create_session(user_id)
    
    return success_response({
        'session': session
    }, 201)


def handle_get_session(event: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """
    GET /chat/sessions/{sessionId} - Get session with message history
    """
    path_params = event.get('pathParameters', {})
    session_id = path_params.get('sessionId')
    
    if not session_id:
        return error_response('sessionId is required', 400)
    
    # Get session
    session = get_session(user_id, session_id)
    if not session:
        return error_response('Session not found', 404)
    
    # Get message history
    thread_id = session['threadId']
    messages = get_message_history(thread_id, limit=100)
    
    return success_response({
        'session': session,
        'messages': messages
    })


def handle_delete_session(event: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """
    DELETE /chat/sessions/{sessionId} - Archive a session
    """
    path_params = event.get('pathParameters', {})
    session_id = path_params.get('sessionId')
    
    if not session_id:
        return error_response('sessionId is required', 400)
    
    # Verify session exists
    session = get_session(user_id, session_id)
    if not session:
        return error_response('Session not found', 404)
    
    # Archive it
    success = archive_session(user_id, session_id)
    
    if success:
        return success_response({'message': 'Session archived'})
    else:
        return error_response('Error archiving session', 500)


def handle_update_session_title(event: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """
    PUT /chat/sessions/{sessionId}/title - Regenerate session title using AI
    """
    path_params = event.get('pathParameters', {})
    session_id = path_params.get('sessionId')
    
    if not session_id:
        return error_response('sessionId is required', 400)
    
    # Verify session exists
    session = get_session(user_id, session_id)
    if not session:
        return error_response('Session not found', 404)
    
    # Get conversation messages
    thread_id = session['threadId']
    messages = get_message_history(thread_id, limit=20)
    
    if not messages:
        return error_response('Cannot generate title for empty conversation', 400)
    
    # Generate AI-powered title
    try:
        import uuid
        trace_id = str(uuid.uuid4())  # Generate new trace for manual title regeneration
        title = generate_ai_title(messages, thread_id=thread_id, user_id=user_id, trace_id=trace_id)
        update_session_title(user_id, session_id, title)
        
        return success_response({
            'title': title,
            'message': 'Title updated successfully'
        })
    except Exception as e:
        logger.error("Error updating session title: %s", str(e))
        return error_response(f'Error generating title: {str(e)}', 500)


def handler(event, context):
    """
    Lambda handler for web chat API
    
    Routes:
    - POST /chat/message - Send message
    - GET /chat/sessions - List sessions
    - POST /chat/sessions - Create session
    - GET /chat/sessions/{sessionId} - Get session details
    - DELETE /chat/sessions/{sessionId} - Archive session
    - PUT /chat/sessions/{sessionId}/title - Regenerate session title
    """
    logger.info("Web chat handler invoked: %s %s", 
                event.get('httpMethod'), event.get('path'))
    
    # Handle OPTIONS for CORS
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': cors_headers(),
            'body': ''
        }
    
    # Get user ID from authorizer
    user_id = get_user_id_from_event(event)
    if not user_id:
        return error_response('Unauthorized', 401)
    
    # Route to appropriate handler
    method = event.get('httpMethod')
    path = event.get('path', '')
    
    try:
        if method == 'POST' and path.endswith('/chat/message'):
            return handle_post_message(event, user_id)
        elif method == 'GET' and path.endswith('/chat/sessions') and not event.get('pathParameters'):
            return handle_get_sessions(user_id)
        elif method == 'POST' and path.endswith('/chat/sessions'):
            return handle_post_session(user_id)
        elif method == 'GET' and '/chat/sessions/' in path and not path.endswith('/title'):
            return handle_get_session(event, user_id)
        elif method == 'PUT' and path.endswith('/title'):
            return handle_update_session_title(event, user_id)
        elif method == 'DELETE' and '/chat/sessions/' in path:
            return handle_delete_session(event, user_id)
        else:
            return error_response('Not found', 404)
    except Exception as e:
        logger.error("Error handling request: %s", str(e), exc_info=True)
        return error_response(f'Internal server error: {str(e)}', 500)

