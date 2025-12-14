"""
Unit tests for JWT authorizer.
Tests JWT validation with mocked JWKS.
"""
import sys
import os
import json
import pytest
import importlib
from unittest.mock import Mock
from types import SimpleNamespace

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))


def test_jwt_authorizer(monkeypatch):
    """Test JWT authorizer with valid token."""
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("DOMAIN", "versiful.io")
    monkeypatch.setenv("REGION", "us-east-1")
    monkeypatch.setenv("CLIENT_ID", "client-id")
    monkeypatch.setenv("USER_POOL_ID", "us-east-1_123")
    
    import lambdas.authorizer.jwt_authorizer as authz
    importlib.reload(authz)
    
    # Patch network and jwt decode
    monkeypatch.setattr("requests.get", lambda url: SimpleNamespace(json=lambda: {"keys": []}))
    monkeypatch.setattr("lambdas.authorizer.jwt_authorizer.get_public_key", lambda token: "pubkey")
    monkeypatch.setattr("jwt.decode", lambda token, key, algorithms: {"sub": "user-123"})
    
    event = {"headers": {"cookie": "access_token=token123"}}
    resp = authz.handler(event, {})
    
    assert resp["isAuthorized"] is True
    assert resp["context"]["userId"] == "user-123"

