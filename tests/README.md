# Testing Strategy

## Structure

```
tests/
  unit/          # Fast, isolated tests with all external deps mocked
  integration/   # Multi-component tests (handler+helpers, mocked AWS/HTTP)
  e2e/           # Real deployed Lambda invocations (requires AWS creds)
  conftest.py    # Shared fixtures
```

## Markers

- `@pytest.mark.unit` - isolated, fast
- `@pytest.mark.integration` - multi-component, mocked external services
- `@pytest.mark.e2e` - real cloud resources

## Running Tests

### Locally / PR Checks (fast, no AWS creds)
```bash
pytest                          # runs unit + integration, skips e2e
pytest tests/unit               # unit only
pytest tests/integration        # integration only
```

### E2E (requires AWS creds + env vars)

**Lambda Invoke Tests:**
```bash
export LAMBDA_WEB_NAME=dev-versiful-web_function
export LAMBDA_SMS_NAME=dev-sms_function
export ALLOW_SMS_E2E=true  # optional, SMS test sends real message
pytest tests/e2e/test_lambdas_e2e.py
```

**API Endpoint Tests:**
```bash
export API_BASE_URL=https://api.dev.versiful.io
export TEST_AUTH_TOKEN=<valid-jwt-access-token>  # optional, for authenticated tests
pytest tests/e2e/test_api_e2e.py
```

**All E2E:**
```bash
pytest -m e2e
```

## CI Strategy

### PR Workflow
- Run `pytest` (unit + integration)
- Fast feedback, no AWS creds required

### Post-Deploy Workflow
- Run `pytest -m e2e` after Terraform apply
- Verify deployed Lambdas work
- Requires AWS creds + env vars for Lambda names

