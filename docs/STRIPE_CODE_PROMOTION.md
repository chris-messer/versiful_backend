# Stripe Integration - Code Promotion Strategy

## Overview

Your code promotion follows a **three-tier environment strategy**:
```
Dev (test) → Staging (test) → Production (live)
```

Each environment is **completely isolated** with separate:
- AWS resources (Lambda functions, API Gateway, DynamoDB tables)
- Terraform state files
- Stripe accounts (test mode for dev/staging, live mode for prod)
- Configuration (tfvars files)

## Environment Configuration

### Current Setup

```
versiful-backend/
├── terraform/
│   ├── dev.tfvars           # Dev environment config (Stripe test keys)
│   ├── staging.tfvars       # Staging environment config (Stripe test keys)
│   ├── prod.tfvars          # Production environment config (Stripe LIVE keys)
│   ├── backend.dev.hcl      # Dev Terraform state config
│   ├── backend.staging.hcl  # Staging Terraform state config
│   ├── backend.prod.hcl     # Production Terraform state config
│   └── main.tf              # Shared infrastructure code
└── lambdas/
    ├── subscription/        # Lambda code (same across all envs)
    └── stripe_webhook/      # Lambda code (same across all envs)
```

### Key Differences Between Environments

| Aspect | Dev | Staging | Production |
|--------|-----|---------|------------|
| **Stripe Mode** | Test | Test | **Live** |
| **Stripe Keys** | `pk_test_...` / `sk_test_...` | `pk_test_...` / `sk_test_...` | `pk_live_...` / `sk_live_...` |
| **Domain** | `api.dev.versiful.io` | `api.staging.versiful.io` | `api.prod.versiful.io` |
| **DynamoDB** | `dev-versiful-users` | `staging-versiful-users` | `prod-versiful-users` |
| **Lambda Names** | `dev-versiful-subscription` | `staging-versiful-subscription` | `prod-versiful-subscription` |
| **Real Money** | ❌ No | ❌ No | ✅ **YES** |

## Code Promotion Workflow

### Phase 1: Development (Dev Environment)

**1. Make code changes**
```bash
# Edit Lambda code
vim lambdas/subscription/subscription_handler.py
vim lambdas/stripe_webhook/webhook_handler.py

# Edit Terraform
vim terraform/modules/stripe/main.tf
vim terraform/modules/lambdas/_subscription.tf
```

**2. Deploy to dev**
```bash
cd /Users/christopher.messer/PycharmProjects/versiful-backend
./scripts/tf-env.sh dev plan    # Review changes
./scripts/tf-env.sh dev apply   # Deploy
```

**3. Test in dev**
```bash
# Use Stripe CLI to test webhooks
stripe listen --forward-to https://api.dev.versiful.io/stripe/webhook

# Trigger test events
stripe trigger checkout.session.completed
stripe trigger invoice.payment_failed

# Test subscription flow through UI
# Use test card: 4242 4242 4242 4242

# Check CloudWatch logs
aws logs tail /aws/lambda/dev-versiful-subscription --follow
aws logs tail /aws/lambda/dev-versiful-stripe-webhook --follow

# Verify DynamoDB updates
aws dynamodb get-item \
  --table-name dev-versiful-users \
  --key '{"userId": {"S": "test-user-123"}}'
```

**4. Iterate until working**
- Fix bugs
- Redeploy: `./scripts/tf-env.sh dev apply`
- Re-test
- Repeat until satisfied

---

### Phase 2: Staging (Pre-Production Testing)

**1. Commit your changes**
```bash
git add .
git commit -m "feat: add Stripe subscription integration with plan caps"
git push origin feature/stripe-integration
```

**2. Deploy to staging**
```bash
# Staging uses SAME CODE as dev, but separate infrastructure
./scripts/tf-env.sh staging plan    # Review changes
./scripts/tf-env.sh staging apply   # Deploy
```

**What happens**:
- Terraform reads `staging.tfvars` (has staging Stripe test keys)
- Creates `staging-versiful-subscription` Lambda
- Creates `staging-versiful-stripe-webhook` Lambda
- Registers webhook at `https://api.staging.versiful.io/stripe/webhook`
- Uses staging DynamoDB table: `staging-versiful-users`

**3. Test in staging (production-like)**
```bash
# Test through actual UI (not CLI)
# Frontend: https://staging.versiful.io

# Full end-to-end tests:
# 1. Sign up new user
# 2. Subscribe to monthly plan
# 3. Complete checkout (test card)
# 4. Verify subscription shows in settings
# 5. Send SMS messages (should be unlimited)
# 6. Click "Manage Subscription" → portal
# 7. Cancel subscription
# 8. Verify reverts to free plan after period ends

# Check logs
aws logs tail /aws/lambda/staging-versiful-subscription --follow
aws logs tail /aws/lambda/staging-versiful-stripe-webhook --follow

# Verify Stripe dashboard (test mode)
# Check webhook delivery success in Stripe
```

**4. Run automated tests** (if you have them)
```bash
cd tests/
pytest integration/ -v --env=staging
pytest e2e/ -v --env=staging
```

**5. Get approval**
- Review with team
- QA sign-off
- Product owner approval

---

### Phase 3: Production (Live Deployment)

**⚠️ CRITICAL: Production uses REAL money and LIVE Stripe keys**

**Pre-deployment checklist**:
- [ ] All tests pass in staging
- [ ] Code reviewed and approved
- [ ] Stripe **LIVE** keys added to `prod.tfvars`
- [ ] Stripe live mode account verified and active
- [ ] Team notified of deployment
- [ ] Rollback plan ready

**1. Merge to main**
```bash
# After PR approval
git checkout main
git pull origin main
git merge feature/stripe-integration
git push origin main
```

**2. Review production plan CAREFULLY**
```bash
./scripts/tf-env.sh prod plan > prod-plan.txt
```

Review `prod-plan.txt` for:
- ✅ Correct Stripe live keys (not test keys)
- ✅ Correct domain: `api.prod.versiful.io`
- ✅ Webhook endpoint uses prod domain
- ✅ Lambda environment variables correct
- ✅ DynamoDB table is `prod-versiful-users`
- ❌ No destructive changes (destroying existing resources)

**3. Deploy to production**
```bash
# Double-check you're on main branch
git branch

# Deploy with live keys
./scripts/tf-env.sh prod apply
```

**4. Verify deployment**
```bash
# Check Lambda functions deployed
aws lambda get-function --function-name prod-versiful-subscription
aws lambda get-function --function-name prod-versiful-stripe-webhook

# Check Stripe webhook registered
stripe webhooks list --live

# Check API Gateway
curl https://api.prod.versiful.io/subscription/prices
```

**5. Smoke test (with real card, small amount)**
```bash
# Option A: Test with your own card (will charge real money)
# 1. Sign up as test user
# 2. Subscribe to monthly ($9.99)
# 3. Complete checkout with real card
# 4. Verify webhook received
# 5. Check DynamoDB: isSubscribed=true, plan_monthly_cap=null
# 6. Cancel subscription immediately (to avoid ongoing charges)

# Option B: Wait for first real customer
# Monitor closely for first 1-2 customers
```

**6. Monitor production (24-48 hours)**
```bash
# Watch logs in real-time
aws logs tail /aws/lambda/prod-versiful-subscription --follow
aws logs tail /aws/lambda/prod-versiful-stripe-webhook --follow

# Check Stripe dashboard (LIVE mode)
# - Webhook delivery success rate
# - Successful payments
# - Any errors

# Check CloudWatch metrics
# - Lambda errors
# - API Gateway 5xx errors
# - DynamoDB throttling
```

---

## What Gets Promoted vs What Stays

### ✅ Gets Promoted (Same Across All Environments)

1. **Lambda Code**
   - `lambdas/subscription/subscription_handler.py`
   - `lambdas/stripe_webhook/webhook_handler.py`
   - Business logic identical in all envs

2. **Terraform Modules**
   - `terraform/modules/stripe/main.tf`
   - `terraform/modules/lambdas/_subscription.tf`
   - `terraform/modules/lambdas/_stripe_webhook.tf`
   - Infrastructure definitions identical

3. **API Routes**
   - `/subscription/checkout`
   - `/subscription/portal`
   - `/stripe/webhook`
   - Same endpoints in all envs

4. **Frontend Code**
   - Same React components
   - Same Stripe.js integration
   - Environment determined by `VITE_DOMAIN` env var

### ❌ Stays Environment-Specific (Never Promoted)

1. **Stripe API Keys**
   - Dev/Staging: `pk_test_...`, `sk_test_...`
   - Production: `pk_live_...`, `sk_live_...`
   - Stored in respective `.tfvars` files

2. **Stripe Products & Prices**
   - Dev creates: `Versiful dev Subscription` product
   - Staging creates: `Versiful staging Subscription` product
   - Production creates: `Versiful prod Subscription` product
   - Each has different price IDs

3. **Webhook Endpoints**
   - Dev: `https://api.dev.versiful.io/stripe/webhook`
   - Staging: `https://api.staging.versiful.io/stripe/webhook`
   - Production: `https://api.prod.versiful.io/stripe/webhook`
   - Stripe registers separately for each

4. **AWS Resources**
   - DynamoDB tables: `{env}-versiful-users`
   - Lambda functions: `{env}-versiful-subscription`
   - API Gateway: `{env}-versiful-gateway`
   - Completely isolated

5. **Terraform State**
   - Dev: S3 backend at `dev` workspace
   - Staging: S3 backend at `staging` workspace
   - Production: S3 backend at `prod` workspace
   - Never shared

---

## Deployment Commands Reference

### Deploy to Specific Environment

```bash
# Dev
./scripts/tf-env.sh dev plan
./scripts/tf-env.sh dev apply

# Staging
./scripts/tf-env.sh staging plan
./scripts/tf-env.sh staging apply

# Production
./scripts/tf-env.sh prod plan
./scripts/tf-env.sh prod apply
```

### What `tf-env.sh` Does

```bash
#!/bin/bash
# Simplified version of what it does

ENV=$1      # dev, staging, or prod
COMMAND=$2  # plan, apply, destroy, etc.

# Initialize Terraform with environment-specific backend
terraform init -backend-config=backend.${ENV}.hcl

# Run command with environment-specific vars
terraform ${COMMAND} -var-file=${ENV}.tfvars
```

### Deploy Only Lambda Code (Faster)

If you only changed Lambda code (not Terraform config):

```bash
# Dev
aws lambda update-function-code \
  --function-name dev-versiful-subscription \
  --zip-file fileb://lambdas/subscription/subscription.zip

# Staging
aws lambda update-function-code \
  --function-name staging-versiful-subscription \
  --zip-file fileb://lambdas/subscription/subscription.zip

# Production
aws lambda update-function-code \
  --function-name prod-versiful-subscription \
  --zip-file fileb://lambdas/subscription/subscription.zip
```

But better to use Terraform for consistency:
```bash
# Terraform handles packaging and deployment
./scripts/tf-env.sh prod apply
```

---

## Rollback Strategy

### If Something Breaks in Production

**Option 1: Revert Lambda to Previous Version**
```bash
# List versions
aws lambda list-versions-by-function \
  --function-name prod-versiful-subscription

# Rollback to version N
aws lambda update-alias \
  --function-name prod-versiful-subscription \
  --name LIVE \
  --function-version 5  # Previous working version
```

**Option 2: Revert Git and Redeploy**
```bash
# Find last working commit
git log --oneline

# Revert to that commit
git revert <commit-hash>
git push origin main

# Redeploy
./scripts/tf-env.sh prod apply
```

**Option 3: Disable Stripe Webhook Temporarily**
```bash
# In Stripe dashboard (live mode):
# Developers → Webhooks → [Your endpoint] → Disable

# Or via CLI
stripe webhooks update <webhook-id> --disabled --live
```

---

## CI/CD Pipeline (Recommended Future Enhancement)

### GitHub Actions Workflow

```yaml
# .github/workflows/deploy.yml
name: Deploy Stripe Integration

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run tests
        run: pytest tests/ -v

  deploy-dev:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Deploy to dev
        run: ./scripts/tf-env.sh dev apply -auto-approve
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}

  deploy-staging:
    needs: deploy-dev
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Deploy to staging
        run: ./scripts/tf-env.sh staging apply -auto-approve

  deploy-prod:
    needs: deploy-staging
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: production  # Requires manual approval
    steps:
      - uses: actions/checkout@v2
      - name: Deploy to production
        run: ./scripts/tf-env.sh prod apply -auto-approve
```

**Benefits**:
- Automatic deployment to dev on every commit to main
- Automatic promotion to staging after dev succeeds
- Manual approval required for production
- Consistent deployment process

---

## Testing Strategy Per Environment

### Dev Environment Testing
```bash
# Quick iteration testing
✅ Stripe CLI for webhook testing
✅ Test cards for payments
✅ Rapid code changes
✅ Check CloudWatch logs
✅ Verify DynamoDB updates
❌ No formal test suite needed
```

### Staging Environment Testing
```bash
# Pre-production validation
✅ Full end-to-end UI testing
✅ Automated test suite (if available)
✅ QA team manual testing
✅ Performance testing
✅ Security scanning
✅ Integration with other services
✅ Load testing (if needed)
```

### Production Environment Testing
```bash
# Smoke testing only
✅ Verify deployment succeeded
✅ Check one successful subscription
✅ Monitor webhooks for first few customers
✅ Watch metrics/logs for 24-48 hours
❌ No extensive testing (already done in staging)
```

---

## Environment Promotion Checklist

### Before Promoting to Staging
- [ ] All features working in dev
- [ ] Stripe webhooks tested in dev
- [ ] Code committed to feature branch
- [ ] PR created and self-reviewed

### Before Promoting to Production
- [ ] All tests pass in staging
- [ ] QA approval
- [ ] Product owner approval
- [ ] Stripe LIVE keys in `prod.tfvars`
- [ ] Stripe live account verified
- [ ] Team notified
- [ ] Deployment window scheduled
- [ ] Rollback plan documented
- [ ] On-call engineer available

### After Production Deployment
- [ ] Smoke test completed
- [ ] Webhooks delivering successfully
- [ ] No errors in CloudWatch
- [ ] Stripe dashboard looks healthy
- [ ] First customer subscription verified
- [ ] Team notified of success
- [ ] Monitor for 24 hours

---

## Common Pitfalls

### ❌ Don't Do This
```bash
# Promoting directly from dev to prod (skipping staging)
./scripts/tf-env.sh dev apply
./scripts/tf-env.sh prod apply  # BAD! Test in staging first!
```

### ❌ Don't Do This
```bash
# Using test keys in production
# prod.tfvars should NEVER have sk_test_ keys
stripe_secret_key = "sk_test_..."  # WRONG!
```

### ❌ Don't Do This
```bash
# Deploying to prod without reviewing plan
./scripts/tf-env.sh prod apply -auto-approve  # DANGEROUS!
```

### ✅ Do This Instead
```bash
# Proper promotion path
./scripts/tf-env.sh dev apply
# Test thoroughly

./scripts/tf-env.sh staging apply
# Test thoroughly, get approval

./scripts/tf-env.sh prod plan > plan.txt
# Review plan.txt carefully

./scripts/tf-env.sh prod apply
# Monitor closely
```

---

## Summary

**Code Promotion Flow**:
1. **Dev**: Rapid iteration, Stripe CLI testing, test mode
2. **Staging**: Full E2E testing, QA approval, test mode
3. **Production**: Careful deployment, live mode, real money

**Key Points**:
- ✅ Same Lambda code across all environments
- ✅ Different Stripe keys per environment (test vs live)
- ✅ Isolated AWS resources (different table/function names)
- ✅ Separate Terraform state per environment
- ✅ Test thoroughly in staging before prod
- ✅ Always review prod plan before applying
- ✅ Monitor production closely after deployment

**Your Deployment Command**:
```bash
# This is all you need to promote through environments
./scripts/tf-env.sh dev apply      # Deploy to dev
./scripts/tf-env.sh staging apply  # Promote to staging
./scripts/tf-env.sh prod apply     # Promote to production
```

The script handles everything: state management, environment variables, and resource naming!

---

**Last Updated**: December 22, 2025  
**Your Setup**: 3 environments (dev/staging/prod) with isolated infrastructure

