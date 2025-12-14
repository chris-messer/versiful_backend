"""
Integration tests for SMS handler - tests handler + helpers interaction with mocked external calls.
"""
import sys
import os
import json
import pytest
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


@pytest.fixture
def mock_gpt_and_twilio():
    """Mock GPT API and Twilio to prevent real API calls."""
    with patch("lambdas.sms.helpers.generate_response") as mock_gen, \
         patch("lambdas.sms.helpers.send_message") as mock_send:
        mock_gen.return_value = {"parable": "Test parable", "verse": "Test verse"}
        yield {"generate": mock_gen, "send": mock_send}


@pytest.fixture
def sms_event():
    """Load real Twilio event sample."""
    event_path = os.path.join(os.path.dirname(__file__), "..", "..", "web_event.json")
    with open(event_path) as f:
        return json.load(f)


@pytest.mark.integration
def test_sms_handler_processes_twilio_event(sms_event, mock_gpt_and_twilio):
    """Test SMS handler parses Twilio event, calls GPT, and sends message."""
    # Patch before importing to ensure mocks are active
    with patch("lambdas.sms.sms_handler.generate_response") as mock_gen, \
         patch("lambdas.sms.sms_handler.send_message") as mock_send:
        mock_gen.return_value = {"parable": "Test parable", "verse": "Test verse"}
        
        from lambdas.sms.sms_handler import handler
        
        response = handler(sms_event, {})
        
        # Verify handler parsed body and called helpers
        assert mock_gen.called
        assert mock_send.called
        assert response["statusCode"] == 200

