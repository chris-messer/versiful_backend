# CRITICAL: Production Webhook Not Working

## Root Cause
The production Stripe webhook has **never been working** because `stripe_webhook_secret` is missing from AWS Secrets Manager.

### Evidence
```bash
# Prod secrets (MISSING stripe_webhook_secret)
$ aws secretsmanager get-secret-value --secret-id prod-versiful_secrets | jq -r '.SecretString | fromjson | keys[]' | grep webhook
# (no output)

# Dev secrets (HAS stripe_webhook_secret)  
$ aws secretsmanager get-secret-value --secret-id dev-versiful_secrets | jq -r '.SecretString | fromjson | keys[]' | grep webhook
stripe_webhook_secret
```

### CloudWatch Logs Show Consistent Failures
Every webhook attempt in prod fails immediately:
```
[ERROR] Stripe webhook secret not configured in Secrets Manager
```

## How to Fix

### Step 1: Get the Webhook Secret from Stripe Dashboard
1. Go to https://dashboard.stripe.com/webhooks
2. Click on your **production** webhook endpoint (should be `https://api.versiful.io/stripe/webhook`)
3. Click "Reveal" next to "Signing secret"
4. Copy the secret (starts with `whsec_...`)

### Step 2: Add to AWS Secrets Manager

```bash
# Get current prod secrets
aws secretsmanager get-secret-value \
  --secret-id prod-versiful_secrets \
  --region us-east-1 \
  --query SecretString \
  --output text > /tmp/prod-secrets.json

# Edit the file to add stripe_webhook_secret
# Then update:
aws secretsmanager put-secret-value \
  --secret-id prod-versiful_secrets \
  --region us-east-1 \
  --secret-string file:///tmp/prod-secrets.json

# Clean up
rm /tmp/prod-secrets.json
```

### Step 3: Test
After adding the secret, test by creating a new subscription in prod and checking CloudWatch logs show:
```
[INFO] Processing webhook event: checkout.session.completed
[INFO] Updated user <userId> with subscription monthly, period_end: <timestamp>
```

## Why Dev Worked But Prod Didn't
- **Dev:** webhook secret was configured → webhooks processed successfully
- **Prod:** webhook secret missing → all webhooks failed with 500 error → database never updated → users never marked as subscribed

## Impact
Every production subscription since launch has likely failed to update the database, requiring manual fixes.

## Priority
🚨 **CRITICAL** - Must be fixed immediately before processing any more payments.

