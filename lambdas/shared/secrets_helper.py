"""
Secrets Manager helper for Lambda functions.

This is the CANONICAL secret-access contract for the backend. It is shipped in the
`shared_dependencies` layer (copied to /opt/python) and used by every lambda that
mounts that layer (users, sms, subscription, stripe_webhook, the companion REST
lambdas, and the companion workers). The companion Neon/memory modules shipped in
this same layer (`neon_client`, `memory_store`, ...) resolve the Neon URL via
`get_neon_database_url` here.

The chat / web-chat lambdas mount this layer too (ordered before the langchain
layer) to pick up those shared memory modules, but they also carry a self-contained
mirror of this exact contract in `lambdas/chat/helpers.py` for their own secret
reads. Both files expose the SAME functions with the SAME resolution behavior:

    get_secrets()             -> full secret dict (cached)
    get_secret(key)           -> single value or None
    get_neon_database_url()   -> the Neon pooled connection string (or None)

Secret resolution order (handles both wiring styles in the codebase):
    1. SECRET_ARN env var  (workers / shared-layer lambdas)
    2. ${ENVIRONMENT}-versiful_secrets  (chat-style name-based lookup fallback)

Caching avoids repeated Secrets Manager calls within a warm Lambda container.
"""
import boto3
import json
import os
from functools import lru_cache

secrets_client = boto3.client('secretsmanager')

# Combined per-env secret name pattern (see COMPANION_SPEC / build plan).
SECRET_NAME_TEMPLATE = "{env}-versiful_secrets"

# Key inside the combined secret that holds the Neon pooled connection string.
NEON_DATABASE_URL_KEY = "neon_database_url"


def _resolve_secret_id() -> str:
    """
    Resolve the SecretId to read.

    Prefers SECRET_ARN (set on shared-layer lambdas); otherwise falls back to the
    name-based pattern `${ENVIRONMENT}-versiful_secrets` so the same helper works on
    lambdas that only receive ENVIRONMENT (parity with chat/helpers.py).
    """
    secret_arn = os.environ.get('SECRET_ARN')
    if secret_arn:
        return secret_arn
    env = os.environ.get('ENVIRONMENT', 'dev')
    return SECRET_NAME_TEMPLATE.format(env=env)


@lru_cache(maxsize=1)
def get_secrets():
    """
    Fetch the combined secret from AWS Secrets Manager.
    Cached to avoid repeated API calls within the same Lambda execution container.
    Returns dict of all secrets.
    """
    secret_id = _resolve_secret_id()
    try:
        response = secrets_client.get_secret_value(SecretId=secret_id)
        return json.loads(response['SecretString'])
    except Exception as e:
        print(f"Error fetching secrets from Secrets Manager (SecretId={secret_id}): {e}")
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


def get_neon_database_url():
    """
    Return the Neon pooled connection string from the combined secret.

    Returns None (never raises) if the secret cannot be read or the key is absent,
    so callers can degrade gracefully when Neon is not yet provisioned/wired.
    """
    try:
        return get_secrets().get(NEON_DATABASE_URL_KEY)
    except Exception as e:
        print(f"Could not resolve {NEON_DATABASE_URL_KEY}: {e}")
        return None


def get_openai_api_key():
    """OpenAI key. Stored under `gpt`, with `openai_api_key` as a legacy fallback."""
    secrets = get_secrets()
    return secrets.get('gpt') or secrets.get('openai_api_key')


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
