"""
Helper functions for the chat / web-chat lambdas.

Secret access here mirrors the CANONICAL contract in
`lambdas/shared/secrets_helper.py` EXACTLY (same function names + resolution
behavior). The chat lambdas keep this self-contained copy for their own secret
reads (`chat_handler` imports `get_secrets` from here). As of the companion memory
promotion, the chat/web-chat lambdas ALSO mount the `shared_dependencies` layer
(ordered before the langchain layer) so they can import the shared Neon/memory
modules — `secrets_helper` therefore resolves on /opt/python too, and this mirror
remains the in-package fallback (see `neon_client.get_neon_database_url` import).

Contract (identical to shared/secrets_helper.py):
    get_secrets()            -> full secret dict (cached)
    get_secret(key)          -> single value or None
    get_neon_database_url()  -> Neon pooled connection string or None

Resolution order: SECRET_ARN env var, else `${ENVIRONMENT}-versiful_secrets`.
"""
import os
import json
import logging
from functools import lru_cache
from typing import Optional, Dict, Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()

ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
REGION_NAME = os.environ.get('AWS_REGION', 'us-east-1')

SECRET_NAME_TEMPLATE = "{env}-versiful_secrets"
NEON_DATABASE_URL_KEY = "neon_database_url"

_secrets_client = boto3.session.Session().client(
    service_name='secretsmanager', region_name=REGION_NAME
)


def _resolve_secret_id() -> str:
    """SECRET_ARN if present, otherwise the name-based per-env pattern."""
    secret_arn = os.environ.get('SECRET_ARN')
    if secret_arn:
        return secret_arn
    return SECRET_NAME_TEMPLATE.format(env=ENVIRONMENT)


@lru_cache(maxsize=1)
def get_secrets() -> Dict[str, Any]:
    """Get the combined secret dict from AWS Secrets Manager (cached per container)."""
    secret_id = _resolve_secret_id()
    try:
        response = _secrets_client.get_secret_value(SecretId=secret_id)
    except ClientError as e:
        logger.error("Error retrieving secret (SecretId=%s): %s", secret_id, str(e))
        raise e
    return json.loads(response['SecretString'])


def get_secret(key: Optional[str] = None):
    """
    Get a specific secret value by key.

    NOTE: For backward compatibility, calling with no key returns the full dict
    (the legacy chat behavior). Prefer `get_secrets()` for the dict and
    `get_secret(key)` for a single value going forward.
    """
    secrets = get_secrets()
    if key is None:
        return secrets
    return secrets.get(key)


def get_neon_database_url() -> Optional[str]:
    """
    Return the Neon pooled connection string, or None if unavailable.

    Never raises — callers degrade gracefully when Neon is not provisioned/wired.
    """
    try:
        return get_secrets().get(NEON_DATABASE_URL_KEY)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("Could not resolve %s: %s", NEON_DATABASE_URL_KEY, str(e))
        return None
