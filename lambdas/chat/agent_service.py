"""
Agent Service using LangChain
Handles conversation logic, memory, and guardrails for Versiful chat agent
"""
import os
import json
import logging
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

import yaml
import boto3
from botocore.exceptions import ClientError
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# DynamoDB setup for user data access
dynamodb = boto3.resource('dynamodb')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'versiful')
USERS_TABLE = os.environ.get(
    'USERS_TABLE',
    f'{ENVIRONMENT}-{PROJECT_NAME}-users'
)
users_table = dynamodb.Table(USERS_TABLE)


@tool
def get_versiful_info() -> str:
    """Get information about Versiful service, features, pricing, and FAQs.
    
    Use this tool when the user asks about:
    - What is Versiful / what service they are using
    - How to upgrade or subscribe
    - Pricing information
    - How to cancel subscription
    - Features of the service
    - Any questions about the Versiful app or service
    
    Returns detailed information about Versiful.
    """
    return """VERSIFUL - Biblical Guidance Via Text

**About Versiful:**
Versiful is a service that provides personalized biblical guidance and wisdom through text messaging and web chat. Users can text their questions, struggles, or situations and receive compassionate responses rooted in Scripture.

**Key Features:**
- 24/7 access to biblical guidance via SMS and web chat
- Personalized responses based on your situation
- Choose your preferred Bible translation (KJV, NIV, ESV, and more)
- Conversation history saved for web users
- Private and secure

**Plans & Pricing:**
- **Free Plan**: 5 messages per month via SMS
- **Paid Subscription**: Unlimited messages
  - Web: Manage subscription at versiful.io/subscription
  - Pricing details available during signup

**How to Upgrade:**
1. Visit https://versiful.io
2. Sign in with your account
3. Go to Settings or Subscription page
4. Choose a paid plan

**How to Cancel Subscription:**
- **Via Web**: Go to https://versiful.io/subscription and click "Manage Subscription" to cancel
- **Via SMS**: Text "STOP" to cancel (this will also opt you out of messages and cancel any active subscription)
- You can also manage your subscription through the Stripe customer portal

**How to Change Bible Version:**
1. Go to https://versiful.io/settings
2. Navigate to "Personalization" section
3. Select your preferred Bible translation
4. All future responses will use your selected version

**Support:**
- Website: https://versiful.io
- Email: support@versiful.com
- SMS Keywords: 
  - HELP - Get help information
  - STOP - Unsubscribe and cancel
  - START - Resubscribe after stopping

**Privacy:**
Your conversations are private and secure. We take your privacy seriously and never share your personal information."""


@tool
def get_user_context(user_id: str) -> str:
    """Get information about the current user including their name and subscription status.
    
    Use this tool when you need to:
    - Address the user by name
    - Check their subscription status
    - Get their preferences
    
    Args:
        user_id: The user's unique identifier
        
    Returns information about the user including first name, subscription status, and plan.
    """
    if not user_id:
        return "User information not available (not logged in or no user_id provided)."
    
    try:
        response = users_table.get_item(Key={'userId': user_id})
        if 'Item' not in response:
            return "User profile not found."
        
        user = response['Item']
        first_name = user.get('firstName', '')
        last_name = user.get('lastName', '')
        is_subscribed = user.get('isSubscribed', False)
        plan = user.get('plan', 'free')
        bible_version = user.get('bibleVersion', 'Not set')
        
        # Build context string
        context_parts = []
        
        if first_name:
            context_parts.append(f"User's name: {first_name}")
            if last_name:
                context_parts[-1] += f" {last_name}"
        
        if is_subscribed:
            context_parts.append(f"Subscription: Active ({plan} plan)")
            context_parts.append("Access: Unlimited messages")
        else:
            context_parts.append(f"Subscription: Free plan")
            context_parts.append("Access: 5 messages per month")
        
        context_parts.append(f"Preferred Bible version: {bible_version}")
        
        return "\n".join(context_parts)
        
    except ClientError as e:
        logger.error(f"Error fetching user context: {str(e)}")
        return "Unable to retrieve user information at this time."


class AgentService:
    """
    LangChain-based agent service for biblical guidance
    """
    
    def __init__(self, config_path: str = None, api_key: str = None):
        """
        Initialize the agent service
        
        Args:
            config_path: Path to agent_config.yaml
            api_key: OpenAI API key (if not in env)
        """
        # Load configuration
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), 'agent_config.yaml')
        
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Set API key
        if api_key:
            os.environ['OPENAI_API_KEY'] = api_key
        
        # Initialize tools
        self.tools = [get_versiful_info, get_user_context]
        
        # Initialize LLM with tool binding
        llm_config = self.config['llm']
        base_llm = ChatOpenAI(
            model=llm_config['model'],
            temperature=llm_config['temperature'],
            max_tokens=llm_config['max_tokens']
        )
        self.llm = base_llm.bind_tools(self.tools)
        
        # Initialize SMS-specific LLM (with tools)
        sms_config = llm_config.get('sms', {})
        base_sms_llm = ChatOpenAI(
            model=llm_config['model'],
            temperature=sms_config.get('temperature', llm_config['temperature']),
            max_tokens=sms_config.get('max_tokens', 300)
        )
        self.sms_llm = base_sms_llm.bind_tools(self.tools)
        
        # Initialize title generation LLM (using GPT-4o-mini for cost efficiency)
        self.title_llm = ChatOpenAI(
            model='gpt-4o-mini',
            temperature=0.5,
            max_tokens=50
        )
        
        logger.info("AgentService initialized with model: %s and %d tools", 
                   llm_config['model'], len(self.tools))
    
    def _check_guardrails(self, message: str) -> tuple[bool, Optional[str], bool]:
        """
        Check for sensitive topics and content filtering
        Returns: (needs_crisis_intervention, crisis_response, is_off_topic)
        """
        message_lower = message.lower()
        
        # Check for crisis keywords
        crisis_keywords = [
            'suicide', 'suicidal', 'kill myself', 'end my life', 
            'self harm', 'hurt myself', 'want to die'
        ]
        
        for keyword in crisis_keywords:
            if keyword in message_lower:
                logger.warning("Crisis intervention triggered")
                return True, self.config['guardrails']['crisis_response'], False
        
        # Check for profanity (basic check)
        if self.config['guardrails'].get('filter_profanity', True):
            profanity_pattern = r'\b(fuck|shit|damn|bitch|ass)\b'
            if re.search(profanity_pattern, message_lower, re.IGNORECASE):
                logger.info("Profanity detected, will redirect conversation")
                return False, None, True
        
        return False, None, False
    
    def _generate_llm_response(
        self,
        messages: List[Dict[str, str]],
        channel: str,
        is_off_topic: bool = False,
        bible_version: str = None,
        user_id: str = None
    ) -> str:
        """Generate response using LLM with tool calling support"""
        # Select appropriate LLM and system prompt
        if channel == 'sms':
            llm = self.sms_llm
            system_prompt = self.config.get('sms_system_prompt', self.config['system_prompt'])
        else:
            llm = self.llm
            system_prompt = self.config['system_prompt']
        
        # Inject bible version preference into system prompt
        if bible_version:
            bible_instruction = f"\n\nIMPORTANT: When citing Bible verses, always use the {bible_version} translation. The user has specifically requested this version."
            system_prompt = system_prompt + bible_instruction
        
        # Build messages for LLM
        llm_messages = [SystemMessage(content=system_prompt)]
        
        # Add conversation history (limit based on config)
        max_history = self.config['history']['context_window']
        recent_messages = messages[-max_history:] if len(messages) > max_history else messages
        
        for msg in recent_messages:
            if msg['role'] == 'user':
                llm_messages.append(HumanMessage(content=msg['content']))
            elif msg['role'] == 'assistant':
                llm_messages.append(AIMessage(content=msg['content']))
        
        # If off-topic, prepend redirect guidance
        if is_off_topic:
            redirect = self.config['guardrails']['redirect_prompt']
            llm_messages.insert(1, SystemMessage(content=f"GUIDANCE: {redirect}"))
        
        # Generate response with tool calling support
        try:
            response = llm.invoke(llm_messages)
            
            # Check if LLM wants to use tools
            if hasattr(response, 'tool_calls') and response.tool_calls:
                logger.info(f"LLM requested {len(response.tool_calls)} tool call(s)")
                
                # Add AI response with tool calls to message history
                llm_messages.append(response)
                
                # Execute tool calls
                for tool_call in response.tool_calls:
                    tool_name = tool_call['name']
                    tool_args = tool_call['args']
                    tool_id = tool_call['id']
                    
                    logger.info(f"Executing tool: {tool_name} with args: {tool_args}")
                    
                    # Find and execute the tool
                    tool_result = None
                    for tool in self.tools:
                        if tool.name == tool_name:
                            try:
                                # Special handling for get_user_context - inject user_id
                                if tool_name == 'get_user_context' and user_id and 'user_id' not in tool_args:
                                    tool_args['user_id'] = user_id
                                
                                tool_result = tool.invoke(tool_args)
                                logger.info(f"Tool {tool_name} result: {tool_result[:100]}...")
                            except Exception as e:
                                tool_result = f"Error executing tool: {str(e)}"
                                logger.error(f"Tool execution error: {str(e)}")
                            break
                    
                    if tool_result is None:
                        tool_result = f"Tool {tool_name} not found"
                    
                    # Add tool result to messages
                    llm_messages.append(ToolMessage(
                        content=str(tool_result),
                        tool_call_id=tool_id
                    ))
                
                # Get final response with tool results
                final_response = llm.invoke(llm_messages)
                return final_response.content
            
            # No tool calls, return direct response
            return response.content
            
        except Exception as e:
            logger.error("Error generating response: %s", str(e))
            return "I apologize, but I'm having trouble responding right now. Please try again in a moment."
    
    def _format_response(self, response: str, channel: str) -> str:
        """Format the response based on channel"""
        # For SMS, ensure it's not too long
        if channel == 'sms':
            # Twilio limit is 1600 chars, but we want to be conservative
            max_length = 1500
            if len(response) > max_length:
                response = response[:max_length-3] + "..."
                logger.info("Truncated SMS response to %d chars", max_length)
        
        return response
    
    def process_message(
        self,
        thread_id: str,
        message: str,
        channel: str,
        history: List[Dict[str, str]] = None,
        user_id: str = None,
        bible_version: str = None
    ) -> Dict[str, Any]:
        """
        Process a message and generate a response
        
        Args:
            thread_id: Unique thread identifier
            message: User's message
            channel: "sms" or "web"
            history: Previous messages in format [{"role": "user/assistant", "content": "..."}]
            user_id: Optional user ID
            bible_version: Optional preferred Bible version (e.g., 'KJV', 'NIV')
            
        Returns:
            Dict with 'response' and metadata
        """
        logger.info("Processing message for thread: %s, channel: %s", thread_id, channel)
        
        if history is None:
            history = []
        
        # Check guardrails first
        needs_crisis, crisis_response, is_off_topic = self._check_guardrails(message)
        
        if needs_crisis:
            # Return crisis intervention response immediately
            response = crisis_response
        else:
            # Add current message to history for context
            messages = history + [{"role": "user", "content": message}]
            
            # Generate LLM response
            response = self._generate_llm_response(messages, channel, is_off_topic, bible_version, user_id)
            
            # Format response
            response = self._format_response(response, channel)
        
        return {
            "response": response,
            "thread_id": thread_id,
            "channel": channel,
            "needs_crisis_intervention": needs_crisis,
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }
    
    def get_conversation_title(self, messages: List[Dict[str, str]]) -> str:
        """
        Generate a concise title for a conversation using GPT-4o-mini
        
        Args:
            messages: List of messages in the conversation
            
        Returns:
            A short title (max 50 chars)
        """
        if not messages:
            return "New Conversation"
        
        # Build a summary of the conversation for title generation
        conversation_text = ""
        for msg in messages[:10]:  # Only use first 10 messages to keep context manageable
            role = msg['role'].capitalize()
            content = msg['content'][:200]  # Limit message length
            conversation_text += f"{role}: {content}\n\n"
        
        # Create prompt for title generation
        title_prompt = f"""Based on the following conversation, generate a very short, descriptive title (maximum 4-6 words).
The title should capture the main topic or theme of the conversation.
Do not use quotes, colons, or special characters. Just provide the plain title.

Conversation:
{conversation_text}

Title:"""
        
        try:
            # Generate title using GPT-4o-mini
            response = self.title_llm.invoke([HumanMessage(content=title_prompt)])
            title = response.content.strip()
            
            # Clean up the title
            title = title.replace('"', '').replace("'", '').strip()
            
            # Ensure it's not too long
            if len(title) > 50:
                title = title[:47] + "..."
            
            logger.info("Generated conversation title: %s", title)
            return title if title else "New Conversation"
            
        except Exception as e:
            logger.error("Error generating title: %s", str(e))
            # Fallback to simple title generation
            first_user_msg = next((m for m in messages if m['role'] == 'user'), None)
            if not first_user_msg:
                return "New Conversation"
            
            content = first_user_msg['content']
            title = content.split('.')[0].split('?')[0].split('!')[0]
            title = title[:47] + "..." if len(title) > 50 else title
            return title or "New Conversation"


def get_agent_service(api_key: str = None) -> AgentService:
    """
    Factory function to get agent service instance
    Useful for Lambda handlers to initialize once
    """
    return AgentService(api_key=api_key)


# For testing
if __name__ == "__main__":
    import sys
    
    # Simple CLI test
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        print("Please set OPENAI_API_KEY environment variable")
        sys.exit(1)
    
    agent = get_agent_service(api_key)
    
    print("Versiful Agent Test (type 'quit' to exit)")
    print("-" * 50)
    
    history = []
    thread_id = "test-thread"
    
    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() in ['quit', 'exit', 'q']:
            break
        
        result = agent.process_message(
            thread_id=thread_id,
            message=user_input,
            channel="web",
            history=history
        )
        
        print(f"\nAgent: {result['response']}")
        
        # Update history
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": result['response']})
