"""
Agent Service using LangChain
Handles conversation logic, memory, and guardrails for Versiful chat agent
"""
import os
import json
import logging
import re
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime

import yaml
import boto3
from botocore.exceptions import ClientError
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_openai import ChatOpenAI

from posthog import Posthog

# Try to import PostHog's LangChain CallbackHandler and trace
POSTHOG_AVAILABLE = False
POSTHOG_TRACE_AVAILABLE = False

try:
    from posthog.ai.langchain import CallbackHandler
    POSTHOG_AVAILABLE = True
    print("✅ PostHog CallbackHandler imported successfully")
except ImportError as e:
    POSTHOG_AVAILABLE = False
    CallbackHandler = None
    print(f"❌ PostHog CallbackHandler not available: {e}")

try:
    from posthog.ai import trace
    POSTHOG_TRACE_AVAILABLE = True
    print("✅ PostHog trace imported successfully")
except ImportError as e:
    POSTHOG_TRACE_AVAILABLE = False
    trace = None
    print(f"❌ PostHog trace not available: {e}")

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
        
        # Initialize tools (just Versiful info)
        self.tools = [get_versiful_info]
        
        # LLM config
        llm_config = self.config['llm']
        self.llm_model = llm_config['model']
        self.llm_temperature = llm_config['temperature']
        self.llm_max_tokens = llm_config['max_tokens']
        
        # SMS config
        sms_config = llm_config.get('sms', {})
        self.sms_temperature = sms_config.get('temperature', llm_config['temperature'])
        self.sms_max_tokens = sms_config.get('max_tokens', 300)
        
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
        user_first_name: str = None,
        user_id: str = None,
        thread_id: str = None,
        phone_number: str = None
    ) -> str:
        """Generate response using LLM with tool calling support via LangChain agent"""
        # Initialize PostHog callback handler for this LLM call
        posthog_api_key = os.environ.get('POSTHOG_API_KEY')
        posthog_handler = None
        
        logger.info(f"PostHog API key present: {bool(posthog_api_key)}, PostHog available: {POSTHOG_AVAILABLE}")
        
        if posthog_api_key and POSTHOG_AVAILABLE:
            try:
                posthog_client = Posthog(
                    posthog_api_key,
                    host='https://us.i.posthog.com'
                )
                
                logger.info(f"Creating PostHog CallbackHandler for user_id={user_id}, thread_id={thread_id}")
                
                # Generate unique trace_id for this message/interaction
                # Each message gets its own trace, while thread_id groups messages in the same conversation
                message_trace_id = str(uuid.uuid4())
                
                # Set trace name based on channel
                trace_name = f"Versiful {channel.upper()} Chat"
                
                posthog_handler = CallbackHandler(
                    client=posthog_client,
                    distinct_id=user_id or phone_number or 'anonymous',
                    trace_id=message_trace_id,  # Unique ID for this message's trace
                    ai_session_id=thread_id,  # Session grouping for conversation
                    properties={
                        'environment': os.environ.get('ENVIRONMENT', 'dev'),
                        'channel': channel,
                        'thread_id': thread_id,  # Group by conversation thread
                        'phone_number': phone_number,
                        '$ai_trace_name': trace_name  # Set the trace display name
                    }
                )
                
                logger.info(f"PostHog CallbackHandler created successfully with trace_id={message_trace_id}, trace_name={trace_name}, ai_session_id={thread_id}")
            except Exception as e:
                logger.error(f"Error initializing PostHog handler: {e}", exc_info=True)
        
        # Select appropriate LLM config and system prompt
        if channel == 'sms':
            llm_temperature = self.sms_temperature
            llm_max_tokens = self.sms_max_tokens
            system_prompt = self.config.get('sms_system_prompt', self.config['system_prompt'])
        else:
            llm_temperature = self.llm_temperature
            llm_max_tokens = self.llm_max_tokens
            system_prompt = self.config['system_prompt']
        
        # Inject user's name into system prompt if available
        if user_first_name:
            name_instruction = f"\n\nThe user's name is {user_first_name}. Feel free to address them by name when appropriate to create a warm, personal connection."
            system_prompt = system_prompt + name_instruction
        
        # Inject bible version preference into system prompt
        if bible_version:
            bible_instruction = f"\n\nIMPORTANT: When citing Bible verses, always use the {bible_version} translation. The user has specifically requested this version."
            system_prompt = system_prompt + bible_instruction
        
        # If off-topic, add redirect guidance
        if is_off_topic:
            redirect = self.config['guardrails']['redirect_prompt']
            system_prompt = system_prompt + f"\n\nGUIDANCE: {redirect}"
        
        # Create LLM with stream_usage enabled to capture token counts
        llm = ChatOpenAI(
            model=self.llm_model,
            temperature=llm_temperature,
            max_tokens=llm_max_tokens,
            stream_usage=True  # Required for usage metadata even in non-streaming mode
        )
        
        # Build conversation history for the agent
        chat_history = []
        max_history = self.config['history']['context_window']
        recent_messages = messages[-max_history:] if len(messages) > max_history else messages
        
        for msg in recent_messages:
            if msg['role'] == 'user':
                chat_history.append(HumanMessage(content=msg['content']))
            elif msg['role'] == 'assistant':
                chat_history.append(AIMessage(content=msg['content']))
        
        # Create prompt template for the agent
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        # Create agent with tools
        agent = create_tool_calling_agent(llm, self.tools, prompt)
        
        # Create agent executor
        agent_executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=False,
            handle_parsing_errors=True
        )
        
        # Get the current user message (last message in messages list)
        current_message = messages[-1]['content'] if messages else ""
        
        # Execute agent
        try:
            response = agent_executor.invoke(
                {
                    "input": current_message,
                    "chat_history": chat_history[:-1] if chat_history else []
                },
                config={"callbacks": [posthog_handler] if posthog_handler else []}
            )
            
            response_text = response.get('output', '')
            
            logger.info(f"Agent response received, text length: {len(response_text)}")
            
            # Flush PostHog events
            if posthog_handler:
                logger.info(f"PostHog handler exists, has client: {hasattr(posthog_handler, 'client')}")
                if hasattr(posthog_handler, 'client'):
                    logger.info("Shutting down PostHog client to flush events")
                    posthog_handler.client.shutdown()
                    logger.info("PostHog client shutdown complete")
                else:
                    logger.warning("PostHog handler has no client attribute")
            else:
                logger.info("No PostHog handler to flush")
            
            return response_text
            
        except Exception as e:
            logger.error("Error generating response: %s", str(e), exc_info=True)
            
            # Flush PostHog events even on error
            if posthog_handler and hasattr(posthog_handler, 'client'):
                logger.info("Shutting down PostHog client (error case)")
                posthog_handler.client.shutdown()
            
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
        bible_version: str = None,
        user_first_name: str = None,
        phone_number: str = None
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
            user_first_name: Optional user's first name for personalization
            phone_number: Optional phone number (for SMS tracking)
            
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
            response = self._generate_llm_response(
                messages, 
                channel, 
                is_off_topic, 
                bible_version, 
                user_first_name,
                user_id,
                thread_id,
                phone_number
            )
            
            # Format response
            response = self._format_response(response, channel)
        
        return {
            "response": response,
            "thread_id": thread_id,
            "channel": channel,
            "needs_crisis_intervention": needs_crisis,
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }
    
    def get_conversation_title(self, messages: List[Dict[str, str]], user_id: str = None, thread_id: str = None, phone_number: str = None) -> str:
        """
        Generate a concise title for a conversation using GPT-4o-mini
        
        Args:
            messages: List of messages in the conversation
            user_id: Optional user ID for tracking
            thread_id: Optional thread ID for tracking
            phone_number: Optional phone number for tracking
            
        Returns:
            A short title (max 50 chars)
        """
        if not messages:
            return "New Conversation"
        
        # Initialize PostHog callback handler for title generation
        posthog_api_key = os.environ.get('POSTHOG_API_KEY')
        posthog_handler = None
        
        logger.info(f"Title generation - PostHog API key present: {bool(posthog_api_key)}, PostHog available: {POSTHOG_AVAILABLE}")
        
        if posthog_api_key and POSTHOG_AVAILABLE:
            try:
                posthog_client = Posthog(
                    posthog_api_key,
                    host='https://us.i.posthog.com'
                )
                
                # Generate unique trace_id for title generation
                title_trace_id = str(uuid.uuid4())
                
                posthog_handler = CallbackHandler(
                    client=posthog_client,
                    distinct_id=user_id or phone_number or 'anonymous',
                    trace_id=title_trace_id,  # Unique trace for title generation
                    ai_session_id=thread_id,  # Session grouping for conversation
                    properties={
                        'environment': os.environ.get('ENVIRONMENT', 'dev'),
                        'channel': 'title_generation',
                        'thread_id': thread_id,
                        'phone_number': phone_number,
                        '$ai_trace_name': 'Versiful Title Generation'  # Set the trace display name
                    }
                )
                logger.info(f"Title generation PostHog CallbackHandler created")
            except Exception as e:
                logger.error(f"Error initializing PostHog handler for title: {e}", exc_info=True)
        
        # Create title LLM with handler
        title_llm = ChatOpenAI(
            model='gpt-4o-mini',
            temperature=0.5,
            max_tokens=50,
            callbacks=[posthog_handler] if posthog_handler else []
        )
        
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
            response = title_llm.invoke([HumanMessage(content=title_prompt)])
            title = response.content.strip()
            
            # Clean up the title
            title = title.replace('"', '').replace("'", '').strip()
            
            # Ensure it's not too long
            if len(title) > 50:
                title = title[:47] + "..."
            
            # Flush PostHog events
            if posthog_handler and hasattr(posthog_handler, 'client'):
                logger.info("Shutting down PostHog client for title generation")
                posthog_handler.client.shutdown()
            
            logger.info("Generated conversation title: %s", title)
            return title if title else "New Conversation"
            
        except Exception as e:
            logger.error("Error generating title: %s", str(e))
            
            # Flush PostHog events even on error
            if posthog_handler and hasattr(posthog_handler, 'client'):
                posthog_handler.client.shutdown()
            
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
