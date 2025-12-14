"""
Unit tests for users helper functions.
Tests CRUD logic with mocked DynamoDB.
"""
import sys
import os
import json
import pytest
from unittest.mock import patch
from botocore.exceptions import ClientError

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))


@pytest.mark.unit
@pytest.fixture
def mock_env_users(monkeypatch):
    """Set required env vars for users helpers."""
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("PROJECT_NAME", "versiful")


@pytest.mark.unit
@pytest.fixture
def mock_dynamodb_table(mock_env_users):
    """Mock DynamoDB table for users helpers."""
    with patch("lambdas.users.helpers.table") as mock_table:
        yield mock_table


@pytest.mark.unit
def test_create_user_new_user(mock_dynamodb_table):
    """Test creating a new user when user doesn't exist."""
    from lambdas.users.helpers import create_user
    
    mock_dynamodb_table.get_item.return_value = {}
    mock_dynamodb_table.put_item.return_value = {}
    
    event = {"requestContext": {"authorizer": {"userId": "user-123"}}}
    
    result = create_user(event, {})
    
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["isSubscribed"] is False
    assert body["isRegistered"] is False
    mock_dynamodb_table.put_item.assert_called_once()


@pytest.mark.unit
def test_create_user_existing_user(mock_dynamodb_table):
    """Test creating a user when user already exists."""
    from lambdas.users.helpers import create_user
    
    mock_dynamodb_table.get_item.return_value = {
        "Item": {
            "userId": "user-123",
            "isSubscribed": True,
            "isRegistered": True
        }
    }
    
    event = {"requestContext": {"authorizer": {"userId": "user-123"}}}
    
    result = create_user(event, {})
    
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["isSubscribed"] is True
    assert body["isRegistered"] is True
    mock_dynamodb_table.put_item.assert_not_called()


@pytest.mark.unit
def test_create_user_missing_user_id(mock_dynamodb_table):
    """Test create_user with missing userId (should raise KeyError)."""
    from lambdas.users.helpers import create_user
    
    event = {"requestContext": {"authorizer": {}}}
    
    with pytest.raises(KeyError):
        create_user(event, {})


@pytest.mark.unit
def test_get_user_profile_success(mock_dynamodb_table):
    """Test retrieving existing user profile."""
    from lambdas.users.helpers import get_user_profile
    
    mock_dynamodb_table.get_item.return_value = {
        "Item": {
            "userId": "user-123",
            "isSubscribed": True,
            "phoneNumber": "+15555555555"
        }
    }
    
    event = {"requestContext": {"authorizer": {"userId": "user-123"}}}
    
    result = get_user_profile(event, {})
    
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["userId"] == "user-123"
    assert body["isSubscribed"] is True


@pytest.mark.unit
def test_get_user_profile_not_found(mock_dynamodb_table):
    """Test retrieving non-existent user profile."""
    from lambdas.users.helpers import get_user_profile
    
    mock_dynamodb_table.get_item.return_value = {}
    
    event = {"requestContext": {"authorizer": {"userId": "user-123"}}}
    
    result = get_user_profile(event, {})
    
    assert result["statusCode"] == 404
    body = json.loads(result["body"])
    assert "error" in body


@pytest.mark.unit
def test_update_user_settings_success(mock_dynamodb_table):
    """Test updating user settings with valid fields."""
    from lambdas.users.helpers import update_user_settings
    
    mock_dynamodb_table.update_item.return_value = {}
    
    event = {
        "requestContext": {"authorizer": {"userId": "user-123"}},
        "body": json.dumps({
            "isSubscribed": True,
            "phoneNumber": "+15555555555"
        })
    }
    
    result = update_user_settings(event, {})
    
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["message"] == "Settings updated"
    mock_dynamodb_table.update_item.assert_called_once()


@pytest.mark.unit
def test_update_user_settings_no_valid_fields(mock_dynamodb_table):
    """Test update with no valid fields."""
    from lambdas.users.helpers import update_user_settings
    
    event = {
        "requestContext": {"authorizer": {"userId": "user-123"}},
        "body": json.dumps({})
    }
    
    result = update_user_settings(event, {})
    
    assert result["statusCode"] == 400
    body = json.loads(result["body"])
    assert "No valid fields" in body["message"]


@pytest.mark.unit
def test_update_user_settings_user_not_exists(mock_dynamodb_table):
    """Test update when user doesn't exist."""
    from lambdas.users.helpers import update_user_settings
    
    mock_dynamodb_table.update_item.side_effect = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException"}},
        "update_item"
    )
    
    event = {
        "requestContext": {"authorizer": {"userId": "user-123"}},
        "body": json.dumps({"isSubscribed": True})
    }
    
    result = update_user_settings(event, {})
    
    assert result["statusCode"] == 500

