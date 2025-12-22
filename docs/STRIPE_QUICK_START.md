# Stripe Integration Quick Start

## TL;DR

This guide provides the essential commands and steps to integrate Stripe payments. See `STRIPE_INTEGRATION_PLAN.md` for complete details.

## Prerequisites

1. **Stripe Account**: 
   - Test account already configured (keys in dev.tfvars)
   - Need production account keys for prod deployment

2. **Current Prices**:
   - Monthly: $9.99/month
   - Annual: $99.99/year

## Quick Setup Steps

### 1. Add Stripe Keys to All Environments

```bash
# Already done for dev ✓
# Add to staging.tfvars (same test keys as dev)
# Add to prod.tfvars (REAL production keys from Stripe dashboard)
```

### 2. Install Stripe CLI (for testing)

```bash
brew install stripe/stripe-cli/stripe
stripe login
```

### 3. Create Required Files

**New Lambda Directories**:
```
lambdas/subscription/
  - subscription_handler.py
  - requirements.txt
  
lambdas/stripe_webhook/
  - webhook_handler.py
  - requirements.txt
```

**New Terraform Files**:
```
terraform/modules/stripe/
  - main.tf
  - variables.tf
  - outputs.tf

terraform/modules/lambdas/
  - _subscription.tf
  - _stripe_webhook.tf
```

### 4. Deployment Commands

```bash
# Deploy to dev
cd /Users/christopher.messer/PycharmProjects/versiful-backend
./scripts/tf-env.sh dev plan
./scripts/tf-env.sh dev apply

# Test webhooks locally
stripe listen --forward-to https://api.dev.versiful.io/stripe/webhook

# Deploy to staging
./scripts/tf-env.sh staging plan
./scripts/tf-env.sh staging apply

# Deploy to production (CAREFULLY!)
./scripts/tf-env.sh prod plan
# Review plan thoroughly!
./scripts/tf-env.sh prod apply
```

## Key API Endpoints Created

- `POST /subscription/checkout` - Create Stripe checkout session (authenticated)
- `POST /subscription/portal` - Access customer portal (authenticated)
- `GET /subscription/prices` - Get Stripe price IDs (public)
- `POST /stripe/webhook` - Receive Stripe events (no auth, signature verified)

## Database Fields Added

Users table will have these new fields (DynamoDB is schemaless, no migration needed):
- `stripeCustomerId` - Stripe customer ID
- `stripeSubscriptionId` - Stripe subscription ID  
- `subscriptionStatus` - active, past_due, canceled, etc.
- `currentPeriodEnd` - Timestamp when current period ends
- `cancelAtPeriodEnd` - Boolean, true if cancellation scheduled
- `plan_monthly_cap` - Number or null; null = unlimited SMS (paid), 5 = free tier

## Frontend Changes

1. Install Stripe.js: `npm install @stripe/stripe-js`
2. Update `Subscription.jsx` to call `/subscription/checkout`
3. Update `Settings.jsx` with "Manage Subscription" button
4. Add Stripe publishable key to env vars

## Testing Checklist

### Test Cards (in dev/staging)
- **Success**: 4242 4242 4242 4242
- **Decline**: 4000 0000 0000 0002
- **Requires Auth**: 4000 0025 0000 3155

### Scenarios to Test
- ✅ Subscribe to monthly plan
- ✅ Subscribe to annual plan
- ✅ Cancel subscription (end of period)
- ✅ Reactivate canceled subscription
- ✅ Change plan (monthly ↔ annual)
- ✅ Payment failure (card declined)
- ✅ Access customer portal
- ✅ Webhook received and processed

## Webhook Events We Handle

| Event | What It Means | Action |
|-------|---------------|--------|
| `checkout.session.completed` | User completed checkout | Create subscription in DB |
| `customer.subscription.created` | Subscription activated | Mark user as subscribed |
| `customer.subscription.updated` | Plan changed or cancellation scheduled | Update subscription details |
| `customer.subscription.deleted` | Subscription ended | Revert to free plan |
| `invoice.payment_succeeded` | Renewal payment successful | Update period end date |
| `invoice.payment_failed` | Payment failed | Mark as past_due, notify user |

## Edge Cases Handled

1. **Payment Failure**: User remains subscribed during Stripe's retry period (3-4 attempts over ~2 weeks)
2. **Cancellation**: User keeps access until end of billing period
3. **Reactivation**: User can undo cancellation before period ends
4. **Plan Changes**: Prorated automatically by Stripe
5. **Duplicate Webhooks**: Idempotent updates prevent issues

## Environment Strategy

- **Dev**: Stripe test mode, test API keys
- **Staging**: Stripe test mode, test API keys (same as dev)
- **Prod**: Stripe live mode, REAL API keys

## Monitoring

### CloudWatch
- Monitor Lambda errors on subscription and webhook handlers
- Set up alarms for error rates > 1%

### Stripe Dashboard
- Check webhook delivery success (should be >99%)
- Monitor failed payments
- Track subscription metrics

## Rollback Plan

If something breaks in production:
1. Revert Lambda functions to previous versions
2. Frontend shows "Checkout temporarily unavailable"
3. Existing subscriptions continue working (webhooks still process)
4. Fix in dev, test in staging, redeploy to prod

## Cost Analysis

### Stripe Fees
- **Monthly**: $9.99 → $0.59 fee → **$9.40 net**
- **Annual**: $99.99 → $3.20 fee → **$96.79 net**

### AWS (per 1000 users/month)
- Lambda: ~$0.20
- DynamoDB: Included in existing
- API Gateway: ~$0.10

## Support Scenarios

### "My payment failed"
→ Direct to Stripe Customer Portal to update card

### "How do I cancel?"
→ Settings → "Manage Subscription" → Stripe portal

### "I was charged but don't have access"
→ Check webhook logs, verify `isSubscribed` in DynamoDB, run sync script

### "I want to change my plan"
→ Stripe Customer Portal → Switch plan (prorated automatically)

## Important URLs

- **Stripe Dashboard**: https://dashboard.stripe.com
- **Stripe Docs**: https://stripe.com/docs/billing
- **Terraform Provider**: https://registry.terraform.io/providers/lukasaron/stripe
- **Test Cards**: https://stripe.com/docs/testing

## Next Actions

1. ✅ Read full plan: `STRIPE_INTEGRATION_PLAN.md`
2. 🔲 Get production Stripe keys
3. 🔲 Create Lambda files (subscription + webhook)
4. 🔲 Create Terraform Stripe module
5. 🔲 Update Terraform Lambda configs
6. 🔲 Deploy to dev and test
7. 🔲 Deploy to staging and test
8. 🔲 Deploy to prod (with real keys)
9. 🔲 Monitor for 24 hours

## Questions?

Refer to the full plan document: `docs/STRIPE_INTEGRATION_PLAN.md`

