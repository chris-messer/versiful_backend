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
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import ChatOpenAI
from posthog import Posthog
from posthog.ai.langchain import CallbackHandler

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
    
    def __init__(self, config_path: str = None, api_key: str = None, posthog_api_key: str = None):
        """
        Initialize the agent service
        
        Args:
            config_path: Path to agent_config.yaml
            api_key: OpenAI API key (if not in env)
            posthog_api_key: PostHog API key (if not in env)
        """
        # Load configuration
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), 'agent_config.yaml')
        
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Set API key
        if api_key:
            os.environ['OPENAI_API_KEY'] = api_key
        
        # Initialize PostHog
        self.posthog = None
        posthog_key = posthog_api_key or os.environ.get('POSTHOG_API_KEY')
        if posthog_key:
            try:
                # Initialize EXACTLY as in the working test - positional args, not named
                self.posthog = Posthog(
                    posthog_key,
                    host='https://us.i.posthog.com'
                )
                logger.info("PostHog initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize PostHog: {str(e)}")
                self.posthog = None
        else:
            logger.warning("PostHog API key not provided, tracing disabled")
        
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
    
    def _create_posthog_callback(
        self,
        thread_id: str,
        channel: str,
        phone_number: str = None,
        user_id: str = None,
        trace_id: str = None
    ) -> Optional[CallbackHandler]:
        """
        Create a PostHog CallbackHandler following official docs pattern
        
        Args:
            thread_id: Thread identifier (used as session_id to group conversation)
            channel: "sms" or "web"
            phone_number: Phone number for SMS (used as session_id)
            user_id: User ID for web (used in distinct_id)
            trace_id: Trace ID to group related LLM calls for handling one message
            
        Returns:
            CallbackHandler or None if PostHog is not initialized
        
        Note: PostHog SDK automatically creates trace hierarchy based on LangChain nesting.
              We just provide trace_id, distinct_id, and custom properties.
        """
        if not self.posthog:
            return None
        
        # Determine session_id based on channel
        if channel == 'sms' and phone_number:
            # Strip symbols from phone number for session_id
            session_id = re.sub(r'\D', '', phone_number)
        elif channel == 'web' and thread_id:
            # For web, use thread_id as session_id
            session_id = thread_id
        else:
            session_id = thread_id
        
        # Let PostHog use its default anonymous distinct_id
        # No custom identification - PostHog will handle it automatically
        distinct_id = None
        
        try:
            # Follow official PostHog LangChain docs pattern - EXACT from working test
            callback_handler = CallbackHandler(
                client=self.posthog,
                distinct_id=distinct_id,
                trace_id=trace_id,
                properties={
                    "conversation_id": session_id,
                    "$ai_session_id": session_id,
                    "channel": channel
                },
                privacy_mode=False
            )
            logger.info(
                f"Created PostHog callback - trace_id: {trace_id}, conversation_id: {session_id}, "
                f"distinct_id: {distinct_id}, channel: {channel}"
            )
            return callback_handler
        except Exception as e:
            logger.error(f"Failed to create PostHog callback handler: {str(e)}")
            return None
    
    def _generate_llm_response(
        self,
        messages: List[Dict[str, str]],
        channel: str,
        is_off_topic: bool = False,
        bible_version: str = None,
        user_first_name: str = None,
        thread_id: str = None,
        phone_number: str = None,
        user_id: str = None,
        trace_id: str = None
    ) -> str:
        """Generate response using LLM with tool calling support and PostHog tracing"""
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
        
        # Create PostHog callback handler
        posthog_callback = self._create_posthog_callback(
            thread_id=thread_id,
            channel=channel,
            phone_number=phone_number,
            user_id=user_id,
            trace_id=trace_id
        )
        
        # Build config with callbacks if PostHog is available
        config = {'callbacks': [posthog_callback]} if posthog_callback else {}
        
        # Create LLM with tools - use CHAIN pattern like the test
        base_llm = ChatOpenAI(
            model=self.llm_model,
            temperature=llm_temperature,
            max_tokens=llm_max_tokens
        )
        
        # Create chain: passthrough messages | LLM with tools
        # This matches the test pattern: prompt | model
        chain = RunnablePassthrough() | base_llm.bind_tools(self.tools)
        
        # Generate response with tool calling support
        try:
            # Invoke chain (not direct LLM) - EXACT pattern from test
            response = chain.invoke(llm_messages, config=config)
            
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
                                tool_result = tool.invoke(tool_args)
                                logger.info(f"Tool {tool_name} result: {tool_result[:200]}...")
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
                
                # Get final response with tool results - use chain pattern
                final_response = chain.invoke(llm_messages, config=config)
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
        bible_version: str = None,
        user_first_name: str = None,
        phone_number: str = None,
        trace_id: str = None
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
            phone_number: Optional phone number (for SMS tracing)
            trace_id: Optional trace ID to group related LLM calls (generated if not provided)
            
        Returns:
            Dict with 'response' and metadata
        """
        logger.info("Processing message for thread: %s, channel: %s", thread_id, channel)
        
        if history is None:
            history = []
        
        # Generate a trace ID for this message if not provided
        # This groups all LLM calls for handling this message together
        if not trace_id:
            import uuid
            trace_id = str(uuid.uuid4())
            logger.info(f"Generated trace_id for message: {trace_id}")
        
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
                thread_id=thread_id,
                phone_number=phone_number,
                user_id=user_id,
                trace_id=trace_id
            )
            
            # Format response
            response = self._format_response(response, channel)
        
        # Flush PostHog events before returning (critical for Lambda)
        if self.posthog:
            try:
                self.posthog.flush()
                logger.info("Flushed PostHog events")
            except Exception as e:
                logger.error(f"Error flushing PostHog: {str(e)}")
        
        return {
            "response": response,
            "thread_id": thread_id,
            "channel": channel,
            "needs_crisis_intervention": needs_crisis,
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "trace_id": trace_id
        }
    
    def get_conversation_title(
        self, 
        messages: List[Dict[str, str]], 
        thread_id: str = None,
        user_id: str = None,
        trace_id: str = None
    ) -> str:
        """
        Generate a concise title for a conversation using GPT-4o-mini
        
        Args:
            messages: List of messages in the conversation
            thread_id: Thread ID of the conversation being summarized (used for PostHog tracing)
            user_id: Optional user ID for PostHog tracking
            trace_id: Optional trace ID to group with parent message handling
            
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
        
        # Create PostHog callback handler for title generation
        posthog_callback = None
        if thread_id and self.posthog:
            try:
                # Determine distinct_id
                distinct_id = user_id or thread_id
                
                # Follow official PostHog LangChain docs pattern - EXACT from working test
                posthog_callback = CallbackHandler(
                    client=self.posthog,
                    distinct_id=distinct_id,
                    trace_id=trace_id,  # Use same trace_id to group with chat generation
                    properties={
                        "conversation_id": thread_id,
                        "$ai_session_id": thread_id,
                        "channel": "web",
                        "operation": "title_generation"
                    },
                    privacy_mode=False
                )
                logger.info(f"Created PostHog callback for title generation - trace_id: {trace_id}, conversation_id: {thread_id}")
            except Exception as e:
                logger.error(f"Failed to create PostHog callback for title generation: {str(e)}")
        
        # Build config with callbacks if PostHog is available
        config = {'callbacks': [posthog_callback]} if posthog_callback else {}
        
        try:
            # Create chain pattern - EXACT like the test: prompt | model
            prompt = ChatPromptTemplate.from_messages([
                ("user", "{input}")
            ])
            chain = prompt | self.title_llm
            
            # Generate title using chain.invoke (not direct llm.invoke)
            response = chain.invoke(
                {"input": title_prompt},
                config=config
            )
            title = response.content.strip()
            
            # Clean up the title
            title = title.replace('"', '').replace("'", '').strip()
            
            # Ensure it's not too long
            if len(title) > 50:
                title = title[:47] + "..."
            
            # Flush PostHog events before returning (critical for Lambda)
            if self.posthog:
                try:
                    self.posthog.flush()
                    logger.info("Flushed PostHog events for title generation")
                except Exception as e:
                    logger.error(f"Error flushing PostHog: {str(e)}")
            
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


def get_agent_service(api_key: str = None, posthog_api_key: str = None) -> AgentService:
    """
    Factory function to get agent service instance
    Useful for Lambda handlers to initialize once
    """
    return AgentService(api_key=api_key, posthog_api_key=posthog_api_key)


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
