"""
Unit tests for users handler.
Tests routing logic with mocked helper functions.
"""
import sys
import os
import json
import pytest
from unittest.mock import patch
from types import SimpleNamespace

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))


def test_users_handler_routes(monkeypatch):
    """Test users handler routing with mocked helpers."""
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("PROJECT_NAME", "versiful")
    monkeypatch.setattr("lambdas.users.users_handler.get_user_profile", lambda e, _: {"ok": "get"})
    monkeypatch.setattr("lambdas.users.users_handler.create_user", lambda e, _: {"ok": "post"})
    monkeypatch.setattr("lambdas.users.users_handler.update_user_settings", lambda e, _: {"ok": "put"})
    
    from lambdas.users.users_handler import handler
    
    # Test GET
    event = {"path": "/users", "httpMethod": "GET"}
    assert handler(event, {}) == {"ok": "get"}
    
    # Test POST
    event["httpMethod"] = "POST"
    assert handler(event, {}) == {"ok": "post"}
    
    # Test PUT
    event["httpMethod"] = "PUT"
    assert handler(event, {}) == {"ok": "put"}
    
    # Test 404 - handler returns error response
    event = {"path": "/invalid", "httpMethod": "GET"}
    result = handler(event, {})
    assert result["statusCode"] == 404

