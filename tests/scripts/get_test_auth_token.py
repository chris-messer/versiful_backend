"""
Helper to fetch a Cognito access token for E2E tests.

Reads environment variables:
  USER_POOL_CLIENT_ID      (required)
  USER_POOL_CLIENT_SECRET  (optional, only if your app client has a secret)
  TEST_USER_EMAIL          (required) - username/email of test user
  TEST_USER_PASSWORD       (required)
  AWS_REGION               (optional, defaults to us-east-1)

Outputs the access token to stdout so you can export it as TEST_AUTH_TOKEN.
"""

import base64
import hashlib
import hmac
import os
import sys

import boto3
from botocore.exceptions import ClientError


def _secret_hash(username: str, client_id: str, client_secret: str) -> str:
    message = (username + client_id).encode("utf-8")
    key = client_secret.encode("utf-8")
    digest = hmac.new(key, message, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def get_access_token(
    username: str,
    password: str,
    client_id: str,
    client_secret: str | None = None,
    region: str = "us-east-1",
    user_pool_id: str | None = None,
):
    """
    Try USER_PASSWORD_AUTH first; if that fails and we have a user_pool_id, fall back to ADMIN_USER_PASSWORD_AUTH.
    """
    client = boto3.client("cognito-idp", region_name=region)

    auth_params = {
        "USERNAME": username,
        "PASSWORD": password,
    }
    if client_secret:
        auth_params["SECRET_HASH"] = _secret_hash(username, client_id, client_secret)

    try:
        resp = client.initiate_auth(
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters=auth_params,
            ClientId=client_id,
        )
        return resp.get("AuthenticationResult", {})
    except ClientError:
        # Fall back to admin auth if pool id provided
        if not user_pool_id:
            raise
        admin_params = {
            "USERNAME": username,
            "PASSWORD": password,
        }
        if client_secret:
            admin_params["SECRET_HASH"] = _secret_hash(username, client_id, client_secret)
        resp = client.admin_initiate_auth(
            UserPoolId=user_pool_id,
            ClientId=client_id,
            AuthFlow="ADMIN_USER_PASSWORD_AUTH",
            AuthParameters=admin_params,
        )
        return resp.get("AuthenticationResult", {})


def main() -> int:
    client_id = os.getenv("USER_POOL_CLIENT_ID")
    client_secret = os.getenv("USER_POOL_CLIENT_SECRET")
    username = os.getenv("TEST_USER_EMAIL")
    password = os.getenv("TEST_USER_PASSWORD")
    region = os.getenv("AWS_REGION", "us-east-1")

    missing = [name for name, val in [
        ("USER_POOL_CLIENT_ID", client_id),
        ("TEST_USER_EMAIL", username),
        ("TEST_USER_PASSWORD", password),
    ] if not val]

    if missing:
        print(f"Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        return 1

    try:
        tokens = get_access_token(
            username=username,
            password=password,
            client_id=client_id,
            client_secret=client_secret,
            region=region,
        )
    except ClientError as e:
        print(f"Auth failed: {e}", file=sys.stderr)
        return 2

    access_token = tokens.get("AccessToken")
    id_token = tokens.get("IdToken")
    refresh_token = tokens.get("RefreshToken")

    if not access_token:
        print("No access token returned.", file=sys.stderr)
        return 3

    print("ACCESS_TOKEN=" + access_token)
    if id_token:
        print("ID_TOKEN=" + id_token)
    if refresh_token:
        print("REFRESH_TOKEN=" + refresh_token)

    return 0


if __name__ == "__main__":
    sys.exit(main())

