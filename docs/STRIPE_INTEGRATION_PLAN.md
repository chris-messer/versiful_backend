# Stripe Payment Integration Plan

## Executive Summary

This document outlines the complete plan for integrating Stripe payment processing into Versiful using Infrastructure as Code (Terraform). The integration will support two subscription plans (monthly $9.99, annual $99.99) across three environments (dev/staging using Stripe test mode, prod using live mode).

## Current State Analysis

### Existing Infrastructure
- **DynamoDB Tables**: `{env}-versiful-users` with `isSubscribed` field
- **User Lambda**: `lambdas/users/` handling user profile CRUD
- **API Gateway**: HTTP API v2 with JWT authorizer
- **Frontend**: React app with subscription page (currently mocking paid plans)
- **Environments**: dev, staging, prod with separate tfvars

### Stripe Keys Already Added
- `stripe_publishable_key` and `stripe_secret_key` in dev.tfvars
- Need to add same keys to staging.tfvars and real production keys to prod.tfvars

## Architecture Overview

```
┌─────────────────┐
│   Frontend      │
│   (React)       │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────┐
│   Stripe Checkout Session          │
│   (Hosted by Stripe)                │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│   API Gateway                       │
│   ├─ POST /subscription/checkout    │◄── Create checkout session
│   ├─ POST /subscription/portal      │◄── Customer portal access
│   └─ POST /stripe/webhook           │◄── Stripe webhook events
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│   Lambda Functions                  │
│   ├─ subscription_handler.py        │
│   └─ stripe_webhook_handler.py      │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│   DynamoDB (users table)            │
│   Fields:                           │
│   - userId (PK)                     │
│   - isSubscribed (boolean)          │
│   - plan (free/monthly/annual)      │
│   - stripeCustomerId                │◄── NEW
│   - stripeSubscriptionId            │◄── NEW
│   - subscriptionStatus              │◄── NEW (active/past_due/canceled/etc)
│   - currentPeriodEnd                │◄── NEW (timestamp)
│   - cancelAtPeriodEnd               │◄── NEW (boolean)
└─────────────────────────────────────┘
```

## Implementation Plan

### Phase 1: Terraform Infrastructure Setup

#### 1.1 Add Stripe Provider
**File**: `terraform/main.tf`

Add Stripe provider configuration:
```hcl
terraform {
  required_providers {
    stripe = {
      source  = "lukasaron/stripe"
      version = "~> 1.0"
    }
  }
}

provider "stripe" {
  api_key = var.stripe_secret_key
}
```

#### 1.2 Update Variables
**File**: `terraform/variables.tf`

Add:
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

#### 1.3 Update All Environment tfvars Files
- **dev.tfvars**: Already has test keys ✓
- **staging.tfvars**: Add same test keys as dev
- **prod.tfvars**: Add LIVE production keys (to be provided)

#### 1.4 Create Stripe Module
**Directory**: `terraform/modules/stripe/`

**Files to create**:
- `main.tf` - Define Stripe products, prices, webhook endpoints
- `variables.tf` - Module inputs
- `outputs.tf` - Module outputs (price IDs, webhook secret)

**Contents of `main.tf`**:
```hcl
# Stripe Product
resource "stripe_product" "versiful_subscription" {
  name        = "Versiful ${var.environment} Subscription"
  description = "Biblical guidance and scripture via SMS"
  type        = "service"
}

# Monthly Price
resource "stripe_price" "monthly" {
  product     = stripe_product.versiful_subscription.id
  nickname    = "Monthly Premium - ${var.environment}"
  unit_amount = 999  # $9.99
  currency    = "usd"
  recurring {
    interval = "month"
  }
}

# Annual Price
resource "stripe_price" "annual" {
  product     = stripe_product.versiful_subscription.id
  nickname    = "Annual Premium - ${var.environment}"
  unit_amount = 9999  # $99.99
  currency    = "usd"
  recurring {
    interval = "year"
  }
}

# Webhook Endpoint
resource "stripe_webhook_endpoint" "versiful_webhook" {
  url = "https://api.${var.environment}.${var.domain_name}/stripe/webhook"
  
  enabled_events = [
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_succeeded",
    "invoice.payment_failed",
    "customer.subscription.trial_will_end",
  ]
}
```

#### 1.5 Add Stripe Secrets to AWS Secrets Manager
**File**: `terraform/modules/secrets/main.tf`

Update secret to include Stripe keys:
```hcl
secret_string = jsonencode({
  # ... existing secrets ...
  "stripe_secret_key"      = var.stripe_secret_key,
  "stripe_publishable_key" = var.stripe_publishable_key,
  "stripe_webhook_secret"  = var.stripe_webhook_secret  # From Stripe module output
})
```

### Phase 2: Lambda Functions

#### 2.1 Subscription Handler Lambda
**File**: `lambdas/subscription/subscription_handler.py`

**Purpose**: Handle checkout session creation and customer portal access

**Endpoints**:
- `POST /subscription/checkout` - Create Stripe checkout session
- `POST /subscription/portal` - Redirect to Stripe customer portal
- `GET /subscription/prices` - Return price IDs for frontend

**Key Logic**:
```python
import json
import os
import boto3
import stripe
from datetime import datetime, timezone

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
dynamodb = boto3.resource("dynamodb")
table_name = f"{os.environ['ENVIRONMENT']}-{os.environ['PROJECT_NAME']}-users"
table = dynamodb.Table(table_name)

def create_checkout_session(event, context):
    """Create a Stripe checkout session for monthly or annual plan"""
    user_id = event["requestContext"]["authorizer"]["userId"]
    body = json.loads(event["body"])
    price_id = body.get("priceId")  # stripe price ID from frontend
    
    # Get or create Stripe customer
    user = table.get_item(Key={"userId": user_id})["Item"]
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
        success_url=f"https://{os.environ['FRONTEND_DOMAIN']}/settings?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"https://{os.environ['FRONTEND_DOMAIN']}/subscription",
        metadata={"userId": user_id}
    )
    
    return {
        "statusCode": 200,
        "body": json.dumps({"sessionId": checkout_session.id})
    }

def create_portal_session(event, context):
    """Create customer portal session for managing subscription"""
    user_id = event["requestContext"]["authorizer"]["userId"]
    user = table.get_item(Key={"userId": user_id})["Item"]
    
    if not user.get("stripeCustomerId"):
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "No subscription found"})
        }
    
    portal_session = stripe.billing_portal.Session.create(
        customer=user["stripeCustomerId"],
        return_url=f"https://{os.environ['FRONTEND_DOMAIN']}/settings"
    )
    
    return {
        "statusCode": 200,
        "body": json.dumps({"url": portal_session.url})
    }

def get_prices(event, context):
    """Return Stripe price IDs for frontend"""
    return {
        "statusCode": 200,
        "body": json.dumps({
            "monthly": os.environ["STRIPE_MONTHLY_PRICE_ID"],
            "annual": os.environ["STRIPE_ANNUAL_PRICE_ID"]
        })
    }
```

#### 2.2 Stripe Webhook Handler Lambda
**File**: `lambdas/stripe_webhook/webhook_handler.py`

**Purpose**: Process Stripe webhook events and update DynamoDB

**Critical Events to Handle**:

1. **checkout.session.completed** - Initial subscription created
2. **customer.subscription.created** - Subscription activated
3. **customer.subscription.updated** - Plan changed, renewed
4. **customer.subscription.deleted** - Subscription canceled
5. **invoice.payment_succeeded** - Successful renewal
6. **invoice.payment_failed** - Failed payment (retry logic)

**Key Logic**:
```python
import json
import os
import boto3
import stripe
from datetime import datetime, timezone

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
endpoint_secret = os.environ["STRIPE_WEBHOOK_SECRET"]
dynamodb = boto3.resource("dynamodb")
table_name = f"{os.environ['ENVIRONMENT']}-{os.environ['PROJECT_NAME']}-users"
table = dynamodb.Table(table_name)

def handler(event, context):
    payload = event["body"]
    sig_header = event["headers"].get("stripe-signature")
    
    try:
        # Verify webhook signature
        webhook_event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        return {"statusCode": 400, "body": "Invalid payload"}
    except stripe.error.SignatureVerificationError as e:
        return {"statusCode": 400, "body": "Invalid signature"}
    
    event_type = webhook_event["type"]
    data = webhook_event["data"]["object"]
    
    # Route to appropriate handler
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
    
    return {"statusCode": 200, "body": "Success"}

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
            ":cap": None,  # Unlimited for paid plans (null = unlimited)
            ":status": subscription["status"],
            ":period_end": subscription["current_period_end"],
            ":cancel": subscription["cancel_at_period_end"],
            ":now": datetime.now(timezone.utc).isoformat()
        }
    )

def handle_subscription_updated(subscription):
    """Subscription was modified (plan change, cancellation scheduled, etc)"""
    customer_id = subscription["customer"]
    
    # Find user by customer ID
    response = table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr("stripeCustomerId").eq(customer_id)
    )
    
    if not response["Items"]:
        print(f"No user found for customer {customer_id}")
        return
    
    user = response["Items"][0]
    plan_interval = subscription["items"]["data"][0]["price"]["recurring"]["interval"]
    plan = "monthly" if plan_interval == "month" else "annual"
    
    # Update subscription details
    table.update_item(
        Key={"userId": user["userId"]},
        UpdateExpression="""
            SET subscriptionStatus = :status,
                plan = :plan,
                plan_monthly_cap = :cap,
                currentPeriodEnd = :period_end,
                cancelAtPeriodEnd = :cancel,
                isSubscribed = :sub,
                updatedAt = :now
        """,
        ExpressionAttributeValues={
            ":status": subscription["status"],
            ":plan": plan,
            ":cap": None,  # Unlimited for paid plans (null = unlimited)
            ":period_end": subscription["current_period_end"],
            ":cancel": subscription["cancel_at_period_end"],
            ":sub": subscription["status"] in ["active", "trialing"],
            ":now": datetime.now(timezone.utc).isoformat()
        }
    )

def handle_subscription_deleted(subscription):
    """Subscription was canceled and has now ended"""
    customer_id = subscription["customer"]
    
    response = table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr("stripeCustomerId").eq(customer_id)
    )
    
    if not response["Items"]:
        return
    
    user = response["Items"][0]
    
    # Mark user as unsubscribed, revert to free plan with message cap
    table.update_item(
        Key={"userId": user["userId"]},
        UpdateExpression="""
            SET isSubscribed = :sub,
                plan = :plan,
                plan_monthly_cap = :cap,
                subscriptionStatus = :status,
                updatedAt = :now
        """,
        ExpressionAttributeValues={
            ":sub": False,
            ":plan": "free",
            ":cap": 5,  # Revert to free tier limit (5 messages/month)
            ":status": "canceled",
            ":now": datetime.now(timezone.utc).isoformat()
        }
    )

def handle_payment_failed(invoice):
    """Payment failed - mark subscription at risk"""
    customer_id = invoice["customer"]
    subscription_id = invoice["subscription"]
    
    response = table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr("stripeCustomerId").eq(customer_id)
    )
    
    if not response["Items"]:
        return
    
    user = response["Items"][0]
    
    # Get current subscription status
    subscription = stripe.Subscription.retrieve(subscription_id)
    
    table.update_item(
        Key={"userId": user["userId"]},
        UpdateExpression="""
            SET subscriptionStatus = :status,
                isSubscribed = :sub,
                plan_monthly_cap = :cap,
                updatedAt = :now
        """,
        ExpressionAttributeValues={
            ":status": subscription["status"],  # Will be "past_due" or "unpaid"
            ":sub": subscription["status"] == "past_due",  # Still subscribed if past_due
            ":cap": None if subscription["status"] == "past_due" else 5,  # Keep unlimited if past_due, else revert to free
            ":now": datetime.now(timezone.utc).isoformat()
        }
    )

def handle_payment_succeeded(invoice):
    """Payment succeeded - renewal confirmed"""
    customer_id = invoice["customer"]
    subscription_id = invoice["subscription"]
    
    if not subscription_id:
        return  # Not a subscription invoice
    
    response = table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr("stripeCustomerId").eq(customer_id)
    )
    
    if not response["Items"]:
        return
    
    user = response["Items"][0]
    subscription = stripe.Subscription.retrieve(subscription_id)
    
    table.update_item(
        Key={"userId": user["userId"]},
        UpdateExpression="""
            SET subscriptionStatus = :status,
                isSubscribed = :sub,
                plan_monthly_cap = :cap,
                currentPeriodEnd = :period_end,
                updatedAt = :now
        """,
        ExpressionAttributeValues={
            ":status": subscription["status"],
            ":sub": True,
            ":cap": None,  # Unlimited for paid plans (null = unlimited)
            ":period_end": subscription["current_period_end"],
            ":now": datetime.now(timezone.utc).isoformat()
        }
    )
```

#### 2.3 Lambda Requirements
**File**: `lambdas/subscription/requirements.txt`
**File**: `lambdas/stripe_webhook/requirements.txt`

```
stripe>=5.0.0
boto3>=1.26.0
```

### Phase 3: Terraform Lambda & API Gateway Configuration

#### 3.1 Create Subscription Lambda Terraform
**File**: `terraform/modules/lambdas/_subscription.tf`

```hcl
# Package subscription lambda
data "archive_file" "subscription_lambda_package" {
  type        = "zip"
  source_dir  = "${path.module}/../../../lambdas/subscription"
  output_path = "${path.module}/../../../lambdas/subscription/subscription.zip"
}

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
      ENVIRONMENT              = var.environment
      PROJECT_NAME             = var.project_name
      STRIPE_SECRET_KEY        = var.stripe_secret_key
      STRIPE_MONTHLY_PRICE_ID  = var.stripe_monthly_price_id
      STRIPE_ANNUAL_PRICE_ID   = var.stripe_annual_price_id
      FRONTEND_DOMAIN          = var.frontend_domain
    }
  }

  layers = [aws_lambda_layer_version.shared_dependencies.arn]
}

# API Gateway routes
resource "aws_apigatewayv2_integration" "subscription_checkout" {
  api_id           = var.apiGateway_lambda_api_id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.subscription.invoke_arn
}

resource "aws_apigatewayv2_route" "subscription_checkout" {
  api_id    = var.apiGateway_lambda_api_id
  route_key = "POST /subscription/checkout"
  target    = "integrations/${aws_apigatewayv2_integration.subscription_checkout.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

resource "aws_apigatewayv2_integration" "subscription_portal" {
  api_id           = var.apiGateway_lambda_api_id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.subscription.invoke_arn
}

resource "aws_apigatewayv2_route" "subscription_portal" {
  api_id    = var.apiGateway_lambda_api_id
  route_key = "POST /subscription/portal"
  target    = "integrations/${aws_apigatewayv2_integration.subscription_portal.id}"
  authorization_type = "CUSTOM"
  authorizer_id      = var.jwt_auth_id
}

resource "aws_apigatewayv2_integration" "subscription_prices" {
  api_id           = var.apiGateway_lambda_api_id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.subscription.invoke_arn
}

resource "aws_apigatewayv2_route" "subscription_prices" {
  api_id    = var.apiGateway_lambda_api_id
  route_key = "GET /subscription/prices"
  target    = "integrations/${aws_apigatewayv2_integration.subscription_prices.id}"
}

resource "aws_lambda_permission" "allow_apigateway_subscription" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.subscription.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${var.apiGateway_execution_arn}/*/*"
}
```

#### 3.2 Create Stripe Webhook Lambda Terraform
**File**: `terraform/modules/lambdas/_stripe_webhook.tf`

```hcl
# Package webhook lambda
data "archive_file" "stripe_webhook_package" {
  type        = "zip"
  source_dir  = "${path.module}/../../../lambdas/stripe_webhook"
  output_path = "${path.module}/../../../lambdas/stripe_webhook/webhook.zip"
}

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
      ENVIRONMENT             = var.environment
      PROJECT_NAME            = var.project_name
      STRIPE_SECRET_KEY       = var.stripe_secret_key
      STRIPE_WEBHOOK_SECRET   = var.stripe_webhook_secret
    }
  }

  layers = [aws_lambda_layer_version.shared_dependencies.arn]
}

# API Gateway webhook route (NO AUTHORIZATION - Stripe needs direct access)
resource "aws_apigatewayv2_integration" "stripe_webhook" {
  api_id           = var.apiGateway_lambda_api_id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.stripe_webhook.invoke_arn
}

resource "aws_apigatewayv2_route" "stripe_webhook" {
  api_id    = var.apiGateway_lambda_api_id
  route_key = "POST /stripe/webhook"
  target    = "integrations/${aws_apigatewayv2_integration.stripe_webhook.id}"
  # NO AUTHORIZER - Stripe webhook signature validation in Lambda
}

resource "aws_lambda_permission" "allow_apigateway_webhook" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.stripe_webhook.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${var.apiGateway_execution_arn}/*/*"
}
```

### Phase 4: Frontend Integration

#### 4.1 Update Subscription Page
**File**: `versiful-frontend/src/pages/Subscription.jsx`

Key changes:
1. Fetch Stripe price IDs from backend on mount
2. For paid plans, call `/subscription/checkout` endpoint
3. Redirect to Stripe Checkout
4. Handle return from Stripe via `session_id` query param

```javascript
const handleSubscribe = async (plan) => {
    const apiUrl = `https://api.${import.meta.env.VITE_DOMAIN}`;
    
    if (plan.id === "free") {
        // Existing free plan logic
        // ...
    } else {
        // Paid plans - redirect to Stripe
        try {
            const response = await fetch(`${apiUrl}/subscription/checkout`, {
                method: "POST",
                credentials: "include",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    priceId: plan.id === "monthly" ? monthlyPriceId : annualPriceId
                })
            });
            
            const { sessionId } = await response.json();
            
            // Redirect to Stripe Checkout
            const stripe = await loadStripe(publishableKey);
            await stripe.redirectToCheckout({ sessionId });
        } catch (error) {
            console.error("Checkout error:", error);
            alert("Failed to start checkout. Please try again.");
        }
    }
};
```

#### 4.2 Add Stripe.js to Frontend
**File**: `versiful-frontend/index.html`

```html
<script src="https://js.stripe.com/v3/"></script>
```

Or install via npm:
```bash
npm install @stripe/stripe-js
```

#### 4.3 Update Settings Page
**File**: `versiful-frontend/src/pages/Settings.jsx`

Add button to manage subscription via Stripe Customer Portal:

```javascript
const handleManageSubscription = async () => {
    try {
        const response = await fetch(`${apiUrl}/subscription/portal`, {
            method: "POST",
            credentials: "include"
        });
        
        const { url } = await response.json();
        window.location.href = url;  // Redirect to Stripe portal
    } catch (error) {
        console.error("Portal error:", error);
    }
};
```

### Phase 5: Database Schema Updates

#### 5.1 DynamoDB Fields to Add
No Terraform changes needed (DynamoDB is schemaless), but document expected fields:

**New fields in users table**:
- `stripeCustomerId` (String) - Stripe customer ID
- `stripeSubscriptionId` (String) - Stripe subscription ID
- `subscriptionStatus` (String) - active, past_due, canceled, unpaid, etc.
- `currentPeriodEnd` (Number) - Unix timestamp of current period end
- `cancelAtPeriodEnd` (Boolean) - True if user scheduled cancellation
- `plan_monthly_cap` (Number or null) - SMS message limit per month; null = unlimited

**Existing fields**:
- `isSubscribed` (Boolean) - Quick lookup for active subscription
- `plan` (String) - free, monthly, annual

### Phase 6: Edge Cases & Error Handling

#### 6.1 Payment Failures
**Scenario**: User's card is declined on renewal

**Handling**:
1. `invoice.payment_failed` webhook received
2. Update `subscriptionStatus` to `past_due`
3. `isSubscribed` remains `true` during retry period (Stripe retries 3-4 times)
4. If all retries fail, Stripe sends `customer.subscription.deleted`
5. Set `isSubscribed` to `false`, `plan` to `free`

**User Experience**:
- Show banner in app: "Payment failed. Please update payment method."
- Link to Stripe Customer Portal to update card

#### 6.2 Subscription Cancellation
**Scenario**: User cancels subscription

**Handling**:
1. User clicks "Manage Subscription" → Stripe Customer Portal
2. Cancels subscription (end of period or immediately)
3. `customer.subscription.updated` webhook: `cancel_at_period_end = true`
4. Update DB: `cancelAtPeriodEnd = true`, `isSubscribed` still `true`
5. At period end: `customer.subscription.deleted` webhook
6. Update DB: `isSubscribed = false`, `plan = free`

**User Experience**:
- "Your subscription will end on [date]"
- Can still use premium features until period end

#### 6.3 Subscription Reactivation
**Scenario**: User canceled, wants to resubscribe before period end

**Handling**:
1. User clicks "Manage Subscription" → Stripe Customer Portal
2. Clicks "Reactivate" in portal
3. `customer.subscription.updated` webhook: `cancel_at_period_end = false`
4. Update DB: `cancelAtPeriodEnd = false`

#### 6.4 Plan Upgrades/Downgrades
**Scenario**: User switches from monthly to annual (or vice versa)

**Handling**:
1. User clicks "Manage Subscription" → Stripe Customer Portal
2. Switches plan
3. `customer.subscription.updated` webhook with new price ID
4. Update `plan` field based on interval (month/year)
5. Proration handled automatically by Stripe

#### 6.5 Duplicate Webhook Events
**Scenario**: Stripe sends same webhook twice

**Handling**:
- Stripe sends `idempotency_key` in webhook
- Lambda should be idempotent (updates are safe to repeat)
- DynamoDB conditional updates prevent race conditions

#### 6.6 Webhook Delivery Failures
**Scenario**: Lambda fails to process webhook

**Handling**:
- Stripe retries webhooks for 3 days
- Lambda should return 200 only after successful DB update
- Implement CloudWatch alarms on Lambda errors
- Manual reconciliation script to sync Stripe → DynamoDB

### Phase 7: Testing Strategy

#### 7.1 Test Mode Setup (Dev/Staging)
Use Stripe test cards:
- Success: `4242 4242 4242 4242`
- Decline: `4000 0000 0000 0002`
- Require auth: `4000 0025 0000 3155`

#### 7.2 Test Scenarios
1. **Happy path**: Sign up → subscribe → webhook → DB updated
2. **Failed payment**: Use declined card → verify past_due status
3. **Cancellation**: Cancel subscription → verify end of period
4. **Immediate cancellation**: Cancel immediately → verify instant access loss
5. **Reactivation**: Cancel → reactivate → verify continues
6. **Plan change**: Switch monthly ↔ annual
7. **Webhook replay**: Replay same event → verify idempotency

#### 7.3 Stripe CLI Testing
```bash
# Listen to webhooks locally
stripe listen --forward-to https://api.dev.versiful.io/stripe/webhook

# Trigger test events
stripe trigger checkout.session.completed
stripe trigger invoice.payment_failed
stripe trigger customer.subscription.deleted
```

### Phase 8: Deployment & Rollout

#### 8.1 Environment Promotion Strategy

**Step 1: Dev Environment**
1. Add Stripe test keys to dev.tfvars
2. Deploy Terraform: `./scripts/tf-env.sh dev apply`
3. Test all scenarios with Stripe CLI
4. Verify webhooks in Stripe dashboard

**Step 2: Staging Environment**
1. Add same test keys to staging.tfvars
2. Deploy: `./scripts/tf-env.sh staging apply`
3. Run full E2E test suite
4. Verify with real Stripe Checkout UI

**Step 3: Production Environment**
1. Get production Stripe keys from Stripe dashboard (live mode)
2. Add to prod.tfvars: `stripe_publishable_key` and `stripe_secret_key`
3. Deploy: `./scripts/tf-env.sh prod plan` (review carefully!)
4. Apply: `./scripts/tf-env.sh prod apply`
5. Monitor CloudWatch logs for 24 hours
6. Verify first real subscription end-to-end

#### 8.2 Rollback Plan
If issues in production:
1. Revert Lambda functions to previous version
2. Update frontend to show "Checkout temporarily unavailable"
3. Existing subscriptions continue unaffected (webhooks still processed)
4. Fix issues in dev/staging, redeploy to prod

### Phase 9: Monitoring & Operations

#### 9.1 CloudWatch Alarms
Create alarms for:
- Lambda errors (subscription & webhook handlers)
- Webhook signature validation failures
- DynamoDB throttling
- API Gateway 5xx errors on subscription endpoints

#### 9.2 Stripe Dashboard Monitoring
- Webhook delivery success rate (should be >99%)
- Failed payment rate
- Subscription churn rate
- Revenue metrics

#### 9.3 Reconciliation Script
Create admin script to sync Stripe → DynamoDB:
```python
# scripts/sync_stripe_subscriptions.py
# Fetch all active subscriptions from Stripe
# Compare with DynamoDB
# Report discrepancies
# Optionally auto-fix
```

### Phase 10: Additional Considerations

#### 10.1 Free Trial (Optional)
If offering trial period:
- Set `trial_period_days` in checkout session
- Handle `customer.subscription.trial_will_end` webhook (3 days before)
- Send email reminder to user

#### 10.2 Coupons/Promotions
- Create coupon codes in Stripe
- Pass to checkout session: `discounts: [{ coupon: 'WELCOME10' }]`

#### 10.3 Tax Collection
- Enable Stripe Tax in dashboard
- Automatically calculates sales tax by location
- No code changes needed

#### 10.4 Invoicing
- Stripe automatically generates invoices
- Configure email settings in Stripe dashboard
- Optionally show past invoices in app via Stripe API

## Implementation Checklist

### Backend
- [ ] Update `terraform/variables.tf` with Stripe variables
- [ ] Add Stripe keys to staging.tfvars and prod.tfvars
- [ ] Create `terraform/modules/stripe/` module
- [ ] Update `terraform/main.tf` to include Stripe provider & module
- [ ] Update `terraform/modules/secrets/main.tf` with Stripe keys
- [ ] Create `lambdas/subscription/subscription_handler.py`
- [ ] Create `lambdas/subscription/requirements.txt`
- [ ] Create `lambdas/stripe_webhook/webhook_handler.py`
- [ ] Create `lambdas/stripe_webhook/requirements.txt`
- [ ] Create `terraform/modules/lambdas/_subscription.tf`
- [ ] Create `terraform/modules/lambdas/_stripe_webhook.tf`
- [ ] Update Lambda layer with Stripe SDK
- [ ] Test webhook signature validation
- [ ] Test all webhook event handlers

### Frontend
- [ ] Install `@stripe/stripe-js` package
- [ ] Update `Subscription.jsx` to call checkout endpoint
- [ ] Add Stripe publishable key to environment variables
- [ ] Update `Settings.jsx` with "Manage Subscription" button
- [ ] Handle return from Stripe checkout (success/cancel)
- [ ] Display subscription status and next billing date
- [ ] Test all subscription flows

### Infrastructure
- [ ] Deploy to dev environment
- [ ] Test with Stripe CLI in dev
- [ ] Deploy to staging environment
- [ ] Run E2E tests in staging
- [ ] Deploy to production (with real keys)
- [ ] Monitor production for 24 hours

### Testing
- [ ] Test successful checkout (monthly)
- [ ] Test successful checkout (annual)
- [ ] Test payment failure
- [ ] Test subscription cancellation
- [ ] Test subscription reactivation
- [ ] Test plan upgrade/downgrade
- [ ] Test webhook idempotency
- [ ] Test customer portal access
- [ ] Verify DynamoDB updates for all events

### Operations
- [ ] Set up CloudWatch alarms
- [ ] Configure Stripe dashboard email notifications
- [ ] Create reconciliation script
- [ ] Document support procedures for payment issues
- [ ] Train support team on Stripe customer portal

## Security Considerations

1. **Webhook Security**: Always verify webhook signature before processing
2. **API Keys**: Never expose secret key to frontend (use publishable key only)
3. **Secrets Management**: Store all keys in AWS Secrets Manager, not in code
4. **HTTPS Only**: All Stripe communication must be over HTTPS
5. **PCI Compliance**: Using Stripe Checkout avoids PCI requirements (Stripe handles card data)

## Cost Estimates

### Stripe Fees
- 2.9% + $0.30 per transaction
- Monthly: $9.99 → $0.59 fee → $9.40 net
- Annual: $99.99 → $3.20 fee → $96.79 net

### AWS Costs (minimal)
- Lambda invocations: ~$0.20/month per 1000 users
- DynamoDB: Included in existing pay-per-request
- API Gateway: ~$0.10/month per 1000 users

## Support & Resources

- **Stripe Docs**: https://stripe.com/docs/billing/subscriptions/overview
- **Stripe Terraform Provider**: https://github.com/lukasaron/terraform-provider-stripe
- **Stripe Test Cards**: https://stripe.com/docs/testing
- **Stripe CLI**: https://stripe.com/docs/stripe-cli

## Next Steps

1. Review this plan with team
2. Get production Stripe account set up and verified
3. Begin Phase 1 (Terraform infrastructure)
4. Proceed through phases sequentially
5. Deploy to dev first, test thoroughly before staging/prod

---

**Document Version**: 1.0  
**Last Updated**: December 22, 2025  
**Author**: AI Assistant (Claude)

