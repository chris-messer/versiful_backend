"""
Unit tests for SMS helper functions.
Tests URL parsing and message formatting.
"""
import sys
import os
import pytest
from unittest.mock import patch

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))


@pytest.mark.unit
def test_parse_url_string():
    """Test URL-encoded string parsing."""
    from lambdas.sms.helpers import parse_url_string
    
    body = "Body=Hello+World&From=%2B15555555555&To=%2B18336811158"
    result = parse_url_string(body)
    
    assert result["Body"] == "Hello World"
    assert result["From"] == "+15555555555"
    assert result["To"] == "+18336811158"


@pytest.mark.unit
def test_parse_url_string_empty():
    """Test parsing empty string."""
    from lambdas.sms.helpers import parse_url_string
    
    result = parse_url_string("")
    assert result == {}


@pytest.mark.unit
@patch.dict(os.environ, {'SECRET_ARN': 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test'})
@patch('lambdas.shared.secrets_helper.get_secret', return_value='fake_stripe_key')
def test_is_toll_free_number(mock_secret):
    """Test toll-free number detection."""
    from lambdas.sms.sms_handler import _is_toll_free_number

    # Test all toll-free prefixes
    assert _is_toll_free_number("+18001234567") == True  # 800
    assert _is_toll_free_number("+18331234567") == True  # 833
    assert _is_toll_free_number("+18441234567") == True  # 844
    assert _is_toll_free_number("+18551234567") == True  # 855
    assert _is_toll_free_number("+18661234567") == True  # 866
    assert _is_toll_free_number("+18771234567") == True  # 877
    assert _is_toll_free_number("+18881234567") == True  # 888

    # Test regular numbers (should not be toll-free)
    assert _is_toll_free_number("+15551234567") == False
    assert _is_toll_free_number("+14151234567") == False
    assert _is_toll_free_number("+12125551234") == False

    # Test edge cases
    assert _is_toll_free_number("") == False
    assert _is_toll_free_number(None) == False


@pytest.mark.unit
@patch.dict(os.environ, {'SECRET_ARN': 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test'})
@patch('lambdas.shared.secrets_helper.get_secret', return_value='fake_stripe_key')
def test_is_toll_free_number_real_example(mock_secret):
    """Test with the actual Bungalow toll-free number that caused the issue."""
    from lambdas.sms.sms_handler import _is_toll_free_number

    # The actual number that created the SMS loop
    assert _is_toll_free_number("+18334543725") == True


# Note: generate_response, send_message, and generate_photo hit real APIs
# and are better tested in integration/E2E tests with mocked externals.

