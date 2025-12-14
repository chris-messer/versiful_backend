import os
import sys

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.mark.unit
def test_gpt4(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "dummy")
    from lambdas.sms.helpers import generate_response

    r = generate_response("Give me a bible verse")
    assert r is not None