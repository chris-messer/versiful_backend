"""
Integration tests for users handler - tests handler routing + helpers with mocked AWS.
"""
import sys
import os
import json
import pytest
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


@pytest.fixture
def mock_dynamodb(monkeypatch):
    """Mock DynamoDB table operations."""
    # Set env vars before import
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("PROJECT_NAME", "versiful")
    
    with patch("lambdas.users.helpers.table") as mock_table:
        mock_table.get_item.return_value = {"Item": {"userId": "user-123", "isSubscribed": True, "isRegistered": True}}
        mock_table.put_item.return_value = {}
        mock_table.update_item.return_value = {}
        yield mock_table


@pytest.fixture
def user_event():
    """Sample user API Gateway event."""
    return {
        "path": "/users",
        "httpMethod": "GET",
        "requestContext": {
            "authorizer": {"userId": "user-123"}
        }
    }


@pytest.mark.integration
def test_users_handler_get_profile(user_event, mock_dynamodb):
    """Test GET /users retrieves user profile from DynamoDB."""
    from lambdas.users.users_handler import handler
    
    response = handler(user_event, {})
    
    assert response["statusCode"] == 200
    assert mock_dynamodb.get_item.called
    body = json.loads(response["body"])
    assert body["userId"] == "user-123"


@pytest.mark.integration
def test_users_handler_create_user(user_event, mock_dynamodb):
    """Test POST /users creates new user."""
    # Mock user doesn't exist
    mock_dynamodb.get_item.return_value = {}
    
    from lambdas.users.users_handler import handler
    
    user_event["httpMethod"] = "POST"
    response = handler(user_event, {})
    
    assert response["statusCode"] == 200
    assert mock_dynamodb.put_item.called


@pytest.mark.integration
def test_users_handler_update_settings(user_event, mock_dynamodb):
    """Test PUT /users updates user settings."""
    from lambdas.users.users_handler import handler
    
    user_event["httpMethod"] = "PUT"
    user_event["body"] = json.dumps({"isSubscribed": True, "phoneNumber": "+15555555555"})
    
    response = handler(user_event, {})
    
    assert response["statusCode"] == 200
    assert mock_dynamodb.update_item.called

