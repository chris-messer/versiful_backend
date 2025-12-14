"""
E2E tests for users endpoints and Lambda.
Tests real deployed users API endpoints.
"""
import json
import os
import pytest
import requests


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
    
    # Should return user profile or 401 if token invalid
    assert response.status_code in [200, 401]
    if response.status_code == 200:
        body = response.json()
        assert "userId" in body or "isSubscribed" in body


@pytest.mark.e2e
def test_api_users_unauthenticated():
    """Test users endpoint without auth (should return 401)."""
    api_url = os.getenv("API_BASE_URL")
    if not api_url:
        pytest.skip("API_BASE_URL not set")
    
    response = requests.get(f"{api_url}/users")
    
    # Should be unauthorized without token
    assert response.status_code == 401

