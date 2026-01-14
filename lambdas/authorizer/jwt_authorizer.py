import json
import logging
import sys
import jwt
import os
import requests
from jwt import PyJWKClient

logger = logging.getLogger()
logger.setLevel(logging.INFO)



if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(handler)


env = os.environ["ENVIRONMENT"]
domain = os.environ["DOMAIN"]
REGION = os.environ["REGION"]
COGNITO_CLIENT_ID = os.environ["CLIENT_ID"]
COGNITO_USER_POOL_ID = os.environ["USER_POOL_ID"]




JWKS_URL = f"https://cognito-idp.{REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}/.well-known/jwks.json"


# Retrieve and cache Cognito public keys
jwks = requests.get(JWKS_URL).json()


def get_public_key(token: str):
    """
    Retrieves the public key from Cognito JWKS to verify JWT.

    Args:
        token: JWT token to verify

    Returns:
        Public key if found, None otherwise
    """
    try:

        jwks_client = PyJWKClient(JWKS_URL)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        return signing_key.key

    except Exception as e:
        logger.error(f"Error extracting public key: {str(e)}")
        return None

def handler(event, context):
    """Lambda Authorizer to validate JWT and extract user ID."""
    logger.info('Received event: %s', event)
    headers = event.get("headers", {})
    cookies = headers.get("cookie", "")

    access_token = None

    # Extract `access_token` from Secure, HttpOnly cookies
    for cookie in cookies.split(";"):
        if "access_token=" in cookie:
            access_token = cookie.split("=")[1].strip()

    if not access_token:
        logger.error("Unauthorized - No access token")
        return {"isAuthorized": False}

    try:
        public_key = get_public_key(access_token)
        if not public_key:
            logger.error("Invalid token - No matching public key")
            return {"isAuthorized": False}

        decoded_token = jwt.decode(access_token, public_key, algorithms=["RS256"])

        return {
            "isAuthorized": True,
            "context": {
                "userId": decoded_token["sub"]
            }
        }

    except jwt.ExpiredSignatureError:
        logger.error('Received ExpiredSignatureError: Token expired')
        return {"isAuthorized": False}
    except jwt.InvalidTokenError:
        logger.error('Received ExpiredSignatureError: Invalid token')
        return {"isAuthorized": False}
    except Exception as e:
        logger.error(f'Unexpected error in authorizer: {str(e)}')
        return {"isAuthorized": False}