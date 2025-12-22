# 🎯 Stripe Integration - Quick Reference Card

## ✅ Status: 100% COMPLETE

---

## 🚀 Start Testing Now

### 1. Start Frontend
```bash
cd /Users/christopher.messer/WebstormProjects/versiful-frontend
npm run dev
```
**Opens:** http://localhost:5173

### 2. Test Checkout
1. Go to http://localhost:5173/subscription
2. Click "Subscribe now" on Monthly ($9.99)
3. Use test card: `4242 4242 4242 4242`
4. Complete checkout
5. Verify redirect to settings with success message

### 3. Test Management Portal
1. Go to http://localhost:5173/settings
2. Click "Manage subscription"
3. Test cancellation/updates in Stripe portal
4. Return and verify status updated

---

## 📊 Key Information

### Pricing
- **Free**: $0/mo • 5 messages/month
- **Monthly**: $9.99/mo • Unlimited
- **Annual**: $99.99/yr • Unlimited (Save 17%)

### Price IDs
- Monthly: `price_1ShDU6B2NunFksMzSwxqBRkb`
- Annual: `price_1ShDUGB2NunFksMzM51dIr0I`

### API Endpoints
- GET  `/subscription/prices` - [Public]
- POST `/subscription/checkout` - [JWT Auth]
- POST `/subscription/portal` - [JWT Auth]  
- POST `/stripe/webhook` - [Signature]

### Stripe Test Cards
- **Success**: 4242 4242 4242 4242
- **Decline**: 4000 0000 0000 0002
- **3D Secure**: 4000 0025 0000 3155

---

## 🔧 Quick Commands

### Check Lambda Logs
```bash
aws logs tail /aws/lambda/dev-versiful-subscription --follow
aws logs tail /aws/lambda/dev-versiful-stripe-webhook --follow
```

### Test Lambda Directly
```bash
aws lambda invoke \
  --function-name dev-versiful-subscription \
  --region us-east-1 \
  --cli-binary-format raw-in-base64-out \
  --payload '{"path": "/subscription/prices", "httpMethod": "GET"}' \
  response.json && cat response.json | jq .
```

### Test Webhook Events
```bash
stripe trigger checkout.session.completed
stripe trigger customer.subscription.deleted
stripe trigger invoice.payment_failed
```

### Check DynamoDB
```bash
aws dynamodb scan \
  --table-name dev-versiful-users \
  --region us-east-1 \
  --projection-expression "userId,isSubscribed,plan_monthly_cap" \
  | jq .
```

---

## 🔗 Quick Links

**Stripe Dashboard:**
https://dashboard.stripe.com/test/dashboard

**Stripe Products:**
https://dashboard.stripe.com/test/products

**Stripe Webhooks:**
https://dashboard.stripe.com/test/webhooks/we_1ShDULB2NunFksMzdL3nHzz8

**AWS Lambda:**
https://console.aws.amazon.com/lambda/home?region=us-east-1

**DynamoDB Table:**
https://console.aws.amazon.com/dynamodbv2/home?region=us-east-1#table?name=dev-versiful-users

**CloudWatch Logs:**
https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups

---

## 📝 What to Test

- [ ] Free plan selection
- [ ] Monthly checkout flow
- [ ] Annual checkout flow
- [ ] Checkout cancellation
- [ ] Success redirect
- [ ] "Manage subscription" button
- [ ] Stripe Customer Portal
- [ ] Subscription status display
- [ ] Message limit display
- [ ] Webhook DynamoDB updates
- [ ] Mobile responsiveness
- [ ] Loading states
- [ ] Error handling

---

## 🐛 Troubleshooting

**Issue**: Checkout button not working
**Fix**: Check browser console for errors, verify price IDs are fetched

**Issue**: Webhook not updating DynamoDB
**Fix**: Check CloudWatch logs for webhook Lambda, verify signature secret

**Issue**: "Manage subscription" not working
**Fix**: Verify user has `stripeCustomerId` in DynamoDB

**Issue**: Environment variable not loading
**Fix**: Restart dev server after changing `.env.local`

---

## 📚 Documentation

All docs in: `/Users/christopher.messer/PycharmProjects/versiful-backend/docs/`

- `STRIPE_FINAL_SUMMARY.md` - Complete overview
- `STRIPE_DEPLOYMENT_COMPLETE.md` - Backend details
- `STRIPE_FRONTEND_COMPLETE.md` - Frontend details
- `STRIPE_INTEGRATION_PLAN.md` - Technical architecture

---

## 🎉 YOU'RE READY!

Everything is deployed and configured.  
**Just start the frontend and test!** 🚀

---

**Last Updated:** December 22, 2025

