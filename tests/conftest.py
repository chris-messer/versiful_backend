import sys
import os
import pytest
from dotenv import load_dotenv
from tests.scripts.load_test_secrets import fetch_secret
from tests.scripts.get_test_auth_token import get_access_token
import boto3
from botocore.exceptions import ClientError

# Add project root to sys.path for module imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load environment variables from .env file and optional generated test env
load_dotenv(dotenv_path=".env")  # explicit path to avoid find_dotenv issues
load_dotenv(dotenv_path=".env.test.generated", override=False)

# Optional: auto-fetch secrets and token for e2e tests when enabled
AUTO_FETCH = os.getenv("AUTO_FETCH_TEST_TOKEN")
if AUTO_FETCH:
    environment = os.getenv("ENVIRONMENT", "dev")
    project = os.getenv("PROJECT_NAME", "versiful")
    region = os.getenv("AWS_REGION", "us-east-1")
    secret_id = os.getenv("TEST_SECRET_ID", f"{environment}-{project}_secrets")
    try:
        secret = fetch_secret(secret_id, region)

        # Populate env vars from secret if present
        for key in [
            "TEST_USER_EMAIL",
            "TEST_USER_PASSWORD",
            "USER_POOL_CLIENT_ID",
            "USER_POOL_CLIENT_SECRET",
            "API_BASE_URL",
        ]:
            if secret.get(key):
                os.environ[key] = secret[key]

        # Fetch an access token and set TEST_AUTH_TOKEN
        try:
            tokens = get_access_token(
                username=os.environ["TEST_USER_EMAIL"],
                password=os.environ["TEST_USER_PASSWORD"],
                client_id=os.environ["USER_POOL_CLIENT_ID"],
                client_secret=os.environ.get("USER_POOL_CLIENT_SECRET"),
                region=region,
                user_pool_id=secret.get("USER_POOL_ID") or os.getenv("USER_POOL_ID"),
            )
        except Exception as _auth_exc:  # noqa: BLE001
            tokens = {}

        if tokens.get("AccessToken"):
            os.environ["TEST_AUTH_TOKEN"] = tokens["AccessToken"]
        else:
            # Attempt to create the user and retry
            pool_id = secret.get("USER_POOL_ID") or os.getenv("USER_POOL_ID")
            if pool_id:
                client = boto3.client("cognito-idp", region_name=region)
                username = os.environ["TEST_USER_EMAIL"]
                password = os.environ["TEST_USER_PASSWORD"]
                try:
                    # Check if user exists; if not, create and set password
                    try:
                        client.admin_get_user(UserPoolId=pool_id, Username=username)
                    except ClientError as e:
                        if e.response["Error"]["Code"] == "UserNotFoundException":
                            client.admin_create_user(
                                UserPoolId=pool_id,
                                Username=username,
                                MessageAction="SUPPRESS",
                                TemporaryPassword=password,
                            )
                        else:
                            raise
                    # Ensure password is set and permanent
                    client.admin_set_user_password(
                        UserPoolId=pool_id,
                        Username=username,
                        Password=password,
                        Permanent=True,
                    )
                    # Retry token fetch
                    tokens = get_access_token(
                        username=username,
                        password=password,
                        client_id=os.environ["USER_POOL_CLIENT_ID"],
                        client_secret=os.environ.get("USER_POOL_CLIENT_SECRET"),
                        region=region,
                        user_pool_id=pool_id,
                    )
                    if tokens.get("AccessToken"):
                        os.environ["TEST_AUTH_TOKEN"] = tokens["AccessToken"]
                except Exception as create_exc:  # noqa: BLE001
                    print(f"[WARN] Auto-fetch failed to create/fetch test user: {create_exc}")
    except Exception as exc:  # noqa: BLE001
        # Do not fail the test suite if optional auto-fetch fails
        print(f"[WARN] Auto-fetch test token failed: {exc}")

# Import test configuration
from tests.config import get_config, ENVIRONMENT

@pytest.fixture(scope="session")
def environment():
    """Return the current test environment (dev/staging/prod)."""
    return ENVIRONMENT

@pytest.fixture(scope="session")
def config():
    """Return environment-specific configuration."""
    return get_config()

@pytest.fixture(scope="session")
def api_base_url(config):
    """Return the API base URL for the current environment."""
    return config['api_base_url']

@pytest.fixture(scope="session")
def aws_region(config):
    """Return the AWS region for the current environment."""
    return config['region']
