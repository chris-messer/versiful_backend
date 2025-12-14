# GitHub CI/CD Configuration - Dev Environment

## ✅ Configuration Complete!

All GitHub secrets, environment variables, and test users have been configured for the **dev** environment.

---

## 📊 Repository-Level Secrets (All Environments)

These secrets are available to all workflows:

| Secret | Value | Purpose |
|--------|-------|---------|
| `AWS_ACCESS_KEY_ID` | `AKIA************` (hidden) | AWS credentials for CI/CD |
| `AWS_SECRET_ACCESS_KEY` | `********` (hidden) | AWS credentials for CI/CD |

**Source**: Automatically retrieved from your AWS CLI configuration (`~/.aws/credentials`)

---

## 🌍 Dev Environment Configuration

### Environment Variables (Public)

| Variable | Value |
|----------|-------|
| `API_BASE_URL` | `https://api.dev.versiful.io` |
| `USER_POOL_ID` | `us-east-1_2cfzb49yx` |
| `USER_POOL_CLIENT_ID` | `4tbhttot4e3iao2oqoj2bm8qhb` |

**Source**: Extracted from Terraform state

### Environment Secrets (Hidden)

| Secret | Value |
|--------|-------|
| `TEST_USER_EMAIL` | `test@versiful.io` |
| `TEST_USER_PASSWORD` | `TestPassword123!` |

---

## 👤 Test User Created

A test user has been created in your Cognito dev user pool:

- **Email**: `test@versiful.io`
- **Password**: `TestPassword123!`
- **Email Verified**: ✅ Yes
- **Status**: Confirmed
- **User Pool**: `us-east-1_2cfzb49yx` (dev)

This user will be used by E2E tests to authenticate and test your API.

---

## 🔍 Verification

You can verify the configuration in GitHub:

```bash
# List all secrets
gh secret list
gh secret list --env dev

# List all variables
gh variable list --env dev

# View in browser
gh repo view --web
# Then go to: Settings → Secrets and variables → Actions
```

---

## 🚀 What Happens Now?

When you push code or create a PR:

1. **Pull Request** to `dev`:
   - ✅ Unit tests run (no AWS credentials needed)
   - ✅ Integration tests run (no AWS credentials needed)
   - ❌ E2E tests DON'T run (save costs, faster feedback)

2. **After Merge** to `dev`:
   - ✅ Unit tests run
   - ✅ Integration tests run
   - ✅ **E2E tests run** using:
     - AWS credentials (from repository secrets)
     - API endpoint: `https://api.dev.versiful.io`
     - Test user: `test@versiful.io` / `TestPassword123!`
     - Cognito: `us-east-1_2cfzb49yx`

---

## 📝 Next Steps

### For Staging and Prod Environments

You'll need to configure `staging` and `prod` environments similarly:

```bash
# Create staging environment
gh api --method PUT -H "Accept: application/vnd.github+json" \
  "/repos/chris-messer/versiful_backend/environments/staging"

# Set staging variables
gh variable set API_BASE_URL --env staging --body "https://api.staging.versiful.io"
# ... (get staging pool IDs from Terraform)

# Create test user in staging Cognito
# ... (same process as dev)
```

**Or wait** - You can set these up when you're ready to use staging/prod.

### Test the CI/CD Pipeline

1. Make a small change:
   ```bash
   echo "# Test CI/CD" >> README.md
   git add README.md
   git commit -m "test: Verify CI/CD pipeline"
   git push origin dev
   ```

2. Watch the workflow:
   ```bash
   gh run watch
   # Or view in browser:
   gh repo view --web
   # Go to Actions tab
   ```

---

## 🔐 Security Notes

- ✅ AWS credentials are stored as **encrypted secrets** in GitHub
- ✅ Test user password is stored as **encrypted secret**
- ✅ Secrets are never exposed in logs
- ⚠️ The test user has access to your **dev** environment only
- ⚠️ Make sure your AWS credentials have appropriate permissions (Lambda, DynamoDB, Cognito, API Gateway read access)

---

## 🛠️ Troubleshooting

### If E2E Tests Fail

```bash
# Test locally first
export ENVIRONMENT=dev
export API_BASE_URL=https://api.dev.versiful.io
export USER_POOL_ID=us-east-1_2cfzb49yx
export USER_POOL_CLIENT_ID=4tbhttot4e3iao2oqoj2bm8qhb
export TEST_USER_EMAIL=test@versiful.io
export TEST_USER_PASSWORD=TestPassword123!

pytest tests/e2e -v -m e2e
```

### If AWS Credentials Don't Work

```bash
# Verify credentials have necessary permissions
aws sts get-caller-identity

# Update if needed
gh secret set AWS_ACCESS_KEY_ID
gh secret set AWS_SECRET_ACCESS_KEY
```

### If Test User Login Fails

```bash
# Check user status
aws cognito-idp admin-get-user \
  --user-pool-id us-east-1_2cfzb49yx \
  --username test@versiful.io

# Reset password if needed
aws cognito-idp admin-set-user-password \
  --user-pool-id us-east-1_2cfzb49yx \
  --username test@versiful.io \
  --password TestPassword123! \
  --permanent
```

---

## 📚 Related Documentation

- [Development Workflow](DEVELOPMENT_WORKFLOW.md)
- [CI/CD Testing Guide](CI_CD_TESTING.md)
- [Quick Reference](QUICK_REFERENCE.md)

---

## ✅ Summary Checklist

- [x] Created `dev` environment in GitHub
- [x] Set repository-level AWS credentials
- [x] Set dev environment variables (API_BASE_URL, USER_POOL_ID, USER_POOL_CLIENT_ID)
- [x] Set dev environment secrets (TEST_USER_EMAIL, TEST_USER_PASSWORD)
- [x] Created test user in Cognito dev pool
- [x] Verified test user status
- [ ] Test CI/CD pipeline with a commit
- [ ] Set up staging environment (when ready)
- [ ] Set up prod environment (when ready)

**You're ready to go!** 🎉

The next time you push to `dev`, your CI/CD pipeline will automatically run all tests, including E2E tests against your real dev environment.

