# Stripe Integration - Manual Deployment Guide

## Issue: Terraform Commands Hanging

If Terraform apply keeps hanging, you can deploy the Lambda functions manually and skip Terraform for now.

## All Code Is Ready! ✅

Everything is written and ready in:
```
lambdas/subscription/subscription_handler.py
lambdas/stripe_webhook/webhook_handler.py
lambdas/shared/secrets_helper.py
terraform/modules/lambdas/_subscription.tf
terraform/modules/lambdas/_stripe_webhook.tf
```

## Option 1: Run Terraform Yourself (Recommended)

Open your terminal and run:

```bash
cd /Users/christopher.messer/PycharmProjects/versiful-backend/terraform
../scripts/tf-env.sh dev apply
```

This will:
- Show you the plan (13 to add, 3 to destroy)
- Ask for confirmation
- Deploy everything

**Why run it yourself?**
- You can see real-time progress
- Cancel if something looks wrong
- Monitor what's taking time
- Terraform often works fine when run directly

## Option 2: Manual Lambda Deployment

If Terraform is completely stuck, deploy manually:

### Step 1: Update Lambda Layer with Stripe

```bash
cd /Users/christopher.messer/PycharmProjects/versiful-backend/lambdas/layer

# Clean and rebuild
rm -rf python layer.zip
mkdir -p python

# Install dependencies including Stripe
pip install -r requirements.txt -t python/

# Copy secrets helper
cp ../shared/secrets_helper.py python/

# Package layer
zip -r layer.zip python/

# Upload to AWS
aws lambda publish-layer-version \
  --layer-name shared_dependencies \
  --description "Shared dependencies including Stripe SDK" \
  --zip-file fileb://layer.zip \
  --compatible-runtimes python3.11 python3.9 \
  --region us-east-1
```

Note the layer ARN that's returned (e.g., `arn:aws:lambda:us-east-1:xxx:layer:shared_dependencies:17`)

### Step 2: Package Lambda Functions

```bash
cd /Users/christopher.messer/PycharmProjects/versiful-backend

# Package subscription Lambda
cd lambdas/subscription
zip subscription.zip subscription_handler.py
cd ../..

# Package webhook Lambda  
cd lambdas/stripe_webhook
zip webhook.zip webhook_handler.py
cd ../..
```

### Step 3: Create Subscription Lambda (AWS Console)

1. Go to AWS Lambda Console: https://console.aws.amazon.com/lambda
2. Click "Create function"
3. Function name: `dev-versiful-subscription`
4. Runtime: Python 3.11
5. Execution role: Use existing role `dev-lambda_exec_role`
6. Click "Create function"
7. Upload `lambdas/subscription/subscription.zip`
8. Add Layer: Select `shared_dependencies` (latest version)
9. Set Handler: `subscription_handler.handler`
10. Set Timeout: 30 seconds
11. Add Environment Variables:
    - `ENVIRONMENT` = `dev`
    - `PROJECT_NAME` = `versiful`
    - `SECRET_ARN` = `arn:aws:secretsmanager:us-east-1:018908982481:secret:dev-versiful_secrets-58vKY5`
    - `FRONTEND_DOMAIN` = `dev.versiful.io`
12. Save

### Step 4: Create Webhook Lambda (AWS Console)

1. Create function: `dev-versiful-stripe-webhook`
2. Runtime: Python 3.11
3. Role: `dev-lambda_exec_role`
4. Upload `lambdas/stripe_webhook/webhook.zip`
5. Add Layer: `shared_dependencies`
6. Handler: `webhook_handler.handler`
7. Timeout: 30 seconds
8. Environment Variables:
    - `ENVIRONMENT` = `dev`
    - `PROJECT_NAME` = `versiful`
    - `SECRET_ARN` = `arn:aws:secretsmanager:us-east-1:018908982481:secret:dev-versiful_secrets-58vKY5`
9. Save

### Step 5: Add Stripe Keys to Secrets Manager

```bash
# Get current secret
aws secretsmanager get-secret-value \
  --secret-id dev-versiful_secrets \
  --region us-east-1 \
  --query SecretString --output text > current.json

# Add Stripe keys
jq '. + {
  "stripe_publishable_key": "pk_test_YOUR_PUBLISHABLE_KEY_HERE",
  "stripe_secret_key": "sk_test_YOUR_SECRET_KEY_HERE"
}' current.json > updated.json

# Update secret
aws secretsmanager update-secret \
  --secret-id dev-versiful_secrets \
  --region us-east-1 \
  --secret-string file://updated.json

# Cleanup
rm current.json updated.json

# Verify
aws secretsmanager get-secret-value \
  --secret-id dev-versiful_secrets \
  --region us-east-1 \
  --query SecretString --output text | jq '.stripe_secret_key'
```

### Step 6: Add API Gateway Routes (AWS Console)

1. Go to API Gateway Console: https://console.aws.amazon.com/apigateway
2. Find your API: `dev-versiful-gateway`
3. Click "Routes"

**Add Route 1: POST /subscription/checkout**
- Method: POST
- Path: `/subscription/checkout`
- Integration: Lambda function `dev-versiful-subscription`
- Authorization: JWT Authorizer (existing)

**Add Route 2: POST /subscription/portal**
- Method: POST
- Path: `/subscription/portal`
- Integration: Lambda function `dev-versiful-subscription`
- Authorization: JWT Authorizer (existing)

**Add Route 3: GET /subscription/prices**
- Method: GET
- Path: `/subscription/prices`
- Integration: Lambda function `dev-versiful-subscription`
- Authorization: NONE (public endpoint)

**Add Route 4: POST /stripe/webhook**
- Method: POST
- Path: `/stripe/webhook`
- Integration: Lambda function `dev-versiful-stripe-webhook`
- Authorization: NONE (signature verified in Lambda)

4. Deploy the changes

### Step 7: Test Lambda Functions

```bash
# Test subscription Lambda
aws lambda invoke \
  --function-name dev-versiful-subscription \
  --region us-east-1 \
  --payload '{"path": "/subscription/prices", "httpMethod": "GET"}' \
  response.json

cat response.json
# Should see: {"statusCode": 200, ...}

# Test webhook Lambda (basic invocation)
aws lambda invoke \
  --function-name dev-versiful-stripe-webhook \
  --region us-east-1 \
  --payload '{"body": "{}", "headers": {}}' \
  webhook-response.json

cat webhook-response.json
# Will fail signature verification (expected), but shows Lambda works
```

## After Deployment (Either Method)

### Create Stripe Products

1. Go to: https://dashboard.stripe.com/test/products
2. Create "Versiful Monthly Premium" - $9.99/month
3. Create "Versiful Annual Premium" - $99.99/year
4. Note the Price IDs

### Create Stripe Webhook

1. Go to: https://dashboard.stripe.com/test/webhooks
2. Add endpoint: `https://api.dev.versiful.io/stripe/webhook`
3. Select events: checkout.session.completed, customer.subscription.*, invoice.*
4. Copy the signing secret

### Add Webhook Secret

```bash
aws secretsmanager get-secret-value \
  --secret-id dev-versiful_secrets \
  --region us-east-1 \
  --query SecretString --output text > secret.json

jq '. + {"stripe_webhook_secret": "whsec_YOUR_SECRET_HERE"}' secret.json > updated.json

aws secretsmanager update-secret \
  --secret-id dev-versiful_secrets \
  --region us-east-1 \
  --secret-string file://updated.json

rm secret.json updated.json
```

## Summary

**Preferred:** Run Terraform yourself in your terminal
**Alternative:** Manual deployment via AWS Console (takes longer but works)

Both paths lead to the same result: Working Stripe integration! 🎉

---

**All code is ready and waiting to be deployed!**

