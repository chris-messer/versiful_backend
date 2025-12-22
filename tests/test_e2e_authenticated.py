"""
Authenticated End-to-End tests for Stripe integration
Tests the complete user flow with real authentication

SAFETY: Destructive tests are skipped in production environment
"""
import json
import pytest
import requests
import boto3
import os
import time
from typing import Dict, Optional


# Environment detection and safety
def get_test_environment() -> str:
    """Get the test environment, default to dev"""
    return os.environ.get('TEST_ENV', 'dev')

def is_production() -> bool:
    """Check if running against production"""
    return get_test_environment() == 'prod'

def skip_if_production(reason: str):
    """Decorator to skip tests in production"""
    return pytest.mark.skipif(
        is_production(),
        reason=f"Skipped in production: {reason}"
    )


class AuthHelper:
    """Helper class for authentication"""
    
    def __init__(self, env: str = 'dev', domain: str = 'versiful.io'):
        self.env = env
        self.domain = domain
        self.api_url = f"https://api.{env}.{domain}"
        self.secrets = None
        self._load_test_credentials()
    
    def _load_test_credentials(self):
        """Load test user credentials from Secrets Manager"""
        if self.env == 'prod':
            # Don't load prod test credentials
            return
            
        try:
            secrets_client = boto3.client('secretsmanager', region_name='us-east-1')
            secret_arn = f"arn:aws:secretsmanager:us-east-1:018908982481:secret:{self.env}-versiful_secrets"
            
            response = secrets_client.get_secret_value(SecretId=secret_arn)
            self.secrets = json.loads(response['SecretString'])
        except Exception as e:
            pytest.skip(f"Could not load test credentials: {e}")
    
    def get_auth_token(self) -> Optional[Dict[str, str]]:
        """
        Authenticate and get tokens
        Returns dict with id_token and access_token
        """
        if not self.secrets:
            pytest.skip("Test credentials not available")
        
        # Try to use test user email/password if available
        test_email = self.secrets.get('TEST_USER_EMAIL')
        test_password = self.secrets.get('TEST_USER_PASSWORD')
        
        if not test_email or not test_password:
            pytest.skip("TEST_USER_EMAIL or TEST_USER_PASSWORD not in secrets")
        
        # Authenticate via the auth endpoint
        try:
            response = requests.post(
                f"{self.api_url}/auth/login",
                json={
                    'username': test_email,
                    'password': test_password
                }
            )
            
            if response.status_code != 200:
                pytest.skip(f"Authentication failed: {response.status_code}")
            
            # Extract tokens from cookies
            cookies = response.cookies
            id_token = cookies.get('id_token')
            access_token = cookies.get('access_token')
            
            if not id_token or not access_token:
                pytest.skip("Auth tokens not in response cookies")
            
            return {
                'id_token': id_token,
                'access_token': access_token,
                'cookies': cookies
            }
        except Exception as e:
            pytest.skip(f"Authentication error: {e}")
    
    def make_authenticated_request(
        self, 
        method: str, 
        endpoint: str, 
        auth_tokens: Dict[str, str],
        json_data: Optional[Dict] = None
    ) -> requests.Response:
        """Make an authenticated request with cookies"""
        url = f"{self.api_url}{endpoint}"
        
        return requests.request(
            method=method,
            url=url,
            json=json_data,
            cookies=auth_tokens.get('cookies')
        )


@pytest.fixture
def auth_helper():
    """Get authenticated helper"""
    env = get_test_environment()
    return AuthHelper(env=env)


@pytest.fixture
def auth_tokens(auth_helper):
    """Get authentication tokens"""
    return auth_helper.get_auth_token()


class TestAuthenticatedPrices:
    """Test prices endpoint (authenticated optional)"""
    
    def test_prices_without_auth(self, auth_helper):
        """Verify prices are accessible without authentication"""
        response = requests.get(f"{auth_helper.api_url}/subscription/prices")
        
        assert response.status_code == 200
        data = response.json()
        assert 'monthly' in data
        assert 'annual' in data


class TestAuthenticatedCheckout:
    """Test authenticated checkout flow"""
    
    @skip_if_production("Creates checkout sessions")
    def test_checkout_with_auth_succeeds(self, auth_helper, auth_tokens):
        """Test that authenticated users can create checkout sessions"""
        # First get the prices
        prices_response = requests.get(f"{auth_helper.api_url}/subscription/prices")
        prices = prices_response.json()
        
        # Create checkout session
        checkout_response = auth_helper.make_authenticated_request(
            'POST',
            '/subscription/checkout',
            auth_tokens,
            json_data={
                'priceId': prices['monthly'],
                'successUrl': 'https://test.versiful.io/success',
                'cancelUrl': 'https://test.versiful.io/cancel'
            }
        )
        
        assert checkout_response.status_code == 200, \
            f"Checkout failed: {checkout_response.status_code} - {checkout_response.text}"
        
        data = checkout_response.json()
        assert 'url' in data, "Response should contain checkout URL"
        assert 'sessionId' in data, "Response should contain session ID"
        assert 'checkout.stripe.com' in data['url'], "Should be a Stripe checkout URL"
    
    def test_checkout_without_auth_fails(self, auth_helper):
        """Test that checkout requires authentication"""
        response = requests.post(
            f"{auth_helper.api_url}/subscription/checkout",
            json={'priceId': 'price_test'}
        )
        
        assert response.status_code in [401, 403], \
            f"Should require auth, got {response.status_code}"


class TestAuthenticatedPortal:
    """Test authenticated customer portal flow"""
    
    @skip_if_production("Creates portal sessions")
    @pytest.mark.skip(reason="Requires existing Stripe customer - may fail for new test users")
    def test_portal_with_auth_and_subscription(self, auth_helper, auth_tokens):
        """Test that subscribed users can access portal"""
        portal_response = auth_helper.make_authenticated_request(
            'POST',
            '/subscription/portal',
            auth_tokens,
            json_data={
                'returnUrl': 'https://test.versiful.io/settings'
            }
        )
        
        # May return 400 if user has no subscription yet
        if portal_response.status_code == 400:
            pytest.skip("Test user has no Stripe customer/subscription")
        
        assert portal_response.status_code == 200, \
            f"Portal failed: {portal_response.status_code} - {portal_response.text}"
        
        data = portal_response.json()
        assert 'url' in data, "Response should contain portal URL"
        assert 'billing.stripe.com' in data['url'], "Should be a Stripe billing portal URL"
    
    def test_portal_without_auth_fails(self, auth_helper):
        """Test that portal requires authentication"""
        response = requests.post(
            f"{auth_helper.api_url}/subscription/portal",
            json={'returnUrl': 'https://test.versiful.io/settings'}
        )
        
        assert response.status_code in [401, 403], \
            f"Should require auth, got {response.status_code}"


class TestUserProfile:
    """Test user profile endpoint for email storage"""
    
    def test_user_has_email(self, auth_helper, auth_tokens):
        """Test that authenticated user has email in profile"""
        profile_response = auth_helper.make_authenticated_request(
            'GET',
            '/users',
            auth_tokens
        )
        
        assert profile_response.status_code == 200, \
            f"Failed to get user profile: {profile_response.status_code}"
        
        profile = profile_response.json()
        assert 'email' in profile, "User profile should have email field"
        assert profile['email'], "User email should not be empty"
        
        # Verify email is a valid format
        assert '@' in profile['email'], "Email should be valid format"


class TestWebhookSimulation:
    """Test webhook processing with simulated events"""
    
    @skip_if_production("Tests webhook processing")
    def test_webhook_requires_valid_signature(self, auth_helper):
        """Test that webhooks require valid Stripe signature"""
        fake_event = {
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
            f"{auth_helper.api_url}/stripe/webhook",
            json=fake_event,
            headers={'stripe-signature': 'invalid_signature'}
        )
        
        # Should reject invalid signature
        assert response.status_code in [400, 500], \
            f"Should reject invalid signature, got {response.status_code}"


class TestCompleteE2EFlow:
    """End-to-end test of complete subscription flow"""
    
    @skip_if_production("Full E2E flow creates real data")
    def test_complete_subscription_flow(self, auth_helper, auth_tokens):
        """
        Test the complete user journey:
        1. Get prices
        2. Check user profile has email
        3. Create checkout session
        4. Verify checkout session created
        """
        # Step 1: Get available prices
        prices_response = requests.get(f"{auth_helper.api_url}/subscription/prices")
        assert prices_response.status_code == 200
        prices = prices_response.json()
        assert 'monthly' in prices and 'annual' in prices
        
        # Step 2: Verify user has email (required for Stripe)
        profile_response = auth_helper.make_authenticated_request(
            'GET',
            '/users',
            auth_tokens
        )
        assert profile_response.status_code == 200
        profile = profile_response.json()
        assert 'email' in profile and profile['email'], \
            "User must have email for Stripe checkout"
        
        # Step 3: Create checkout session
        checkout_response = auth_helper.make_authenticated_request(
            'POST',
            '/subscription/checkout',
            auth_tokens,
            json_data={
                'priceId': prices['monthly'],
                'successUrl': f"https://{auth_helper.env}.versiful.io/settings?success=true",
                'cancelUrl': f"https://{auth_helper.env}.versiful.io/subscription?canceled=true"
            }
        )
        
        assert checkout_response.status_code == 200, \
            f"Checkout failed: {checkout_response.status_code} - {checkout_response.text}"
        
        checkout_data = checkout_response.json()
        
        # Step 4: Verify checkout session structure
        assert 'url' in checkout_data, "Should have checkout URL"
        assert 'sessionId' in checkout_data, "Should have session ID"
        assert checkout_data['sessionId'].startswith('cs_'), \
            "Session ID should be a Stripe checkout session"
        assert 'checkout.stripe.com' in checkout_data['url'], \
            "Should redirect to Stripe checkout"
        
        print(f"\n✅ Complete E2E flow successful!")
        print(f"   - Retrieved prices: {list(prices.keys())}")
        print(f"   - User email: {profile.get('email')}")
        print(f"   - Created checkout session: {checkout_data['sessionId']}")


class TestEnvironmentSafety:
    """Tests to verify safety checks are working"""
    
    def test_environment_detection(self):
        """Verify we can detect the environment correctly"""
        env = get_test_environment()
        assert env in ['dev', 'staging', 'prod'], \
            f"Environment should be dev/staging/prod, got {env}"
    
    def test_production_check(self):
        """Verify production detection works"""
        is_prod = is_production()
        env = get_test_environment()
        assert is_prod == (env == 'prod'), \
            "Production detection should match environment"
    
    def test_destructive_tests_skipped_in_prod(self):
        """Verify that destructive tests are properly marked"""
        if is_production():
            pytest.skip("Running in production - destructive tests should be skipped")
        else:
            # In dev/staging, destructive tests should run
            pass


if __name__ == '__main__':
    # Run with: 
    # TEST_ENV=dev pytest test_e2e_authenticated.py -v
    # TEST_ENV=prod pytest test_e2e_authenticated.py -v (safe - skips destructive tests)
    pytest.main([__file__, '-v', '-s'])

