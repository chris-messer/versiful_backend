"""
Unit tests for the Stripe webhook handler Lambda
"""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))

# Mock environment variables before importing handler
os.environ['ENVIRONMENT'] = 'test'
os.environ['PROJECT_NAME'] = 'versiful'
os.environ['SECRET_ARN'] = 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test-secret'

# Mock the secrets and stripe initialization
with patch('secrets_helper.get_secret', return_value='sk_test_fake_key'):
    with patch('secrets_helper.get_secrets', return_value={'stripe_webhook_secret': 'whsec_test'}):
        import webhook_handler


class TestWebhookSignatureVerification:
    """Test webhook signature verification"""
    
    @patch('webhook_handler.stripe.Webhook.construct_event')
    def test_valid_signature(self, mock_construct_event):
        """Test that valid signatures are accepted"""
        # Mock a valid Stripe event
        mock_event = {
            'type': 'customer.subscription.created',
            'data': {
                'object': {
                    'id': 'sub_test123',
                    'customer': 'cus_test123',
                    'status': 'active',
                    'metadata': {'userId': 'user-123'}
                }
            }
        }
        mock_construct_event.return_value = mock_event
        
        event = {
            'body': json.dumps({'test': 'data'}),
            'headers': {
                'stripe-signature': 'valid_signature'
            }
        }
        
        with patch('webhook_handler.table.update_item') as mock_update:
            response = webhook_handler.handler(event, {})
            
            assert response['statusCode'] == 200
            mock_construct_event.assert_called_once()
    
    @patch('webhook_handler.stripe.Webhook.construct_event')
    @patch('webhook_handler.get_secrets')
    def test_invalid_signature(self, mock_get_secrets, mock_construct_event):
        """Test that invalid signatures are rejected"""
        # Mock signature verification failure
        import stripe
        mock_construct_event.side_effect = stripe.error.SignatureVerificationError(
            "Invalid signature", "sig_header"
        )
        mock_get_secrets.return_value = {'stripe_webhook_secret': 'whsec_test'}
        
        event = {
            'body': json.dumps({'test': 'data'}),
            'headers': {
                'stripe-signature': 'invalid_signature'
            }
        }
        
        response = webhook_handler.handler(event, {})
        
        assert response['statusCode'] == 400


class TestCheckoutCompleted:
    """Test handling of checkout.session.completed events"""
    
    @patch('webhook_handler.stripe.Subscription.retrieve')
    @patch('webhook_handler.stripe.Webhook.construct_event')
    @patch('webhook_handler.get_secrets')
    @patch('webhook_handler.table.update_item')
    def test_checkout_completed_monthly_subscription(
        self, 
        mock_update, 
        mock_get_secrets,
        mock_construct_event,
        mock_retrieve_sub
    ):
        """Test that checkout.completed creates subscription with correct values"""
        # Mock Stripe subscription response
        mock_retrieve_sub.return_value = {
            'id': 'sub_test123',
            'customer': 'cus_test123',
            'status': 'active',
            'current_period_end': 1735689600,  # Unix timestamp (int)
            'cancel_at_period_end': False,
            'items': {
                'data': [{
                    'price': {
                        'recurring': {
                            'interval': 'month'
                        }
                    }
                }]
            }
        }
        
        mock_event = {
            'type': 'checkout.session.completed',
            'data': {
                'object': {
                    'id': 'cs_test123',
                    'customer': 'cus_test123',
                    'subscription': 'sub_test123',
                    'metadata': {'userId': 'user-123'}
                }
            }
        }
        mock_construct_event.return_value = mock_event
        mock_get_secrets.return_value = {'stripe_webhook_secret': 'whsec_test'}
        
        event = {
            'body': json.dumps(mock_event),
            'headers': {'stripe-signature': 'sig'}
        }
        
        response = webhook_handler.handler(event, {})
        
        assert response['statusCode'] == 200
        
        # Verify DynamoDB update was called
        mock_update.assert_called_once()
        call_args = mock_update.call_args[1]
        
        # Check that plan_monthly_cap is -1 (not None!)
        assert call_args['ExpressionAttributeValues'][':cap'] == -1, \
            "plan_monthly_cap must be -1 (int) for unlimited, not None"
        
        # Check that isSubscribed is True
        assert call_args['ExpressionAttributeValues'][':sub'] is True
        
        # Check that currentPeriodEnd is an integer
        period_end = call_args['ExpressionAttributeValues'][':period_end']
        assert isinstance(period_end, int), \
            f"current_period_end must be an int, got {type(period_end)}"
        assert period_end == 1735689600
        
        # Check that plan is 'monthly'
        assert call_args['ExpressionAttributeValues'][':plan'] == 'monthly'
    
    @patch('webhook_handler.stripe.Subscription.retrieve')
    @patch('webhook_handler.stripe.Webhook.construct_event')
    @patch('webhook_handler.get_secrets')
    @patch('webhook_handler.table.update_item')
    def test_checkout_completed_annual_subscription(
        self, 
        mock_update, 
        mock_get_secrets,
        mock_construct_event,
        mock_retrieve_sub
    ):
        """Test that checkout.completed handles annual subscriptions correctly"""
        mock_retrieve_sub.return_value = {
            'id': 'sub_test456',
            'customer': 'cus_test456',
            'status': 'active',
            'current_period_end': 1767225600,  # Unix timestamp
            'cancel_at_period_end': False,
            'items': {
                'data': [{
                    'price': {
                        'recurring': {
                            'interval': 'year'
                        }
                    }
                }]
            }
        }
        
        mock_event = {
            'type': 'checkout.session.completed',
            'data': {
                'object': {
                    'id': 'cs_test456',
                    'customer': 'cus_test456',
                    'subscription': 'sub_test456',
                    'metadata': {'userId': 'user-456'}
                }
            }
        }
        mock_construct_event.return_value = mock_event
        mock_get_secrets.return_value = {'stripe_webhook_secret': 'whsec_test'}
        
        event = {
            'body': json.dumps(mock_event),
            'headers': {'stripe-signature': 'sig'}
        }
        
        response = webhook_handler.handler(event, {})
        
        assert response['statusCode'] == 200
        call_args = mock_update.call_args[1]
        
        # Verify annual plan is set correctly
        assert call_args['ExpressionAttributeValues'][':plan'] == 'annual'
        assert call_args['ExpressionAttributeValues'][':cap'] == -1
        assert call_args['ExpressionAttributeValues'][':sub'] is True


class TestSubscriptionCreated:
    """Test handling of subscription.created events"""
    
    @patch('webhook_handler.stripe.Webhook.construct_event')
    @patch('webhook_handler.get_secrets')
    @patch('webhook_handler.table.update_item')
    def test_subscription_created_sets_unlimited(
        self, 
        mock_update,
        mock_get_secrets,
        mock_construct_event
    ):
        """Test that subscription.created sets unlimited plan"""
        mock_event = {
            'type': 'customer.subscription.created',
            'data': {
                'object': {
                    'id': 'sub_test123',
                    'customer': 'cus_test123',
                    'status': 'active',
                    'metadata': {'userId': 'user-123'}
                }
            }
        }
        mock_construct_event.return_value = mock_event
        mock_get_secrets.return_value = {'stripe_webhook_secret': 'whsec_test'}
        
        event = {
            'body': json.dumps(mock_event),
            'headers': {'stripe-signature': 'sig'}
        }
        
        response = webhook_handler.handler(event, {})
        
        assert response['statusCode'] == 200


class TestSubscriptionUpdated:
    """Test handling of subscription.updated events"""
    
    @patch('webhook_handler.stripe.Subscription.retrieve')
    @patch('webhook_handler.stripe.Webhook.construct_event')
    @patch('webhook_handler.get_secrets')
    @patch('webhook_handler.table.scan')
    @patch('webhook_handler.table.update_item')
    def test_subscription_updated_active(
        self, 
        mock_update,
        mock_scan,
        mock_get_secrets,
        mock_construct_event,
        mock_retrieve_sub
    ):
        """Test that subscription.updated with active status maintains subscription"""
        # Mock the scan to find the user
        mock_scan.return_value = {
            'Items': [{
                'userId': 'user-123',
                'email': 'test@example.com',
                'stripeCustomerId': 'cus_test123'
            }]
        }
        
        mock_event = {
            'type': 'customer.subscription.updated',
            'data': {
                'object': {
                    'id': 'sub_test123',
                    'customer': 'cus_test123',
                    'status': 'active',
                    'current_period_end': 1735689600,  # Unix timestamp
                    'cancel_at_period_end': False,
                    'items': {
                        'data': [{
                            'price': {
                                'recurring': {
                                    'interval': 'month'
                                }
                            }
                        }]
                    }
                }
            }
        }
        mock_construct_event.return_value = mock_event
        mock_get_secrets.return_value = {'stripe_webhook_secret': 'whsec_test'}
        
        event = {
            'body': json.dumps(mock_event),
            'headers': {'stripe-signature': 'sig'}
        }
        
        response = webhook_handler.handler(event, {})
        
        assert response['statusCode'] == 200
        mock_update.assert_called_once()
        call_args = mock_update.call_args[1]
        
        # Verify unlimited cap is set correctly
        assert call_args['ExpressionAttributeValues'][':cap'] == -1, \
            "Updated subscription must have plan_monthly_cap = -1 for unlimited"
        assert call_args['ExpressionAttributeValues'][':sub'] is True
        
        # Verify period_end is an integer
        period_end = call_args['ExpressionAttributeValues'][':period_end']
        assert isinstance(period_end, int), \
            f"current_period_end must be int, got {type(period_end)}"
    
    @patch('webhook_handler.stripe.Webhook.construct_event')
    @patch('webhook_handler.get_secrets')
    @patch('webhook_handler.table.scan')
    @patch('webhook_handler.table.update_item')
    def test_subscription_updated_canceled(
        self, 
        mock_update,
        mock_scan,
        mock_get_secrets,
        mock_construct_event
    ):
        """Test that subscription.updated with canceled status removes subscription"""
        mock_scan.return_value = {
            'Items': [{
                'userId': 'user-123',
                'stripeCustomerId': 'cus_test123'
            }]
        }
        
        mock_event = {
            'type': 'customer.subscription.updated',
            'data': {
                'object': {
                    'id': 'sub_test123',
                    'customer': 'cus_test123',
                    'status': 'canceled',
                    'current_period_end': 1735689600,
                    'cancel_at_period_end': True,
                    'items': {
                        'data': [{
                            'price': {
                                'recurring': {
                                    'interval': 'month'
                                }
                            }
                        }]
                    }
                }
            }
        }
        mock_construct_event.return_value = mock_event
        mock_get_secrets.return_value = {'stripe_webhook_secret': 'whsec_test'}
        
        event = {
            'body': json.dumps(mock_event),
            'headers': {'stripe-signature': 'sig'}
        }
        
        response = webhook_handler.handler(event, {})
        
        assert response['statusCode'] == 200
        mock_update.assert_called_once()
        call_args = mock_update.call_args[1]
        
        # When canceled, status is not active/trialing, so isSubscribed should be False
        assert call_args['ExpressionAttributeValues'][':sub'] is False


class TestSubscriptionDeleted:
    """Test handling of subscription.deleted events"""
    
    @patch('webhook_handler.stripe.Webhook.construct_event')
    @patch('webhook_handler.get_secrets')
    @patch('webhook_handler.table.scan')
    @patch('webhook_handler.table.update_item')
    def test_subscription_deleted_removes_subscription(
        self, 
        mock_update,
        mock_scan,
        mock_get_secrets,
        mock_construct_event
    ):
        """Test that subscription.deleted removes subscription and resets to free"""
        mock_scan.return_value = {
            'Items': [{
                'userId': 'user-123',
                'stripeCustomerId': 'cus_test123'
            }]
        }
        
        mock_event = {
            'type': 'customer.subscription.deleted',
            'data': {
                'object': {
                    'id': 'sub_test123',
                    'customer': 'cus_test123'
                }
            }
        }
        mock_construct_event.return_value = mock_event
        mock_get_secrets.return_value = {'stripe_webhook_secret': 'whsec_test'}
        
        event = {
            'body': json.dumps(mock_event),
            'headers': {'stripe-signature': 'sig'}
        }
        
        response = webhook_handler.handler(event, {})
        
        assert response['statusCode'] == 200
        mock_update.assert_called_once()
        call_args = mock_update.call_args[1]
        
        # When deleted, user should be reverted to free tier
        assert call_args['ExpressionAttributeValues'][':sub'] is False
        assert call_args['ExpressionAttributeValues'][':cap'] == 5, \
            "Deleted subscription must revert to free tier with 5 messages"
        assert call_args['ExpressionAttributeValues'][':plan'] == 'free'


class TestPaymentSucceeded:
    """Test handling of payment succeeded events"""
    
    @patch('webhook_handler.stripe.Subscription.retrieve')
    @patch('webhook_handler.stripe.Webhook.construct_event')
    @patch('webhook_handler.get_secrets')
    @patch('webhook_handler.table.scan')
    @patch('webhook_handler.table.update_item')
    def test_payment_succeeded_maintains_unlimited(
        self,
        mock_update,
        mock_scan,
        mock_get_secrets,
        mock_construct_event,
        mock_retrieve_sub
    ):
        """Test that payment success maintains unlimited plan cap"""
        mock_scan.return_value = {
            'Items': [{
                'userId': 'user-123',
                'stripeCustomerId': 'cus_test123'
            }]
        }
        
        mock_retrieve_sub.return_value = {
            'id': 'sub_test123',
            'status': 'active',
            'current_period_end': 1735689600  # Unix timestamp
        }
        
        mock_event = {
            'type': 'invoice.payment_succeeded',
            'data': {
                'object': {
                    'id': 'in_test123',
                    'customer': 'cus_test123',
                    'subscription': 'sub_test123'
                }
            }
        }
        mock_construct_event.return_value = mock_event
        mock_get_secrets.return_value = {'stripe_webhook_secret': 'whsec_test'}
        
        event = {
            'body': json.dumps(mock_event),
            'headers': {'stripe-signature': 'sig'}
        }
        
        response = webhook_handler.handler(event, {})
        
        assert response['statusCode'] == 200
        mock_update.assert_called_once()
        call_args = mock_update.call_args[1]
        
        # Payment success should maintain unlimited cap
        assert call_args['ExpressionAttributeValues'][':cap'] == -1, \
            "Successful payment must maintain plan_monthly_cap = -1"
        assert call_args['ExpressionAttributeValues'][':sub'] is True
        
        # Verify period_end is int
        period_end = call_args['ExpressionAttributeValues'][':period_end']
        assert isinstance(period_end, int)


class TestPaymentFailed:
    """Test handling of payment failed events"""
    
    @patch('webhook_handler.stripe.Subscription.retrieve')
    @patch('webhook_handler.stripe.Webhook.construct_event')
    @patch('webhook_handler.get_secrets')
    @patch('webhook_handler.table.scan')
    @patch('webhook_handler.table.update_item')
    @patch('webhook_handler.logger.warning')
    def test_invoice_payment_failed_past_due(
        self, 
        mock_logger,
        mock_update,
        mock_scan,
        mock_get_secrets,
        mock_construct_event,
        mock_retrieve_sub
    ):
        """Test that payment failures maintain access for past_due status"""
        mock_scan.return_value = {
            'Items': [{
                'userId': 'user-123',
                'stripeCustomerId': 'cus_test123'
            }]
        }
        
        mock_retrieve_sub.return_value = {
            'id': 'sub_test123',
            'status': 'past_due'
        }
        
        mock_event = {
            'type': 'invoice.payment_failed',
            'data': {
                'object': {
                    'id': 'in_test123',
                    'customer': 'cus_test123',
                    'subscription': 'sub_test123'
                }
            }
        }
        mock_construct_event.return_value = mock_event
        mock_get_secrets.return_value = {'stripe_webhook_secret': 'whsec_test'}
        
        event = {
            'body': json.dumps(mock_event),
            'headers': {'stripe-signature': 'sig'}
        }
        
        response = webhook_handler.handler(event, {})
        
        assert response['statusCode'] == 200
        mock_update.assert_called_once()
        call_args = mock_update.call_args[1]
        
        # past_due should still be subscribed with unlimited
        assert call_args['ExpressionAttributeValues'][':sub'] is True
        assert call_args['ExpressionAttributeValues'][':cap'] == -1, \
            "past_due status should maintain unlimited access"
        
        # Verify warning was logged
        mock_logger.assert_called()


class TestUnhandledEvents:
    """Test handling of unhandled event types"""
    
    @patch('webhook_handler.stripe.Webhook.construct_event')
    @patch('webhook_handler.logger.info')
    def test_unhandled_event_returns_success(
        self, 
        mock_logger,
        mock_construct_event
    ):
        """Test that unhandled events return 200 but are logged"""
        mock_event = {
            'type': 'customer.created',
            'data': {
                'object': {
                    'id': 'cus_test123'
                }
            }
        }
        mock_construct_event.return_value = mock_event
        
        event = {
            'body': json.dumps(mock_event),
            'headers': {'stripe-signature': 'sig'}
        }
        
        response = webhook_handler.handler(event, {})
        
        assert response['statusCode'] == 200
        # Verify it was logged as unhandled
        assert any('Unhandled' in str(call) or 'unhandled' in str(call) 
                  for call in mock_logger.call_args_list)


class TestMissingUserId:
    """Test handling of events without userId in metadata"""
    
    @patch('webhook_handler.stripe.Subscription.retrieve')
    @patch('webhook_handler.stripe.Webhook.construct_event')
    @patch('webhook_handler.get_secrets')
    @patch('webhook_handler.logger.error')
    def test_missing_user_id_logs_error(
        self,
        mock_logger,
        mock_get_secrets,
        mock_construct_event,
        mock_retrieve_sub
    ):
        """Test that missing userId is handled gracefully"""
        mock_retrieve_sub.return_value = {
            'id': 'sub_test123',
            'status': 'active',
            'current_period_end': 1735689600,
            'cancel_at_period_end': False,
            'items': {
                'data': [{
                    'price': {
                        'recurring': {
                            'interval': 'month'
                        }
                    }
                }]
            }
        }
        
        mock_event = {
            'type': 'checkout.session.completed',
            'data': {
                'object': {
                    'id': 'cs_test123',
                    'customer': 'cus_test123',
                    'subscription': 'sub_test123',
                    'metadata': {}  # No userId
                }
            }
        }
        mock_construct_event.return_value = mock_event
        mock_get_secrets.return_value = {'stripe_webhook_secret': 'whsec_test'}
        
        event = {
            'body': json.dumps(mock_event),
            'headers': {'stripe-signature': 'sig'}
        }
        
        response = webhook_handler.handler(event, {})
        
        # Should still return 200 to acknowledge receipt
        assert response['statusCode'] == 200
        # But should log an error
        mock_logger.assert_called()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

