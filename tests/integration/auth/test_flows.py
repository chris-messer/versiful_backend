"""
Integration tests for auth handler - tests OAuth flow with mocked Cognito/requests.
"""
import sys
import os
import json
import pytest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


@pytest.fixture
def auth_event():
    """Sample auth callback event."""
    return {
        "path": "/auth/callback",
        "httpMethod": "POST",
        "body": json.dumps({
            "code": "auth-code-123",
            "redirectUri": "http://localhost:5173/callback"
        })
    }


@pytest.fixture
def mock_cognito_token_exchange():
    """Mock Cognito OAuth token endpoint."""
    fake_response = SimpleNamespace(
        status_code=200,
        json=lambda: {
            "id_token": "id_token_123",
            "access_token": "access_token_123",
            "refresh_token": "refresh_token_123"
        }
    )
    with patch("requests.post", return_value=fake_response):
        yield


@pytest.mark.integration
def test_auth_handler_callback_success(auth_event, mock_cognito_token_exchange, monkeypatch):
    """Test auth callback exchanges code for tokens and sets cookies."""
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("PROJECT_NAME", "versiful")
    monkeypatch.setenv("DOMAIN", "versiful.io")
    monkeypatch.setenv("CLIENT_ID", "test-client-id")
    monkeypatch.setenv("USER_POOL_ID", "us-east-1_test123")
    
    from lambdas.auth.auth_handler import handler
    
    response = handler(auth_event, {})
    
    assert response["statusCode"] == 200
    assert "multiValueHeaders" in response
    assert "Set-Cookie" in response["multiValueHeaders"]
    cookies = response["multiValueHeaders"]["Set-Cookie"]
    assert any("id_token=" in c for c in cookies)
    assert any("access_token=" in c for c in cookies)


@pytest.mark.integration
def test_auth_handler_callback_missing_code(monkeypatch):
    """Test auth callback with missing authorization code."""
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("PROJECT_NAME", "versiful")
    monkeypatch.setenv("DOMAIN", "versiful.io")
    monkeypatch.setenv("CLIENT_ID", "test-client-id")
    monkeypatch.setenv("USER_POOL_ID", "us-east-1_test123")
    
    from lambdas.auth.auth_handler import handler
    
    event = {
        "path": "/auth/callback",
        "httpMethod": "POST",
        "body": json.dumps({"redirectUri": "http://localhost:5173/callback"})
    }
    
    response = handler(event, {})
    
    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "error" in body


@pytest.mark.integration
def test_auth_handler_logout(monkeypatch):
    """Test logout clears auth cookies."""
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("PROJECT_NAME", "versiful")
    monkeypatch.setenv("DOMAIN", "versiful.io")
    monkeypatch.setenv("CLIENT_ID", "test-client-id")
    monkeypatch.setenv("USER_POOL_ID", "us-east-1_test123")
    
    from lambdas.auth.auth_handler import handler
    
    event = {
        "path": "/auth/logout",
        "httpMethod": "POST",
        "body": "{}"
    }
    
    response = handler(event, {})
    
    assert response["statusCode"] == 200
    cookies = response["multiValueHeaders"]["Set-Cookie"]
    # Verify cookies are cleared (Max-Age=0)
    assert any("Max-Age=0" in c for c in cookies)

