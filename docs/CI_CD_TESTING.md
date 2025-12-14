# CI/CD Testing Setup Guide

## Overview

This repository uses GitHub Actions to run automated tests on different environments:
- **PRs**: Unit + Integration tests (no AWS resources needed)
- **Merges to dev/staging/prod**: Unit + Integration + E2E tests against respective environments

## Test Types

1. **Unit Tests** (`tests/unit/`)
   - Fast, isolated tests
   - All external dependencies mocked
   - Run on every PR and push
   - Marker: `@pytest.mark.unit`

2. **Integration Tests** (`tests/integration/`)
   - Test multiple components together
   - External services mocked (AWS, APIs)
   - Run on every PR and push
   - Marker: `@pytest.mark.integration`

3. **E2E Tests** (`tests/e2e/`)
   - Test against real deployed AWS resources
   - Only run after merge to dev/staging/prod
   - Marker: `@pytest.mark.e2e`

## GitHub Configuration Required

### 1. Repository Secrets (Settings → Secrets → Actions)

Add these secrets that will be used across ALL environments:

```
AWS_ACCESS_KEY_ID         # AWS credentials for CI/CD
AWS_SECRET_ACCESS_KEY     # AWS credentials for CI/CD
```

### 2. Environment-Specific Secrets

Create three environments (Settings → Environments → New environment):

#### Environment: `dev`
**Variables:**
- `API_BASE_URL` = `https://api.dev.versiful.io`
- `USER_POOL_ID` = `<your-dev-user-pool-id>`
- `USER_POOL_CLIENT_ID` = `<your-dev-client-id>`

**Secrets:**
- `TEST_USER_EMAIL` = `test@example.com`
- `TEST_USER_PASSWORD` = `<test-password>`

#### Environment: `staging`
**Variables:**
- `API_BASE_URL` = `https://api.staging.versiful.io`
- `USER_POOL_ID` = `<your-staging-user-pool-id>`
- `USER_POOL_CLIENT_ID` = `<your-staging-client-id>`

**Secrets:**
- `TEST_USER_EMAIL` = `test@example.com`
- `TEST_USER_PASSWORD` = `<test-password>`

#### Environment: `prod`
**Variables:**
- `API_BASE_URL` = `https://api.versiful.io`
- `USER_POOL_ID` = `<your-prod-user-pool-id>`
- `USER_POOL_CLIENT_ID` = `<your-prod-client-id>`

**Secrets:**
- `TEST_USER_EMAIL` = `test@example.com`
- `TEST_USER_PASSWORD` = `<test-password>`

**Protection Rules (Recommended):**
- ✅ Required reviewers (1)
- ✅ Prevent administrators from bypassing required reviewers

## Workflow Triggers

### Pull Requests
```yaml
Runs: Unit + Integration tests
Target: Mocked environment (no real AWS)
Purpose: Validate code quality before merge
```

### Push to dev/staging/prod
```yaml
Runs: Unit + Integration + E2E tests
Target: Real environment resources
Purpose: Validate deployment and integration
```

### Manual Trigger
```yaml
Actions → Test Suite → Run workflow → Select environment
```

## Running Tests Locally

### Unit Tests Only
```bash
pytest tests/unit -v -m unit
```

### Integration Tests
```bash
pytest tests/integration -v -m integration
```

### E2E Tests (against dev)
```bash
export ENVIRONMENT=dev
export API_BASE_URL=https://api.dev.versiful.io
export USER_POOL_ID=<your-pool-id>
export USER_POOL_CLIENT_ID=<your-client-id>
export TEST_USER_EMAIL=<test-email>
export TEST_USER_PASSWORD=<test-password>

pytest tests/e2e -v -m e2e
```

### All Tests
```bash
pytest tests/ -v
```

## Getting Resource IDs for Configuration

### User Pool ID and Client ID
```bash
# Dev environment
cd terraform
terraform workspace select dev  # or use -var-file=dev.tfvars
terraform output user_pool_id
terraform output user_pool_client_id
```

Or from AWS Console:
1. Go to AWS Cognito
2. Select your user pool
3. Copy the Pool ID
4. Go to "App clients" tab
5. Copy the Client ID

### API Base URL
Check your API Gateway custom domain or CloudFormation outputs.

## Test User Setup

Create a test user in each Cognito user pool:
```bash
aws cognito-idp admin-create-user \
  --user-pool-id <pool-id> \
  --username test@example.com \
  --user-attributes Name=email,Value=test@example.com Name=email_verified,Value=true \
  --message-action SUPPRESS

aws cognito-idp admin-set-user-password \
  --user-pool-id <pool-id> \
  --username test@example.com \
  --password <secure-password> \
  --permanent
```

## Workflow Status Badges

Add to README.md:
```markdown
![Tests](https://github.com/<username>/versiful-backend/workflows/Test%20Suite/badge.svg?branch=dev)
```

## Troubleshooting

### Tests fail with "Unable to locate credentials"
- Check that `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are set in repository secrets

### E2E tests can't reach API
- Verify `API_BASE_URL` is correct in environment variables
- Check API Gateway is deployed and accessible
- Verify security groups/CORS settings

### Authentication errors in E2E tests
- Verify `USER_POOL_ID` and `USER_POOL_CLIENT_ID` match your environment
- Ensure test user exists in Cognito
- Check password meets Cognito policy requirements

## Best Practices

1. **Keep E2E tests focused** - Only test critical user journeys
2. **Use test data cleanup** - Clean up test data after E2E tests
3. **Isolate test users** - Use dedicated test users, not real users
4. **Monitor costs** - E2E tests use real AWS resources
5. **Run E2E tests in order** - Use `pytest-ordering` if tests have dependencies
6. **Set timeouts** - Prevent tests from hanging indefinitely

## CI/CD Pipeline Flow

```
┌─────────────────────────────────────────────────────┐
│ Developer creates PR                                │
└─────────────┬───────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────┐
│ Run: Unit + Integration Tests                       │
│ Environment: Mocked (no AWS)                        │
│ Duration: ~2-5 minutes                              │
└─────────────┬───────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────┐
│ PR Reviewed & Approved                              │
└─────────────┬───────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────┐
│ Merge to dev/staging/prod                           │
└─────────────┬───────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────┐
│ Run: Unit + Integration + E2E Tests                 │
│ Environment: Real AWS resources (dev/staging/prod)  │
│ Duration: ~5-15 minutes                             │
└─────────────┬───────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────┐
│ ✅ Tests Pass → Deployment validated                │
│ ❌ Tests Fail → Alert team, investigate            │
└─────────────────────────────────────────────────────┘
```

