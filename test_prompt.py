#!/usr/bin/env python3
"""
Test script to output the full prompt sent to the LLM for a web user query
"""
import os
import yaml

def test_web_prompt():
    """Test what prompt is sent for a web user asking about botox"""
    
    print("=" * 80)
    print("Testing Web Chat Prompt Generation")
    print("=" * 80)
    print()
    
    # Load the config
    config_path = os.path.join(os.path.dirname(__file__), 'lambdas', 'chat', 'agent_config.yaml')
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    print(f"Configuration File: {config_path}")
    print()
    
    # Get the system prompt for web
    system_prompt = config['system_prompt']
    
    # The user's question
    user_message = "what does the bible say about botox?"
    
    print(f"User Message: {user_message}")
    print()
    print("=" * 80)
    print("FULL PROMPT SENT TO LLM (Web Channel)")
    print("=" * 80)
    print()
    
    # Build the messages that would be sent to the LLM (no history)
    print(f"Message 1 [SystemMessage - System]:")
    print("-" * 80)
    print(system_prompt)
    print()
    
    print(f"Message 2 [HumanMessage - Human]:")
    print("-" * 80)
    print(user_message)
    print()
    
    print("=" * 80)
    print("END OF PROMPT (No Conversation History)")
    print("=" * 80)
    print()
    
    # Now test with conversation history
    print()
    print("=" * 80)
    print("TESTING WITH CONVERSATION HISTORY")
    print("=" * 80)
    print()
    
    conversation_history = [
        {'role': 'user', 'content': 'I am feeling lost'},
        {'role': 'assistant', 'content': 'Luke 15:11-32\n\nThe Parable of the Prodigal Son tells of a young man who felt lost...'}
    ]
    
    print(f"Message 1 [SystemMessage - System]:")
    print("-" * 80)
    print(system_prompt)
    print()
    
    print(f"Message 2 [HumanMessage - Human]:")
    print("-" * 80)
    print(conversation_history[0]['content'])
    print()
    
    print(f"Message 3 [AIMessage - Assistant]:")
    print("-" * 80)
    print(conversation_history[1]['content'])
    print()
    
    print(f"Message 4 [HumanMessage - Human]:")
    print("-" * 80)
    print(user_message)
    print()
    
    print("=" * 80)
    print("CONFIGURATION DETAILS")
    print("=" * 80)
    print()
    print(f"Model: {config['llm']['model']}")
    print(f"Temperature: {config['llm']['temperature']}")
    print(f"Max Tokens (Web): {config['llm']['max_tokens']}")
    print(f"Max Tokens (SMS): {config['llm']['sms']['max_tokens']}")
    print()
    print(f"Context Window (last N messages used): {config['history']['context_window']}")
    print()
    
    print("=" * 80)
    print("SMS SYSTEM PROMPT (for comparison)")
    print("=" * 80)
    print()
    print(config['sms_system_prompt'])
    print()

if __name__ == '__main__':
    test_web_prompt()

