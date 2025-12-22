# Stripe Integration Troubleshooting Guide

This document covers common issues you might encounter during Stripe integration and how to resolve them.

## 🔍 General Debugging Tips

### 1. Check Stripe Dashboard First
- Go to https://dashboard.stripe.com/test (for dev/staging) or https://dashboard.stripe.com (for prod)
- Check "Developers → Webhooks" for delivery status
- Check "Developers → Events" for all API events
- Check "Developers → Logs" for API request details

### 2. Check CloudWatch Logs
```bash
# View subscription lambda logs
aws logs tail /aws/lambda/{env}-versiful-subscription --follow

# View webhook lambda logs
aws logs tail /aws/lambda/{env}-versiful-stripe-webhook --follow

# View API Gateway logs
aws logs tail /aws/api-gateway/{env}-versiful-stage --follow
```

### 3. Test with Stripe CLI
```bash
# Listen to webhooks locally
stripe listen --forward-to https://api.dev.versiful.io/stripe/webhook

# Trigger test events
stripe trigger checkout.session.completed
stripe trigger invoice.payment_failed

# View recent events
stripe events list --limit 10
```

## ❌ Common Errors & Solutions

### Error: "No such price: 'price_xxxxx'"

**Symptoms**: Checkout fails with error about invalid price ID

**Causes**:
- Price ID from Terraform output doesn't match what's in Stripe
- Using test mode price ID in live mode (or vice versa)
- Environment variable not set correctly in Lambda

**Solutions**:
```bash
# 1. Verify price IDs in Stripe
stripe prices list

# 2. Check Terraform outputs
cd terraform
./scripts/tf-env.sh dev output

# 3. Verify Lambda environment variables
aws lambda get-function-configuration \
  --function-name dev-versiful-subscription \
  --query 'Environment.Variables'

# 4. If mismatch, update Terraform and redeploy
./scripts/tf-env.sh dev apply
```

---

### Error: "No signatures found matching the expected signature for payload"

**Symptoms**: Webhook returns 400, Stripe dashboard shows failed deliveries

**Causes**:
- Webhook secret mismatch between Stripe and Lambda
- Webhook secret not properly passed to Lambda
- Request body modified by API Gateway

**Solutions**:
```bash
# 1. Get webhook secret from Stripe
stripe webhooks list

# 2. Verify in Terraform output
./scripts/tf-env.sh dev output stripe_webhook_secret

# 3. Check Lambda environment variable
aws lambda get-function-configuration \
  --function-name dev-versiful-stripe-webhook \
  --query 'Environment.Variables.STRIPE_WEBHOOK_SECRET'

# 4. Verify AWS Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id dev-versiful_secrets \
  --query 'SecretString' --output text | jq .stripe_webhook_secret

# 5. Update if needed
cd terraform
./scripts/tf-env.sh dev apply
```

**Code Fix** (if API Gateway is modifying body):
Ensure API Gateway integration is `AWS_PROXY` type (passes request unmodified):
```hcl
resource "aws_apigatewayv2_integration" "stripe_webhook" {
  integration_type = "AWS_PROXY"  # MUST be AWS_PROXY
  # ...
}
```

---

### Error: "Access denied" when creating checkout session

**Symptoms**: User gets error when clicking "Subscribe"

**Causes**:
- JWT authorizer rejecting request
- CORS issue (OPTIONS preflight failing)
- User not authenticated

**Solutions**:
```bash
# 1. Check JWT authorizer logs
aws logs tail /aws/lambda/{env}-versiful-authorizer --follow

# 2. Verify CORS configuration
aws apigatewayv2 get-api --api-id <api-id>

# 3. Test with curl (replace with real token)
curl -X POST https://api.dev.versiful.io/subscription/checkout \
  -H "Content-Type: application/json" \
  -H "Cookie: id_token=<token>" \
  -d '{"priceId": "price_xxxxx"}'

# 4. Check if route requires auth
aws apigatewayv2 get-route --api-id <api-id> --route-id <route-id>
```

---

### Error: "Customer not found" in webhook

**Symptoms**: Webhook processing fails with "No such customer: 'cus_xxxxx'"

**Causes**:
- Customer was deleted in Stripe but webhook references it
- Using test mode customer ID in live mode (or vice versa)

**Solutions**:
```python
# Add try/except in webhook handler
try:
    customer = stripe.Customer.retrieve(customer_id)
except stripe.error.InvalidRequestError as e:
    logger.error(f"Customer {customer_id} not found: {e}")
    # Gracefully handle - maybe mark user as unsubscribed
    return {"statusCode": 200}  # Return 200 to prevent retries
```

---

### Error: "User not found" when updating DynamoDB

**Symptoms**: Webhook processes but DynamoDB update fails

**Causes**:
- User record doesn't exist in DynamoDB
- Looking up by wrong field (using email instead of userId)
- Environment mismatch (dev webhook updating prod DB)

**Solutions**:
```python
# In webhook handler, add defensive checks
response = table.scan(
    FilterExpression=Attr("stripeCustomerId").eq(customer_id)
)

if not response["Items"]:
    logger.warning(f"No user found for customer {customer_id}")
    # Create placeholder record or alert admins
    return {"statusCode": 200}

user = response["Items"][0]

# Always use conditional updates
try:
    table.update_item(
        Key={"userId": user["userId"]},
        UpdateExpression="SET isSubscribed = :val",
        ExpressionAttributeValues={":val": True},
        ConditionExpression="attribute_exists(userId)"  # Ensure it exists
    )
except ClientError as e:
    if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
        logger.error(f"User {user['userId']} doesn't exist in DB")
```

---

### Error: "Checkout redirects to error page"

**Symptoms**: After entering card, user is redirected to error URL instead of success

**Causes**:
- Payment declined
- Card requires 3D Secure authentication
- Checkout session expired (24 hours)

**Solutions**:
```bash
# 1. Check checkout session in Stripe
stripe checkout sessions list --limit 5

# 2. Get session details
stripe checkout sessions retrieve cs_xxxxx

# 3. Check payment intent status
stripe payment_intents retrieve pi_xxxxx

# 4. For testing, use success test cards
# Success: 4242 4242 4242 4242
# 3DS: 4000 0025 0000 3155
# Decline: 4000 0000 0000 0002
```

**Frontend Update** (handle errors):
```javascript
const handleSubscribe = async (plan) => {
    try {
        const response = await fetch(`${apiUrl}/subscription/checkout`, {
            method: "POST",
            credentials: "include",
            body: JSON.stringify({ priceId: plan.priceId })
        });
        
        if (!response.ok) {
            const error = await response.json();
            alert(`Checkout error: ${error.message}`);
            return;
        }
        
        const { sessionId } = await response.json();
        const stripe = await loadStripe(publishableKey);
        const { error } = await stripe.redirectToCheckout({ sessionId });
        
        if (error) {
            alert(`Redirect error: ${error.message}`);
        }
    } catch (e) {
        console.error("Checkout error:", e);
        alert("Failed to start checkout. Please try again.");
    }
};
```

---

### Error: "Webhook received but DB not updated"

**Symptoms**: Stripe shows webhook delivered, but `isSubscribed` still false

**Causes**:
- Lambda processed event but DB update failed
- Lambda returned 200 before completing DB update
- DynamoDB throttling or timeout

**Solutions**:
```python
# Ensure Lambda returns 200 ONLY after successful DB update
def handler(event, context):
    try:
        # ... verify signature ...
        event_type = webhook_event["type"]
        
        if event_type == "checkout.session.completed":
            handle_checkout_completed(webhook_event["data"]["object"])
        
        # ONLY return 200 after all processing complete
        return {"statusCode": 200, "body": "Success"}
    except Exception as e:
        logger.error(f"Webhook processing failed: {e}")
        # Return 500 so Stripe retries
        return {"statusCode": 500, "body": "Processing failed"}

def handle_checkout_completed(session):
    # ... process ...
    
    # Wait for DB update to complete
    response = table.update_item(
        Key={"userId": user_id},
        UpdateExpression="SET isSubscribed = :val",
        ExpressionAttributeValues={":val": True},
        ReturnValues="ALL_NEW"
    )
    
    logger.info(f"DB updated successfully: {response}")
    # No return until this completes
```

**Add timeout monitoring**:
```python
import time

def handle_checkout_completed(session):
    start_time = time.time()
    
    # ... processing ...
    
    elapsed = time.time() - start_time
    if elapsed > 25:  # Lambda timeout is 30s
        logger.error(f"Processing took {elapsed}s, near timeout!")
```

---

### Error: "Price not found" on frontend

**Symptoms**: Frontend can't fetch price IDs, subscription page doesn't load

**Causes**:
- `/subscription/prices` endpoint not deployed
- API Gateway route not configured
- CORS blocking request

**Solutions**:
```bash
# 1. Test endpoint directly
curl https://api.dev.versiful.io/subscription/prices

# 2. Check if route exists
aws apigatewayv2 get-routes --api-id <api-id> | grep prices

# 3. Check Lambda
aws lambda get-function --function-name dev-versiful-subscription

# 4. If missing, redeploy Terraform
cd terraform
./scripts/tf-env.sh dev apply
```

**Frontend code** (handle missing prices):
```javascript
const [prices, setPrices] = useState({ monthly: null, annual: null });
const [loading, setLoading] = useState(true);

useEffect(() => {
    const fetchPrices = async () => {
        try {
            const response = await fetch(`${apiUrl}/subscription/prices`);
            if (response.ok) {
                const data = await response.json();
                setPrices(data);
            } else {
                console.error("Failed to fetch prices");
            }
        } catch (e) {
            console.error("Error fetching prices:", e);
        } finally {
            setLoading(false);
        }
    };
    
    fetchPrices();
}, []);

if (loading) return <div>Loading...</div>;
if (!prices.monthly) return <div>Pricing unavailable. Please try again later.</div>;
```

---

### Error: "Too many redirects" when accessing customer portal

**Symptoms**: Infinite redirect loop when clicking "Manage Subscription"

**Causes**:
- Portal session creation failing
- CORS issue
- Incorrect return URL

**Solutions**:
```python
# In subscription_handler.py, add better error handling
def create_portal_session(event, context):
    try:
        user_id = event["requestContext"]["authorizer"]["userId"]
        user = table.get_item(Key={"userId": user_id})
        
        if "Item" not in user:
            return {
                "statusCode": 404,
                "body": json.dumps({"error": "User not found"})
            }
        
        if not user["Item"].get("stripeCustomerId"):
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "No active subscription"})
            }
        
        portal_session = stripe.billing_portal.Session.create(
            customer=user["Item"]["stripeCustomerId"],
            return_url=f"https://{os.environ['FRONTEND_DOMAIN']}/settings"
        )
        
        logger.info(f"Portal session created: {portal_session.id}")
        
        return {
            "statusCode": 200,
            "body": json.dumps({"url": portal_session.url})
        }
    except Exception as e:
        logger.error(f"Portal session error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
```

---

## 🔐 Security Issues

### Issue: Webhook endpoint receiving spam/invalid requests

**Solution**: Signature verification handles this automatically. But add rate limiting:

```hcl
# In API Gateway Terraform
resource "aws_apigatewayv2_route" "stripe_webhook" {
  # ...
  throttle_settings {
    rate_limit  = 100  # requests per second
    burst_limit = 50
  }
}
```

### Issue: Exposed Stripe secret key in logs

**Solution**: Never log full keys. Mask them:

```python
import re

def mask_key(key):
    if not key:
        return None
    return key[:7] + "..." + key[-4:]

logger.info(f"Using Stripe key: {mask_key(stripe.api_key)}")
```

---

## 🔄 Sync & Reconciliation Issues

### Issue: DynamoDB and Stripe out of sync

**Symptoms**: User shows as subscribed in Stripe but not in DynamoDB (or vice versa)

**Solution**: Run reconciliation script

```python
# scripts/sync_stripe_subscriptions.py
import stripe
import boto3
from datetime import datetime

stripe.api_key = "sk_test_..."
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("dev-versiful-users")

def sync_subscriptions():
    # Get all active subscriptions from Stripe
    subscriptions = stripe.Subscription.list(status="active", limit=100)
    
    discrepancies = []
    
    for sub in subscriptions.auto_paging_iter():
        customer_id = sub["customer"]
        
        # Find user in DynamoDB
        response = table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr("stripeCustomerId").eq(customer_id)
        )
        
        if not response["Items"]:
            discrepancies.append({
                "type": "missing_in_db",
                "customer_id": customer_id,
                "subscription_id": sub["id"]
            })
            continue
        
        user = response["Items"][0]
        
        # Check if DB matches Stripe
        if not user.get("isSubscribed"):
            discrepancies.append({
                "type": "not_subscribed_in_db",
                "user_id": user["userId"],
                "customer_id": customer_id,
                "should_be": True,
                "currently_is": False
            })
            
            # Auto-fix
            table.update_item(
                Key={"userId": user["userId"]},
                UpdateExpression="SET isSubscribed = :val, subscriptionStatus = :status",
                ExpressionAttributeValues={":val": True, ":status": sub["status"]}
            )
            print(f"Fixed: {user['userId']}")
    
    print(f"\nFound {len(discrepancies)} discrepancies")
    for d in discrepancies:
        print(d)

if __name__ == "__main__":
    sync_subscriptions()
```

Run it:
```bash
cd scripts
python sync_stripe_subscriptions.py
```

---

## 📊 Monitoring & Alerts

### Set up CloudWatch Alarms

```bash
# Lambda error rate alarm
aws cloudwatch put-metric-alarm \
  --alarm-name "dev-stripe-webhook-errors" \
  --alarm-description "Stripe webhook Lambda error rate > 1%" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --evaluation-periods 1 \
  --threshold 1 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=FunctionName,Value=dev-versiful-stripe-webhook

# Webhook delivery failures (via Stripe)
# Go to Stripe Dashboard → Developers → Webhooks → [Your endpoint]
# Click "..." → Configure alerts → Enable email notifications
```

### Check Metrics

```bash
# Lambda invocations
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=dev-versiful-stripe-webhook \
  --start-time 2025-12-22T00:00:00Z \
  --end-time 2025-12-22T23:59:59Z \
  --period 3600 \
  --statistics Sum

# Lambda errors
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=dev-versiful-stripe-webhook \
  --start-time 2025-12-22T00:00:00Z \
  --end-time 2025-12-22T23:59:59Z \
  --period 3600 \
  --statistics Sum
```

---

## 🚨 Emergency Procedures

### Rollback Lambda Functions

```bash
# List previous versions
aws lambda list-versions-by-function --function-name dev-versiful-stripe-webhook

# Rollback to previous version
aws lambda update-alias \
  --function-name dev-versiful-stripe-webhook \
  --name LIVE \
  --function-version <previous-version>
```

### Disable Webhook Temporarily

```bash
# Via Stripe CLI
stripe webhooks update <webhook-id> --disabled

# Via Dashboard
# Go to Developers → Webhooks → [Your endpoint] → Disable
```

### Manual Subscription Fix

```python
# If user paid but not subscribed in DB
import boto3

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("dev-versiful-users")

table.update_item(
    Key={"userId": "<user-id>"},
    UpdateExpression="""
        SET isSubscribed = :sub,
            plan = :plan,
            subscriptionStatus = :status,
            stripeCustomerId = :cid,
            stripeSubscriptionId = :sid,
            currentPeriodEnd = :end
    """,
    ExpressionAttributeValues={
        ":sub": True,
        ":plan": "monthly",
        ":status": "active",
        ":cid": "<cus_xxx>",
        ":sid": "<sub_xxx>",
        ":end": 1738368000
    }
)
```

---

## 📞 Getting Help

### Stripe Support
- **Dashboard**: https://dashboard.stripe.com/support
- **Docs**: https://stripe.com/docs
- **Status**: https://status.stripe.com

### AWS Support
- **Lambda Logs**: CloudWatch Logs
- **Support Center**: AWS Console → Support

### Internal Escalation
1. Check this troubleshooting guide
2. Check CloudWatch logs and Stripe dashboard
3. Run reconciliation script
4. Contact devops/backend team
5. If payment issue, contact Stripe support

---

**Last Updated**: December 22, 2025  
**Maintainer**: [Your Name]

