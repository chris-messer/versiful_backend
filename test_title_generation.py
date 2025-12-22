#!/usr/bin/env python3
"""
Test script for AI-powered conversation title generation
"""
import os
import sys

# Add lambdas/chat to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../lambdas/chat'))

from agent_service import get_agent_service


def test_title_generation():
    """Test the title generation functionality"""
    
    # Check for API key
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        print("ERROR: Please set OPENAI_API_KEY environment variable")
        sys.exit(1)
    
    # Initialize agent
    print("Initializing agent service...")
    agent = get_agent_service(api_key=api_key)
    
    # Test conversations
    test_conversations = [
        {
            "name": "Prayer Request",
            "messages": [
                {"role": "user", "content": "I'm feeling really anxious about my job interview tomorrow. Can you pray with me?"},
                {"role": "assistant", "content": "I understand your anxiety. Let's turn to Philippians 4:6-7..."},
                {"role": "user", "content": "Thank you, that really helps. What other verses talk about anxiety?"},
                {"role": "assistant", "content": "Here are several verses about peace and anxiety..."}
            ]
        },
        {
            "name": "Bible Study",
            "messages": [
                {"role": "user", "content": "Can you help me understand the parable of the prodigal son?"},
                {"role": "assistant", "content": "The parable of the prodigal son is found in Luke 15:11-32..."},
                {"role": "user", "content": "Why did the father celebrate when the son returned?"},
                {"role": "assistant", "content": "This represents God's unconditional love and forgiveness..."}
            ]
        },
        {
            "name": "Life Guidance",
            "messages": [
                {"role": "user", "content": "I'm struggling with forgiving someone who hurt me deeply"},
                {"role": "assistant", "content": "Forgiveness is one of the most challenging aspects of faith..."},
                {"role": "user", "content": "What does the Bible say about forgiveness?"},
                {"role": "assistant", "content": "The Bible has much to say about forgiveness. Let's look at Ephesians 4:32..."}
            ]
        }
    ]
    
    print("\n" + "="*60)
    print("Testing AI Title Generation with GPT-4o-mini")
    print("="*60 + "\n")
    
    for i, conversation in enumerate(test_conversations, 1):
        print(f"\nTest {i}: {conversation['name']}")
        print("-" * 60)
        print(f"First message: {conversation['messages'][0]['content'][:60]}...")
        
        try:
            title = agent.get_conversation_title(conversation['messages'])
            print(f"✓ Generated Title: '{title}'")
            print(f"  Length: {len(title)} characters")
        except Exception as e:
            print(f"✗ Error: {str(e)}")
    
    print("\n" + "="*60)
    print("Title Generation Tests Complete!")
    print("="*60 + "\n")


if __name__ == "__main__":
    test_title_generation()

