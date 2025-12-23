# SMS Notifications

This document describes the SMS notification system that sends automated messages to users at key lifecycle events.

## Overview

Versiful sends SMS notifications via Twilio at three critical user journey moments:

1. **Welcome Message** - When a user first registers their phone number
2. **Subscription Confirmation** - When a user subscribes to a paid plan
3. **Cancellation Notice** - When a user's subscription is canceled

## Architecture

### Shared Module
- **Location**: `lambdas/shared/sms_notifications.py`
- **Purpose**: Centralized SMS notification functions used across multiple Lambdas
- **Deployment**: Included in `shared_dependencies` Lambda layer via Terraform
- **Dependencies**: Twilio SDK (already in layer requirements)

### Integration Points

#### 1. Users Lambda (`lambdas/users/helpers.py`)
**Trigger**: Phone number registration (first time only)
- Detects when a user sets their phone number for the first time
- Sends welcome SMS with:
  - Greeting
  - Free tier information (5 messages/month)
  - Link to subscribe for unlimited
  - Encouragement to save the number
- SMS failures are logged but don't fail the request

```python
# In update_user_settings()
if is_new_phone_registration:
    send_welcome_sms(phone_number)
```

#### 2. Stripe Webhook Lambda (`lambdas/stripe_webhook/webhook_handler.py`)

**Trigger A**: `checkout.session.completed` event
- Sends subscription confirmation SMS when user completes checkout
- Thanks user and confirms unlimited access
- Only sends if user has registered phone number

```python
# In handle_checkout_completed()
send_subscription_confirmation_sms(phone_number)
```

**Trigger B**: `customer.subscription.deleted` event
- Sends cancellation notice when subscription ends
- Informs user they're back on free tier (5 messages/month)
- Offers link to resubscribe
- Only sends if user has registered phone number

```python
# In handle_subscription_deleted()
send_cancellation_sms(phone_number)
```

## Message Content

### Welcome Message
```
Welcome to Versiful! 🙏

You have 5 free messages per month. Text us anytime for biblical guidance and wisdom.

Want unlimited messages? Subscribe at https://versiful.io

Save this number to your contacts for easy access!
```

### Subscription Confirmation
```
Thank you for subscribing to Versiful! 🎉

You now have unlimited messages. Text us anytime for guidance, wisdom, and comfort from Scripture.

We're honored to walk with you on your spiritual journey.
```

### Cancellation Notice
```
We're sorry to see you go! 😢

Your subscription has been canceled and you've been moved back to our free plan with 5 messages per month.

You're always welcome back. Text us anytime or resubscribe at https://versiful.io

Blessings on your journey! 🙏
```

## Implementation Details

### SMS Sending
- **Provider**: Twilio
- **From Number**: +1-833-681-1158 (VERSIFUL_PHONE constant)
- **Format**: Plain text SMS
- **Error Handling**: Errors are logged but don't fail the primary operation

### Credentials
- Stored in AWS Secrets Manager
- Keys: `twilio_account_sid`, `twilio_auth`
- Retrieved via `secrets_helper.get_secrets()`

### Lambda Layers
The `shared_dependencies` layer includes:
- Twilio SDK
- `secrets_helper.py`
- `sms_notifications.py`

Used by:
- `users_function`
- `stripe_webhook_function`
- `subscription_function`

## Terraform Configuration

### Layer Build Process
Location: `terraform/modules/lambdas/main.tf`

```hcl
resource "null_resource" "package_layer" {
  provisioner "local-exec" {
    command = <<EOT
      cd ${path.module}/../../../lambdas/layer && \
      rm -rf python && \
      mkdir python && \
      pip install -r requirements.txt -t python && \
      cp ${path.module}/../../../lambdas/shared/*.py python/ && \
      zip -r layer.zip python
    EOT
  }

  triggers = {
    requirements = filemd5("${path.module}/../../../lambdas/layer/requirements.txt")
    shared_secrets = filemd5("${path.module}/../../../lambdas/shared/secrets_helper.py")
    shared_sms = filemd5("${path.module}/../../../lambdas/shared/sms_notifications.py")
  }
}
```

The layer automatically rebuilds when:
- `requirements.txt` changes
- `secrets_helper.py` changes
- `sms_notifications.py` changes

### Lambda Configuration Updates

**Users Lambda** (`_users.tf`):
```hcl
layers = [aws_lambda_layer_version.shared_dependencies.arn]
```

**Stripe Webhook Lambda** (`_stripe_webhook.tf`):
```hcl
layers = [aws_lambda_layer_version.shared_dependencies.arn]
```

## Testing

### Local Testing
1. Ensure Twilio credentials are in Secrets Manager for the environment
2. Test each trigger independently:

**Test Welcome SMS**:
```bash
# Register a phone number via PUT /users
curl -X PUT https://api.dev.versiful.io/users \
  -H "Authorization: Bearer $ID_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"phoneNumber": "+15551234567"}'
```

**Test Subscription SMS**:
```bash
# Complete a Stripe checkout in test mode
# Webhook will automatically fire
```

**Test Cancellation SMS**:
```bash
# Cancel a subscription via Stripe dashboard
# Or let a test subscription expire
```

### Monitoring

**CloudWatch Logs**:
- Users Lambda: `/aws/lambda/{env}-versiful-users_function`
- Stripe Webhook: `/aws/lambda/{env}-versiful-stripe-webhook`

**Log Messages to Look For**:
```
Sending welcome SMS to +1##########
SMS sent to +1##########: SM...
Failed to send SMS to +1##########: [error details]
```

### Twilio Dashboard
- View sent messages
- Check delivery status
- Monitor costs

## Error Handling

All SMS operations use try-except blocks to ensure:
1. Primary operations (user updates, webhook processing) succeed even if SMS fails
2. Errors are logged with full context
3. Webhooks return 200 (preventing Stripe retries for SMS-only failures)

Example:
```python
try:
    send_welcome_sms(phone_number)
except Exception as sms_error:
    # Log error but don't fail the request
    logger.error(f"Failed to send SMS: {str(sms_error)}")
```

## Future Enhancements

Potential improvements:
1. **vCard Attachments**: Include contact card in welcome SMS (requires MMS)
2. **Personalization**: Use user's name in messages
3. **Delivery Tracking**: Store SMS delivery status in DynamoDB
4. **Message Templates**: Externalize message content for easier updates
5. **Unsubscribe Link**: Add SMS opt-out mechanism
6. **Retry Logic**: Implement retries for failed SMS sends
7. **Rate Limiting**: Prevent duplicate messages within time window

## Deployment

### Prerequisites
- Twilio account with active phone number (+1-833-681-1158)
- Credentials in Secrets Manager: `{env}-versiful_secrets`
- Lambda execution role has Secrets Manager read permissions

### Deployment Steps
```bash
# 1. Deploy shared layer and Lambda functions
cd terraform
./scripts/tf-env.sh dev apply

# 2. Verify layer attachment
aws lambda get-function --function-name dev-versiful-users_function \
  | jq '.Configuration.Layers'

# 3. Test with a real phone number
# Register phone via frontend or API

# 4. Monitor logs
aws logs tail /aws/lambda/dev-versiful-users_function --follow
```

### Rollback
If SMS notifications cause issues:
1. Comment out `send_*_sms()` calls in handlers
2. Redeploy affected Lambdas
3. Investigate and fix
4. Restore SMS calls and redeploy

## Cost Considerations

**Twilio SMS Costs** (as of Dec 2024):
- Outbound SMS (US): ~$0.0079 per message
- Monthly cost estimate:
  - 100 new registrations: $0.79
  - 50 new subscriptions: $0.40
  - 10 cancellations: $0.08
  - **Total: ~$1.27/month** (low volume)

**AWS Costs**:
- Lambda execution: Minimal increase (<1ms per SMS call)
- Layer storage: ~10MB for Twilio SDK
- CloudWatch logs: Negligible

## Security

- Twilio credentials never exposed in logs or code
- Retrieved at runtime from Secrets Manager
- Phone numbers logged only at INFO level (not in production)
- SMS content doesn't include sensitive data

## Troubleshooting

**SMS not received**:
1. Check CloudWatch logs for "SMS sent" confirmation
2. Verify phone number format (+1##########)
3. Check Twilio dashboard for delivery status
4. Verify Twilio account balance

**Import errors**:
1. Ensure layer is attached to Lambda
2. Verify layer contents include `sms_notifications.py`
3. Check layer compatibility (Python 3.11)

**Secrets not found**:
1. Verify secret name: `{env}-versiful_secrets`
2. Check Lambda IAM role has `secretsmanager:GetSecretValue`
3. Confirm keys exist: `twilio_account_sid`, `twilio_auth`

## Contact

For Twilio account access or credentials:
- Check project documentation
- Contact project admin

