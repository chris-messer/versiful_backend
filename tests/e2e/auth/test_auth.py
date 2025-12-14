"""
E2E tests for auth endpoints and Lambda.
Tests real deployed auth API endpoints.
"""
import json
import os
import pytest
import requests


@pytest.mark.e2e
def test_api_auth_callback_missing_code():
    """Test auth callback endpoint with missing code (should return 400)."""
    api_url = os.getenv("API_BASE_URL")
    if not api_url:
        pytest.skip("API_BASE_URL not set")
    
    response = requests.post(
        f"{api_url}/auth/callback",
        json={"redirectUri": "http://localhost:5173/callback"},
        headers={"Content-Type": "application/json"}
    )
    
    assert response.status_code == 400
    body = response.json()
    assert "error" in body

