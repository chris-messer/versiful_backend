"""
Unit tests for SMS handler - specifically testing plan_monthly_cap logic
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

# Mock environment variables
os.environ['ENVIRONMENT'] = 'test'
os.environ['PROJECT_NAME'] = 'versiful'
os.environ['SECRET_ARN'] = 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret'

import sms_handler


class TestPlanMonthlyCapLogic:
    """Test that plan_monthly_cap values are correctly interpreted"""
    
    @patch('sms_handler.get_sms_usage')
    @patch('sms_handler.get_user_by_id')
    def test_isSubscribed_true_grants_unlimited(
        self,
        mock_get_user,
        mock_get_usage
    ):
        """Test that isSubscribed=true grants unlimited access"""
        mock_get_usage.return_value = {
            'phoneNumber': '+15555551234',
            'userId': 'user-123'
        }
        
        mock_get_user.return_value = {
            'userId': 'user-123',
            'email': 'test@example.com',
            'isSubscribed': True,
            'plan_monthly_cap': -1
        }
        
        result = sms_handler._evaluate_usage('+15555551234')
        
        # Should be allowed with no limit
        assert result['allowed'] is True
        assert result['limit'] is None
        assert result['reason'] == 'subscribed'
    
    @patch('sms_handler.get_sms_usage')
    @patch('sms_handler.get_user_by_id')
    def test_plan_monthly_cap_minus_one_grants_unlimited(
        self,
        mock_get_user,
        mock_get_usage
    ):
        """
        Test that plan_monthly_cap=-1 grants unlimited even if isSubscribed=false.
        This is critical - -1 should NEVER be passed to consume_message_if_allowed.
        """
        mock_get_usage.return_value = {
            'phoneNumber': '+15555551234',
            'userId': 'user-123'
        }
        
        # User with isSubscribed=false but plan_monthly_cap=-1
        # This might happen in edge cases or during testing
        mock_get_user.return_value = {
            'userId': 'user-123',
            'email': 'test@example.com',
            'isSubscribed': False,
            'plan_monthly_cap': -1
        }
        
        result = sms_handler._evaluate_usage('+15555551234')
        
        # Should be allowed with no limit
        assert result['allowed'] is True, \
            "plan_monthly_cap=-1 must grant unlimited access"
        assert result['limit'] is None, \
            "limit must be None (unlimited), not -1"
        assert result['reason'] == 'unlimited_cap'
    
    @patch('sms_handler.get_sms_usage')
    @patch('sms_handler.get_user_by_id')
    @patch('sms_handler.consume_message_if_allowed')
    def test_plan_monthly_cap_specific_limit(
        self,
        mock_consume,
        mock_get_user,
        mock_get_usage
    ):
        """Test that specific plan_monthly_cap values are enforced"""
        mock_get_usage.return_value = {
            'phoneNumber': '+15555551234',
            'userId': 'user-123'
        }
        
        mock_get_user.return_value = {
            'userId': 'user-123',
            'email': 'test@example.com',
            'isSubscribed': False,
            'plan_monthly_cap': 50  # Custom limit
        }
        
        # Mock successful consumption
        mock_consume.return_value = {
            'phoneNumber': '+15555551234',
            'plan_messages_sent': 10
        }
        
        result = sms_handler._evaluate_usage('+15555551234')
        
        # Should use the custom limit
        mock_consume.assert_called_once_with(
            '+15555551234',
            50,  # Should use plan_monthly_cap
            user_id='user-123'
        )
        assert result['allowed'] is True
        assert result['limit'] == 50
    
    @patch('sms_handler.get_sms_usage')
    @patch('sms_handler.get_user_by_id')
    @patch('sms_handler.consume_message_if_allowed')
    def test_plan_monthly_cap_free_tier_default(
        self,
        mock_consume,
        mock_get_user,
        mock_get_usage
    ):
        """Test that null plan_monthly_cap defaults to 5 messages"""
        mock_get_usage.return_value = {
            'phoneNumber': '+15555551234',
            'userId': 'user-123'
        }
        
        mock_get_user.return_value = {
            'userId': 'user-123',
            'email': 'test@example.com',
            'isSubscribed': False,
            'plan_monthly_cap': None  # No cap specified
        }
        
        mock_consume.return_value = {
            'phoneNumber': '+15555551234',
            'plan_messages_sent': 3
        }
        
        result = sms_handler._evaluate_usage('+15555551234')
        
        # Should default to FREE_MONTHLY_LIMIT (5)
        mock_consume.assert_called_once()
        call_args = mock_consume.call_args[0]
        assert call_args[1] == 5, "Should default to 5 messages for free tier"
    
    @patch('sms_handler.get_sms_usage')
    @patch('sms_handler.get_user_by_id')
    @patch('sms_handler.consume_message_if_allowed')
    def test_never_pass_negative_one_to_consume(
        self,
        mock_consume,
        mock_get_user,
        mock_get_usage
    ):
        """
        Critical test: Ensure -1 is NEVER passed to consume_message_if_allowed.
        If -1 is passed, the condition (messages_sent < -1) will always fail.
        """
        mock_get_usage.return_value = {
            'phoneNumber': '+15555551234',
            'userId': 'user-123'
        }
        
        mock_get_user.return_value = {
            'userId': 'user-123',
            'isSubscribed': False,
            'plan_monthly_cap': -1
        }
        
        result = sms_handler._evaluate_usage('+15555551234')
        
        # consume_message_if_allowed should NEVER be called with -1
        mock_consume.assert_not_called()
        assert result['allowed'] is True
        assert result['limit'] is None


class TestConsistentBehavior:
    """Test that both isSubscribed and plan_monthly_cap=-1 behave identically"""
    
    @patch('sms_handler.get_sms_usage')
    @patch('sms_handler.get_user_by_id')
    def test_unlimited_via_isSubscribed_vs_cap(
        self,
        mock_get_user,
        mock_get_usage
    ):
        """Test that unlimited via isSubscribed and plan_monthly_cap=-1 behave the same"""
        mock_get_usage.return_value = {
            'phoneNumber': '+15555551234',
            'userId': 'user-123'
        }
        
        # Test with isSubscribed=true
        mock_get_user.return_value = {
            'userId': 'user-123',
            'isSubscribed': True,
            'plan_monthly_cap': -1
        }
        result1 = sms_handler._evaluate_usage('+15555551234')
        
        # Test with isSubscribed=false but plan_monthly_cap=-1
        mock_get_user.return_value = {
            'userId': 'user-123',
            'isSubscribed': False,
            'plan_monthly_cap': -1
        }
        result2 = sms_handler._evaluate_usage('+15555551234')
        
        # Both should grant unlimited access
        assert result1['allowed'] is True
        assert result1['limit'] is None
        assert result2['allowed'] is True
        assert result2['limit'] is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

