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
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI

logger = logging.getLogger()
logger.setLevel(logging.INFO)


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
        
        # Initialize LLM
        llm_config = self.config['llm']
        self.llm = ChatOpenAI(
            model=llm_config['model'],
            temperature=llm_config['temperature'],
            max_tokens=llm_config['max_tokens']
        )
        
        # Initialize SMS-specific LLM
        sms_config = llm_config.get('sms', {})
        self.sms_llm = ChatOpenAI(
            model=llm_config['model'],
            temperature=sms_config.get('temperature', llm_config['temperature']),
            max_tokens=sms_config.get('max_tokens', 300)
        )
        
        logger.info("AgentService initialized with model: %s", llm_config['model'])
    
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
        is_off_topic: bool = False
    ) -> str:
        """Generate response using LLM"""
        # Select appropriate LLM and system prompt
        if channel == 'sms':
            llm = self.sms_llm
            system_prompt = self.config.get('sms_system_prompt', self.config['system_prompt'])
        else:
            llm = self.llm
            system_prompt = self.config['system_prompt']
        
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
        
        # Generate response
        try:
            response = llm.invoke(llm_messages)
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
        user_id: str = None
    ) -> Dict[str, Any]:
        """
        Process a message and generate a response
        
        Args:
            thread_id: Unique thread identifier
            message: User's message
            channel: "sms" or "web"
            history: Previous messages in format [{"role": "user/assistant", "content": "..."}]
            user_id: Optional user ID
            
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
            response = self._generate_llm_response(messages, channel, is_off_topic)
            
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
        Generate a title for a conversation based on initial messages
        
        Args:
            messages: List of messages in the conversation
            
        Returns:
            A short title (max 50 chars)
        """
        if not messages:
            return "New Conversation"
        
        # Get first user message
        first_user_msg = next((m for m in messages if m['role'] == 'user'), None)
        if not first_user_msg:
            return "New Conversation"
        
        content = first_user_msg['content']
        
        # Simple title generation: take first sentence or 50 chars
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
