# Stripe Integration - Executive Summary

## Overview

This directory contains a complete plan for integrating Stripe subscription payments into Versiful using Terraform Infrastructure as Code (IaC).

## What You Asked For

✅ **Stripe payment integration** with monthly ($9.99) and annual ($99.99) plans  
✅ **Terraform deployment** using the Stripe provider for IaC  
✅ **Three environments**: dev/staging (test mode) and prod (live mode)  
✅ **Webhook handling** for subscription events (payment, cancellation, etc.)  
✅ **Edge case handling** including payment failures, cancellations, renewals  
✅ **DynamoDB integration** updating `isSubscribed` field  

## What I've Built For You

### 📚 Documentation (3 files)

1. **STRIPE_INTEGRATION_PLAN.md** (10,000+ words)
   - Complete technical implementation guide
   - All Lambda code with full logic
   - All Terraform configurations
   - Edge case handling for every scenario
   - Testing strategy and deployment plan

2. **STRIPE_QUICK_START.md** (Quick reference)
   - TL;DR version with essential commands
   - Checklist for implementation
   - Common support scenarios
   - Cost analysis

3. **STRIPE_ARCHITECTURE_DIAGRAMS.md** (Visual guide)
   - System architecture diagram
   - Payment flow sequences
   - Webhook event handling flows
   - State machine diagrams
   - Security flow visualization

## Current State of Your System

### ✅ Already Have
- DynamoDB table: `{env}-versiful-users` with fields including `isSubscribed`
- API Gateway (HTTP API v2) with JWT authorizer
- User Lambda handling profile CRUD
- Terraform infrastructure for dev/staging/prod
- Stripe test keys in `dev.tfvars`
- Frontend subscription page (currently mocking paid plans)

### 🔲 Need to Build
- **2 new Lambda functions** (subscription handler + webhook handler)
- **Stripe Terraform module** (products, prices, webhook endpoints)
- **API Gateway routes** for subscription and webhook
- **Frontend updates** to call Stripe Checkout
- **Secrets Manager** updates with Stripe keys

## Key Design Decisions

### 1. **Webhook-Driven Architecture**
- All subscription state changes flow through Stripe webhooks
- Ensures single source of truth (Stripe)
- Handles edge cases automatically (retries, failures, etc.)

### 2. **No PCI Compliance Needed**
- Using Stripe Checkout (hosted by Stripe)
- Card data never touches your servers
- Dramatically reduces security burden

### 3. **Idempotent Operations**
- All webhook handlers can be called multiple times safely
- DynamoDB updates use conditional expressions
- Prevents duplicate charges or status issues

### 4. **Environment Separation**
- Dev/Staging use Stripe test mode (same test keys)
- Prod uses Stripe live mode (real keys)
- Stripe creates separate products per environment

### 5. **Graceful Degradation**
- Payment failures don't immediately revoke access
- Stripe retries 3-4 times over ~2 weeks
- User marked as `past_due` but still subscribed
- Only after all retries fail → revert to free plan

## Database Schema Changes

### New Fields (No Migration Needed - DynamoDB is Schemaless)

```javascript
{
  // Existing fields
  userId: "google_123456",
  email: "user@example.com",
  isSubscribed: true,        // Quick boolean for access checks
  plan: "monthly",           // free | monthly | annual
  
  // NEW Stripe fields
  stripeCustomerId: "cus_ABC123",           // Stripe customer ID
  stripeSubscriptionId: "sub_XYZ789",       // Stripe subscription ID
  subscriptionStatus: "active",             // active | past_due | canceled | unpaid
  currentPeriodEnd: 1738368000,             // Unix timestamp
  cancelAtPeriodEnd: false,                 // Boolean
  plan_monthly_cap: null,                   // Number or null; null = unlimited SMS
  updatedAt: "2025-12-22T10:00:00Z"        // ISO timestamp
}
```

## API Endpoints Being Added

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/subscription/checkout` | POST | JWT | Create Stripe checkout session |
| `/subscription/portal` | POST | JWT | Access Stripe customer portal |
| `/subscription/prices` | GET | None | Get Stripe price IDs |
| `/stripe/webhook` | POST | Signature | Receive Stripe events |

## Webhook Events We Handle

| Event | What Happens | DB Update |
|-------|-------------|-----------|
| `checkout.session.completed` | User finished checkout | Create subscription record |
| `customer.subscription.created` | Subscription activated | Mark as subscribed |
| `customer.subscription.updated` | Plan changed or cancellation scheduled | Update status/plan |
| `customer.subscription.deleted` | Subscription ended | Revert to free plan |
| `invoice.payment_succeeded` | Renewal payment successful | Update period end date |
| `invoice.payment_failed` | Payment failed | Mark as past_due, user notified |

## Edge Cases Covered

### ✅ Payment Failure on Renewal
- Stripe automatically retries 3-4 times
- User stays subscribed during retry period (`past_due` status)
- UI shows "Payment failed, please update card"
- After all retries fail → revert to free plan

### ✅ User Cancels Subscription
- Two options: cancel immediately or at period end
- If at period end: `cancelAtPeriodEnd = true`, user keeps access
- Period ends → `subscription.deleted` webhook → revert to free

### ✅ User Reactivates Before Period End
- Clicks "Manage Subscription" → Stripe portal
- Clicks "Reactivate" → `subscription.updated` webhook
- `cancelAtPeriodEnd` set back to `false`

### ✅ Plan Upgrade/Downgrade
- User switches monthly ↔ annual in portal
- Stripe handles proration automatically
- Webhook updates `plan` field in DB

### ✅ Duplicate Webhooks
- Stripe may send same event twice (rare)
- Lambda handlers are idempotent
- DynamoDB updates are safe to repeat

### ✅ Webhook Delivery Failure
- Stripe retries failed webhooks for 3 days
- Lambda only returns 200 after successful DB update
- CloudWatch alarms notify if error rate > 1%

## Cost Analysis

### Stripe Fees (Per Transaction)
- 2.9% + $0.30 per successful charge
- **Monthly**: $9.99 → $0.59 fee → **$9.40 net revenue**
- **Annual**: $99.99 → $3.20 fee → **$96.79 net revenue**

### AWS Costs (Per 1,000 Users/Month)
- Lambda invocations: ~$0.20
- DynamoDB writes: Included in pay-per-request
- API Gateway: ~$0.10
- **Total**: ~$0.30 per 1,000 users

## Implementation Time Estimate

| Phase | Tasks | Time |
|-------|-------|------|
| **Phase 1**: Terraform setup | Add Stripe module, variables, provider | 2-3 hours |
| **Phase 2**: Lambda functions | Write subscription + webhook handlers | 4-6 hours |
| **Phase 3**: Terraform Lambda config | API Gateway routes, IAM permissions | 2-3 hours |
| **Phase 4**: Frontend updates | Stripe.js integration, UI changes | 3-4 hours |
| **Phase 5**: Testing | All scenarios in dev/staging | 4-6 hours |
| **Phase 6**: Production deployment | Deploy to prod, monitor | 2 hours |
| **Total** | | **17-24 hours** |

## Deployment Order

1. ✅ Read documentation (you are here!)
2. 🔲 Get production Stripe API keys from Stripe dashboard
3. 🔲 Add keys to `staging.tfvars` (test keys) and `prod.tfvars` (live keys)
4. 🔲 Create Stripe Terraform module
5. 🔲 Create Lambda functions (subscription + webhook)
6. 🔲 Update Terraform Lambda configs
7. 🔲 Deploy to **dev**: `./scripts/tf-env.sh dev apply`
8. 🔲 Test in dev with Stripe CLI
9. 🔲 Deploy to **staging**: `./scripts/tf-env.sh staging apply`
10. 🔲 Test in staging with real UI
11. 🔲 Update frontend code
12. 🔲 Deploy to **prod**: `./scripts/tf-env.sh prod apply` ⚠️
13. 🔲 Monitor production for 24 hours

## Files You Need to Create

### Backend (Terraform + Lambda)

```
terraform/modules/stripe/
  ├── main.tf           (Stripe products, prices, webhooks)
  ├── variables.tf      (Module inputs)
  └── outputs.tf        (Price IDs, webhook secret)

terraform/modules/lambdas/
  ├── _subscription.tf  (Subscription Lambda + API routes)
  └── _stripe_webhook.tf (Webhook Lambda + API route)

lambdas/subscription/
  ├── subscription_handler.py (Checkout + portal logic)
  └── requirements.txt         (stripe>=5.0.0)

lambdas/stripe_webhook/
  ├── webhook_handler.py (Event processing)
  └── requirements.txt    (stripe>=5.0.0)
```

### Frontend

```
src/pages/
  ├── Subscription.jsx (Update to call /subscription/checkout)
  └── Settings.jsx     (Add "Manage Subscription" button)
```

### Configuration Updates

```
terraform/
  ├── variables.tf     (Add stripe_publishable_key, stripe_secret_key)
  ├── staging.tfvars   (Add test keys)
  └── prod.tfvars      (Add LIVE keys)

terraform/modules/secrets/
  └── main.tf          (Add Stripe keys to Secrets Manager)
```

## Security Checklist

- ✅ Stripe secret key stored in AWS Secrets Manager
- ✅ Webhook signature verification prevents unauthorized calls
- ✅ JWT auth on all subscription management endpoints
- ✅ HTTPS only (enforced by API Gateway)
- ✅ No card data touches your servers (Stripe Checkout handles it)
- ✅ Publishable key safe for frontend (read-only, scoped)

## Testing Checklist

### Dev Environment (Stripe CLI)
- [ ] Create checkout session
- [ ] Complete checkout with test card (4242 4242 4242 4242)
- [ ] Verify webhook received and processed
- [ ] Check DynamoDB updated correctly
- [ ] Trigger `invoice.payment_failed` event
- [ ] Trigger `customer.subscription.deleted` event

### Staging Environment (Real UI)
- [ ] Sign up → select monthly plan → checkout
- [ ] Complete payment with test card
- [ ] Verify subscription shows in Settings
- [ ] Click "Manage Subscription" → Stripe portal
- [ ] Cancel subscription (end of period)
- [ ] Reactivate subscription
- [ ] Switch plan (monthly → annual)

### Production Environment
- [ ] Monitor first real subscription end-to-end
- [ ] Verify webhook delivery in Stripe dashboard
- [ ] Check CloudWatch logs for errors
- [ ] Verify email receipts sent by Stripe
- [ ] Test customer portal access

## Monitoring Setup

### CloudWatch Alarms
```bash
# Create alarms for:
- Lambda errors > 1% error rate
- Webhook signature failures
- DynamoDB throttling
- API Gateway 5xx errors
```

### Stripe Dashboard
- Monitor webhook delivery success rate (target: >99%)
- Track failed payments
- Review subscription churn
- Check revenue metrics

## Rollback Plan

If anything goes wrong in production:

1. **Immediate**: Revert Lambda functions to previous version
2. **Frontend**: Show "Checkout temporarily unavailable" message
3. **Existing subscriptions**: Continue working (webhooks still process)
4. **Fix**: Debug in dev, test in staging, redeploy to prod

## Support Playbook

### "My payment failed"
→ Direct user to Settings → "Manage Subscription" → Update payment method

### "How do I cancel?"
→ Settings → "Manage Subscription" → Cancel subscription

### "I was charged but don't have access"
→ Check webhook logs, verify `isSubscribed` in DynamoDB, run sync script

### "I want to change my plan"
→ Settings → "Manage Subscription" → Switch subscription (prorated automatically)

## Next Steps for You

1. **Review the full plan**: Read `STRIPE_INTEGRATION_PLAN.md` carefully
2. **Get Stripe production keys**: Log into Stripe dashboard, get live mode keys
3. **Start with Terraform**: Create the Stripe module first
4. **Build Lambdas**: Implement subscription and webhook handlers
5. **Test in dev**: Use Stripe CLI to verify webhook handling
6. **Update frontend**: Integrate Stripe.js and Checkout
7. **Deploy to staging**: Full E2E testing with real UI
8. **Go to production**: Carefully deploy with live keys
9. **Monitor closely**: Watch logs for first 24 hours

## Questions?

- **Full technical details**: `STRIPE_INTEGRATION_PLAN.md`
- **Quick commands**: `STRIPE_QUICK_START.md`
- **Visual flows**: `STRIPE_ARCHITECTURE_DIAGRAMS.md`
- **Stripe docs**: https://stripe.com/docs/billing
- **Terraform provider**: https://registry.terraform.io/providers/lukasaron/stripe

## Confidence Level

I've designed this integration to handle:
- ✅ All standard subscription flows
- ✅ All common edge cases (payment failures, cancellations)
- ✅ Security best practices
- ✅ Idempotent operations
- ✅ Multi-environment deployment
- ✅ Graceful error handling
- ✅ Monitoring and alerting

This is a **production-ready** plan that follows Stripe's best practices and AWS architectural patterns.

---

**Created**: December 22, 2025  
**Author**: AI Assistant (Claude Sonnet 4.5)  
**Status**: Ready for implementation

