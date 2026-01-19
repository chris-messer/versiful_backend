# Richard's User Record - Comparison & Fix Plan

## User Information
**Richard Rodriguez**
- Email: richie.rich8696@gmail.com
- Phone: +18455548473
- UUID: c428a478-e031-705e-db1d-fe9577d74a24

---

## Field Comparison

### ✅ Fields Richard Currently Has
| Field | Value | Status |
|-------|-------|--------|
| `userId` | c428a478-e031-705e-db1d-fe9577d74a24 | ✅ Correct |
| `email` | richie.rich8696@gmail.com | ✅ Correct |
| `firstName` | Richard | ✅ Correct |
| `lastName` | Rodriguez | ✅ Correct |
| `phoneNumber` | +18455548473 | ✅ Correct |
| `bibleVersion` | KJV | ✅ Correct |
| `isRegistered` | true | ✅ Correct |
| `isSubscribed` | true | ✅ Correct (manually fixed) |
| `stripeCustomerId` | cus_Toz6CdFWeVRNJL | ✅ Correct |

### ❌ Fields Richard Is Missing (Present in Staging Test User)
| Field | Expected Value | Currently | Impact |
|-------|---------------|----------|---------|
| `stripeSubscriptionId` | sub_xxxxx | **MISSING** | ⚠️ Can't track subscription in Stripe |
| `plan` | "monthly" or "annual" | **MISSING** | ⚠️ Unknown which plan |
| `plan_monthly_cap` | -1 (unlimited) | **MISSING** | 🚨 **CRITICAL** - SMS limit not set |
| `subscriptionStatus` | "active" | **MISSING** | ⚠️ Can't check status |
| `cancelAtPeriodEnd` | false | **MISSING** | ⚠️ Can't track cancellation |
| `currentPeriodEnd` | Unix timestamp | **MISSING** | ⚠️ Can't track billing cycle |
| `updatedAt` | ISO timestamp | **MISSING** | Minor - audit trail |

---

## Impact Analysis

### 🚨 CRITICAL ISSUE: `plan_monthly_cap`
**Problem:** Without this field set to `-1`, Richard will hit the free tier 5-message limit.

**Current behavior:**
- SMS handler checks `plan_monthly_cap` field
- If missing or not `-1`, defaults to free tier limit (5 messages/month)
- Richard will get "limit reached" errors again

**SMS Handler Logic:**
```python
if user_profile and user_profile.get("plan_monthly_cap") is not None:
    limit = int(user_profile["plan_monthly_cap"])
    if limit == -1:  # Unlimited
        return allowed
else:
    limit = FREE_MONTHLY_LIMIT  # 5 messages
```

### ⚠️ Missing Subscription Tracking
Without `stripeSubscriptionId`:
- Can't look up subscription in Stripe
- Can't handle subscription updates (cancellation, renewal)
- Can't process webhook events properly

### ⚠️ Missing Billing Information
Without `currentPeriodEnd`:
- Can't show when subscription renews
- Can't warn user before billing
- Frontend can't display billing date

---

## Fix Plan

### Option 1: Get Data from Stripe (Recommended)
**Steps:**
1. Look up Richard's Stripe subscription using his customer ID: `cus_Toz6CdFWeVRNJL`
2. Retrieve subscription details (subscription ID, plan, period end, status)
3. Update DynamoDB with all missing fields

**Advantages:**
- Accurate data from source of truth
- Ensures consistency with Stripe

**Command to get Stripe data:**
```bash
stripe customers retrieve cus_Toz6CdFWeVRNJL --expand subscriptions
```

### Option 2: Manual Entry (Faster but less reliable)
**If we can't access Stripe or subscription doesn't exist:**
1. Set `plan_monthly_cap` to `-1` (CRITICAL - enables unlimited SMS)
2. Set `subscriptionStatus` to "active"
3. Set `cancelAtPeriodEnd` to false
4. Set `plan` to "monthly" (or "annual" if known)
5. Set `updatedAt` to current timestamp
6. Leave `stripeSubscriptionId` and `currentPeriodEnd` empty for now

**Minimum Required Fields:**
```json
{
  "plan_monthly_cap": -1,
  "subscriptionStatus": "active",
  "cancelAtPeriodEnd": false
}
```

---

## Recommended Approach

### Step 1: Query Stripe
```bash
# Get Richard's customer details with subscriptions
stripe customers retrieve cus_Toz6CdFWeVRNJL --expand subscriptions
```

### Step 2: Extract Values
From Stripe response, we need:
- `subscriptions.data[0].id` → `stripeSubscriptionId`
- `subscriptions.data[0].items.data[0].price.recurring.interval` → `plan` ("monthly" or "annual")
- `subscriptions.data[0].current_period_end` → `currentPeriodEnd`
- `subscriptions.data[0].status` → `subscriptionStatus`
- `subscriptions.data[0].cancel_at_period_end` → `cancelAtPeriodEnd`

### Step 3: Update DynamoDB
```bash
aws dynamodb update-item \
  --table-name prod-versiful-users \
  --key '{"userId": {"S": "c428a478-e031-705e-db1d-fe9577d74a24"}}' \
  --update-expression "SET ..." \
  --expression-attribute-values '...'
```

---

## Next Steps

1. **Retrieve Stripe data** for customer `cus_Toz6CdFWeVRNJL`
2. **Verify subscription exists** in Stripe
3. **Extract all required fields** from Stripe response
4. **Update DynamoDB** with complete subscription data
5. **Verify SMS works** by testing message count

**Priority:** HIGH - Richard could hit the 5-message limit again without `plan_monthly_cap: -1`

---

## Testing After Fix
1. Check Richard's user record has all fields
2. Verify `plan_monthly_cap` is `-1`
3. Send test SMS to confirm unlimited messages work
4. Check subscription displays correctly in frontend

