# Stripe Integration - Ready to Deploy!

## 🎉 Implementation Complete!

All backend code and Terraform configurations are ready. Here's what to do next.

## Phase 1-3 Complete ✅

- ✅ Terraform variables and secrets configured
- ✅ Lambda functions created (subscription + webhook)
- ✅ Secrets helper with caching
- ✅ Terraform Lambda deployment configs
- ✅ API Gateway routes configured

## Next: Deploy to Dev

### Step 1: Deploy Backend Infrastructure

```bash
cd /Users/christopher.messer/PycharmProjects/versiful-backend

# Review what will be created
./scripts/tf-env.sh dev plan

# Deploy! (this creates the Lambda functions and API routes)
./scripts/tf-env.sh dev apply
```

**What this creates**:
- `dev-versiful-subscription` Lambda function
- `dev-versiful-stripe-webhook` Lambda function
- API routes: POST /subscription/checkout, POST /subscription/portal, GET /subscription/prices, POST /stripe/webhook
- Stripe keys stored in Secrets Manager

### Step 2: Create Stripe Products (Manual)

1. Go to https://dashboard.stripe.com/test (make sure you're in TEST mode)
2. Click **Products** → **Add product**
3. Create **Monthly Premium**:
   - Name: "Versiful Monthly Premium"
   - Description: "Unlimited biblical guidance via SMS"
   - Pricing: $9.99 USD, recurring monthly
   - Click **Save product**
   - **Copy the Price ID** (starts with `price_`)

4. Create **Annual Premium**:
   - Name: "Versiful Annual Premium"
   - Description: "Unlimited biblical guidance via SMS - Annual"
   - Pricing: $99.99 USD, recurring yearly
   - Click **Save product**
   - **Copy the Price ID** (starts with `price_`)

### Step 3: Create Stripe Webhook (Manual)

1. Go to https://dashboard.stripe.com/test/webhooks
2. Click **Add endpoint**
3. Endpoint URL: `https://api.dev.versiful.io/stripe/webhook`
4. Description: "Versiful Dev Webhook"
5. Events to send - click "Select events" and choose:
   - ✅ checkout.session.completed
   - ✅ customer.subscription.created
   - ✅ customer.subscription.updated
   - ✅ customer.subscription.deleted
   - ✅ invoice.payment_succeeded
   - ✅ invoice.payment_failed
6. Click **Add endpoint**
7. **Copy the Signing secret** (starts with `whsec_`)

### Step 4: Add Webhook Secret to Secrets Manager

```bash
cd /Users/christopher.messer/PycharmProjects/versiful-backend

# Get current secret
aws secretsmanager get-secret-value \
  --secret-id dev-versiful_secrets \
  --region us-east-1 \
  --query SecretString --output text > current_secret.json

# Add webhook secret (replace YOUR_SECRET_HERE with actual secret)
jq '. + {"stripe_webhook_secret": "whsec_YOUR_SECRET_HERE"}' current_secret.json > updated_secret.json

# Update Secrets Manager
aws secretsmanager update-secret \
  --secret-id dev-versiful_secrets \
  --region us-east-1 \
  --secret-string file://updated_secret.json

# Verify it was added
aws secretsmanager get-secret-value \
  --secret-id dev-versiful_secrets \
  --region us-east-1 \
  --query SecretString --output text | jq .stripe_webhook_secret

# Clean up temp files
rm current_secret.json updated_secret.json
```

### Step 5: Test Lambda Functions

```bash
# Test subscription Lambda
aws lambda invoke \
  --function-name dev-versiful-subscription \
  --region us-east-1 \
  --payload '{"path": "/subscription/prices", "httpMethod": "GET"}' \
  response.json

cat response.json
# Should see: {"statusCode": 200, ...}

# Check logs
aws logs tail /aws/lambda/dev-versiful-subscription --follow --region us-east-1
```

### Step 6: Test Webhook with Stripe CLI

```bash
# Install Stripe CLI (if not installed)
brew install stripe/stripe-cli/stripe

# Login to Stripe
stripe login

# Forward webhooks to your dev environment
stripe listen --forward-to https://api.dev.versiful.io/stripe/webhook

# In another terminal, trigger test events
stripe trigger checkout.session.completed
stripe trigger invoice.payment_failed
stripe trigger customer.subscription.deleted

# Watch the webhook Lambda logs
aws logs tail /aws/lambda/dev-versiful-stripe-webhook --follow --region us-east-1
```

## Verification Checklist

- [ ] Terraform apply completed successfully
- [ ] Lambda functions visible in AWS console
- [ ] API Gateway routes exist (check API Gateway console)
- [ ] Stripe products created (2 products)
- [ ] Stripe webhook endpoint created
- [ ] Webhook secret added to Secrets Manager
- [ ] Subscription Lambda responds to test invocation
- [ ] Webhook Lambda processes test events
- [ ] CloudWatch logs show no errors

## Troubleshooting

### Lambda can't find secrets_helper
**Problem**: `ImportError: No module named 'secrets_helper'`
**Solution**: The helper should be in the Lambda layer. Check:
```bash
ls lambdas/layer/python/secrets_helper.py
# If missing, copy it
cp lambdas/shared/secrets_helper.py lambdas/layer/python/
# Redeploy
./scripts/tf-env.sh dev apply
```

### Webhook signature validation fails
**Problem**: Webhook returns 400 "Invalid signature"
**Solution**: 
1. Check webhook secret is in Secrets Manager
2. Verify it matches the secret from Stripe dashboard
3. Re-add if necessary

### Lambda times out
**Problem**: Lambda execution time exceeds 30 seconds
**Solution**: Check if Secrets Manager is accessible from Lambda (VPC issues)

### Can't find Stripe keys
**Problem**: `KeyError: 'stripe_secret_key'`
**Solution**: 
```bash
# Verify keys are in Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id dev-versiful_secrets \
  --region us-east-1 \
  --query SecretString --output text | jq .
# Should see stripe_publishable_key and stripe_secret_key
```

## Next Steps

Once backend is working:

1. **Frontend Integration** (1-2 hours)
   - Install @stripe/stripe-js
   - Update Subscription.jsx
   - Update Settings.jsx
   - Test complete flow

2. **Full E2E Testing** (1-2 hours)
   - Test subscription checkout
   - Test cancellation
   - Test payment failures
   - Verify DynamoDB updates

3. **Deploy to Staging** (30 minutes)
   - Same steps as dev
   - Test with QA team

4. **Deploy to Production** (when ready)
   - Update prod.tfvars with LIVE Stripe keys
   - Review plan carefully
   - Deploy during maintenance window
   - Monitor for 24 hours

## Quick Reference

### Stripe Dashboard URLs
- **Test Mode**: https://dashboard.stripe.com/test
- **Live Mode**: https://dashboard.stripe.com
- **Test Products**: https://dashboard.stripe.com/test/products
- **Test Webhooks**: https://dashboard.stripe.com/test/webhooks
- **Test API Keys**: https://dashboard.stripe.com/test/apikeys

### AWS Console URLs  
- **Lambda**: https://console.aws.amazon.com/lambda
- **API Gateway**: https://console.aws.amazon.com/apigateway
- **Secrets Manager**: https://console.aws.amazon.com/secretsmanager
- **CloudWatch Logs**: https://console.aws.amazon.com/cloudwatch

### Important Files
- Lambda code: `lambdas/subscription/`, `lambdas/stripe_webhook/`
- Terraform config: `terraform/modules/lambdas/_subscription.tf`, `_stripe_webhook.tf`
- Environment config: `terraform/dev.tfvars`

---

**Status**: Ready to deploy! 🚀  
**Estimated Time**: 30-60 minutes for deployment + testing  
**Next Action**: Run `./scripts/tf-env.sh dev apply`

