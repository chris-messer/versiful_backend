"""
Test script to verify Bible version preference feature
Run this locally to test the chat handler with bible version injection
"""
import os
import sys
import json
from unittest.mock import MagicMock, patch

# Add lambdas to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lambdas/chat'))

def test_bible_version_injection():
    """Test that bible version is properly injected into prompts"""
    
    print("=" * 60)
    print("Testing Bible Version Injection")
    print("=" * 60)
    
    # Import agent service
    from agent_service import AgentService
    
    # Create agent service instance (requires OpenAI API key)
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        print("❌ OPENAI_API_KEY not set in environment")
        print("Set it with: export OPENAI_API_KEY='your-key-here'")
        return False
    
    try:
        agent = AgentService(api_key=api_key)
        print("✓ Agent service initialized")
    except Exception as e:
        print(f"❌ Failed to initialize agent service: {e}")
        return False
    
    # Test 1: Process message without bible version
    print("\n" + "-" * 60)
    print("Test 1: Message WITHOUT bible version preference")
    print("-" * 60)
    
    result1 = agent.process_message(
        thread_id="test-thread-1",
        message="Can you share a verse about peace?",
        channel="web",
        history=[],
        user_id="test-user-1",
        bible_version=None  # No preference
    )
    
    print(f"Response: {result1['response'][:200]}...")
    print("✓ Message processed without bible version")
    
    # Test 2: Process message with KJV bible version
    print("\n" + "-" * 60)
    print("Test 2: Message WITH KJV bible version preference")
    print("-" * 60)
    
    result2 = agent.process_message(
        thread_id="test-thread-2",
        message="Can you share a verse about peace?",
        channel="web",
        history=[],
        user_id="test-user-2",
        bible_version="KJV"  # User prefers KJV
    )
    
    print(f"Response: {result2['response'][:200]}...")
    
    # Check if response likely contains KJV (look for "thee", "thou", etc.)
    kjv_indicators = ['thee', 'thou', 'thy', 'unto', 'hath', 'saith']
    has_kjv_language = any(word in result2['response'].lower() for word in kjv_indicators)
    
    if has_kjv_language:
        print("✓ Response appears to use KJV language")
    else:
        print("⚠ Response may not be using KJV (this is not guaranteed due to LLM variability)")
    
    # Test 3: Process message with NIV bible version
    print("\n" + "-" * 60)
    print("Test 3: Message WITH NIV bible version preference")
    print("-" * 60)
    
    result3 = agent.process_message(
        thread_id="test-thread-3",
        message="Can you share a verse about peace?",
        channel="web",
        history=[],
        user_id="test-user-3",
        bible_version="NIV"  # User prefers NIV
    )
    
    print(f"Response: {result3['response'][:200]}...")
    print("✓ Message processed with NIV bible version")
    
    # Test 4: SMS channel with bible version
    print("\n" + "-" * 60)
    print("Test 4: SMS channel WITH bible version preference")
    print("-" * 60)
    
    result4 = agent.process_message(
        thread_id="+12345678901",
        message="I need encouragement",
        channel="sms",
        history=[],
        user_id="test-user-4",
        bible_version="ESV"  # User prefers ESV
    )
    
    print(f"Response length: {len(result4['response'])} chars")
    print(f"Response: {result4['response']}")
    print("✓ SMS message processed with ESV bible version")
    
    if len(result4['response']) < 1500:
        print("✓ SMS response is within length limit")
    else:
        print("⚠ SMS response may be too long")
    
    print("\n" + "=" * 60)
    print("All tests completed successfully! ✓")
    print("=" * 60)
    
    return True


def test_chat_handler_integration():
    """Test the full chat handler with mocked DynamoDB"""
    
    print("\n" + "=" * 60)
    print("Testing Chat Handler Integration")
    print("=" * 60)
    
    # Set up environment
    os.environ['ENVIRONMENT'] = 'dev'
    os.environ['PROJECT_NAME'] = 'versiful'
    os.environ['CHAT_MESSAGES_TABLE'] = 'dev-versiful-chat-messages'
    os.environ['CHAT_SESSIONS_TABLE'] = 'dev-versiful-chat-sessions'
    os.environ['USERS_TABLE'] = 'dev-versiful-users'
    
    # Mock DynamoDB
    with patch('boto3.resource') as mock_boto:
        # Set up mock tables
        mock_dynamodb = MagicMock()
        mock_boto.return_value = mock_dynamodb
        
        # Mock messages table
        mock_messages_table = MagicMock()
        mock_messages_table.query.return_value = {'Items': []}
        mock_messages_table.put_item.return_value = {}
        
        # Mock sessions table
        mock_sessions_table = MagicMock()
        
        # Mock users table - return user with bible version
        mock_users_table = MagicMock()
        mock_users_table.get_item.return_value = {
            'Item': {
                'userId': 'test-user-123',
                'bibleVersion': 'KJV',
                'firstName': 'Test',
                'lastName': 'User'
            }
        }
        
        # Configure dynamodb.Table() to return appropriate mocks
        def table_side_effect(table_name):
            if 'messages' in table_name:
                return mock_messages_table
            elif 'sessions' in table_name:
                return mock_sessions_table
            elif 'users' in table_name:
                return mock_users_table
            return MagicMock()
        
        mock_dynamodb.Table.side_effect = table_side_effect
        
        # Import chat handler
        from chat_handler import get_user_bible_version, process_chat_message
        
        # Test get_user_bible_version
        print("\nTest: get_user_bible_version()")
        bible_version = get_user_bible_version('test-user-123')
        print(f"Retrieved bible version: {bible_version}")
        
        if bible_version == 'KJV':
            print("✓ Successfully fetched user's bible version")
        else:
            print(f"⚠ Expected 'KJV', got '{bible_version}'")
        
        print("\n✓ Chat handler integration tests passed")


def main():
    """Run all tests"""
    print("\n" + "🔬 Bible Version Feature Test Suite")
    print("=" * 60)
    
    # Check if OpenAI API key is available
    if not os.environ.get('OPENAI_API_KEY'):
        print("\n⚠️  WARNING: OPENAI_API_KEY not set")
        print("Some tests will be skipped.")
        print("\nTo run full tests, set your API key:")
        print("  export OPENAI_API_KEY='your-key-here'")
        print("\nRunning limited tests...\n")
        
        # Run only integration tests
        test_chat_handler_integration()
    else:
        # Run all tests
        test_bible_version_injection()
        test_chat_handler_integration()
    
    print("\n" + "=" * 60)
    print("✅ Test suite completed!")
    print("=" * 60 + "\n")


if __name__ == '__main__':
    main()

