# Stripe Integration Implementation Checklist

Use this file to track your progress implementing the Stripe payment integration.

## 📋 Pre-Implementation

- [ ] Read `STRIPE_README.md` (executive summary)
- [ ] Read `STRIPE_INTEGRATION_PLAN.md` (full technical details)
- [ ] Review `STRIPE_ARCHITECTURE_DIAGRAMS.md` (visual flows)
- [ ] Get Stripe production account set up
- [ ] Obtain production API keys (live mode)
- [ ] Install Stripe CLI: `brew install stripe/stripe-cli/stripe`
- [ ] Login to Stripe CLI: `stripe login`

## 🏗️ Phase 1: Terraform Infrastructure (Est: 2-3 hours)

### 1.1 Update Root Terraform Files
- [ ] Add Stripe provider to `terraform/main.tf`
- [ ] Add `stripe_publishable_key` variable to `terraform/variables.tf`
- [ ] Add `stripe_secret_key` variable to `terraform/variables.tf`
- [ ] Add test keys to `terraform/staging.tfvars`
- [ ] Add production keys to `terraform/prod.tfvars`
- [ ] Update `terraform/main.tf` to include Stripe module

### 1.2 Create Stripe Module
- [ ] Create directory: `terraform/modules/stripe/`
- [ ] Create `terraform/modules/stripe/main.tf`
  - [ ] Define `stripe_product` resource
  - [ ] Define `stripe_price` for monthly plan ($9.99)
  - [ ] Define `stripe_price` for annual plan ($99.99)
  - [ ] Define `stripe_webhook_endpoint` resource
- [ ] Create `terraform/modules/stripe/variables.tf`
  - [ ] Add `environment` variable
  - [ ] Add `domain_name` variable
  - [ ] Add `stripe_secret_key` variable
- [ ] Create `terraform/modules/stripe/outputs.tf`
  - [ ] Output `monthly_price_id`
  - [ ] Output `annual_price_id`
  - [ ] Output `webhook_secret`
  - [ ] Output `product_id`

### 1.3 Update Secrets Manager
- [ ] Update `terraform/modules/secrets/main.tf`
  - [ ] Add `stripe_secret_key` to secret JSON
  - [ ] Add `stripe_publishable_key` to secret JSON
  - [ ] Add `stripe_webhook_secret` to secret JSON
- [ ] Update `terraform/modules/secrets/variables.tf`
  - [ ] Add `stripe_publishable_key` variable
  - [ ] Add `stripe_secret_key` variable
  - [ ] Add `stripe_webhook_secret` variable

## 🔧 Phase 2: Lambda Functions (Est: 4-6 hours)

### 2.1 Subscription Handler Lambda
- [ ] Create directory: `lambdas/subscription/`
- [ ] Create `lambdas/subscription/subscription_handler.py`
  - [ ] Import required libraries (stripe, boto3, json)
  - [ ] Implement `handler()` function (routes to sub-handlers)
  - [ ] Implement `create_checkout_session()` function
  - [ ] Implement `create_portal_session()` function
  - [ ] Implement `get_prices()` function
  - [ ] Add error handling and logging
- [ ] Create `lambdas/subscription/requirements.txt`
  - [ ] Add `stripe>=5.0.0`
  - [ ] Add `boto3>=1.26.0`

### 2.2 Stripe Webhook Handler Lambda
- [ ] Create directory: `lambdas/stripe_webhook/`
- [ ] Create `lambdas/stripe_webhook/webhook_handler.py`
  - [ ] Import required libraries
  - [ ] Implement `handler()` function (verify signature, route events)
  - [ ] Implement `handle_checkout_completed()` function
  - [ ] Implement `handle_subscription_created()` function
  - [ ] Implement `handle_subscription_updated()` function
  - [ ] Implement `handle_subscription_deleted()` function
  - [ ] Implement `handle_payment_succeeded()` function
  - [ ] Implement `handle_payment_failed()` function
  - [ ] Add webhook signature verification
  - [ ] Add error handling and logging
- [ ] Create `lambdas/stripe_webhook/requirements.txt`
  - [ ] Add `stripe>=5.0.0`
  - [ ] Add `boto3>=1.26.0`

## 🚀 Phase 3: Terraform Lambda Configuration (Est: 2-3 hours)

### 3.1 Subscription Lambda Terraform
- [ ] Create `terraform/modules/lambdas/_subscription.tf`
  - [ ] Add `data.archive_file` for packaging
  - [ ] Add `aws_lambda_function` resource
  - [ ] Add environment variables (Stripe keys, price IDs, frontend domain)
  - [ ] Add API Gateway integration for `POST /subscription/checkout`
  - [ ] Add API Gateway route with JWT auth
  - [ ] Add API Gateway integration for `POST /subscription/portal`
  - [ ] Add API Gateway route with JWT auth
  - [ ] Add API Gateway integration for `GET /subscription/prices`
  - [ ] Add API Gateway route (public)
  - [ ] Add Lambda permission for API Gateway

### 3.2 Webhook Lambda Terraform
- [ ] Create `terraform/modules/lambdas/_stripe_webhook.tf`
  - [ ] Add `data.archive_file` for packaging
  - [ ] Add `aws_lambda_function` resource
  - [ ] Add environment variables (Stripe secret, webhook secret)
  - [ ] Add API Gateway integration for `POST /stripe/webhook`
  - [ ] Add API Gateway route (NO auth - signature verified in Lambda)
  - [ ] Add Lambda permission for API Gateway

### 3.3 Update Lambda Module Variables
- [ ] Update `terraform/modules/lambdas/variables.tf`
  - [ ] Add `stripe_secret_key` variable
  - [ ] Add `stripe_publishable_key` variable
  - [ ] Add `stripe_monthly_price_id` variable
  - [ ] Add `stripe_annual_price_id` variable
  - [ ] Add `stripe_webhook_secret` variable
  - [ ] Add `frontend_domain` variable

## 💻 Phase 4: Frontend Integration (Est: 3-4 hours)

### 4.1 Install Dependencies
- [ ] Run `npm install @stripe/stripe-js` in frontend directory

### 4.2 Update Subscription Page
- [ ] Open `versiful-frontend/src/pages/Subscription.jsx`
- [ ] Import `loadStripe` from `@stripe/stripe-js`
- [ ] Add state for Stripe price IDs
- [ ] Fetch price IDs from `/subscription/prices` on mount
- [ ] Update `handleSubscribe()` function:
  - [ ] Keep free plan logic as-is
  - [ ] For monthly/annual: call `/subscription/checkout`
  - [ ] Get `sessionId` from response
  - [ ] Call `loadStripe()` with publishable key
  - [ ] Redirect to Stripe Checkout
- [ ] Handle return from checkout (success/cancel)
- [ ] Add error handling

### 4.3 Update Settings Page
- [ ] Open `versiful-frontend/src/pages/Settings.jsx`
- [ ] Add "Manage Subscription" button (conditional on `isSubscribed`)
- [ ] Implement `handleManageSubscription()` function:
  - [ ] Call `POST /subscription/portal`
  - [ ] Get portal URL from response
  - [ ] Redirect to portal URL
- [ ] Display subscription status (plan, next billing date)
- [ ] Show cancelation status if `cancelAtPeriodEnd` is true

### 4.4 Environment Variables
- [ ] Add `VITE_STRIPE_PUBLISHABLE_KEY` to `.env.development`
- [ ] Add `VITE_STRIPE_PUBLISHABLE_KEY` to `.env.production`
- [ ] Update build configs if needed

## 🧪 Phase 5: Testing (Est: 4-6 hours)

### 5.1 Dev Environment Testing
- [ ] Deploy to dev: `./scripts/tf-env.sh dev plan && ./scripts/tf-env.sh dev apply`
- [ ] Set up Stripe CLI webhook forwarding:
  ```bash
  stripe listen --forward-to https://api.dev.versiful.io/stripe/webhook
  ```
- [ ] Test checkout session creation via API
- [ ] Test webhook signature verification
- [ ] Trigger test events:
  - [ ] `stripe trigger checkout.session.completed`
  - [ ] `stripe trigger invoice.payment_failed`
  - [ ] `stripe trigger customer.subscription.deleted`
- [ ] Verify DynamoDB updates for each event
- [ ] Check CloudWatch logs for errors

### 5.2 Staging Environment Testing
- [ ] Deploy to staging: `./scripts/tf-env.sh staging plan && ./scripts/tf-env.sh staging apply`
- [ ] Deploy frontend to staging
- [ ] Test full user flows:
  - [ ] Sign up → Subscribe to monthly → Complete checkout
  - [ ] Verify subscription shows in Settings
  - [ ] Click "Manage Subscription" → Access portal
  - [ ] Cancel subscription (end of period)
  - [ ] Verify `cancelAtPeriodEnd` flag set
  - [ ] Reactivate subscription before period ends
  - [ ] Switch plan (monthly → annual)
  - [ ] Test with declined card (4000 0000 0000 0002)
- [ ] Verify all webhooks received and processed
- [ ] Check DynamoDB data accuracy

### 5.3 Edge Case Testing
- [ ] Test duplicate webhook (replay same event)
- [ ] Test webhook with invalid signature
- [ ] Test checkout with existing customer
- [ ] Test payment failure → retry → success
- [ ] Test payment failure → all retries fail → cancel
- [ ] Test user with no Stripe customer ID

## 🌐 Phase 6: Production Deployment (Est: 2 hours)

### 6.1 Pre-Deployment
- [ ] Review production Stripe keys (LIVE mode)
- [ ] Update `terraform/prod.tfvars` with live keys
- [ ] Review Terraform plan carefully:
  ```bash
  ./scripts/tf-env.sh prod plan
  ```
- [ ] Get approval from team/stakeholders
- [ ] Schedule maintenance window (if needed)

### 6.2 Deployment
- [ ] Deploy backend:
  ```bash
  ./scripts/tf-env.sh prod apply
  ```
- [ ] Verify Stripe resources created in dashboard
- [ ] Verify webhook endpoint registered
- [ ] Deploy frontend to production
- [ ] Smoke test: create test subscription with real card
- [ ] Verify webhook received for test subscription
- [ ] Cancel test subscription

### 6.3 Post-Deployment Monitoring
- [ ] Monitor CloudWatch logs for 1 hour
- [ ] Check Stripe webhook delivery success rate
- [ ] Monitor error rates in Lambdas
- [ ] Check first real customer subscription end-to-end
- [ ] Verify email receipts sent by Stripe
- [ ] Set up CloudWatch alarms (if not already done)

## 📊 Phase 7: Monitoring & Operations (Ongoing)

### 7.1 CloudWatch Alarms
- [ ] Create alarm: Lambda error rate > 1%
- [ ] Create alarm: Webhook signature failures
- [ ] Create alarm: DynamoDB throttling
- [ ] Create alarm: API Gateway 5xx errors
- [ ] Test alarms trigger correctly

### 7.2 Stripe Dashboard Setup
- [ ] Configure email notifications for failed payments
- [ ] Set up revenue reports
- [ ] Enable Stripe billing email receipts
- [ ] Configure customer portal settings
- [ ] Set up subscription churn alerts

### 7.3 Reconciliation Script
- [ ] Create `scripts/sync_stripe_subscriptions.py`
  - [ ] Fetch all active subscriptions from Stripe
  - [ ] Compare with DynamoDB records
  - [ ] Report discrepancies
  - [ ] Optionally auto-fix mismatches
- [ ] Schedule weekly reconciliation (cron/EventBridge)

## 📚 Documentation & Training

- [ ] Update API documentation with new endpoints
- [ ] Document support procedures for payment issues
- [ ] Create runbook for common issues
- [ ] Train support team on Stripe customer portal
- [ ] Document rollback procedure
- [ ] Update deployment documentation

## 🎯 Optional Enhancements (Future)

- [ ] Add free trial period (7 or 14 days)
- [ ] Implement coupon/promo code support
- [ ] Enable Stripe Tax for automatic tax calculation
- [ ] Add invoice history in user settings
- [ ] Implement usage-based billing (if needed)
- [ ] Add referral program
- [ ] Integrate with customer support tools (Intercom, Zendesk)

## 🐛 Known Issues & Workarounds

_Document any issues encountered during implementation here_

- Issue: [Description]
  - Workaround: [Solution]
  - Status: [Open/Resolved]

## 📝 Notes & Learnings

_Document key learnings, gotchas, and useful tips here_

---

## Progress Summary

**Started**: [Date]  
**Completed**: [Date]  
**Total Time**: [Hours]  

**Status**: 
- [ ] Not Started
- [ ] In Progress
- [ ] Testing
- [ ] Deployed to Dev
- [ ] Deployed to Staging
- [ ] Deployed to Production
- [ ] Complete

**Team Members**:
- Developer: [Name]
- Reviewer: [Name]
- QA: [Name]

**Related PRs**:
- Backend: [PR link]
- Frontend: [PR link]
- Infrastructure: [PR link]

---

**Last Updated**: December 22, 2025  
**Maintained By**: [Your Name]

