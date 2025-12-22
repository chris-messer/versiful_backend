# Stripe Integration Bug Fixes

## Date: December 22, 2025

## Summary

This document details critical bugs found and fixed in the Stripe webhook integration, along with comprehensive tests that would have caught these issues earlier.

---

## Bug #1: Webhook Handler Using `None` Instead of `-1` for Unlimited

### Problem
The webhook handler was setting `plan_monthly_cap = None` for unlimited subscriptions, but the SMS handler's logic expects `-1` to represent unlimited.

### Location
`lambdas/stripe_webhook/webhook_handler.py` - Multiple functions

### What Happened
When a user subscribed, the webhook would update DynamoDB with:
```python
":cap": None  # ❌ Wrong - DynamoDB doesn't handle Python None well
```

### Impact
- Users' subscriptions were created in Stripe ✅
- But `plan_monthly_cap` remained `null` in DynamoDB ❌
- Users didn't get unlimited messages ❌

### Fix
Changed all instances to use `-1`:
```python
":cap": -1  # ✅ Correct - explicit unlimited value
```

### Files Changed
- `lambdas/stripe_webhook/webhook_handler.py` (lines 137, 189, 273, 315)

---

## Bug #2: `current_period_end` Not Cast to Integer

### Problem
Stripe's `subscription["current_period_end"]` is a Unix timestamp (int), but wasn't being explicitly cast to `int`, causing DynamoDB update errors.

### Error Message
```
Error processing webhook: 'current_period_end'
":period_end": subscription["current_period_end"],
```

### Location
`lambdas/stripe_webhook/webhook_handler.py` - All subscription update functions

### What Happened
When the webhook tried to write to DynamoDB:
```python
":period_end": subscription["current_period_end"]  # ❌ Type ambiguity
```

DynamoDB threw a validation error because the type wasn't explicitly an integer.

### Impact
- All webhook events failed to process ❌
- Users subscribed in Stripe but weren't marked as subscribed in DynamoDB ❌
- `isSubscribed` remained `false` ❌
- Users were limited to 5 messages despite paying ❌

### Fix
Explicitly cast to integer:
```python
":period_end": int(subscription["current_period_end"])  # ✅ Explicit type
```

### Files Changed
- `lambdas/stripe_webhook/webhook_handler.py` (lines 139, 190, 316)

---

## Bug #3: SMS Handler Not Checking for `-1` Before Calling `consume_message_if_allowed`

### Problem
The SMS handler would pass `plan_monthly_cap = -1` directly to `consume_message_if_allowed`, which uses the condition `plan_messages_sent < limit`. Since messages start at 0 or higher, `0 < -1` is always false, blocking ALL messages.

### Location
`lambdas/sms/sms_handler.py` - `_evaluate_usage` function (lines 104-109)

### What Happened
```python
if user_profile and user_profile.get("plan_monthly_cap") is not None:
    limit = int(user_profile["plan_monthly_cap"])  # limit = -1
    # ...
    updated = consume_message_if_allowed(phone_number, limit, ...)  # ❌ Passes -1!
```

The `consume_message_if_allowed` function checks:
```python
ConditionExpression="plan_messages_sent < :limit"  # 0 < -1 = False!
```

### Impact
If a user had `isSubscribed=false` but `plan_monthly_cap=-1`, they would be blocked from ALL messages, not granted unlimited.

### Fix
Added explicit check for `-1` before calling `consume_message_if_allowed`:
```python
if user_profile and user_profile.get("plan_monthly_cap") is not None:
    limit = int(user_profile["plan_monthly_cap"])
    # NEW: Check for unlimited before passing to consume function
    if limit == -1:
        return {
            "allowed": True,
            "limit": None,
            "usage": usage,
            "user_profile": user_profile,
            "reason": "unlimited_cap",
        }
else:
    limit = FREE_MONTHLY_LIMIT

updated = consume_message_if_allowed(phone_number, limit, ...)  # Now never gets -1
```

### Files Changed
- `lambdas/sms/sms_handler.py` (lines 104-120)

---

## Tests That Would Have Caught These Bugs

### Webhook Handler Tests
**File**: `lambdas/stripe_webhook/test_webhook_handler.py`

#### Test 1: `test_checkout_completed_monthly_subscription`
✅ **Catches Bug #1**: Asserts that `plan_monthly_cap` is `-1` (int), not `None`
✅ **Catches Bug #2**: Asserts that `current_period_end` is an `int`

```python
# Check that plan_monthly_cap is -1 (not None!)
assert call_args['ExpressionAttributeValues'][':cap'] == -1, \
    "plan_monthly_cap must be -1 (int) for unlimited, not None"

# Check that currentPeriodEnd is an integer
period_end = call_args['ExpressionAttributeValues'][':period_end']
assert isinstance(period_end, int), \
    f"current_period_end must be an int, got {type(period_end)}"
```

#### Test 2: `test_subscription_updated_active`
✅ **Catches Bug #1**: Verifies updated subscriptions maintain `-1` cap
✅ **Catches Bug #2**: Verifies period_end is always an int

#### Test 3: `test_payment_succeeded_maintains_unlimited`
✅ **Catches Bug #1**: Ensures payment renewals maintain `-1` cap

### SMS Handler Tests
**File**: `lambdas/sms/test_sms_handler.py`

#### Test 1: `test_plan_monthly_cap_minus_one_grants_unlimited`
✅ **Catches Bug #3**: Verifies that `plan_monthly_cap=-1` grants unlimited access

```python
mock_get_user.return_value = {
    'userId': 'user-123',
    'isSubscribed': False,
    'plan_monthly_cap': -1  # Critical case
}

result = sms_handler._evaluate_usage('+15555551234')

assert result['allowed'] is True, \
    "plan_monthly_cap=-1 must grant unlimited access"
assert result['limit'] is None, \
    "limit must be None (unlimited), not -1"
```

#### Test 2: `test_never_pass_negative_one_to_consume`
✅ **Catches Bug #3**: Ensures `-1` is never passed to `consume_message_if_allowed`

```python
mock_get_user.return_value = {
    'plan_monthly_cap': -1
}

result = sms_handler._evaluate_usage('+15555551234')

# consume_message_if_allowed should NEVER be called with -1
mock_consume.assert_not_called()
assert result['allowed'] is True
```

---

## Test Results

### Webhook Handler Tests
```bash
$ cd lambdas/stripe_webhook
$ python -m pytest test_webhook_handler.py -v
============================== 12 passed in 0.23s ==============================
```

✅ All 12 tests pass, including:
- Signature verification
- Checkout completion (monthly and annual)
- Subscription updates
- Payment success/failure
- Subscription deletion

### SMS Handler Tests
```bash
$ cd lambdas/sms
$ python -m pytest test_sms_handler.py -v
============================== 6 passed in 0.28s ==============================
```

✅ All 6 tests pass, including:
- Unlimited via `isSubscribed`
- Unlimited via `plan_monthly_cap=-1`
- Custom cap enforcement
- Free tier defaults
- Never passing `-1` to consume function

---

## Deployment Status

All fixes have been deployed to `dev` environment:

1. ✅ Webhook handler updated and deployed
2. ✅ SMS handler updated and deployed
3. ✅ Manual DynamoDB update performed for existing test user
4. ✅ User verified with correct values:
   - `isSubscribed: true`
   - `plan_monthly_cap: -1`
   - `plan: "monthly"`
   - `subscriptionStatus: "active"`

---

## How to Run Tests

### Prerequisites
```bash
cd /Users/christopher.messer/PycharmProjects/versiful-backend
```

### Run Webhook Tests
```bash
cd lambdas/stripe_webhook
python -m pytest test_webhook_handler.py -v
```

### Run SMS Handler Tests
```bash
cd lambdas/sms
python -m pytest test_sms_handler.py -v
```

### Run All Tests
```bash
cd tests
python -m pytest ../lambdas/stripe_webhook/test_webhook_handler.py \
                 ../lambdas/sms/test_sms_handler.py -v
```

---

## Prevention Checklist

To prevent similar bugs in the future:

- [x] ✅ Unit tests for webhook handlers
- [x] ✅ Unit tests for SMS cap logic
- [x] ✅ Tests verify exact data types (int vs None)
- [x] ✅ Tests verify specific values (-1 vs None)
- [x] ✅ Tests cover edge cases (unlimited cap scenarios)
- [ ] ⏳ Integration tests with real Stripe test events
- [ ] ⏳ E2E tests for complete subscription flow

---

## Lessons Learned

1. **Be Explicit About Data Types**: Always cast values like timestamps to their expected type
2. **Avoid `None` for Semantic Values**: Use `-1` for "unlimited" instead of `None` 
3. **Test Edge Cases**: Test special values like `-1`, `0`, `null` explicitly
4. **Mock Real Webhook Events**: Use actual Stripe webhook structure in tests
5. **Verify Database Updates**: Don't just test that functions run, verify the exact values written to DynamoDB

---

## Related Documentation

- [STRIPE_INTEGRATION_PLAN.md](./STRIPE_INTEGRATION_PLAN.md) - Main integration plan
- [STRIPE_PLAN_CAPS_INTEGRATION.md](./STRIPE_PLAN_CAPS_INTEGRATION.md) - Plan caps documentation
- [STRIPE_TESTING.md](./STRIPE_TESTING.md) - Testing guide

---

**Document Version**: 1.0  
**Last Updated**: December 22, 2025  
**Status**: ✅ All bugs fixed and deployed to dev

