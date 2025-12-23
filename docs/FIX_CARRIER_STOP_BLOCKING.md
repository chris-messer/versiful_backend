# Fix Carrier-Blocked STOP Messages

## Problem
When you text STOP, your carrier (AT&T/Verizon/T-Mobile) intercepts it and blocks the number at the network level. The message never reaches Twilio or your backend.

## Why This Happens
Major carriers have built-in STOP keyword filtering. When they detect STOP, they:
1. Block the number from sending you more messages
2. Send you a confirmation ("Texts from this number will be blocked")
3. **Never forward the STOP message** to the destination

This is actually **good** (proves carriers are compliant), but it means your backend cancellation logic never runs.

## The Solution: Configure Twilio Properly

### Step 1: Check if Message Reached Twilio

1. Login to Twilio Console: https://console.twilio.com
2. Go to **Monitor → Logs → Messaging**
3. Filter by date/time and your phone number
4. Look for the STOP message

**If found**: Issue is webhook configuration (see Step 3)  
**If NOT found**: Issue is carrier blocking (see Step 2)

### Step 2: Disable Carrier-Level Filtering (Advanced Opt-Out)

#### For Toll-Free Numbers (833-681-1158):

1. **Twilio Console → Phone Numbers → Manage → Active Numbers**
2. Click your toll-free number **(833-681-1158)**
3. Scroll to **Messaging Configuration**
4. Under **"A MESSAGE COMES IN"**:
   - Make sure webhook URL is set correctly
   - Should point to your SMS handler Lambda

5. **Look for "Advanced Opt-Out" or "Opt-Out Management"** (may be in Settings)
6. **Change from "Automatic" to "Custom" or "Webhook-based"**
   - This tells Twilio: "Forward STOP messages to my webhook, don't handle them"

#### Alternative: Use Messaging Service

If you can't find Advanced Opt-Out for toll-free:

1. **Create a Messaging Service**:
   - Twilio Console → Messaging → Services → Create new service
   
2. **Configure the service**:
   - Add your toll-free number to the service
   - Set "Opt-Out Management" to **"Advanced Opt-Out: Webhook-based"**
   - Configure webhook to point to your SMS handler

3. **Update your code** to send from Messaging Service SID instead of phone number

### Step 3: Verify Webhook Configuration

Your webhook URL should be:
```
https://api.versiful.io/sms
```

Or for dev:
```
https://api.dev.versiful.io/sms
```

In Twilio Console, verify:
- Phone number messaging webhook points to correct URL
- HTTP POST method
- Returns 200 OK

### Step 4: Test Again

After configuration:

1. **Remove the carrier block** (depends on carrier):
   - Text **"START"** or **"UNSTOP"** to 833-681-1158
   - Or wait 30 days (carrier blocks are usually temporary)
   - Or contact carrier support

2. **Test from a different phone** (or use Twilio's test number)

3. **Send STOP** and check:
   - Twilio logs show message received
   - CloudWatch logs show your handler processed it
   - DynamoDB shows `optedOut = true`
   - You receive confirmation SMS

## Alternative Solution: Accept Carrier-Level STOP

Some argue this is actually **better** for compliance:

### Pros of Carrier-Level STOP
- ✅ **Instant blocking** - Can't accidentally send more messages
- ✅ **Carrier enforced** - Even if your system fails, user is protected
- ✅ **Meets legal requirements** - TCPA compliance achieved
- ✅ **Industry standard** - Many SMS services work this way

### Cons
- ❌ Your backend doesn't know user opted out
- ❌ Stripe subscription not automatically canceled
- ❌ User might still get billed

### Hybrid Approach (Recommended)

**Accept both**:
1. Keep your backend STOP handler (for users who reach it)
2. Set up **manual monitoring** for carrier-blocked users:
   - Twilio can notify you when carrier blocks a number
   - You manually cancel their subscription
3. Or **proactive detection**:
   - Before sending SMS, check Twilio's blocklist
   - If blocked, mark user as opted out in your DB

## Implementation: Check Twilio Blocklist Before Sending

Add this to your `send_message()` function:

```python
def send_message(phone_number: str, message: str):
    """Send SMS and check if number is blocked"""
    try:
        client = get_twilio_client()
        
        # Send message
        twilio_message = client.messages.create(
            from_=VERSIFUL_PHONE,
            body=message,
            to=phone_number
        )
        
        logger.info(f"SMS sent: {twilio_message.sid}")
        return twilio_message.sid
        
    except TwilioRestException as e:
        # Error 21610: User has unsubscribed (carrier blocked)
        if e.code == 21610:
            logger.warning(f"User {phone_number} has unsubscribed via carrier")
            # Trigger backend STOP handler
            _handle_carrier_stop(phone_number)
        else:
            logger.error(f"Twilio error: {e.code} - {e.msg}")
        return None

def _handle_carrier_stop(phone_number: str):
    """Handle when carrier blocks number (user texted STOP to carrier)"""
    logger.info(f"Handling carrier-level STOP for {phone_number}")
    # Use same logic as _handle_stop_keyword()
    # Cancel subscription, update DB, etc.
    # Don't send confirmation SMS (carrier already did)
```

## Recommended Path Forward

### Immediate (Do This Now)
1. ✅ Check Twilio logs to confirm message was blocked
2. ✅ Configure Advanced Opt-Out if available
3. ✅ Test from different phone number

### Short Term (This Week)
1. Add Twilio error code 21610 handling to detect carrier blocks
2. Trigger backend cancellation when you try to message blocked user
3. Monitor Twilio delivery errors

### Long Term (Nice to Have)
1. Implement Messaging Service with proper opt-out handling
2. Set up alerts for delivery failures
3. Regular audit of blocked numbers vs database opt-out status

## Testing Without Blocking Your Number

**Use Twilio's Test Credentials**:
```bash
# In Twilio Console, get test phone numbers
# Send test STOP messages without affecting real users
```

**Or test with a friend's number** (with permission)

## Summary

Your STOP implementation is correct, but:
- **Carriers block STOP before it reaches you** (common issue)
- **Solution**: Configure Twilio Advanced Opt-Out to forward STOPs to webhook
- **Alternative**: Detect carrier blocks via error codes and handle retroactively
- **Best**: Both approaches (defense in depth)

The fact that the carrier blocked it proves the system is working - just not at the level you expected!

