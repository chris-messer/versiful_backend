# Stripe Keys in Secrets Manager - Quick Summary

## What You Asked For

✅ **Deploy Stripe keys to AWS Secrets Manager**  
✅ **Lambda functions reference keys from Secrets Manager at runtime**  
✅ **Keys never passed as environment variables from Terraform**

## The Solution

### Before (Less Secure) ❌
```hcl
# Terraform passes keys directly to Lambda
resource "aws_lambda_function" "subscription" {
  environment {
    variables = {
      STRIPE_SECRET_KEY = var.stripe_secret_key  # Visible in console!
    }
  }
}
```

### After (More Secure) ✅
```hcl
# Terraform only passes ARN
resource "aws_lambda_function" "subscription" {
  environment {
    variables = {
      SECRET_ARN = aws_secretsmanager_secret.secrets.arn  # Just reference
    }
  }
}
```

```python
# Lambda fetches at runtime
from secrets_helper import get_secret
stripe.api_key = get_secret('stripe_secret_key')  # Fetched from Secrets Manager
```

## What Gets Stored in Secrets Manager

Your existing secret: `{env}-versiful_secrets`

**New fields added**:
```json
{
  "twilio_sid": "SKxxx",
  "gpt": "sk-xxx",
  ...existing secrets...,
  
  "stripe_publishable_key": "pk_test_xxx",     // NEW
  "stripe_secret_key": "sk_test_xxx",          // NEW
  "stripe_webhook_secret": "whsec_xxx",        // NEW
  "stripe_monthly_price_id": "price_xxx",      // NEW (optional)
  "stripe_annual_price_id": "price_xxx"        // NEW (optional)
}
```

## Implementation Steps

### 1. Update Secrets Module

**File**: `terraform/modules/secrets/variables.tf`
```hcl
variable "stripe_publishable_key" {
  description = "Stripe publishable key"
  type        = string
  sensitive   = true
}

variable "stripe_secret_key" {
  description = "Stripe secret key"
  type        = string
  sensitive   = true
}
```

**File**: `terraform/modules/secrets/main.tf`
```hcl
secret_string = jsonencode({
  # ...existing secrets...
  "stripe_publishable_key" = var.stripe_publishable_key,
  "stripe_secret_key"      = var.stripe_secret_key
})
```

### 2. Create Secrets Helper

**File**: `lambdas/shared/secrets_helper.py`
```python
import boto3
import json
import os
from functools import lru_cache

secrets_client = boto3.client('secretsmanager')

@lru_cache(maxsize=1)  # Cache for performance
def get_secrets():
    secret_arn = os.environ['SECRET_ARN']
    response = secrets_client.get_secret_value(SecretId=secret_arn)
    return json.loads(response['SecretString'])

def get_secret(key):
    return get_secrets().get(key)
```

### 3. Update Lambda Code

**File**: `lambdas/subscription/subscription_handler.py`
```python
import sys
sys.path.append('/opt/python')  # Lambda layer
from secrets_helper import get_secret

# Fetch at runtime from Secrets Manager
stripe.api_key = get_secret('stripe_secret_key')
```

**File**: `lambdas/stripe_webhook/webhook_handler.py`
```python
from secrets_helper import get_secret, get_secrets

stripe.api_key = get_secret('stripe_secret_key')

# In handler
secrets = get_secrets()
endpoint_secret = secrets['stripe_webhook_secret']
```

### 4. Update Lambda Terraform

**Remove keys from environment variables**:
```hcl
environment {
  variables = {
    ENVIRONMENT   = var.environment
    PROJECT_NAME  = var.project_name
    SECRET_ARN    = var.secret_arn  # Only pass ARN
    # REMOVED: STRIPE_SECRET_KEY
    # REMOVED: STRIPE_PUBLISHABLE_KEY
  }
}
```

### 5. Add Helper to Lambda Layer

```bash
# Copy to layer
mkdir -p lambdas/layer/python
cp lambdas/shared/secrets_helper.py lambdas/layer/python/
```

Or Terraform will package it automatically if you update the layer source.

## Security Benefits

| Aspect | Before (Env Vars) | After (Secrets Manager) |
|--------|------------------|------------------------|
| **Visibility** | ❌ Visible in Lambda console | ✅ Hidden |
| **Terraform State** | ❌ Keys in state file | ✅ Only ARN in state |
| **Rotation** | ❌ Must redeploy Lambda | ✅ No redeployment needed |
| **Audit Trail** | ❌ None | ✅ CloudWatch logs access |
| **Accidental Logging** | ❌ Easy to log keys | ✅ Keys never in env vars |
| **IAM Control** | ⚠️ Anyone with Lambda access | ✅ Fine-grained IAM |

## Performance

**First Lambda invocation (cold start)**:
- Fetch from Secrets Manager: ~50-100ms
- Parse JSON: ~1ms
- **Total added latency**: ~100ms

**Subsequent invocations (warm)**:
- Cached in Lambda memory: <1ms
- **Total added latency**: negligible

Lambda containers are reused for ~15 minutes, so cache is effective!

## Cost

**AWS Secrets Manager**:
- $0.40 per secret per month
- $0.05 per 10,000 API calls

**Your cost**:
- 3 environments × 1 secret = $1.20/month
- API calls: ~10 per Lambda cold start
- **Total: ~$1.50/month**

Worth it for the security improvement! 💰

## Where Keys Come From

### Dev & Staging
```hcl
# dev.tfvars and staging.tfvars
stripe_publishable_key = "pk_test_..."  # From Stripe dashboard (test mode)
stripe_secret_key = "sk_test_..."       # From Stripe dashboard (test mode)
```

### Production
```hcl
# prod.tfvars
stripe_publishable_key = "pk_live_..."  # From Stripe dashboard (live mode)
stripe_secret_key = "sk_live_..."       # From Stripe dashboard (live mode)
```

**Get them from**:
1. Go to https://dashboard.stripe.com
2. Toggle test/live mode
3. Click **Developers** → **API keys**
4. Copy publishable and secret keys
5. Add to appropriate `.tfvars` file

## Deployment

```bash
# Deploy to dev (with test keys)
./scripts/tf-env.sh dev apply

# Deploy to staging (with test keys)
./scripts/tf-env.sh staging apply

# Deploy to production (with LIVE keys)
./scripts/tf-env.sh prod apply
```

Terraform will:
1. ✅ Store keys in Secrets Manager
2. ✅ Grant Lambda IAM permission to read secret
3. ✅ Pass only SECRET_ARN to Lambda (not actual keys)

## Verification

### Check secret exists
```bash
aws secretsmanager get-secret-value \
  --secret-id dev-versiful_secrets \
  --query 'SecretString' --output text | jq .stripe_secret_key
```

### Test Lambda
```bash
# Invoke subscription Lambda
aws lambda invoke \
  --function-name dev-versiful-subscription \
  --payload '{"path": "/subscription/prices", "httpMethod": "GET"}' \
  response.json

cat response.json
```

### Check CloudWatch logs
```bash
aws logs tail /aws/lambda/dev-versiful-subscription --follow
```

You should see Lambda successfully initializing Stripe without any keys in env vars!

## Files Changed

### New Files
- ✅ `lambdas/shared/secrets_helper.py` - Reusable helper
- ✅ `docs/STRIPE_SECRETS_MANAGER.md` - Full guide

### Modified Files
- ✅ `terraform/modules/secrets/main.tf` - Add Stripe keys to secret
- ✅ `terraform/modules/secrets/variables.tf` - Add Stripe key variables
- ✅ `terraform/main.tf` - Pass Stripe keys to secrets module
- ✅ `terraform/modules/lambdas/_subscription.tf` - Remove keys from env
- ✅ `terraform/modules/lambdas/_stripe_webhook.tf` - Remove keys from env
- ✅ `lambdas/subscription/subscription_handler.py` - Fetch from Secrets Manager
- ✅ `lambdas/stripe_webhook/webhook_handler.py` - Fetch from Secrets Manager
- ✅ `lambdas/layer/` - Include secrets_helper.py

## Existing Setup Already Works! ✅

Good news: Your existing Lambdas already have:
- ✅ IAM permission to read Secrets Manager (`secrets_manager_policy`)
- ✅ Access to the secret ARN via environment variable
- ✅ Lambda layer for shared code

You just need to:
1. Add Stripe keys to the secret
2. Create `secrets_helper.py`
3. Update Lambda code to use helper
4. Remove keys from Lambda environment variables

## Quick Start

**For full details**: See `docs/STRIPE_SECRETS_MANAGER.md`

**For complete implementation**: Follow `docs/STRIPE_INTEGRATION_PLAN.md` with Secrets Manager approach

**TL;DR**:
1. Stripe keys go into Secrets Manager
2. Lambda fetches at runtime (cached)
3. More secure, rotatable, auditable
4. Minimal performance impact (~100ms cold start, negligible warm)
5. Worth the $1.50/month cost

---

**Created**: December 22, 2025  
**Security Improvement**: High 🔒  
**Performance Impact**: Negligible ⚡  
**Cost**: ~$1.50/month 💰

