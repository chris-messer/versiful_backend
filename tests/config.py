"""
Configuration for environment-specific testing.
This allows tests to dynamically target dev/staging/prod environments.
"""
import os

# Determine environment from environment variable or default to dev
ENVIRONMENT = os.getenv('ENVIRONMENT', 'dev')

# Environment-specific configurations
ENVIRONMENTS = {
    'dev': {
        'api_base_url': os.getenv('API_BASE_URL', 'https://api.dev.versiful.io'),
        'user_pool_id': os.getenv('USER_POOL_ID'),
        'user_pool_client_id': os.getenv('USER_POOL_CLIENT_ID'),
        'region': 'us-east-1',
        'dynamodb_table': 'dev-versiful-users',
    },
    'staging': {
        'api_base_url': os.getenv('API_BASE_URL', 'https://api.staging.versiful.io'),
        'user_pool_id': os.getenv('USER_POOL_ID'),
        'user_pool_client_id': os.getenv('USER_POOL_CLIENT_ID'),
        'region': 'us-east-1',
        'dynamodb_table': 'staging-versiful-users',
    },
    'prod': {
        'api_base_url': os.getenv('API_BASE_URL', 'https://api.versiful.io'),
        'user_pool_id': os.getenv('USER_POOL_ID'),
        'user_pool_client_id': os.getenv('USER_POOL_CLIENT_ID'),
        'region': 'us-east-1',
        'dynamodb_table': 'prod-versiful-users',
    }
}

# Get config for current environment
def get_config():
    """Get configuration for the current environment."""
    return ENVIRONMENTS.get(ENVIRONMENT, ENVIRONMENTS['dev'])

# Test credentials (should come from GitHub secrets)
TEST_USER_EMAIL = os.getenv('TEST_USER_EMAIL')
TEST_USER_PASSWORD = os.getenv('TEST_USER_PASSWORD')

