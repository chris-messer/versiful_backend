"""
Unit tests for SMS handler.
Tests SMS processing logic with mocked helpers.
"""
import sys
import os
import json
import pytest
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))


@pytest.mark.unit
@pytest.fixture()
def sms_event():
    """Load real Twilio event sample."""
    event_path = os.path.join(os.path.dirname(__file__), "..", "..", "web_event.json")
    with open(event_path) as f:
        return json.load(f)


@pytest.mark.unit
def test_sms_handler_success(sms_event):
    """Test SMS handler with mocked Twilio and GPT."""
    # Mock external dependencies
    with patch("lambdas.sms.sms_handler.Client") as mock_client, \
         patch("lambdas.sms.sms_handler.MessagingResponse") as mock_resp, \
         patch("lambdas.sms.sms_handler.generate_response", return_value={"parable": "test"}), \
         patch("lambdas.sms.sms_handler.send_message") as mock_send, \
         patch("lambdas.sms.helpers.generate_response", return_value={"parable": "test"}), \
         patch("lambdas.sms.helpers.send_message"):
        
        from lambdas.sms.sms_handler import handler
        
        response = handler(sms_event, {})
        
        assert response["statusCode"] == 200
        mock_send.assert_called_once()


@pytest.mark.unit
def test_sms_handler_no_body():
    """Test SMS handler with no body (OPTIONS request)."""
    event = {
        "body": None,
        "isBase64Encoded": False
    }
    
    from lambdas.sms.sms_handler import handler
    
    response = handler(event, {})
    
    assert response["statusCode"] == 200
    assert "Access-Control-Allow-Origin" in response["headers"]


@pytest.mark.unit
def test_sms_handler_error():
    """Test SMS handler when GPT fails."""
    event = {
        "body": "Body=Test&From=%2B1234567890",
        "isBase64Encoded": False
    }
    
    # Mock GPT to raise exception
    with patch("lambdas.sms.sms_handler.generate_response", side_effect=Exception("GPT Error")):
        from lambdas.sms.sms_handler import handler
        
        response = handler(event, {})
        
        assert response["statusCode"] == 500
        assert "error" in json.loads(response["body"])


@pytest.mark.unit
def test_sms_handler_error_dict():
    """Test SMS handler when GPT returns structured error dict."""
    event = {
        "body": "Body=Test&From=%2B1234567890",
        "isBase64Encoded": False
    }

    with patch("lambdas.sms.sms_handler.generate_response", return_value={"error": "no key"}), \
         patch("lambdas.sms.sms_handler.send_message") as mock_send:
        from lambdas.sms.sms_handler import handler

        response = handler(event, {})

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "error" in body
        mock_send.assert_not_called()

