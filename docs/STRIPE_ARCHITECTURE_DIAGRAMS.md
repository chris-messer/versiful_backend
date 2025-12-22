# Stripe Payment Architecture & Flow Diagrams

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Versiful Frontend (React)                     │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐    │
│  │ Subscription.jsx │  │   Settings.jsx   │  │    Navbar.jsx    │    │
│  │  - Select Plan   │  │ - Manage Sub     │  │ - Show Status    │    │
│  │  - Start Checkout│  │ - Customer Portal│  │ - Next Bill Date │    │
│  └────────┬─────────┘  └────────┬─────────┘  └─────────┬────────┘    │
└───────────┼────────────────────┼────────────────────────┼─────────────┘
            │                    │                        │
            │ POST /subscription/│ POST /subscription/    │ GET /users
            │      checkout      │      portal            │
            ▼                    ▼                        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    API Gateway (api.{env}.versiful.io)                  │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │  Routes:                                                         │  │
│  │  POST /subscription/checkout    [JWT Auth Required]             │  │
│  │  POST /subscription/portal      [JWT Auth Required]             │  │
│  │  GET  /subscription/prices      [Public]                        │  │
│  │  POST /stripe/webhook           [No Auth - Signature Verified]  │  │
│  └─────────────────────────────────────────────────────────────────┘  │
└───────────┬────────────────────┬───────────────────────┬───────────────┘
            │                    │                       │
            ▼                    ▼                       ▼
┌─────────────────────┐  ┌──────────────────┐  ┌───────────────────────┐
│ Subscription Lambda │  │  Webhook Lambda  │  │   Users Lambda        │
│ - Create Checkout   │  │ - Process Events │  │ - Get/Update Profile  │
│ - Customer Portal   │  │ - Update DB      │  │ - Subscription Status │
│ - Return Price IDs  │  │ - Handle Failures│  └───────┬───────────────┘
└──────────┬──────────┘  └────────┬─────────┘          │
           │                      │                    │
           │ Stripe API           │                    │
           │ Calls                │                    │
           ▼                      │                    │
┌─────────────────────────────────┤                    │
│        Stripe Platform          │                    │
│  ┌──────────────────────────┐  │                    │
│  │  Checkout Sessions       │  │                    │
│  │  Customer Portal         │  │                    │
│  │  Subscriptions           │  │                    │
│  │  Webhooks               │───┘                    │
│  │  Products & Prices       │                       │
│  └──────────────────────────┘                       │
└──────────────────────────────────────────────────────┘
           │                      │                    │
           │ All Lambdas Write    ▼                    │
           └──────────────────►┌───────────────────────┴──┐
                                │   DynamoDB Users Table   │
                                │  ┌────────────────────┐  │
│  │ userId (PK)        │  │
│  │ email              │  │
│  │ isSubscribed       │  │
│  │ plan               │  │
│  │ plan_monthly_cap   │  │
│  │ stripeCustomerId   │  │
│  │ stripeSubscriptionId│ │
│  │ subscriptionStatus │  │
│  │ currentPeriodEnd   │  │
│  │ cancelAtPeriodEnd  │  │
                                │  └────────────────────┘  │
                                └──────────────────────────┘
```

## Payment Flow Sequence

### Flow 1: User Subscribes to Monthly Plan

```
User                Frontend         API Gateway      Subscription    Stripe          Webhook         DynamoDB
 │                    │                   │              Lambda         │              Lambda           │
 │ 1. Click          │                   │                │             │                │              │
 │ "Subscribe"       │                   │                │             │                │              │
 │──────────────────>│                   │                │             │                │              │
 │                   │ 2. POST           │                │             │                │              │
 │                   │ /subscription/    │                │             │                │              │
 │                   │ checkout          │                │             │                │              │
 │                   │ {priceId: monthly}│                │             │                │              │
 │                   │──────────────────>│ 3. Invoke      │             │                │              │
 │                   │                   │ with JWT       │             │                │              │
 │                   │                   │───────────────>│             │                │              │
 │                   │                   │                │ 4. Get/Create             │              │
 │                   │                   │                │    Customer │             │              │
 │                   │                   │                │────────────>│             │              │
 │                   │                   │                │<────────────│             │              │
 │                   │                   │                │ customerId  │             │              │
 │                   │                   │                │             │             │              │
 │                   │                   │                │ 5. Create   │             │              │
 │                   │                   │                │    Checkout │             │              │
 │                   │                   │                │    Session  │             │              │
 │                   │                   │                │────────────>│             │              │
 │                   │                   │                │<────────────│             │              │
 │                   │                   │                │ sessionId   │             │              │
 │                   │                   │<───────────────│             │             │              │
 │                   │<──────────────────│ 6. Return      │             │             │              │
 │                   │ {sessionId}       │    sessionId   │             │             │              │
 │                   │                   │                │             │             │              │
 │ 7. Redirect to    │                   │                │             │             │              │
 │    Stripe Checkout│                   │                │             │             │              │
 │<──────────────────│                   │                │             │             │              │
 │                   │                   │                │             │             │              │
 │ 8. Enter Card     │                   │                │             │             │              │
 │    & Complete     │                   │                │             │             │              │
 │──────────────────────────────────────────────────────>│             │             │              │
 │                   │                   │                │             │             │              │
 │                   │                   │                │ 9. Process  │             │              │
 │                   │                   │                │    Payment  │             │              │
 │                   │                   │                │    (Stripe) │             │              │
 │                   │                   │                │             │             │              │
 │ 10. Redirect      │                   │                │             │             │              │
 │     back to app   │                   │                │             │             │              │
 │<──────────────────────────────────────────────────────┘             │             │              │
 │                   │                   │                              │             │              │
 │                   │                   │                              │ 11. Send    │              │
 │                   │                   │                              │   Webhook   │              │
 │                   │                   │                              │ checkout.   │              │
 │                   │                   │                              │ session.    │              │
 │                   │                   │                              │ completed   │              │
 │                   │                   │              ┌───────────────┼────────────>│              │
 │                   │                   │              │               │             │ 12. Verify  │
 │                   │                   │              │               │             │    Signature│
 │                   │                   │              │               │             │              │
 │                   │                   │              │               │             │ 13. Update  │
 │                   │                   │              │               │             │    User     │
 │                   │                   │              │               │             │    Record   │
 │                   │                   │              │               │             │─────────────>│
 │                   │                   │              │               │             │ SET         │
 │                   │                   │              │               │             │ isSubscribed│
 │                   │                   │              │               │             │ = true      │
 │                   │                   │              │               │             │ plan=monthly│
 │                   │                   │              │               │             │<─────────────│
 │                   │                   │              └───────────────┼─────────────┤              │
 │                   │                   │                              │             │ 14. Return  │
 │                   │                   │                              │<────────────┤    200 OK   │
 │ 15. Check status  │                   │                              │             │              │
 │─────────────────>│ GET /users        │                              │             │              │
 │                  │──────────────────>│                              │             │              │
 │                  │                   │──────────────────────────────────────────────────────────>│
 │                  │                   │                              │             │  GET userId  │
 │                  │                   │<──────────────────────────────────────────────────────────│
 │                  │<──────────────────│ {isSubscribed:true, plan:"monthly"}      │              │
 │<─────────────────│                   │                              │             │              │
 │ Show subscribed! │                   │                              │             │              │
```

## Webhook Event Handling Flow

### Flow 2: Payment Failure → Retry → Cancellation

```
Stripe                 Webhook            DynamoDB           User App
  │                    Lambda               │                  │
  │                      │                  │                  │
  │ Renewal Due          │                  │                  │
  │ Charge Card          │                  │                  │
  │ DECLINED!            │                  │                  │
  │                      │                  │                  │
  │ Send Webhook:        │                  │                  │
  │ invoice.payment_     │                  │                  │
  │ failed               │                  │                  │
  │─────────────────────>│                  │                  │
  │                      │ Update Status    │                  │
  │                      │─────────────────>│                  │
  │                      │ subscriptionStatus│                 │
  │                      │ = "past_due"     │                  │
  │                      │ isSubscribed=true│                  │
  │                      │<─────────────────│                  │
  │                      │                  │                  │
  │                      │                  │ User sees banner:│
  │                      │                  │ "Payment Failed" │
  │                      │                  │─────────────────>│
  │                      │                  │                  │
  │ Retry 1 (3 days)     │                  │                  │
  │ DECLINED!            │                  │                  │
  │                      │                  │                  │
  │ Retry 2 (5 days)     │                  │                  │
  │ DECLINED!            │                  │                  │
  │                      │                  │                  │
  │ Retry 3 (7 days)     │                  │                  │
  │ DECLINED!            │                  │                  │
  │                      │                  │                  │
  │ All retries failed   │                  │                  │
  │ Cancel subscription  │                  │                  │
  │                      │                  │                  │
  │ Send Webhook:        │                  │                  │
  │ customer.subscription│                  │                  │
  │ .deleted             │                  │                  │
  │─────────────────────>│                  │                  │
  │                      │ Update User      │                  │
  │                      │─────────────────>│                  │
  │                      │ isSubscribed=false                  │
  │                      │ plan="free"      │                  │
  │                      │ status="canceled"│                  │
  │                      │<─────────────────│                  │
  │                      │                  │                  │
  │                      │                  │ User sees:       │
  │                      │                  │ "Reverted to     │
  │                      │                  │  Free Plan"      │
  │                      │                  │─────────────────>│
```

### Flow 3: User Cancels Subscription (End of Period)

```
User              Frontend       Subscription    Stripe          Webhook         DynamoDB
 │                  │              Lambda          │              Lambda           │
 │                  │                │             │                │              │
 │ Click "Manage    │                │             │                │              │
 │ Subscription"    │                │             │                │              │
 │─────────────────>│                │             │                │              │
 │                  │ POST           │             │                │              │
 │                  │ /subscription/ │             │                │              │
 │                  │ portal         │             │                │              │
 │                  │───────────────>│             │                │              │
 │                  │                │ Create      │                │              │
 │                  │                │ Portal      │                │              │
 │                  │                │ Session     │                │              │
 │                  │                │────────────>│                │              │
 │                  │                │<────────────│                │              │
 │                  │<───────────────│ portal URL  │                │              │
 │                  │                │             │                │              │
 │ Redirect to      │                │             │                │              │
 │ Stripe Portal    │                │             │                │              │
 │<─────────────────│                │             │                │              │
 │                  │                │             │                │              │
 │ Click "Cancel    │                │             │                │              │
 │ Subscription"    │                │             │                │              │
 │ (at period end)  │                │             │                │              │
 │────────────────────────────────────────────────>│                │              │
 │                  │                │             │                │              │
 │                  │                │             │ Update Sub     │              │
 │                  │                │             │ cancel_at_     │              │
 │                  │                │             │ period_end=true│              │
 │                  │                │             │                │              │
 │                  │                │             │ Send Webhook:  │              │
 │                  │                │             │ customer.      │              │
 │                  │                │             │ subscription.  │              │
 │                  │                │             │ updated        │              │
 │                  │                │             │───────────────>│              │
 │                  │                │             │                │ Update DB    │
 │                  │                │             │                │─────────────>│
 │                  │                │             │                │ cancelAtPeriod│
 │                  │                │             │                │ End=true     │
 │                  │                │             │                │ isSubscribed │
 │                  │                │             │                │ =true (still)│
 │                  │                │             │                │<─────────────│
 │                  │                │             │                │              │
 │ Show message:    │                │             │                │              │
 │ "Access until    │                │             │                │              │
 │  Jan 22, 2026"   │                │             │                │              │
 │<─────────────────────────────────────────────────────────────────────────────────
 │                  │                │             │                │              │
 │ [Time passes...] │                │             │                │              │
 │                  │                │             │                │              │
 │ [Period Ends]    │                │             │ Send Webhook:  │              │
 │                  │                │             │ customer.      │              │
 │                  │                │             │ subscription.  │              │
 │                  │                │             │ deleted        │              │
 │                  │                │             │───────────────>│              │
 │                  │                │             │                │ Update DB    │
 │                  │                │             │                │─────────────>│
 │                  │                │             │                │ isSubscribed │
 │                  │                │             │                │ =false       │
 │                  │                │             │                │ plan="free"  │
 │                  │                │             │                │<─────────────│
 │                  │                │             │                │              │
 │ Next visit shows │                │             │                │              │
 │ "Free Plan"      │                │             │                │              │
```

## State Transitions

### Subscription Status State Machine

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         Subscription Lifecycle                           │
└──────────────────────────────────────────────────────────────────────────┘

    [New User]
         │
         │ User registers
         ▼
    ┌─────────┐
    │  FREE   │ (isSubscribed = false, plan = "free")
    └────┬────┘
         │
         │ Clicks "Subscribe", completes checkout
         │ checkout.session.completed webhook
         ▼
    ┌──────────┐
    │  ACTIVE  │ (isSubscribed = true, plan = "monthly" or "annual")
    └────┬─────┘  subscriptionStatus = "active"
         │
         │
    ┌────┴────────────────────────────────┬────────────────────┬─────────────┐
    │                                     │                    │             │
    │ Payment fails                       │ User cancels       │ Payment     │
    │ invoice.payment_failed              │ (end of period)    │ succeeds    │
    │                                     │ subscription.      │ (renewal)   │
    │                                     │ updated            │             │
    ▼                                     ▼                    │             │
┌──────────┐                          ┌─────────────────┐     │             │
│ PAST_DUE │                          │  CANCEL_PENDING │     │             │
└────┬─────┘                          └────┬────────────┘     │             │
     │ (isSubscribed = true)               │ (isSubscribed = true)          │
     │  subscriptionStatus = "past_due"    │  cancelAtPeriodEnd = true)    │
     │                                     │  (User keeps access)          │
     │                                     │                                │
     │ Stripe retries 3-4 times            │ Period ends                   │
     │                                     │ subscription.deleted          │
     │                                     │                                │
     ├─────────────┬──────────────────────┼────────────────────────────────┘
     │             │                      │
     │ Payment     │ All retries fail     │
     │ succeeds    │ subscription.deleted │
     │             │                      │
     ▼             ▼                      ▼
┌──────────┐  ┌────────────┐        ┌─────────┐
│  ACTIVE  │  │  CANCELED  │        │  FREE   │
└──────────┘  └─────┬──────┘        └─────────┘
     │              │ (isSubscribed = false)
     │              │  plan = "free"
     │              │  subscriptionStatus = "canceled"
     │              │
     │              │ Can resubscribe
     │              │
     └──────────────┴─────────────────────────────────────────>
                   User subscribes again
```

## Database Schema Evolution

### Before Stripe Integration
```
Users Table:
┌────────────────┬──────────┬─────────────────────────┐
│ Field          │ Type     │ Example                 │
├────────────────┼──────────┼─────────────────────────┤
│ userId         │ String   │ "google_123456"         │
│ email          │ String   │ "user@example.com"      │
│ phoneNumber    │ String   │ "+15551234567"          │
│ isRegistered   │ Boolean  │ true                    │
│ isSubscribed   │ Boolean  │ false                   │
│ plan           │ String   │ "free"                  │
│ bibleVersion   │ String   │ "NIV"                   │
│ responseStyle  │ String   │ "gentle"                │
└────────────────┴──────────┴─────────────────────────┘
```

### After Stripe Integration
```
Users Table:
┌───────────────────────┬──────────┬─────────────────────────┐
│ Field                 │ Type     │ Example                 │
├───────────────────────┼──────────┼─────────────────────────┤
│ userId                │ String   │ "google_123456"         │
│ email                 │ String   │ "user@example.com"      │
│ phoneNumber           │ String   │ "+15551234567"          │
│ isRegistered          │ Boolean  │ true                    │
│ isSubscribed          │ Boolean  │ true                    │◄─ Quick lookup
│ plan                  │ String   │ "monthly"               │◄─ free/monthly/annual
│ bibleVersion          │ String   │ "NIV"                   │
│ responseStyle         │ String   │ "gentle"                │
│ stripeCustomerId      │ String   │ "cus_ABC123"            │◄─ NEW
│ stripeSubscriptionId  │ String   │ "sub_XYZ789"            │◄─ NEW
│ subscriptionStatus    │ String   │ "active"                │◄─ NEW (active/past_due/canceled)
│ currentPeriodEnd      │ Number   │ 1738368000              │◄─ NEW (Unix timestamp)
│ cancelAtPeriodEnd     │ Boolean  │ false                   │◄─ NEW
│ plan_monthly_cap      │ Number   │ null                    │◄─ NEW (null=unlimited, 5=free)
│ updatedAt             │ String   │ "2025-12-22T10:00:00Z"  │
└───────────────────────┴──────────┴─────────────────────────┘
```

## Error Handling Matrix

| Error Scenario | Detection | Response | User Experience |
|----------------|-----------|----------|-----------------|
| Checkout fails (card declined) | Stripe returns error in checkout | Show error in UI | "Card declined. Please try another." |
| Webhook signature invalid | Lambda verifies signature | Return 401, log error | (Backend only, no user impact) |
| Webhook processing fails | Lambda throws exception | Return 500, Stripe retries | Webhook reprocessed automatically |
| Payment failure on renewal | `invoice.payment_failed` event | Update to `past_due`, send email | "Payment failed. Update payment method." |
| All retries exhausted | `subscription.deleted` event | Revert to free plan | "Subscription ended. Resubscribe anytime." |
| User has no Stripe customer | API call finds no customerId | Create new customer | Transparent to user |
| Duplicate webhook | Same event ID received twice | Idempotent update, same result | No duplicate charges or status changes |
| API Gateway timeout | Lambda exceeds 30s | Return 504 | "Request timeout. Please try again." |

## Security Flow

### Webhook Signature Verification

```
┌────────────────────────────────────────────────────────────────────┐
│                    Stripe Webhook Security                         │
└────────────────────────────────────────────────────────────────────┘

Stripe Server                          API Gateway         Webhook Lambda
     │                                      │                     │
     │ 1. Construct payload                 │                     │
     │    {event data...}                   │                     │
     │                                      │                     │
     │ 2. Generate signature                │                     │
     │    HMAC-SHA256(payload,              │                     │
     │                webhook_secret)       │                     │
     │                                      │                     │
     │ 3. POST /stripe/webhook              │                     │
     │    Headers:                          │                     │
     │    - Stripe-Signature: t=timestamp,  │                     │
     │      v1=signature                    │                     │
     │    Body: {event data...}             │                     │
     │─────────────────────────────────────>│                     │
     │                                      │ 4. Forward          │
     │                                      │───────────────────> │
     │                                      │                     │
     │                                      │         5. Extract  │
     │                                      │            signature│
     │                                      │            from     │
     │                                      │            header   │
     │                                      │                     │
     │                                      │         6. Verify   │
     │                                      │            using    │
     │                                      │            webhook  │
     │                                      │            secret   │
     │                                      │            from     │
     │                                      │            env vars │
     │                                      │                     │
     │                                      │         7. If valid,│
     │                                      │            process  │
     │                                      │            event    │
     │                                      │                     │
     │                                      │         8. If invalid│
     │                                      │            return 401│
     │                                      │<────────────────────│
     │<─────────────────────────────────────│                     │
     │                                      │                     │
     │ 9. If 401, mark webhook as failed    │                     │
     │    Retry later                       │                     │
```

**Key Security Points**:
1. ✅ Webhook endpoint has NO JWT auth (Stripe can't send JWT)
2. ✅ Instead, verify `Stripe-Signature` header using webhook secret
3. ✅ Webhook secret stored in AWS Secrets Manager
4. ✅ Signature includes timestamp to prevent replay attacks
5. ✅ Lambda rejects events with signature mismatch or too old

---

**Document Version**: 1.0  
**Last Updated**: December 22, 2025

