import os
import sys

import pytest

import types
import json
import requests

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.mark.unit
def test_gpt4(monkeypatch):
    # Stub secrets and OpenAI call to avoid real AWS/OpenAI usage
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "dummy")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "dummy")

    # Fake Secrets Manager client
    class FakeSecretsClient:
        def get_secret_value(self, SecretId):
            return {"SecretString": json.dumps({"gpt": "dummy-key"})}

    monkeypatch.setattr(
        "boto3.session.Session",
        lambda: types.SimpleNamespace(client=lambda service_name, region_name=None: FakeSecretsClient()),
    )

    # Fake OpenAI response
    class FakeResp:
        def __init__(self):
            self._json = {
                "choices": [
                    {"message": {"content": "parable: Good Samaritan\nsummary: Help others"}}
                ]
            }

        def raise_for_status(self):
            return None

        def json(self):
            return self._json

    monkeypatch.setattr("requests.post", lambda *args, **kwargs: FakeResp())

    from lambdas.sms.helpers import generate_response

    r = generate_response("Give me a bible verse")
    assert "parable" in r or "summary" in r or "Good Samaritan" in r


@pytest.mark.unit
def test_gpt4_error(monkeypatch):
    """Ensure errors are returned as dict with 'error' key."""
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "dummy")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "dummy")

    class FakeSecretsClient:
        def get_secret_value(self, SecretId):
            return {"SecretString": json.dumps({"gpt": "dummy-key"})}

    monkeypatch.setattr(
        "boto3.session.Session",
        lambda: types.SimpleNamespace(client=lambda service_name, region_name=None: FakeSecretsClient()),
    )

    def raise_req(*args, **kwargs):
        raise requests.exceptions.RequestException("boom")

    monkeypatch.setattr("requests.post", raise_req)

    from lambdas.sms.helpers import generate_response

    r = generate_response("test failure")
    assert isinstance(r, dict)
    assert "error" in r