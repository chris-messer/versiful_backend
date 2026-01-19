# Richard's Stripe Data Analysis

## ⚠️ ISSUE: TWO ACTIVE SUBSCRIPTIONS

Richard has **2 active subscriptions** in Stripe, confirming the double charge issue.

### Subscription 1 (Earlier - Should be Cancelled)
- **ID:** `sub_1SrL8OBcYhqWB9qEbgEcZYsi`
- **Created:** 1768839414 (Jan 19, 2026 ~10:30 AM)
- **Status:** active
- **Plan:** Monthly ($9.99)
- **Current Period End:** 1771517814 (Feb 20, 2026)
- **Cancel At Period End:** false

### Subscription 2 (Later - Keep This One)
- **ID:** `sub_1SrLMZBcYhqWB9qEYC59bAxY`
- **Created:** 1768840293 (Jan 19, 2026 ~10:44 AM) - 15 min later
- **Status:** active
- **Plan:** Monthly ($9.99)
- **Current Period End:** 1771518693 (Feb 20, 2026)
- **Cancel At Period End:** false

---

## Recommended Action Plan

### Step 1: Cancel First Subscription (Keep Second)
**Why:** The second subscription (14 minutes later) is the one Richard intended to keep after the first failed to show as subscribed.

**Command:**
```bash
stripe subscriptions cancel sub_1SrL8OBcYhqWB9qEbgEcZYsi
```

### Step 2: Update Richard's DynamoDB Record
Use the **second subscription** data (the one we're keeping):

**Values to add:**
```json
{
  "stripeSubscriptionId": "sub_1SrLMZBcYhqWB9qEYC59bAxY",
  "plan": "monthly",
  "plan_monthly_cap": -1,
  "subscriptionStatus": "active",
  "cancelAtPeriodEnd": false,
  "currentPeriodEnd": 1771518693,
  "updatedAt": "2026-01-19T18:30:00+00:00"
}
```

### Step 3: Verify Refund Was Processed
The first subscription should be refunded since we're canceling it.

---

## DynamoDB Update Command

```bash
aws dynamodb update-item \
  --table-name prod-versiful-users \
  --key '{"userId": {"S": "c428a478-e031-705e-db1d-fe9577d74a24"}}' \
  --region us-east-1 \
  --update-expression "SET stripeSubscriptionId = :sub_id, #plan = :plan, plan_monthly_cap = :cap, subscriptionStatus = :status, cancelAtPeriodEnd = :cancel, currentPeriodEnd = :period_end, updatedAt = :updated" \
  --expression-attribute-names '{"#plan": "plan"}' \
  --expression-attribute-values '{
    ":sub_id": {"S": "sub_1SrLMZBcYhqWB9qEYC59bAxY"},
    ":plan": {"S": "monthly"},
    ":cap": {"N": "-1"},
    ":status": {"S": "active"},
    ":cancel": {"BOOL": false},
    ":period_end": {"N": "1771518693"},
    ":updated": {"S": "2026-01-19T18:30:00+00:00"}
  }'
```

---

## Execution Order

1. ✅ **First:** Cancel the first subscription in Stripe
2. ✅ **Second:** Update DynamoDB with second subscription data
3. ✅ **Third:** Verify Richard can send unlimited SMS messages
4. ✅ **Fourth:** Confirm frontend shows subscription correctly

---

## Notes

- **Current Period End:** Feb 20, 2026 (both subscriptions end same day, ~15 min apart)
- **Plan:** Monthly $9.99
- **Most Critical:** Setting `plan_monthly_cap: -1` to enable unlimited messages
- **Refund:** The first subscription cancellation should trigger a prorated refund

