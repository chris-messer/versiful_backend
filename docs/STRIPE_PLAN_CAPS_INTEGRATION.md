# Stripe Integration - Plan Caps & Message Limits

## Overview

This document details how Stripe subscription plans integrate with Versiful's SMS message cap system.

## Current SMS Cap Logic

The SMS handler (`lambdas/sms/sms_handler.py`) implements the following logic:

```python
def _evaluate_usage(phone_number: str):
    # 1. If user is subscribed (isSubscribed = True), allow unlimited
    if user_profile and user_profile.get("isSubscribed"):
        return {
            "allowed": True,
            "limit": None,  # Unlimited
            "reason": "subscribed"
        }
    
    # 2. Otherwise, check plan_monthly_cap field
    if user_profile and user_profile.get("plan_monthly_cap") is not None:
        limit = int(user_profile["plan_monthly_cap"])
    else:
        limit = FREE_MONTHLY_LIMIT  # Default: 5 messages
    
    # 3. Enforce the limit
    updated = consume_message_if_allowed(phone_number, limit, user_id=user_id)
```

**Key Points**:
- If `isSubscribed == True` → **Unlimited messages** (limit = None)
- If `plan_monthly_cap` is set → Use that value
- If neither → Default to `FREE_MONTHLY_LIMIT` (currently 5)

## Plan Tiers & Message Caps

### Current Plans

| Plan | Price | Stripe Interval | `plan` Field | `isSubscribed` | `plan_monthly_cap` | Messages |
|------|-------|----------------|--------------|----------------|-------------------|----------|
| Free | $0 | - | `"free"` | `false` | `null` or `5` | 5/month |
| Monthly Premium | $9.99 | `month` | `"monthly"` | `true` | `null` (unlimited) | Unlimited |
| Annual Premium | $99.99 | `year` | `"annual"` | `true` | `null` (unlimited) | Unlimited |

### Future Plans (Extensible)

| Plan | Price | `plan` Field | `isSubscribed` | `plan_monthly_cap` | Messages |
|------|-------|--------------|----------------|-------------------|----------|
| Basic | $4.99 | `"basic"` | `true` | `50` | 50/month |
| Pro | $14.99 | `"pro"` | `true` | `null` (unlimited) | Unlimited |

## Database Schema Changes

### Users Table - New/Updated Fields

```javascript
{
  userId: "google_123456",
  email: "user@example.com",
  
  // Subscription fields
  isSubscribed: true,              // Boolean - quick access check
  plan: "monthly",                 // String - "free" | "monthly" | "annual" | "basic" | "pro"
  plan_monthly_cap: null,          // Number or null - null = unlimited
  
  // Stripe fields
  stripeCustomerId: "cus_ABC123",
  stripeSubscriptionId: "sub_XYZ789",
  subscriptionStatus: "active",
  currentPeriodEnd: 1738368000,
  cancelAtPeriodEnd: false
}
```

**Field Details**:
- `isSubscribed`: Set to `true` for ANY paid plan, `false` for free
- `plan`: The plan identifier (free/monthly/annual/etc.)
- `plan_monthly_cap`: 
  - `null` or undefined → Unlimited (for paid plans)
  - `5` → Free plan default
  - Any number → Custom tier limit

## Webhook Handler Updates

### Updated: `handle_checkout_completed()` in `webhook_handler.py`

```python
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
            ":cap": None,  # ← Unlimited for paid plans
            ":status": subscription["status"],
            ":period_end": subscription["current_period_end"],
            ":cancel": subscription["cancel_at_period_end"],
            ":now": datetime.now(timezone.utc).isoformat()
        }
    )
```

### Updated: `handle_subscription_updated()` in `webhook_handler.py`

```python
def handle_subscription_updated(subscription):
    """Subscription was modified (plan change, cancellation scheduled, etc)"""
    customer_id = subscription["customer"]
    
    # Find user by customer ID
    response = table.scan(
        FilterExpression=Attr("stripeCustomerId").eq(customer_id)
    )
    
    if not response["Items"]:
        print(f"No user found for customer {customer_id}")
        return
    
    user = response["Items"][0]
    plan_interval = subscription["items"]["data"][0]["price"]["recurring"]["interval"]
    plan = "monthly" if plan_interval == "month" else "annual"
    
    # Determine cap based on plan
    # For current plans: all paid plans are unlimited
    plan_cap = None  # Unlimited
    
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
            ":cap": plan_cap,  # ← Set unlimited
            ":period_end": subscription["current_period_end"],
            ":cancel": subscription["cancel_at_period_end"],
            ":sub": subscription["status"] in ["active", "trialing"],
            ":now": datetime.now(timezone.utc).isoformat()
        }
    )
```

### Updated: `handle_subscription_deleted()` in `webhook_handler.py`

```python
def handle_subscription_deleted(subscription):
    """Subscription was canceled and has now ended"""
    customer_id = subscription["customer"]
    
    response = table.scan(
        FilterExpression=Attr("stripeCustomerId").eq(customer_id)
    )
    
    if not response["Items"]:
        return
    
    user = response["Items"][0]
    
    # Mark user as unsubscribed, revert to free plan with cap
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
            ":cap": 5,  # ← Revert to free tier limit
            ":status": "canceled",
            ":now": datetime.now(timezone.utc).isoformat()
        }
    )
```

## Future: Adding Tiered Plans

When adding new tiers (e.g., Basic at $4.99 with 50 messages/month):

### 1. Create Product & Price in Stripe

```hcl
# In terraform/modules/stripe/main.tf

resource "stripe_price" "basic" {
  product     = stripe_product.versiful_subscription.id
  nickname    = "Basic - ${var.environment}"
  unit_amount = 499  # $4.99
  currency    = "usd"
  recurring {
    interval = "month"
  }
  
  metadata = {
    plan_monthly_cap = "50"  # Store cap in Stripe metadata
  }
}
```

### 2. Update Webhook Handler Logic

```python
def get_plan_cap_from_subscription(subscription):
    """
    Extract plan cap from subscription metadata.
    Returns None for unlimited, or integer for capped plans.
    """
    price = subscription["items"]["data"][0]["price"]
    
    # Check if metadata includes plan_monthly_cap
    metadata = price.get("metadata", {})
    cap_value = metadata.get("plan_monthly_cap")
    
    if cap_value is None or cap_value == "unlimited":
        return None  # Unlimited
    
    try:
        return int(cap_value)
    except (ValueError, TypeError):
        return None  # Default to unlimited if invalid

def handle_checkout_completed(session):
    """Updated to handle plan caps from metadata"""
    # ... existing code ...
    
    subscription = stripe.Subscription.retrieve(subscription_id)
    plan_interval = subscription["items"]["data"][0]["price"]["recurring"]["interval"]
    
    # Determine plan name (you might want a mapping)
    plan = "monthly" if plan_interval == "month" else "annual"
    
    # Get cap from Stripe metadata
    plan_cap = get_plan_cap_from_subscription(subscription)
    
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
            ":cap": plan_cap,  # ← Now reads from metadata
            ":status": subscription["status"],
            ":period_end": subscription["current_period_end"],
            ":cancel": subscription["cancel_at_period_end"],
            ":now": datetime.now(timezone.utc).isoformat()
        }
    )
```

### 3. Plan Mapping (Optional but Recommended)

Create a mapping from Stripe price ID to plan details:

```python
# In webhook_handler.py

PLAN_CONFIGS = {
    os.environ.get("STRIPE_MONTHLY_PRICE_ID"): {
        "name": "monthly",
        "cap": None  # Unlimited
    },
    os.environ.get("STRIPE_ANNUAL_PRICE_ID"): {
        "name": "annual",
        "cap": None  # Unlimited
    },
    # Future plans
    os.environ.get("STRIPE_BASIC_PRICE_ID"): {
        "name": "basic",
        "cap": 50
    },
}

def get_plan_config(subscription):
    """Get plan configuration from price ID"""
    price_id = subscription["items"]["data"][0]["price"]["id"]
    config = PLAN_CONFIGS.get(price_id)
    
    if not config:
        # Fallback: try to read from metadata
        price = subscription["items"]["data"][0]["price"]
        metadata = price.get("metadata", {})
        return {
            "name": metadata.get("plan_name", "unknown"),
            "cap": int(metadata["plan_monthly_cap"]) if "plan_monthly_cap" in metadata else None
        }
    
    return config

def handle_checkout_completed(session):
    # ... existing code ...
    
    subscription = stripe.Subscription.retrieve(subscription_id)
    plan_config = get_plan_config(subscription)
    
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
            ":plan": plan_config["name"],
            ":cap": plan_config["cap"],
            ":status": subscription["status"],
            ":period_end": subscription["current_period_end"],
            ":cancel": subscription["cancel_at_period_end"],
            ":now": datetime.now(timezone.utc).isoformat()
        }
    )
```

## Testing Plan Caps

### Test Free Plan (5 messages)
1. Create account without subscribing
2. Send 5 SMS messages
3. 6th message should return quota exceeded
4. Wait for next month → counter resets

### Test Monthly Premium (Unlimited)
1. Subscribe to monthly plan
2. Complete checkout
3. Verify in DynamoDB: `isSubscribed=true`, `plan="monthly"`, `plan_monthly_cap=null`
4. Send 10+ SMS messages
5. All should go through (no limit)

### Test Annual Premium (Unlimited)
1. Subscribe to annual plan
2. Complete checkout
3. Verify in DynamoDB: `isSubscribed=true`, `plan="annual"`, `plan_monthly_cap=null`
4. Send 10+ SMS messages
5. All should go through (no limit)

### Test Subscription Cancellation
1. User with active subscription
2. Cancel subscription (end of period)
3. Wait for period to end
4. Verify webhook fires: `subscription.deleted`
5. Verify in DynamoDB: `isSubscribed=false`, `plan="free"`, `plan_monthly_cap=5`
6. Send 5 messages → OK
7. 6th message → quota exceeded

### Test Future: Basic Plan (50 messages)
1. Subscribe to basic plan
2. Verify in DynamoDB: `isSubscribed=true`, `plan="basic"`, `plan_monthly_cap=50`
3. Send 50 messages → all OK
4. 51st message → quota exceeded

## Summary of Changes Needed

### 1. Update `lambdas/stripe_webhook/webhook_handler.py`

Add `plan_monthly_cap` field to all update expressions:

- `handle_checkout_completed()`: Set `plan_monthly_cap = None` (unlimited)
- `handle_subscription_created()`: Set `plan_monthly_cap = None` (unlimited)
- `handle_subscription_updated()`: Set `plan_monthly_cap = None` (unlimited)
- `handle_subscription_deleted()`: Set `plan_monthly_cap = 5` (free tier)

### 2. Update `STRIPE_INTEGRATION_PLAN.md`

Update the webhook handler code sections to include the `plan_monthly_cap` field in all UpdateExpressions.

### 3. Update Frontend (Optional)

Show message quota in user settings:

```javascript
// In Settings.jsx
{user.plan === "free" && (
  <p className="text-sm text-gray-600">
    Message limit: {user.plan_monthly_cap || 5} per month
  </p>
)}

{user.isSubscribed && (
  <p className="text-sm text-green-600">
    ✓ Unlimited messages
  </p>
)}
```

## Quick Reference

**For current implementation (free or unlimited only)**:
- Paid subscriber: `plan_monthly_cap = null` → Unlimited
- Free user: `plan_monthly_cap = null` or `5` → 5 messages/month

**For future tiered plans**:
- Store cap in Stripe price metadata: `plan_monthly_cap = "50"`
- Webhook reads metadata and sets in DynamoDB
- SMS handler enforces the cap

**SMS Handler Logic (no changes needed)**:
```python
if isSubscribed == True:
    return unlimited (limit = None)
elif plan_monthly_cap is not None:
    return plan_monthly_cap
else:
    return FREE_MONTHLY_LIMIT (5)
```

This design means:
- ✅ No changes to SMS handler needed
- ✅ All logic controlled by DynamoDB fields
- ✅ Webhook sets appropriate cap on subscription changes
- ✅ Future-proof for tiered plans

---

**Document Version**: 1.0  
**Last Updated**: December 22, 2025  
**Integration Point**: Stripe webhooks → DynamoDB → SMS handler

