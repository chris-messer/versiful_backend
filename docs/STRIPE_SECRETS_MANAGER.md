# Stripe Integration - Secrets Manager Configuration

## Overview

This guide shows how to properly store Stripe keys in AWS Secrets Manager and reference them from Lambda functions at runtime, rather than passing them as environment variables from Terraform.

## Security Benefits

### ❌ Less Secure (Passing as Environment Variables)
```hcl
resource "aws_lambda_function" "subscription" {
  # ...
  environment {
    variables = {
      STRIPE_SECRET_KEY = var.stripe_secret_key  # Visible in Lambda console
    }
  }
}
```

**Problems**:
- Keys visible in Lambda console (anyone with AWS access can see)
- Keys visible in Terraform state
- Must redeploy Lambda to rotate keys
- Keys logged in CloudWatch if Lambda prints env vars

### ✅ More Secure (Secrets Manager at Runtime)
```hcl
resource "aws_lambda_function" "subscription" {
  # ...
  environment {
    variables = {
      SECRET_ARN = aws_secretsmanager_secret.secrets.arn  # Just ARN, not keys
    }
  }
}
```

```python
# Lambda reads from Secrets Manager at runtime
import boto3
import json

secrets_client = boto3.client('secretsmanager')
secret_arn = os.environ['SECRET_ARN']
secret_value = secrets_client.get_secret_value(SecretId=secret_arn)
secrets = json.loads(secret_value['SecretString'])
stripe.api_key = secrets['stripe_secret_key']
```

**Benefits**:
- ✅ Keys never visible in Lambda console
- ✅ Keys can be rotated without redeploying Lambda
- ✅ Centralized secret management
- ✅ Audit trail of secret access via CloudWatch
- ✅ Fine-grained IAM permissions

## Implementation

### Step 1: Update Secrets Manager Module

**File**: `terraform/modules/secrets/variables.tf`

Add Stripe key variables:

```hcl
variable "stripe_publishable_key" {
  description = "Stripe publishable key (safe to expose)"
  type        = string
  sensitive   = true
}

variable "stripe_secret_key" {
  description = "Stripe secret key (never expose)"
  type        = string
  sensitive   = true
}
```

**File**: `terraform/modules/secrets/main.tf`

Add Stripe keys to the secret:

```hcl
resource "aws_secretsmanager_secret" "secrets" {
  name = "${var.environment}-${var.project_name}_secrets"
}

resource "aws_secretsmanager_secret_version" "secret_version" {
  secret_id     = aws_secretsmanager_secret.secrets.id

  secret_string = jsonencode({
    # Existing secrets
    "twilio_sid"          = var.twilio_sid,
    "twilio_secret"       = var.twilio_secret,
    "twilio_auth"         = var.twilio_auth,
    "twilio_account_sid"  = var.twilio_account_sid,
    "gpt"                 = var.gpt_api_key,
    "AWS_S3_IAM_SECRET"   = var.AWS_S3_IAM_SECRET,
    "TEST_USER_EMAIL"         = var.test_user_email,
    "TEST_USER_PASSWORD"      = var.test_user_password,
    "USER_POOL_CLIENT_ID"     = var.test_user_pool_client_id,
    "USER_POOL_CLIENT_SECRET" = var.test_user_pool_client_secret,
    "API_BASE_URL"            = var.test_api_base_url,
    "USER_POOL_ID"            = var.test_user_pool_id,
    
    # NEW: Stripe keys
    "stripe_publishable_key" = var.stripe_publishable_key,
    "stripe_secret_key"      = var.stripe_secret_key
  })
}
```

### Step 2: Update Root Terraform

**File**: `terraform/main.tf`

Pass Stripe keys to secrets module:

```hcl
module "secrets" {
  source = "./modules/secrets"

  environment  = local.environment
  project_name = local.project_name
  domain_name  = local.domain

  twilio_sid         = var.twilio_sid
  twilio_secret      = var.twilio_secret
  twilio_auth        = var.twilio_auth
  twilio_account_sid = var.twilio_account_sid
  gpt_api_key        = var.gpt_api_key
  AWS_S3_IAM_SECRET  = module.s3.AWS_S3_IAM_SECRET

  # Test/e2e credentials
  test_user_email             = var.test_user_email
  test_user_password          = var.test_user_password
  test_user_pool_client_id    = var.test_user_pool_client_id
  test_user_pool_client_secret= var.test_user_pool_client_secret
  test_api_base_url           = var.test_api_base_url
  test_user_pool_id           = var.test_user_pool_id
  
  # NEW: Stripe keys
  stripe_publishable_key = var.stripe_publishable_key
  stripe_secret_key      = var.stripe_secret_key
}
```

### Step 3: Update Lambda Configuration

**File**: `terraform/modules/lambdas/_subscription.tf`

Remove Stripe keys from environment variables, only pass Secret ARN:

```hcl
resource "aws_lambda_function" "subscription" {
  filename         = data.archive_file.subscription_lambda_package.output_path
  function_name    = "${var.environment}-${var.project_name}-subscription"
  role            = aws_iam_role.lambda_exec_role.arn
  handler         = "subscription_handler.handler"
  runtime         = "python3.9"
  timeout         = 30
  source_code_hash = data.archive_file.subscription_lambda_package.output_base64sha256

  environment {
    variables = {
      ENVIRONMENT   = var.environment
      PROJECT_NAME  = var.project_name
      SECRET_ARN    = var.secret_arn  # Only pass ARN, not actual keys
      FRONTEND_DOMAIN = var.frontend_domain
    }
  }

  layers = [aws_lambda_layer_version.shared_dependencies.arn]
}
```

**File**: `terraform/modules/lambdas/_stripe_webhook.tf`

Same pattern:

```hcl
resource "aws_lambda_function" "stripe_webhook" {
  filename         = data.archive_file.stripe_webhook_package.output_path
  function_name    = "${var.environment}-${var.project_name}-stripe-webhook"
  role            = aws_iam_role.lambda_exec_role.arn
  handler         = "webhook_handler.handler"
  runtime         = "python3.9"
  timeout         = 30
  source_code_hash = data.archive_file.stripe_webhook_package.output_base64sha256

  environment {
    variables = {
      ENVIRONMENT   = var.environment
      PROJECT_NAME  = var.project_name
      SECRET_ARN    = var.secret_arn  # Only pass ARN, not actual keys
    }
  }

  layers = [aws_lambda_layer_version.shared_dependencies.arn]
}
```

### Step 4: Create Secrets Helper Module

**File**: `lambdas/shared/secrets_helper.py`

Create a reusable helper for accessing secrets:

```python
"""
Secrets Manager helper for Lambda functions.
Provides caching to avoid repeated API calls.
"""
import boto3
import json
import os
from functools import lru_cache

secrets_client = boto3.client('secretsmanager')

@lru_cache(maxsize=1)
def get_secrets():
    """
    Fetch secrets from AWS Secrets Manager.
    Cached to avoid repeated API calls within same Lambda execution.
    """
    secret_arn = os.environ.get('SECRET_ARN')
    if not secret_arn:
        raise ValueError("SECRET_ARN environment variable not set")
    
    try:
        response = secrets_client.get_secret_value(SecretId=secret_arn)
        return json.loads(response['SecretString'])
    except Exception as e:
        print(f"Error fetching secrets: {e}")
        raise

def get_secret(key):
    """Get a specific secret by key."""
    secrets = get_secrets()
    return secrets.get(key)

def get_stripe_keys():
    """Get Stripe API keys."""
    secrets = get_secrets()
    return {
        'secret_key': secrets.get('stripe_secret_key'),
        'publishable_key': secrets.get('stripe_publishable_key')
    }
```

### Step 5: Update Lambda Functions to Use Secrets Manager

**File**: `lambdas/subscription/subscription_handler.py`

```python
import json
import os
import boto3
import stripe
from datetime import datetime, timezone

# Import secrets helper
import sys
sys.path.append('/opt/python')  # Lambda layer path
from secrets_helper import get_secret

# Initialize Stripe with key from Secrets Manager
stripe.api_key = get_secret('stripe_secret_key')

# DynamoDB setup
dynamodb = boto3.resource("dynamodb")
env = os.environ["ENVIRONMENT"]
project_name = os.environ["PROJECT_NAME"]
table_name = f"{env}-{project_name}-users"
table = dynamodb.Table(table_name)

def handler(event, context):
    """Main handler routes to sub-handlers."""
    path = event.get("path", "")
    method = event.get("httpMethod", "")
    
    if method == "POST" and path.endswith("/subscription/checkout"):
        return create_checkout_session(event, context)
    elif method == "POST" and path.endswith("/subscription/portal"):
        return create_portal_session(event, context)
    elif method == "GET" and path.endswith("/subscription/prices"):
        return get_prices(event, context)
    else:
        return {
            "statusCode": 404,
            "body": json.dumps({"error": "Not found"})
        }

def create_checkout_session(event, context):
    """Create a Stripe checkout session for monthly or annual plan"""
    user_id = event["requestContext"]["authorizer"]["userId"]
    body = json.loads(event["body"])
    price_id = body.get("priceId")
    
    # Get secrets for additional info if needed
    frontend_domain = os.environ.get("FRONTEND_DOMAIN")
    
    # Get or create Stripe customer
    user = table.get_item(Key={"userId": user_id}).get("Item", {})
    email = user.get("email")
    
    if user.get("stripeCustomerId"):
        customer_id = user["stripeCustomerId"]
    else:
        customer = stripe.Customer.create(
            email=email,
            metadata={"userId": user_id}
        )
        customer_id = customer.id
        table.update_item(
            Key={"userId": user_id},
            UpdateExpression="SET stripeCustomerId = :cid",
            ExpressionAttributeValues={":cid": customer_id}
        )
    
    # Create checkout session
    checkout_session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=f"https://{frontend_domain}/settings?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"https://{frontend_domain}/subscription",
        metadata={"userId": user_id}
    )
    
    return {
        "statusCode": 200,
        "body": json.dumps({"sessionId": checkout_session.id})
    }

def create_portal_session(event, context):
    """Create customer portal session for managing subscription"""
    user_id = event["requestContext"]["authorizer"]["userId"]
    user = table.get_item(Key={"userId": user_id}).get("Item", {})
    
    if not user.get("stripeCustomerId"):
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "No subscription found"})
        }
    
    frontend_domain = os.environ.get("FRONTEND_DOMAIN")
    portal_session = stripe.billing_portal.Session.create(
        customer=user["stripeCustomerId"],
        return_url=f"https://{frontend_domain}/settings"
    )
    
    return {
        "statusCode": 200,
        "body": json.dumps({"url": portal_session.url})
    }

def get_prices(event, context):
    """Return Stripe price IDs - read from Secrets Manager"""
    secrets = get_secrets()
    
    # Price IDs should also be in Secrets Manager or fetched from Stripe
    # For now, we can list products and find our prices
    products = stripe.Product.list(limit=10)
    
    # Or store price IDs in secrets too
    return {
        "statusCode": 200,
        "body": json.dumps({
            "monthly": secrets.get("stripe_monthly_price_id"),
            "annual": secrets.get("stripe_annual_price_id")
        })
    }
```

**File**: `lambdas/stripe_webhook/webhook_handler.py`

```python
import json
import os
import boto3
import stripe
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Attr

# Import secrets helper
import sys
sys.path.append('/opt/python')  # Lambda layer path
from secrets_helper import get_secret, get_secrets

# Initialize Stripe with key from Secrets Manager
stripe.api_key = get_secret('stripe_secret_key')

# DynamoDB setup
dynamodb = boto3.resource("dynamodb")
env = os.environ["ENVIRONMENT"]
project_name = os.environ["PROJECT_NAME"]
table_name = f"{env}-{project_name}-users"
table = dynamodb.Table(table_name)

def handler(event, context):
    """Handle Stripe webhook events."""
    payload = event["body"]
    sig_header = event["headers"].get("stripe-signature") or event["headers"].get("Stripe-Signature")
    
    # Get webhook secret from Secrets Manager
    secrets = get_secrets()
    endpoint_secret = secrets.get("stripe_webhook_secret")
    
    try:
        # Verify webhook signature
        webhook_event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        print(f"Invalid payload: {e}")
        return {"statusCode": 400, "body": "Invalid payload"}
    except stripe.error.SignatureVerificationError as e:
        print(f"Invalid signature: {e}")
        return {"statusCode": 400, "body": "Invalid signature"}
    
    event_type = webhook_event["type"]
    data = webhook_event["data"]["object"]
    
    print(f"Processing webhook event: {event_type}")
    
    # Route to appropriate handler
    try:
        if event_type == "checkout.session.completed":
            handle_checkout_completed(data)
        elif event_type == "customer.subscription.created":
            handle_subscription_created(data)
        elif event_type == "customer.subscription.updated":
            handle_subscription_updated(data)
        elif event_type == "customer.subscription.deleted":
            handle_subscription_deleted(data)
        elif event_type == "invoice.payment_succeeded":
            handle_payment_succeeded(data)
        elif event_type == "invoice.payment_failed":
            handle_payment_failed(data)
        else:
            print(f"Unhandled event type: {event_type}")
        
        return {"statusCode": 200, "body": "Success"}
    except Exception as e:
        print(f"Error processing webhook: {e}")
        # Return 500 so Stripe retries
        return {"statusCode": 500, "body": f"Processing failed: {str(e)}"}

def handle_checkout_completed(session):
    """User completed checkout - subscription is being set up"""
    customer_id = session["customer"]
    subscription_id = session["subscription"]
    user_id = session["metadata"]["userId"]
    
    # Get subscription details
    subscription = stripe.Subscription.retrieve(subscription_id)
    plan_interval = subscription["items"]["data"][0]["price"]["recurring"]["interval"]
    plan = "monthly" if plan_interval == "month" else "annual"
    
    table.update_item(
        Key={"userId": user_id},
        UpdateExpression="""
            SET stripeCustomerId = :cid,
                stripeSubscriptionId = :sid,
                isSubscribed = :sub,
                plan = :plan,
                plan_monthly_cap = :cap,
                subscriptionStatus = :status,
                currentPeriodEnd = :period_end,
                cancelAtPeriodEnd = :cancel,
                updatedAt = :now
        """,
        ExpressionAttributeValues={
            ":cid": customer_id,
            ":sid": subscription_id,
            ":sub": True,
            ":plan": plan,
            ":cap": None,  # Unlimited for paid plans
            ":status": subscription["status"],
            ":period_end": subscription["current_period_end"],
            ":cancel": subscription["cancel_at_period_end"],
            ":now": datetime.now(timezone.utc).isoformat()
        }
    )
    print(f"Subscription created for user {user_id}: {plan}")

# ... other webhook handlers (same as in main integration plan)
```

### Step 6: Add Secrets Helper to Lambda Layer

**File**: `lambdas/layer/requirements.txt`

Add boto3 if not already there (it's included in Lambda runtime, but good to be explicit):

```txt
stripe>=5.0.0
boto3>=1.26.0
```

**Copy secrets helper to layer**:

```bash
mkdir -p lambdas/layer/python
cp lambdas/shared/secrets_helper.py lambdas/layer/python/
```

Or update the layer packaging in Terraform to include it.

### Step 7: Store Stripe Webhook Secret in Secrets Manager

The webhook secret is generated by Stripe when you create the webhook endpoint. We need to handle this carefully.

**Option A: Manual (Simpler for now)**

After Terraform creates the webhook endpoint:

```bash
# Get webhook secret from Stripe
stripe webhooks list

# Add it to Secrets Manager manually
aws secretsmanager update-secret \
  --secret-id dev-versiful_secrets \
  --secret-string "$(aws secretsmanager get-secret-value \
    --secret-id dev-versiful_secrets \
    --query SecretString --output text | \
    jq '. + {"stripe_webhook_secret": "whsec_xxx"}')"
```

**Option B: Terraform (More complex but automated)**

Use Terraform's Stripe provider to get the webhook secret:

```hcl
# In terraform/modules/stripe/main.tf
resource "stripe_webhook_endpoint" "versiful_webhook" {
  url = "https://api.${var.environment}.${var.domain_name}/stripe/webhook"
  
  enabled_events = [
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_succeeded",
    "invoice.payment_failed",
  ]
}

# Output the secret
output "webhook_secret" {
  value     = stripe_webhook_endpoint.versiful_webhook.secret
  sensitive = true
}
```

Then in `terraform/modules/secrets/main.tf`:

```hcl
variable "stripe_webhook_secret" {
  description = "Stripe webhook signing secret"
  type        = string
  sensitive   = true
}

resource "aws_secretsmanager_secret_version" "secret_version" {
  secret_id = aws_secretsmanager_secret.secrets.id

  secret_string = jsonencode({
    # ... other secrets ...
    "stripe_secret_key"      = var.stripe_secret_key,
    "stripe_publishable_key" = var.stripe_publishable_key,
    "stripe_webhook_secret"  = var.stripe_webhook_secret
  })
}
```

And pass it through in `terraform/main.tf`:

```hcl
module "secrets" {
  source = "./modules/secrets"
  
  # ... other variables ...
  stripe_publishable_key = var.stripe_publishable_key
  stripe_secret_key      = var.stripe_secret_key
  stripe_webhook_secret  = module.stripe.webhook_secret
}
```

### Step 8: Optional - Store Price IDs in Secrets Manager Too

Instead of hardcoding price IDs, store them in Secrets Manager:

```hcl
# In terraform/modules/secrets/main.tf
resource "aws_secretsmanager_secret_version" "secret_version" {
  secret_id = aws_secretsmanager_secret.secrets.id

  secret_string = jsonencode({
    # ... other secrets ...
    "stripe_secret_key"       = var.stripe_secret_key,
    "stripe_publishable_key"  = var.stripe_publishable_key,
    "stripe_webhook_secret"   = var.stripe_webhook_secret,
    "stripe_monthly_price_id" = var.stripe_monthly_price_id,
    "stripe_annual_price_id"  = var.stripe_annual_price_id
  })
}
```

Then Lambdas can fetch price IDs from secrets instead of environment variables.

## Secrets Structure

Your Secrets Manager secret will look like this:

```json
{
  "twilio_sid": "SKxxx",
  "twilio_secret": "xxx",
  "twilio_auth": "xxx",
  "twilio_account_sid": "ACxxx",
  "gpt": "sk-xxx",
  "AWS_S3_IAM_SECRET": "xxx",
  "TEST_USER_EMAIL": "test@example.com",
  "TEST_USER_PASSWORD": "password",
  "USER_POOL_CLIENT_ID": "xxx",
  "USER_POOL_CLIENT_SECRET": null,
  "API_BASE_URL": "https://api.dev.versiful.io",
  "USER_POOL_ID": "us-east-1_xxx",
  "stripe_publishable_key": "pk_test_xxx",
  "stripe_secret_key": "sk_test_xxx",
  "stripe_webhook_secret": "whsec_xxx",
  "stripe_monthly_price_id": "price_xxx",
  "stripe_annual_price_id": "price_xxx"
}
```

## Performance Considerations

### Caching Secrets

The `@lru_cache` decorator caches secrets for the lifetime of the Lambda execution environment:

```python
@lru_cache(maxsize=1)
def get_secrets():
    # Only called once per Lambda container
    # Subsequent calls return cached value
    response = secrets_client.get_secret_value(SecretId=secret_arn)
    return json.loads(response['SecretString'])
```

**Benefits**:
- First invocation: ~50-100ms to fetch from Secrets Manager
- Subsequent invocations in same container: <1ms (cached)
- Lambda containers are reused, so cache persists across invocations

### Cold Start Impact

- First Lambda invocation (cold start): +50-100ms
- Warm invocations: negligible (cached)
- Still faster than storing as environment variables and parsing

## Cost

**AWS Secrets Manager Pricing**:
- $0.40 per secret per month
- $0.05 per 10,000 API calls

**Your costs**:
- 3 environments × 1 secret = **$1.20/month**
- API calls: ~10 per Lambda cold start, containers reused
- Estimated: **~$1.50/month total** for Secrets Manager

**Worth it for**:
- ✅ Better security
- ✅ Centralized management
- ✅ Rotation without redeployment
- ✅ Audit trail

## IAM Permissions

Your Lambda execution role already has Secrets Manager access:

```hcl
# In terraform/modules/lambdas/main.tf
resource "aws_iam_policy" "secrets_manager_policy" {
  name        = "${var.environment}-${var.project_name}-LambdaSecretsManagerPolicy"
  description = "Allows Lambda to access secrets in AWS Secrets Manager"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Effect   = "Allow"
        Resource = var.secret_arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "attach_policy" {
  role       = aws_iam_role.lambda_exec_role.name
  policy_arn = aws_iam_policy.secrets_manager_policy.arn
}
```

This is already in place! ✅

## Testing

### Test Locally

```python
# test_secrets.py
import os
os.environ['SECRET_ARN'] = 'arn:aws:secretsmanager:us-east-1:xxx:secret:dev-versiful_secrets-xxx'

from secrets_helper import get_secret, get_stripe_keys

# Test fetching secrets
stripe_keys = get_stripe_keys()
print(f"Publishable: {stripe_keys['publishable_key'][:20]}...")
print(f"Secret: {stripe_keys['secret_key'][:20]}...")

# Test caching (should be instant second time)
import time
start = time.time()
get_secret('stripe_secret_key')
print(f"First call: {time.time() - start:.3f}s")

start = time.time()
get_secret('stripe_secret_key')
print(f"Second call (cached): {time.time() - start:.3f}s")
```

### Test in Lambda

Deploy and invoke:

```bash
aws lambda invoke \
  --function-name dev-versiful-subscription \
  --payload '{"path": "/subscription/prices", "httpMethod": "GET"}' \
  response.json

cat response.json
```

## Summary

**Changes Made**:
1. ✅ Added `stripe_publishable_key` and `stripe_secret_key` to Secrets Manager
2. ✅ Lambda functions fetch keys from Secrets Manager at runtime
3. ✅ Created reusable `secrets_helper.py` with caching
4. ✅ Removed keys from Lambda environment variables
5. ✅ Only pass `SECRET_ARN` to Lambda environment

**Security Improvements**:
- 🔒 Keys never visible in Lambda console
- 🔒 Keys can be rotated without redeploying
- 🔒 Centralized secret management
- 🔒 Audit trail via CloudWatch
- 🔒 Fine-grained IAM permissions

**Performance**:
- First call: +50-100ms (fetch from Secrets Manager)
- Subsequent calls: <1ms (cached in Lambda container)
- Negligible impact on user experience

---

**Last Updated**: December 22, 2025  
**Security Level**: Production-ready ✅

