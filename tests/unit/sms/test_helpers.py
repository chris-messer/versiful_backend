"""
Unit tests for SMS helper functions.
Tests URL parsing and message formatting.
"""
import sys
import os
import pytest

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


# Note: generate_response, send_message, and generate_photo hit real APIs
# and are better tested in integration/E2E tests with mocked externals.

