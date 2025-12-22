"""
Secrets Manager helper for Lambda functions.
Provides caching to avoid repeated API calls within same Lambda execution.
"""
import boto3
import json
import os
from functools import lru_cache

secrets_client = boto3.client('secretsmanager')


@lru_cache(maxsize=1)
def get_secrets():
    """
    Fetch secrets from AWS Secrets Manager.
    Cached to avoid repeated API calls within same Lambda execution.
    Returns dict of all secrets.
    """
    secret_arn = os.environ.get('SECRET_ARN')
    if not secret_arn:
        raise ValueError("SECRET_ARN environment variable not set")
    
    try:
        response = secrets_client.get_secret_value(SecretId=secret_arn)
        return json.loads(response['SecretString'])
    except Exception as e:
        print(f"Error fetching secrets from Secrets Manager: {e}")
        raise


def get_secret(key):
    """
    Get a specific secret by key.
    
    Args:
        key: The secret key to retrieve
        
    Returns:
        The secret value, or None if not found
    """
    secrets = get_secrets()
    return secrets.get(key)


def get_stripe_keys():
    """
    Get Stripe API keys.
    
    Returns:
        dict with 'secret_key' and 'publishable_key'
    """
    secrets = get_secrets()
    return {
        'secret_key': secrets.get('stripe_secret_key'),
        'publishable_key': secrets.get('stripe_publishable_key')
    }

