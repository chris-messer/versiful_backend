"""
Integration tests for Stripe Lambdas
Tests the actual deployed Lambda functions in AWS
"""
import json
import boto3
import pytest
import requests
import os


class TestSubscriptionIntegration:
    """Integration tests for subscription Lambda"""
    
    @pytest.fixture
    def api_url(self):
        """Get the API URL from environment or use dev"""
        env = os.environ.get('TEST_ENV', 'dev')
        domain = os.environ.get('TEST_DOMAIN', 'versiful.io')
        return f"https://api.{env}.{domain}"
    
    def test_prices_endpoint_accessible(self, api_url):
        """Test that the /subscription/prices endpoint is publicly accessible"""
        response = requests.get(f"{api_url}/subscription/prices")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert 'monthly' in data, "Response should contain 'monthly' price ID"
        assert 'annual' in data, "Response should contain 'annual' price ID"
        assert data['monthly'].startswith('price_'), "Monthly should be a Stripe price ID"
        assert data['annual'].startswith('price_'), "Annual should be a Stripe price ID"
    
    def test_prices_response_structure(self, api_url):
        """Test that prices response has correct structure"""
        response = requests.get(f"{api_url}/subscription/prices")
        
        data = response.json()
        
        # Check that price IDs are valid Stripe format
        assert len(data['monthly']) > 10, "Price ID should be a valid Stripe ID"
        assert len(data['annual']) > 10, "Price ID should be a valid Stripe ID"
        
        # Monthly and annual should be different
        assert data['monthly'] != data['annual'], "Monthly and annual prices should be different"
    
    def test_checkout_requires_auth(self, api_url):
        """Test that checkout endpoint requires authentication"""
        response = requests.post(
            f"{api_url}/subscription/checkout",
            json={'priceId': 'price_test123'}
        )
        
        # Should return 401 or 403 without auth
        assert response.status_code in [401, 403], \
            f"Checkout should require auth, got {response.status_code}"
    
    def test_portal_requires_auth(self, api_url):
        """Test that portal endpoint requires authentication"""
        response = requests.post(
            f"{api_url}/subscription/portal",
            json={'returnUrl': 'https://test.com'}
        )
        
        # Should return 401 or 403 without auth
        assert response.status_code in [401, 403], \
            f"Portal should require auth, got {response.status_code}"


class TestWebhookIntegration:
    """Integration tests for webhook Lambda"""
    
    @pytest.fixture
    def api_url(self):
        """Get the API URL from environment or use dev"""
        env = os.environ.get('TEST_ENV', 'dev')
        domain = os.environ.get('TEST_DOMAIN', 'versiful.io')
        return f"https://api.{env}.{domain}"
    
    def test_webhook_endpoint_accessible(self, api_url):
        """Test that the /stripe/webhook endpoint is accessible (no auth)"""
        # Send invalid webhook to check endpoint exists
        response = requests.post(
            f"{api_url}/stripe/webhook",
            json={'test': 'data'},
            headers={'stripe-signature': 'invalid'}
        )
        
        # Should return 400 (bad signature) not 404 or 403
        assert response.status_code in [400, 500], \
            f"Webhook should be accessible but reject invalid signature, got {response.status_code}"
    
    def test_webhook_requires_signature(self, api_url):
        """Test that webhook requires Stripe signature"""
        response = requests.post(
            f"{api_url}/stripe/webhook",
            json={'test': 'data'}
        )
        
        # Should fail without signature
        assert response.status_code in [400, 500], \
            f"Webhook should require signature, got {response.status_code}"


class TestLambdaInvocation:
    """Direct Lambda invocation tests using boto3"""
    
    @pytest.fixture
    def lambda_client(self):
        """Get AWS Lambda client"""
        return boto3.client('lambda', region_name='us-east-1')
    
    @pytest.fixture
    def env(self):
        """Get environment from TEST_ENV or default to dev"""
        return os.environ.get('TEST_ENV', 'dev')
    
    def test_subscription_lambda_invocation(self, lambda_client, env):
        """Test direct invocation of subscription Lambda"""
        function_name = f"{env}-versiful-subscription"
        
        # Test get_prices
        payload = {
            'path': '/subscription/prices',
            'httpMethod': 'GET'
        }
        
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        assert response['StatusCode'] == 200, "Lambda invocation should succeed"
        
        response_payload = json.loads(response['Payload'].read())
        assert response_payload['statusCode'] == 200, \
            f"Expected 200 status, got {response_payload.get('statusCode')}: {response_payload.get('body')}"
        
        body = json.loads(response_payload['body'])
        assert 'monthly' in body
        assert 'annual' in body
    
    def test_webhook_lambda_exists(self, lambda_client, env):
        """Test that webhook Lambda exists and is configured"""
        function_name = f"{env}-versiful-stripe-webhook"
        
        try:
            response = lambda_client.get_function(FunctionName=function_name)
            assert response['Configuration']['Runtime'] == 'python3.11'
            assert response['Configuration']['Handler'] == 'webhook_handler.handler'
            
            # Check that Lambda has required environment variables
            env_vars = response['Configuration']['Environment']['Variables']
            assert 'ENVIRONMENT' in env_vars
            assert 'PROJECT_NAME' in env_vars
            assert 'SECRET_ARN' in env_vars
            
        except lambda_client.exceptions.ResourceNotFoundException:
            pytest.fail(f"Lambda function {function_name} not found")
    
    def test_lambda_has_stripe_layer(self, lambda_client, env):
        """Test that subscription Lambda has the shared dependencies layer"""
        function_name = f"{env}-versiful-subscription"
        
        response = lambda_client.get_function(FunctionName=function_name)
        layers = response['Configuration'].get('Layers', [])
        
        assert len(layers) > 0, "Lambda should have at least one layer"
        
        # Check that one layer is the shared_dependencies layer
        layer_arns = [layer['Arn'] for layer in layers]
        assert any('shared_dependencies' in arn for arn in layer_arns), \
            "Lambda should have shared_dependencies layer with Stripe"


class TestEndToEnd:
    """End-to-end test scenarios"""
    
    @pytest.fixture
    def api_url(self):
        """Get the API URL from environment or use dev"""
        env = os.environ.get('TEST_ENV', 'dev')
        domain = os.environ.get('TEST_DOMAIN', 'versiful.io')
        return f"https://api.{env}.{domain}"
    
    def test_complete_flow_simulation(self, api_url):
        """Test a complete user flow (without actual authentication)"""
        # Step 1: Get prices (public endpoint)
        prices_response = requests.get(f"{api_url}/subscription/prices")
        assert prices_response.status_code == 200
        prices = prices_response.json()
        
        # Step 2: Try to checkout (should fail without auth)
        checkout_response = requests.post(
            f"{api_url}/subscription/checkout",
            json={
                'priceId': prices['monthly'],
                'successUrl': 'https://test.com/success',
                'cancelUrl': 'https://test.com/cancel'
            }
        )
        # Should require authentication
        assert checkout_response.status_code in [401, 403]
        
        # Step 3: Try to access portal (should fail without auth)
        portal_response = requests.post(
            f"{api_url}/subscription/portal",
            json={'returnUrl': 'https://test.com/settings'}
        )
        # Should require authentication
        assert portal_response.status_code in [401, 403]
    
    def test_webhook_flow_simulation(self, api_url):
        """Test webhook flow (without valid signature)"""
        # Simulate a Stripe webhook event
        webhook_event = {
            'type': 'customer.subscription.created',
            'data': {
                'object': {
                    'id': 'sub_test',
                    'customer': 'cus_test',
                    'status': 'active',
                    'metadata': {'userId': 'test-user'}
                }
            }
        }
        
        response = requests.post(
            f"{api_url}/stripe/webhook",
            json=webhook_event,
            headers={'stripe-signature': 'test_signature'}
        )
        
        # Should reject invalid signature
        assert response.status_code in [400, 500]


if __name__ == '__main__':
    # Run with: pytest test_integration.py -v
    # Or with specific environment: TEST_ENV=dev pytest test_integration.py -v
    pytest.main([__file__, '-v', '-s'])

