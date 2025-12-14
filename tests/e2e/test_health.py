"""
E2E cross-cutting tests.
Tests CORS and health check endpoints that span multiple lambdas.
"""
import os
import pytest
import requests


@pytest.mark.e2e
def test_api_cors_options():
    """Test CORS preflight request."""
    api_url = os.getenv("API_BASE_URL")
    if not api_url:
        pytest.skip("API_BASE_URL not set")
    
    response = requests.options(
        f"{api_url}/sms",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST"
        }
    )
    
    assert response.status_code in [200, 204]
    assert "Access-Control-Allow-Origin" in response.headers


@pytest.mark.e2e
def test_api_health_check():
    """Verify API is reachable and returns valid response."""
    api_url = os.getenv("API_BASE_URL")
    if not api_url:
        pytest.skip("API_BASE_URL not set")
    
    # Try a simple endpoint to verify API Gateway is up
    response = requests.options(f"{api_url}/sms")
    
    # Any valid HTTP response means API Gateway is working
    assert response.status_code < 500
