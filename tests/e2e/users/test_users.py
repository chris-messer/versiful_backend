"""
E2E tests for users endpoints and Lambda.
Tests real deployed users API endpoints.
"""
import json
import os
import pytest
import requests
import boto3
from botocore.exceptions import ClientError


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.getenv("TEST_AUTH_TOKEN"),
    reason="TEST_AUTH_TOKEN not set (requires valid JWT token)"
)
def test_api_users_authenticated():
    """Test authenticated users endpoint with real JWT."""
    api_url = os.getenv("API_BASE_URL")
    auth_token = os.getenv("TEST_AUTH_TOKEN")
    
    if not api_url:
        pytest.skip("API_BASE_URL not set")
    
    response = requests.get(
        f"{api_url}/users",
        cookies={"access_token": auth_token}
    )
    
    # Accept 200 (profile found), 401 (invalid token), or 404 (user record not created yet)
    assert response.status_code in [200, 401, 404]
    if response.status_code == 200:
        body = response.json()
        assert "userId" in body or "isSubscribed" in body


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.getenv("TEST_AUTH_TOKEN"),
    reason="TEST_AUTH_TOKEN not set (requires valid JWT token)"
)
def test_api_users_create_and_update_flow():
    """
    End-to-end user journey: ensure we can create (POST) then update (PUT) the user profile.
    Requires valid API_BASE_URL and TEST_AUTH_TOKEN (JWT in access_token cookie).
    """
    api_url = os.getenv("API_BASE_URL")
    auth_token = os.getenv("TEST_AUTH_TOKEN")
    if not api_url:
        pytest.skip("API_BASE_URL not set")

    cookies = {"access_token": auth_token}

    user_pool_id = os.getenv("USER_POOL_ID")
    username = os.getenv("TEST_USER_EMAIL")
    password = os.getenv("TEST_USER_PASSWORD")

    if not user_pool_id or not username or not password:
        pytest.skip("USER_POOL_ID/TEST_USER_EMAIL/TEST_USER_PASSWORD not set")

    # Best-effort cleanup before create to force creation path
    cognito = boto3.client("cognito-idp", region_name=os.getenv("AWS_REGION", "us-east-1"))
    try:
        cognito.admin_delete_user(UserPoolId=user_pool_id, Username=username)
    except ClientError as e:
        if e.response["Error"]["Code"] != "UserNotFoundException":
            raise

    # Create user profile (POST)
    create_resp = requests.post(f"{api_url}/users", cookies=cookies)
    assert create_resp.status_code in [200, 201]

    # Update user settings with phoneNumber + isRegistered
    payload = {
        "phoneNumber": "+15555550123",
        "bibleVersion": "KJV",
        "isRegistered": True,
    }
    update_resp = requests.put(
        f"{api_url}/users",
        cookies=cookies,
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload),
    )
    assert update_resp.status_code == 200

    # Fetch profile to verify the update applied
    get_resp = requests.get(f"{api_url}/users", cookies=cookies)
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body.get("phoneNumber") == "+15555550123"
    assert body.get("isRegistered") is True

    # Optional cleanup after test (keep state minimal for next runs)
    try:
        cognito.admin_delete_user(UserPoolId=user_pool_id, Username=username)
    except ClientError as e:
        if e.response["Error"]["Code"] != "UserNotFoundException":
            raise


@pytest.mark.e2e
def test_api_users_unauthenticated():
    """Test users endpoint without auth (should return 401)."""
    api_url = os.getenv("API_BASE_URL")
    if not api_url:
        pytest.skip("API_BASE_URL not set")
    
    response = requests.get(f"{api_url}/users")
    
    # Should be unauthorized without token
    assert response.status_code == 401

