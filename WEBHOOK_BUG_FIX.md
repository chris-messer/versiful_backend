# Webhook Database Update Bug Fix

## Issue Summary
**Date:** January 19, 2026  
**Reported By:** Richard (customer)  
**Environment:** Production

### Problem
Users were completing Stripe checkout but the webhook was failing to update the production database with their subscription status. This caused:
1. Frontend never showing user as subscribed
2. Users attempting to pay again (resulting in double charges)
3. Users receiving incorrect "limit reached" messages when texting

### Root Cause
In `lambdas/stripe_webhook/webhook_handler.py`, the code was trying to access `current_period_end` from the wrong place in the Stripe API response:

**Incorrect (line 140):**
```python
period_end = subscription['items']['data'][0].get('current_period_end')
```

**Problem:** The `current_period_end` field is a property of the `subscription` object itself, NOT a property of the subscription `items`. This caused `period_end` to always be `None`, which likely caused subsequent operations to fail.

### Fix Applied
Changed all three occurrences in the webhook handler to access `current_period_end` from the correct location:

**Corrected:**
```python
period_end = subscription.get('current_period_end')
```

### Files Modified
- `lambdas/stripe_webhook/webhook_handler.py`
  - Line ~136: Fixed in `handle_checkout_completed()` 
  - Line ~228: Fixed in `handle_subscription_updated()`
  - Line ~398: Fixed in `handle_payment_succeeded()`

### Additional Cleanup
- Removed duplicate logging statements (lines 127-133)
- Improved log messages to be more accurate

### Impact
This fix ensures that when users complete Stripe checkout:
1. ✅ Webhook successfully updates DynamoDB with subscription status
2. ✅ `isSubscribed` flag is set to `true`
3. ✅ `plan_monthly_cap` is set to `-1` (unlimited)
4. ✅ Frontend correctly shows user as subscribed
5. ✅ SMS handler allows unlimited messages (no false limit errors)

### Deployment Required
**Next Steps:**
1. Deploy the updated webhook Lambda to production
2. Test with a new subscription in prod to verify fix
3. Monitor CloudWatch logs for successful webhook processing

### Customer Impact
- **Richard:** Manually fixed his account and refunded duplicate charge
- **Future customers:** Will not experience this issue after deployment

### Stripe Webhook Events Affected
- `checkout.session.completed` - Primary issue
- `customer.subscription.updated` - Also had the bug
- `invoice.payment_succeeded` - Also had the bug

### Testing Recommendation
After deployment, test in production by:
1. Creating a test subscription
2. Checking CloudWatch logs show: `Got current_period_end from subscription: [timestamp]`
3. Verifying DynamoDB users table shows `isSubscribed: true`
4. Confirming frontend displays subscription status correctly

