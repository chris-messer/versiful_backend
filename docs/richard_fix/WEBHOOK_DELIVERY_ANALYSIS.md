# Webhook Delivery Issue Analysis

## Timeline

1. **4:30 PM - 5:32 PM** - Multiple webhook failures with "Stripe webhook secret not configured"
2. **5:53 PM** - Deployed updated Lambda and Secrets Manager with webhook secret
3. **7:01 PM** - `customer.subscription.deleted` event created (when we canceled subscription)
4. **7:01 PM onward** - NO LOG ENTRIES for webhook Lambda

## Problem

The `customer.subscription.deleted` event shows:
- **`pending_webhooks: 1`** - Stripe is still trying to deliver
- **No logs in Lambda** - Either not reaching Lambda OR being filtered before logging

## Possible Causes

### 1. Stripe Retry Backoff
Stripe uses exponential backoff for failed webhooks:
- 1st retry: immediate
- 2nd retry: ~1 hour later
- 3rd retry: ~2 hours later
- etc.

Since the webhook endpoint was **failing for hours** before we fixed it, Stripe may have marked it as "unhealthy" and is waiting longer between retries.

### 2. Lambda Not Logging
The Lambda receives the event but returns 500 **before** logging the event type.

Looking at the code:
```python
def handler(event, context):
    logger.info("Received webhook event")  # ✅ This logs
    
    # ... get signature ...
    
    if not endpoint_secret:
        logger.error("Stripe webhook secret not configured")  # ✅ This logged before
        return {"statusCode": 500}
    
    # ... verify signature ...
    
    event_type = webhook_event["type"]
    data = webhook_event["data"]["object"]
    
    logger.info(f"Processing webhook event: {event_type}")  # ❌ We'd see this if working
```

### 3. Signature Verification Failing
If the webhook secret is wrong or the signature verification is failing, we'd see:
```python
except stripe.error.SignatureVerificationError as e:
    logger.error(f"Invalid signature: {e}")
```

But we're not seeing ANY logs, which means the Lambda isn't being invoked at all.

## Most Likely Cause

**Stripe is using exponential backoff** because the endpoint failed repeatedly before we fixed it. The webhook will eventually retry, but it might take 1-2 hours.

## Solution Options

### Option 1: Wait for Stripe Retry (Recommended)
- Stripe will eventually retry the webhook
- Could take 1-2 hours based on backoff schedule
- No action needed

### Option 2: Manually Trigger Webhook Event
We can manually send a test webhook to verify the endpoint works:
```bash
stripe events resend evt_1SrMyHBcYhqWB9qELyKku8J3
```

### Option 3: Create Test Event
Cancel and recreate a test subscription to generate a fresh event.

## Verification Steps

1. **Check if secret is accessible in Lambda:**
```bash
aws lambda invoke --function-name prod-versiful-stripe-webhook \
  --payload '{"test": "access"}' \
  /tmp/response.json
```

2. **Manually retry the event in Stripe Dashboard:**
- Go to Stripe Dashboard → Developers → Events
- Find event `evt_1SrMyHBcYhqWB9qELyKku8J3`
- Click "Send test webhook"

3. **Check webhook endpoint health:**
```bash
curl -X POST https://api.versiful.io/stripe/webhook \
  -H "Content-Type: application/json" \
  -d '{"test": "ping"}'
```

## Expected Behavior Once Fixed

When webhook delivers successfully, you should see:
```
[INFO] Received webhook event
[INFO] Processing webhook event: customer.subscription.deleted
[INFO] Subscription deleted for customer cus_Toz6CdFWeVRNJL
[INFO] Found user: c428a478-e031-705e-db1d-fe9577d74a24
[INFO] Reverted user c428a478-e031-705e-db1d-fe9577d74a24 to free plan after subscription ended
```

## Impact

**For this specific event:** None - we already manually canceled the subscription and updated the database.

**For future events:** Webhooks should work correctly now that the secret is configured, but Stripe might still be in exponential backoff mode for a while.

