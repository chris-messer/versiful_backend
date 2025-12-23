# SMS Notifications - Quick Deployment Guide

## What Was Added

Three SMS notifications for user lifecycle events:
1. Welcome SMS when registering phone number
2. Subscription confirmation when user subscribes
3. Cancellation notice when subscription ends

## Files Modified

### New Files
- `lambdas/shared/sms_notifications.py` - SMS notification functions

### Modified Files
- `lambdas/users/helpers.py` - Added welcome SMS on phone registration
- `lambdas/stripe_webhook/webhook_handler.py` - Added subscription lifecycle SMS
- `terraform/modules/lambdas/main.tf` - Updated layer build to include shared modules
- `terraform/modules/lambdas/_users.tf` - Added shared_dependencies layer
- `docs/context.md` - Documented SMS notifications
- `docs/SMS_NOTIFICATIONS.md` - Full documentation

## Deployment Steps

### 1. Verify Twilio Credentials
Ensure these keys exist in AWS Secrets Manager secret `{env}-versiful_secrets`:
```json
{
  "twilio_account_sid": "AC...",
  "twilio_auth": "..."
}
```

### 2. Deploy to Dev
```bash
cd /Users/christopher.messer/PycharmProjects/versiful-backend/terraform
./scripts/tf-env.sh dev plan
./scripts/tf-env.sh dev apply
```

This will:
- Rebuild shared_dependencies layer with Twilio + shared modules
- Update users_function to use the layer
- Deploy stripe_webhook_function changes

### 3. Test Welcome SMS
```bash
# Get an ID token (login via frontend or auth API)
ID_TOKEN="your_token_here"

# Register a phone number (use your real number for testing)
curl -X PUT https://api.dev.versiful.io/users \
  -H "Authorization: Bearer $ID_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"phoneNumber": "+15551234567", "isRegistered": true}'

# Check CloudWatch logs
aws logs tail /aws/lambda/dev-versiful-users_function --follow
```

Expected: Welcome SMS received within seconds

### 4. Test Subscription SMS
1. Complete a Stripe checkout in test mode
2. Checkout completion triggers webhook
3. Check CloudWatch logs: `/aws/lambda/dev-versiful-stripe-webhook`

### 5. Test Cancellation SMS
1. Cancel a test subscription via Stripe dashboard
2. Subscription deletion triggers webhook
3. Check logs for cancellation SMS

### 6. Deploy to Staging/Prod
```bash
# Staging
./scripts/tf-env.sh staging plan
./scripts/tf-env.sh staging apply

# Production
./scripts/tf-env.sh prod plan
./scripts/tf-env.sh prod apply
```

## Verification Checklist

- [ ] Shared layer includes `sms_notifications.py` and Twilio SDK
- [ ] Users Lambda has layer attached
- [ ] Stripe Webhook Lambda has layer attached
- [ ] Welcome SMS sent on phone registration
- [ ] Subscription SMS sent on checkout completion
- [ ] Cancellation SMS sent on subscription deletion
- [ ] CloudWatch logs show "SMS sent" confirmations
- [ ] Twilio dashboard shows delivered messages
- [ ] No errors in Lambda logs

## Monitoring

**CloudWatch Log Groups**:
```bash
# Users Lambda
aws logs tail /aws/lambda/dev-versiful-users_function --follow

# Stripe Webhook Lambda
aws logs tail /aws/lambda/dev-versiful-stripe-webhook --follow
```

**Key Log Messages**:
```
Sending welcome SMS to +1##########
SMS sent to +1##########: SM...
Sending subscription confirmation SMS to +1##########
Sending cancellation SMS to +1##########
```

**Error Messages**:
```
Failed to send welcome SMS to +1##########: [error]
Failed to send subscription confirmation SMS: [error]
Failed to send cancellation SMS: [error]
```

## Rollback Plan

If issues arise:

### Quick Disable (no redeploy needed)
Comment out SMS calls and redeploy:

**In `lambdas/users/helpers.py`**:
```python
# Temporarily disable
# if is_new_phone_registration:
#     send_welcome_sms(phone_number)
```

**In `lambdas/stripe_webhook/webhook_handler.py`**:
```python
# Temporarily disable
# send_subscription_confirmation_sms(phone_number)
# send_cancellation_sms(phone_number)
```

Then redeploy:
```bash
./scripts/tf-env.sh dev apply
```

### Full Rollback
```bash
git revert <commit_hash>
./scripts/tf-env.sh dev apply
```

## Troubleshooting

### SMS Not Received

1. **Check Lambda logs** for "SMS sent" message
2. **Check Twilio dashboard** for delivery status
3. **Verify phone number format**: Must be +1##########
4. **Check Twilio balance**: Ensure account has funds

### Import Errors

```
ImportError: No module named 'sms_notifications'
```

**Fix**:
1. Verify layer is attached: `aws lambda get-function --function-name dev-versiful-users_function`
2. Check layer contents: Unzip `lambdas/layer/layer.zip` and verify `python/sms_notifications.py` exists
3. Rebuild layer: `./scripts/tf-env.sh dev apply`

### Secrets Not Found

```
Failed to send SMS: Twilio credentials not found
```

**Fix**:
1. Check secret exists: `aws secretsmanager get-secret-value --secret-id dev-versiful_secrets`
2. Verify keys: `twilio_account_sid`, `twilio_auth`
3. Check Lambda IAM role has `secretsmanager:GetSecretValue` permission

## Cost Impact

**Per Environment**:
- ~$1-2/month at low volume (100-200 SMS/month)
- Scales linearly with user growth
- No additional AWS Lambda costs (minimal execution time)

## Support

- **Full Documentation**: `docs/SMS_NOTIFICATIONS.md`
- **Twilio Dashboard**: https://console.twilio.com/
- **CloudWatch Logs**: AWS Console → Lambda → Function → Monitor → Logs

