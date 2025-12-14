"""
Unit tests for auth handler.
Tests OAuth callback flow with mocked Cognito.
"""
import sys
import os
import json
import pytest
from unittest.mock import patch
from types import SimpleNamespace

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))


@pytest.mark.unit
def test_auth_handler_callback(monkeypatch):
    """Test auth callback with valid code."""
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("PROJECT_NAME", "versiful")
    monkeypatch.setenv("DOMAIN", "versiful.io")
    monkeypatch.setenv("CLIENT_ID", "client-id")
    monkeypatch.setenv("USER_POOL_ID", "us-east-1_123")
    
    class FakeResp(SimpleNamespace):
        def json(self):
            return {"id_token": "id", "access_token": "acc", "refresh_token": "ref"}
    
    monkeypatch.setattr("requests.post", lambda url, data, headers: FakeResp(status_code=200))
    
    import lambdas.auth.auth_handler as auth_handler
    import importlib
    importlib.reload(auth_handler)
    
    event = {
        "path": "/auth/callback",
        "httpMethod": "POST",
        "body": json.dumps({"code": "auth123", "redirectUri": "http://localhost:5173/callback"})
    }
    
    resp = auth_handler.handler(event, {})
    assert resp["statusCode"] == 200
    assert "Set-Cookie" in resp["multiValueHeaders"]

