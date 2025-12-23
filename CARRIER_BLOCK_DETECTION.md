# Carrier Block Detection - Implementation Summary

## Problem Solved

When users text STOP to their carrier (AT&T/Verizon/T-Mobile), the carrier blocks the number before the message reaches Twilio. This means:
- ❌ Your backend STOP handler never runs
- ❌ Stripe subscription not canceled
- ❌ User might still get billed
- ❌ Database doesn't know user opted out

## Solution Implemented

**Proactive Detection**: When Twilio tries to send a message to a carrier-blocked number, it returns error code `21610`. We now detect this and automatically trigger the same cancellation logic as if they texted STOP to your webhook.

## What Was Changed

### File: `/lambdas/sms/helpers.py`

#### 1. Added Imports
```python
from twilio.base.exceptions import TwilioRestException
import logging
```

#### 2. Enhanced `send_message()` Function
- Now catches `TwilioRestException`
- Detects error code `21610` (unsubscribed recipient)
- Calls `_mark_carrier_opted_out()` to handle it

#### 3. New Function: `_mark_carrier_opted_out(phone_number)`
When carrier block detected:
1. Finds user by phone number in DynamoDB
2. Marks user as opted out:
   - `optedOut = true`
   - `optedOutAt = timestamp`
3. If user has active Stripe subscription:
   - Cancels subscription via Stripe API
   - Updates database (same as STOP handler)
   - Reverts to free plan

## How It Works

```
Your system tries to send SMS
    ↓
Twilio: "Error 21610 - User unsubscribed"
    ↓
We detect: "User texted STOP to carrier"
    ↓
Trigger same logic as STOP handler:
  - Mark opted out
  - Cancel Stripe subscription
  - Update to free plan
    ↓
Done ✓
```

## When This Triggers

1. **User texts STOP to carrier** (not to your webhook)
2. **Carrier blocks number** at network level
3. **Next time you try to send SMS** to that number:
   - Twilio returns error 21610
   - We detect it and process cancellation
   - User is marked as opted out
   - Subscription canceled (if exists)

## What You Need to Do

### 1. Check Twilio Configuration (Immediate)

Go to Twilio Console and check if your STOP message reached them:
- https://console.twilio.com/us1/monitor/logs/messaging
- Look for messages from your phone number
- If you don't see your STOP message → Carrier blocked it before reaching Twilio

### 2. Deploy Updated Code (This Week)

```bash
cd /Users/christopher.messer/PycharmProjects/versiful-backend/terraform
./scripts/tf-env.sh dev apply
```

This updates the SMS Lambda with carrier block detection.

### 3. Test the Fix

#### Option A: Unblock Your Number First
Text **"START"** to 833-681-1158 to remove carrier block, then test STOP again.

#### Option B: Test Carrier Block Detection
1. Leave your number blocked
2. Have someone else text your service
3. Try to reply to them (or send them a notification)
4. System sends message
5. **If your number is blocked**, Twilio returns 21610
6. **But this doesn't help with testing** since you need an actual blocked number

#### Option C: Test with Different Phone
Use a different phone number to test the full STOP flow.

### 4. Monitor Logs

After deployment, watch for these log messages:

```
# Carrier block detected
"Carrier block detected for +1##########  (Error 21610). User texted STOP to carrier."

# Opt-out recorded
"Marking +1########## as opted out due to carrier block"
"User user-id marked as opted out due to carrier block"

# Subscription canceled
"Canceling subscription for carrier-blocked user user-id"
"Subscription canceled for user user-id"
```

## Two Layers of Protection

Your system now has **defense in depth**:

### Layer 1: Webhook STOP Handler (Existing)
- If message reaches your webhook
- User texts STOP/UNSUBSCRIBE/CANCEL/etc.
- Immediate processing

### Layer 2: Carrier Block Detection (New)
- If carrier blocks STOP before reaching webhook
- Detected on next message attempt
- Deferred processing but still automatic

## Twilio Error Codes Reference

| Code | Meaning | Our Action |
|------|---------|------------|
| 21610 | Unsubscribed recipient | Mark opted out + cancel subscription |
| 21408 | Permission to send denied | Log error (different issue) |
| 21211 | Invalid phone number | Log error (bad number) |
| 30007 | Message delivery failed | Log error (network issue) |

Currently only handling 21610 (most important).

## Important Notes

### ⏱️ Timing Difference
- **Webhook STOP**: Instant cancellation
- **Carrier block detection**: Triggered on next message attempt (could be hours/days later)

### 📧 No Confirmation SMS
When carrier block is detected:
- We DON'T send confirmation SMS (number is blocked!)
- Cancellation happens silently from user's perspective
- They already got carrier's "You're unsubscribed" message

### 💰 Billing Window
If user texts STOP to carrier and we don't detect it immediately:
- They might get one more bill cycle
- Detection happens when we try to message them next
- This is unavoidable with carrier-level blocking

### 🔄 Best Practice
Configure Twilio to forward STOPs to webhook (see FIX_CARRIER_STOP_BLOCKING.md) to avoid this delay.

## Testing Checklist

After deployment:

- [ ] Deploy updated Lambda
- [ ] Check CloudWatch logs work
- [ ] Simulate carrier block (or wait for real one)
- [ ] Verify user marked opted out in DynamoDB
- [ ] Verify subscription canceled in Stripe
- [ ] Verify no more messages sent to that number
- [ ] Check error handling (non-21610 errors still logged)

## Benefits

✅ **Automatic**: No manual intervention needed  
✅ **Comprehensive**: Catches carrier-level blocks  
✅ **Compliant**: User's STOP intent is honored  
✅ **Prevents Billing**: Subscription canceled automatically  
✅ **Database Sync**: DynamoDB reflects opt-out status  
✅ **Graceful**: Doesn't break message sending to other users  

## Limitations

⚠️ **Not Instant**: Only triggered when we try to message blocked user  
⚠️ **No Confirmation**: Can't send confirmation to blocked number  
⚠️ **Requires Attempt**: User must be "active" enough to receive messages  

## Combined Strategy

**Best approach** (recommended):

1. ✅ Configure Twilio Advanced Opt-Out to forward STOPs (prevents carrier blocking)
2. ✅ Keep webhook STOP handler (processes forwarded STOPs)
3. ✅ Keep carrier block detection (catches any that slip through)

This gives you **maximum coverage**.

---

## Files Modified

- ✅ `/lambdas/sms/helpers.py`
  - Enhanced `send_message()` with error detection
  - Added `_mark_carrier_opted_out()` function
  - Added Twilio exception handling

## Dependencies

All already present:
- ✅ `twilio` SDK
- ✅ `boto3` for DynamoDB
- ✅ `stripe` SDK
- ✅ Secrets Manager access

## Next Steps

1. **Immediate**: Check Twilio logs to confirm carrier blocked your STOP
2. **Short-term**: Deploy this code to detect future carrier blocks
3. **Long-term**: Configure Twilio Advanced Opt-Out to prevent carrier blocks

You now have **two ways** to handle STOP: webhook and carrier block detection! 🎉

