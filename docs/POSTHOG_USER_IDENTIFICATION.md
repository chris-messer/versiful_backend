# PostHog User Identification Guide

## Overview

This document explains how user identification works in PostHog across both frontend and backend systems, ensuring users are properly tracked with meaningful identifiers instead of anonymous UUIDs.

## User Identification Strategy

### Distinct ID Strategy

PostHog uses `distinct_id` as the primary user identifier. Versiful uses a **consistent** distinct_id strategy:

| Context | Distinct ID | Person Properties |
|---------|-------------|-------------------|
| **Logged-in Web User** | Cognito `userId` (e.g., `google_123456` or `cognito-sub-xyz`) | email, name, phone, subscription details, preferences |
| **SMS User (with account)** | Cognito `userId` (linked via phone lookup) | email, name, phone, subscription details, preferences |
| **SMS User (no account)** | Phone number (digits only, e.g., `15551234567`) | phone_number |
| **Anonymous Web User** | Auto-generated UUID (by PostHog SDK) | None (tracked but not identified) |

**Key Principle**: Use Cognito `userId` whenever available to link activity across channels (web + SMS).

## Implementation Details

### Frontend Identification

#### Location: `versiful-frontend/src/context/AuthContext.jsx`

When a user logs in, `AuthContext` identifies them in PostHog:

```javascript
const checkLoginState = async () => {
    const userData = await fetch(`${API_BASE}/users`, ...);
    
    if (response.ok && userData && posthog) {
        // Identify user with Cognito userId as distinct_id
        posthog.identify(userData.userId, {
            email: userData.email,
            is_subscribed: userData.isSubscribed || false,
            plan: userData.plan || 'free',
            phone_number: userData.phoneNumber,
            first_name: userData.firstName,
            last_name: userData.lastName,
            bible_version: userData.bibleVersion,
            response_style: userData.responseStyle
        });
    }
};
```

**When identification happens**:
- On app load (if user is already logged in)
- After successful login
- After OAuth callback
- After registration

#### Helper Function: `versiful-frontend/src/utils/posthogHelpers.js`

A reusable `identifyUser()` function handles all identification logic:

```javascript
export const identifyUser = (posthog, userData) => {
  posthog.identify(userData.userId, {
    email: userData.email,
    is_subscribed: userData.isSubscribed || false,
    plan: userData.plan || 'free',
    // ... other properties
  });
};
```

#### Logout and Reset

When users log out, PostHog is reset to unlink future events:

```javascript
const logout = async () => {
    await fetch(`${API_BASE}/auth/logout`, ...);
    
    // Reset PostHog to prevent linking future events to this user
    if (posthog) {
        posthog.reset();
    }
    
    setIsLoggedIn(false);
    setUser(null);
};
```

**Important**: `posthog.reset()` is critical for shared devices to prevent user data leakage.

### Backend Identification

#### Location: `versiful-backend/lambdas/chat/agent_service.py`

The backend automatically identifies users in PostHog during LLM tracing:

```python
def _create_posthog_callback(
    self,
    thread_id: str,
    channel: str,
    phone_number: str = None,
    user_id: str = None,
    trace_id: str = None
) -> Optional[CallbackHandler]:
    # Determine distinct_id based on available information
    if user_id:
        distinct_id = user_id  # ✅ Prioritize userId (matches frontend)
    elif phone_number:
        distinct_id = re.sub(r'\D', '', phone_number)  # Fallback to phone
    else:
        distinct_id = session_id  # Last resort
    
    callback_handler = CallbackHandler(
        client=self.posthog,
        distinct_id=distinct_id,
        properties={
            "conversation_id": session_id,
            "$ai_session_id": session_id,
            "channel": channel
        }
    )
```

**User ID is passed from**:
1. **Web Chat**: JWT authorizer extracts `userId` from token
2. **SMS**: SMS handler looks up userId from phone number in DynamoDB

#### SMS Handler: `versiful-backend/lambdas/sms/sms_handler.py`

When processing SMS messages, the handler attempts to find the associated userId:

```python
# Get user_id if available (links SMS activity to logged-in user)
user_id = decision.get("user_profile", {}).get("userId")

# Invoke chat handler with both phone and userId
chat_result = _invoke_chat_handler(
    thread_id=from_num_normalized,
    message=body,
    user_id=user_id,  # ✅ Passed to PostHog if available
    phone_number=from_num_normalized
)
```

## Person Properties

### Core Properties

These properties are set for all identified users:

| Property | Type | Example | Source |
|----------|------|---------|--------|
| `email` | String | `user@example.com` | Cognito + DynamoDB |
| `is_subscribed` | Boolean | `true` | DynamoDB users table |
| `plan` | String | `monthly`, `annual`, `free` | DynamoDB users table |

### Optional Properties

These are included when available:

| Property | Type | Example | Notes |
|----------|------|---------|-------|
| `phone_number` | String | `+15551234567` | E.164 format |
| `first_name` | String | `John` | From welcome form |
| `last_name` | String | `Doe` | From welcome form |
| `bible_version` | String | `NIV`, `KJV` | User preference |
| `response_style` | String | `gentle`, `direct` | User preference |
| `internal_user` | Boolean | `true` | For filtering internal team |

### Internal User Filtering

Internal/admin users are tagged for easy filtering:

```javascript
// In posthogHelpers.js
export const identifyInternalUser = (posthog, userEmail) => {
  const internalEmails = [
    'christopher.messer@versiful.io',
    'chris@versiful.io',
    // ...
  ];
  
  if (isInternal) {
    posthog.register({
      internal_user: true,
      user_type: 'internal'
    });
  }
};
```

**Filter internal users in PostHog**:
- Dashboard filter: `internal_user = false`
- Insight filter: `Where user_type != internal`

## Data Flow

### Web User Journey

```
1. User logs in via Google OAuth or email/password
   ↓
2. AuthContext fetches /users endpoint with auth cookies
   ↓
3. User data loaded (userId, email, phone, preferences)
   ↓
4. posthog.identify(userId, {...properties})
   ↓
5. All future events tied to this userId
   ↓
6. User chats → Events sent with distinct_id = userId
   ↓
7. User logs out → posthog.reset() called
```

### SMS User Journey (Registered)

```
1. User texts Versiful number
   ↓
2. SMS handler receives message with phone number
   ↓
3. Lookup phone in sms-usage table → find userId
   ↓
4. Invoke chat handler with userId + phone_number
   ↓
5. LLM trace events sent with distinct_id = userId
   ↓
6. Events automatically linked to web activity (same userId)
```

### SMS User Journey (Unregistered)

```
1. User texts Versiful number (no account)
   ↓
2. SMS handler receives message with phone number
   ↓
3. Lookup phone → no userId found
   ↓
4. Invoke chat handler with phone_number only
   ↓
5. LLM trace events sent with distinct_id = phone (digits only)
   ↓
6. If user later registers → posthog.alias() links old phone to new userId
```

## Cross-Platform Tracking

### Linking SMS and Web Activity

When a user interacts via both SMS and web:

1. **User creates account via web** → identified with `userId`
2. **User adds phone number** → stored in DynamoDB
3. **User texts Versiful** → SMS handler looks up userId from phone
4. **Both channels use same userId** → activity automatically linked

### Alias for Merging Identities

If needed, use PostHog's alias to merge anonymous and identified users:

```javascript
// If user was tracked anonymously, then logged in
const anonymousId = posthog.get_distinct_id();
posthog.alias(userData.userId, anonymousId);
```

**Currently**: Not implemented (most users identify immediately upon signup).

## Best Practices

### ✅ Do's

1. **Call identify early** - As soon as user data is available
2. **Use consistent IDs** - Always use Cognito userId when available
3. **Reset on logout** - Prevent data leakage on shared devices
4. **Set person properties** - Enrich profiles with subscription, preferences
5. **Filter internal users** - Use `internal_user` property in dashboards

### ❌ Don'ts

1. **Don't identify with email** - Use userId as distinct_id, email as property
2. **Don't identify multiple times unnecessarily** - PostHog deduplicates
3. **Don't forget to reset** - Critical for logout flow
4. **Don't expose sensitive data** - No passwords, tokens, or PII beyond necessary

## Debugging

### Check Current User Identity

**Frontend**:
```javascript
const currentDistinctId = posthog.get_distinct_id();
console.log('Current PostHog distinct_id:', currentDistinctId);
```

**PostHog Dashboard**:
1. Go to Persons tab
2. Search by email or userId
3. View person profile → distinct IDs → events

### Verify Identification

**Expected**:
- Logged-in users: distinct_id = Cognito userId (e.g., `google_123456`)
- Anonymous users: distinct_id = UUID (e.g., `1a2b3c4d-...`)
- SMS-only users: distinct_id = phone digits (e.g., `15551234567`)

**Check event**:
```javascript
posthog.capture('test_event', { source: 'debug' });
// Look for this event in PostHog → should have correct distinct_id
```

### Common Issues

#### Issue: Users showing as UUIDs in PostHog

**Cause**: `posthog.identify()` not called or called with wrong data

**Fix**: 
- Check AuthContext is calling identify after user data loads
- Verify userData.userId exists
- Check PostHog instance is initialized

#### Issue: SMS and web activity not linked

**Cause**: userId not passed from SMS handler to chat handler

**Fix**:
- Verify phone number is stored in users table
- Check sms-usage table has userId field
- Ensure SMS handler passes user_id to chat handler

#### Issue: Users not resetting on logout

**Cause**: `posthog.reset()` not called

**Fix**:
- Verify logout function calls `posthog.reset()`
- Check PostHog instance is available in logout context

## Testing

### Manual Testing

#### Test Web Identification

1. Open browser DevTools → Console
2. Log out (if logged in)
3. Check distinct_id: `posthog.get_distinct_id()` → Should be UUID
4. Log in with test account
5. Check distinct_id again → Should be Cognito userId
6. Navigate to PostHog → Persons → Search by email → View events

#### Test SMS Identification

1. Register account via web with phone number
2. Send SMS from that phone number
3. Check PostHog → Search by phone number or email
4. Verify both web and SMS events linked to same person

#### Test Logout Reset

1. Log in → Note distinct_id
2. Capture test event: `posthog.capture('before_logout')`
3. Log out
4. Check distinct_id → Should change to new UUID
5. Capture test event: `posthog.capture('after_logout')`
6. In PostHog → Events should be under different persons

## Environment Considerations

User identification works the same across all environments:

- **Dev**: `https://dev.versiful.io` (test accounts)
- **Staging**: `https://staging.versiful.io` (pre-prod testing)
- **Production**: `https://versiful.io` (real users)

**Note**: Same PostHog project key used across all environments (filtered by environment property in events).

## Privacy & Compliance

### Data Collected

**Personal Identifiers**:
- Cognito userId (UUID or provider ID)
- Email address
- Phone number (E.164 format)

**Profile Data**:
- First and last name (optional)
- Subscription status and plan
- Bible version and response style preferences

**Not Collected**:
- Passwords or authentication tokens
- Payment information (handled by Stripe)
- Full message content (only metadata and summaries)

### User Rights

Users have the right to:
- **Access**: View their data in PostHog
- **Deletion**: Remove person profile via PostHog admin
- **Opt-out**: Disable tracking (future feature)

### Retention

- **Events**: Retained indefinitely (free tier)
- **Person profiles**: Retained while active
- **Deleted users**: Can be manually removed from PostHog

## Related Documentation

- [PostHog LLM Tracing](./POSTHOG_LLM_TRACING.md) - Backend LLM analytics
- [PostHog Implementation Summary](./POSTHOG_IMPLEMENTATION_SUMMARY.md) - Initial setup
- [PostHog Official Docs - Identifying Users](https://posthog.com/docs/product-analytics/identify)
- [Frontend PostHog Setup](../../../versiful-frontend/POSTHOG_SETUP_COMPLETE.md)

## Changelog

**2026-01-17**: Initial documentation
- Documented consistent userId-based identification across frontend and backend
- Added logout reset flow
- Included cross-platform tracking strategy
- Added debugging and testing guides

---

**Questions?** Check CloudWatch logs (frontend: browser console, backend: Lambda logs) or PostHog dashboard (Persons tab).

