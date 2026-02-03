# PostHog User Tracking Implementation Complete

## Date
2026-02-03

## Summary
Implemented comprehensive PostHog user tracking using stable user IDs (DynamoDB UUIDs) with searchable person properties across all channels (web, SMS).

---

## Implementation Highlights

### Core Strategy
- **Primary Identifier**: `userId` (DynamoDB UUID) - stable, immutable
- **Person Properties**: email, phone_number, first_name, plan, is_subscribed, bible_version, etc. - searchable in PostHog
- **Anonymous SMS**: Uses `anon_sms_{phone_digits}` for unregistered users, stored in sms-usage table
- **History Linking**: `posthog.alias()` merges anonymous events when user registers

---

## Backend Changes

### 1. `lambdas/sms/sms_handler.py`
**Added**:
- PostHog client initialization
- `_get_or_create_posthog_id()` - manages anonymous SMS IDs in sms-usage table
- `_identify_sms_user()` - identifies registered/unregistered SMS users
- Updated `_invoke_chat_handler()` to pass `posthog_distinct_id`
- Added `uuid4` and `re` imports

**Flow**:
```
SMS arrives → Evaluate usage → Identify user in PostHog → Pass distinct_id to chat handler
```

### 2. `lambdas/chat/chat_handler.py`
**Added**:
- `posthog_distinct_id` parameter to `process_chat_message()`
- `posthog_distinct_id` parameter to `handler()`
- Pass-through to agent_service

### 3. `lambdas/chat/agent_service.py`
**Added**:
- `posthog_distinct_id` parameter to `process_message()`
- `posthog_distinct_id` parameter to `_generate_llm_response()`
- `posthog_distinct_id` parameter to `_create_posthog_callback()`
- Logic to use provided distinct_id over auto-generated one

**Flow**:
```
Uses posthog_distinct_id (if provided) > user_id > None (auto-generate)
```

### 4. `lambdas/users/helpers.py`
**Added**:
- PostHog client import
- `link_sms_history_to_user()` - aliases anonymous SMS ID to userId
- Updated `ensure_sms_usage_record()` to call linking function

**Flow**:
```
Phone added → Link userId in sms-usage → Look up posthogAnonymousId → Alias to userId
```

---

## Frontend Changes

### 1. `src/pages/SignIn.jsx`
**Added**:
- PostHog identification after successful login/signup
- Person properties: email, plan, is_subscribed, phone_number, etc.
- `posthog.alias()` to link anonymous web events to userId

**When**: Immediately after successful auth, before navigation

### 2. `src/pages/Callback.jsx`
**Added**:
- PostHog identification after OAuth callback
- Same person properties as SignIn
- `posthog.alias()` to link anonymous events

**When**: After successful OAuth authentication, before navigation

### 3. `src/components/welcome/WelcomeForm.jsx`
**Added**:
- PostHog phone number update
- `posthog.alias(userId, anon_sms_{phoneDigits})` to link SMS history
- Person properties update with phone, name, bible version

**When**: After user submits phone number in welcome form

### 4. `src/context/AuthContext.jsx`
**Added**:
- PostHog identification for logged-in users on page load
- Updates person properties (no aliasing)

**When**: On initial page load when auth state is checked

---

## User Journey Flows

### Flow 1: Unregistered SMS User
```
1. Text arrives from +15551234567
2. sms_handler checks sms-usage → no userId
3. _get_or_create_posthog_id() → generates UUID (e.g., "8a7b3c2d-...")
4. Stores in sms-usage: posthogAnonymousId = "8a7b3c2d-..."
5. PostHog identifies: distinct_id = "8a7b3c2d-...", properties = { phone_number: "+15551234567", registration_status: "unregistered" }
6. LLM traces tagged with "8a7b3c2d-..."
```

### Flow 2: Text → Register
```
Day 1: User texts (as above, gets anon ID "8a7b3c2d-...")

Day 3: User signs up on web
1. Sign up creates userId: "019c200b-..."
2. posthog.identify("019c200b-...", { email: "user@example.com", ... })
3. posthog.alias("019c200b-...", web_anon_id)

Day 3: User adds phone in welcome form
4. Updates sms-usage with userId
5. users/helpers.py calls link_sms_history_to_user()
6. Looks up posthogAnonymousId: "8a7b3c2d-..."
7. posthog.alias("019c200b-...", "8a7b3c2d-...")
8. ALL SMS events from Day 1 now merged into user profile!
```

### Flow 3: Register → Text
```
Day 1: User registers on web
1. Sign up creates userId: "019c300c-..."
2. posthog.identify("019c300c-...", { email: "user@example.com", ... })
3. User adds phone: +15559876543
4. Updates sms-usage with userId (no posthogAnonymousId yet)
5. link_sms_history_to_user() finds no SMS history → skip alias

Day 3: User texts from +15559876543
6. sms_handler looks up sms-usage → finds userId!
7. _identify_sms_user() uses userId: "019c300c-..."
8. PostHog identifies: distinct_id = "019c300c-...", properties = { email, phone, ... }
9. LLM traces tagged with "019c300c-..."
10. SMS and web events show under ONE profile!
```

---

## Database Schema Update

### `{env}-versiful-sms-usage` Table
**New Field**:
- `posthogAnonymousId` (String) - UUID for unregistered SMS users
- Stores the anonymous PostHog distinct_id for later linking

**Usage**:
- Created when unregistered user first texts
- Used to link SMS history when user registers
- Remains in record even after user registers (for audit trail)

---

## PostHog Schema

### Person Profile
```json
{
  "distinct_id": "019c200b-f248-7253-8869-e0dc2fe874e6",
  "properties": {
    "email": "user@example.com",
    "phone_number": "+15551234567",
    "first_name": "John",
    "last_name": "Doe",
    "plan": "free",
    "is_subscribed": false,
    "bible_version": "KJV",
    "registration_status": "registered",
    "channel": "sms",
    "created_at": "2026-02-03T10:30:00Z"
  }
}
```

### Searchable Queries
- `email = "user@example.com"` - Find by email
- `phone_number = "+15551234567"` - Find by phone
- `registration_status = "unregistered"` - All anonymous users
- `is_subscribed = true` - All paid users

---

## Key Benefits

✅ **Stable Identity**: UUID never changes  
✅ **Cross-Channel**: Same userId for web + SMS  
✅ **Human-Readable**: Search by email/phone  
✅ **Anonymous Support**: Unregistered users can text  
✅ **Historical Linking**: Pre-registration events preserved  
✅ **Privacy-Friendly**: No phone in distinct_id  

---

## Files Modified

### Backend (4 files)
1. `lambdas/sms/sms_handler.py` - SMS user identification
2. `lambdas/chat/chat_handler.py` - Pass-through distinct_id
3. `lambdas/chat/agent_service.py` - Use distinct_id for traces
4. `lambdas/users/helpers.py` - Link SMS history

### Frontend (4 files)
1. `src/pages/SignIn.jsx` - Web signup identification
2. `src/pages/Callback.jsx` - OAuth identification
3. `src/components/welcome/WelcomeForm.jsx` - Phone linking
4. `src/context/AuthContext.jsx` - Logged-in state

---

## Testing Checklist

- [ ] Test unregistered SMS user (should get anon ID)
- [ ] Test registered SMS user (should use userId)
- [ ] Test web signup → phone add → SMS (should merge history)
- [ ] Test SMS → web signup (should merge history)
- [ ] Check PostHog person properties are searchable
- [ ] Verify LLM traces tagged with correct distinct_id

---

## Next Steps

1. Deploy to dev environment
2. Test all user flows
3. Deploy to staging
4. Monitor PostHog events
5. Deploy to production

## Documentation
- Full implementation plan: `docs/POSTHOG_USER_TRACKING_PLAN.md`

