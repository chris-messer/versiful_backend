"""
Unit tests for the Stripe subscription handler Lambda
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
os.environ['FRONTEND_DOMAIN'] = 'test.versiful.io'

# Mock the secrets helper before importing
with patch('subscription_handler.get_secret') as mock_get_secret:
    mock_get_secret.return_value = 'sk_test_fake_key'
    import subscription_handler


class TestGetPrices:
    """Test the get_prices endpoint"""
    
    def test_get_prices_returns_correct_structure(self):
        """Test that get_prices returns the expected price IDs"""
        event = {
            'path': '/subscription/prices',
            'httpMethod': 'GET'
        }
        
        response = subscription_handler.get_prices(event, {})
        
        assert response['statusCode'] == 200
        assert 'Content-Type' in response['headers']
        assert response['headers']['Content-Type'] == 'application/json'
        
        body = json.loads(response['body'])
        assert 'monthly' in body
        assert 'annual' in body
        assert body['monthly'].startswith('price_')
        assert body['annual'].startswith('price_')
    
    def test_get_prices_handles_errors(self):
        """Test that get_prices handles errors gracefully"""
        event = {
            'path': '/subscription/prices',
            'httpMethod': 'GET'
        }
        
        with patch('subscription_handler.logger.error') as mock_logger:
            # Even if there's an internal error, the function should return valid price IDs
            response = subscription_handler.get_prices(event, {})
            assert response['statusCode'] == 200


class TestCreateCheckoutSession:
    """Test the create_checkout_session endpoint"""
    
    @patch('subscription_handler.stripe.checkout.Session.create')
    @patch('subscription_handler.stripe.Customer.create')
    @patch('subscription_handler.table.get_item')
    @patch('subscription_handler.table.update_item')
    def test_create_checkout_session_new_customer(
        self, 
        mock_update, 
        mock_get_item, 
        mock_create_customer,
        mock_create_session
    ):
        """Test creating a checkout session for a new customer"""
        # Mock user data without existing Stripe customer
        mock_get_item.return_value = {
            'Item': {
                'userId': 'test-user-123',
                'email': 'test@example.com'
            }
        }
        
        # Mock Stripe customer creation
        mock_create_customer.return_value = Mock(id='cus_test123')
        
        # Mock Stripe checkout session creation
        mock_create_session.return_value = Mock(
            id='cs_test123',
            url='https://checkout.stripe.com/test'
        )
        
        event = {
            'path': '/subscription/checkout',
            'httpMethod': 'POST',
            'requestContext': {
                'authorizer': {
                    'userId': 'test-user-123'
                }
            },
            'body': json.dumps({
                'priceId': 'price_test123',
                'successUrl': 'https://test.com/success',
                'cancelUrl': 'https://test.com/cancel'
            })
        }
        
        response = subscription_handler.create_checkout_session(event, {})
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'url' in body
        assert 'sessionId' in body
        assert body['sessionId'] == 'cs_test123'
        
        # Verify customer was created and saved
        mock_create_customer.assert_called_once()
        mock_update.assert_called_once()
    
    @patch('subscription_handler.stripe.checkout.Session.create')
    @patch('subscription_handler.table.get_item')
    def test_create_checkout_session_existing_customer(
        self, 
        mock_get_item, 
        mock_create_session
    ):
        """Test creating a checkout session for an existing customer"""
        # Mock user data with existing Stripe customer
        mock_get_item.return_value = {
            'Item': {
                'userId': 'test-user-123',
                'email': 'test@example.com',
                'stripeCustomerId': 'cus_existing123'
            }
        }
        
        # Mock Stripe checkout session creation
        mock_create_session.return_value = Mock(
            id='cs_test456',
            url='https://checkout.stripe.com/test'
        )
        
        event = {
            'path': '/subscription/checkout',
            'httpMethod': 'POST',
            'requestContext': {
                'authorizer': {
                    'userId': 'test-user-123'
                }
            },
            'body': json.dumps({
                'priceId': 'price_test123',
                'successUrl': 'https://test.com/success',
                'cancelUrl': 'https://test.com/cancel'
            })
        }
        
        response = subscription_handler.create_checkout_session(event, {})
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['sessionId'] == 'cs_test456'
    
    @patch('subscription_handler.table.get_item')
    def test_create_checkout_session_missing_email(self, mock_get_item):
        """Test that checkout session fails without user email"""
        # Mock user data without email
        mock_get_item.return_value = {
            'Item': {
                'userId': 'test-user-123'
            }
        }
        
        event = {
            'path': '/subscription/checkout',
            'httpMethod': 'POST',
            'requestContext': {
                'authorizer': {
                    'userId': 'test-user-123'
                }
            },
            'body': json.dumps({
                'priceId': 'price_test123',
                'successUrl': 'https://test.com/success',
                'cancelUrl': 'https://test.com/cancel'
            })
        }
        
        response = subscription_handler.create_checkout_session(event, {})
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'error' in body
        assert 'email' in body['error'].lower()
    
    def test_create_checkout_session_missing_price_id(self):
        """Test that checkout session fails without priceId"""
        event = {
            'path': '/subscription/checkout',
            'httpMethod': 'POST',
            'requestContext': {
                'authorizer': {
                    'userId': 'test-user-123'
                }
            },
            'body': json.dumps({
                'successUrl': 'https://test.com/success',
                'cancelUrl': 'https://test.com/cancel'
            })
        }
        
        response = subscription_handler.create_checkout_session(event, {})
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'error' in body
        assert 'priceId' in body['error']


class TestCreatePortalSession:
    """Test the create_portal_session endpoint"""
    
    @patch('subscription_handler.stripe.billing_portal.Session.create')
    @patch('subscription_handler.table.get_item')
    def test_create_portal_session_success(self, mock_get_item, mock_create_portal):
        """Test creating a customer portal session"""
        # Mock user data with Stripe customer
        mock_get_item.return_value = {
            'Item': {
                'userId': 'test-user-123',
                'email': 'test@example.com',
                'stripeCustomerId': 'cus_test123'
            }
        }
        
        # Mock Stripe portal session creation
        mock_create_portal.return_value = Mock(
            url='https://billing.stripe.com/session/test'
        )
        
        event = {
            'path': '/subscription/portal',
            'httpMethod': 'POST',
            'requestContext': {
                'authorizer': {
                    'userId': 'test-user-123'
                }
            },
            'body': json.dumps({
                'returnUrl': 'https://test.com/settings'
            })
        }
        
        response = subscription_handler.create_portal_session(event, {})
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'url' in body
        assert 'billing.stripe.com' in body['url']
    
    @patch('subscription_handler.table.get_item')
    def test_create_portal_session_no_customer(self, mock_get_item):
        """Test that portal session fails without Stripe customer"""
        # Mock user data without Stripe customer
        mock_get_item.return_value = {
            'Item': {
                'userId': 'test-user-123',
                'email': 'test@example.com'
            }
        }
        
        event = {
            'path': '/subscription/portal',
            'httpMethod': 'POST',
            'requestContext': {
                'authorizer': {
                    'userId': 'test-user-123'
                }
            },
            'body': json.dumps({
                'returnUrl': 'https://test.com/settings'
            })
        }
        
        response = subscription_handler.create_portal_session(event, {})
        
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'error' in body
        assert 'subscription' in body['error'].lower()


class TestHandler:
    """Test the main handler routing"""
    
    def test_handler_routes_to_prices(self):
        """Test that handler routes GET /subscription/prices correctly"""
        event = {
            'path': '/subscription/prices',
            'httpMethod': 'GET'
        }
        
        response = subscription_handler.handler(event, {})
        
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'monthly' in body
        assert 'annual' in body
    
    def test_handler_invalid_route(self):
        """Test that handler returns 404 for invalid routes"""
        event = {
            'path': '/subscription/invalid',
            'httpMethod': 'GET'
        }
        
        response = subscription_handler.handler(event, {})
        
        assert response['statusCode'] == 404
        body = json.loads(response['body'])
        assert 'error' in body


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

