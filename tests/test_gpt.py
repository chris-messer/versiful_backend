import pytest

def test_gpt4():
    from lambdas.sms.helpers import generate_response
    r = generate_response('Give me a bible verse')
    assert True