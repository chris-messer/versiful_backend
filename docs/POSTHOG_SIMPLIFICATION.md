# PostHog Simplification

## Date
2026-02-02

## Problem
Custom PostHog identification and aliasing logic was causing issues with user tracking:
- Race conditions between PostHog initialization and identify/alias calls
- Complex logic trying to link phone numbers, emails, and user IDs
- Events appearing as anonymous when they should be identified
- Inconsistent behavior between web signup, OAuth, and SMS flows

## Solution
Removed ALL custom PostHog identification and aliasing logic. Now using PostHog's default anonymous ID system.

## Changes Made

### Frontend Changes

#### 1. `src/pages/SignIn.jsx`
- **Removed**: All PostHog imports (`usePostHog`, `identifyInternalUser`)
- **Removed**: All `posthog.identify()` and `posthog.alias()` calls after signup/login
- **Result**: Users now get default anonymous PostHog IDs

#### 2. `src/pages/Callback.jsx`
- **Removed**: All PostHog imports (`usePostHog`, `identifyInternalUser`)
- **Removed**: All `posthog.identify()` and `posthog.alias()` calls after OAuth callback
- **Result**: Google OAuth users now get default anonymous PostHog IDs

#### 3. `src/components/welcome/WelcomeForm.jsx`
- **Removed**: PostHog import (`usePostHog`)
- **Removed**: Logic to alias phone number events to user ID when phone is submitted
- **Result**: Phone number submission no longer triggers any PostHog aliasing

#### 4. `src/context/AuthContext.jsx`
- **Removed**: `identifyInternalUser` import
- **Removed**: All PostHog identification logic in `checkLoginState()`
- **Result**: Auth state changes no longer trigger PostHog identification

### Backend Changes

#### 1. `lambdas/chat/agent_service.py`
- **Modified**: `_create_posthog_callback()` method
- **Before**: Complex logic to determine `distinct_id` based on user_id, phone_number, or session_id
- **After**: Sets `distinct_id = None` to let PostHog use its default anonymous ID
- **Result**: All LLM trace events now use PostHog's default anonymous IDs

## Benefits

1. **Simplicity**: No more complex identification logic to maintain
2. **Reliability**: No more race conditions or timing issues
3. **Consistency**: All events use PostHog's standard anonymous ID system
4. **Less Code**: Removed ~200 lines of custom identification code

## Trade-offs

1. **No User Linking**: Events are no longer linked to specific user accounts (email, phone)
2. **Anonymous Only**: All users appear as anonymous in PostHog
3. **No Cross-Device Tracking**: Cannot track same user across web and SMS
4. **No Historical Linking**: Cannot link pre-signup events to post-signup user account

## When to Use This Approach

✅ **Use when**:
- You want simple, reliable event tracking
- You don't need to identify specific users
- You want to avoid race conditions and timing issues
- You primarily care about aggregate analytics, not individual user journeys

❌ **Don't use when**:
- You need to track specific users by email or phone
- You need to link events across devices/channels
- You need to attribute pre-signup events to users after they sign up
- You need user-level analytics and cohort analysis

## Testing Plan

After deploying these changes:

1. **Web Signup Flow**
   - Visit site, generate anonymous events
   - Sign up with email/password
   - Verify all events show as anonymous (no user identification)

2. **OAuth Flow**
   - Visit site, generate anonymous events
   - Sign in with Google
   - Verify all events show as anonymous (no user identification)

3. **SMS Flow**
   - Text the number (unregistered)
   - Verify SMS events appear with anonymous ID
   - Register account with that phone number
   - Verify no linking occurs (SMS events stay separate)

4. **Backend Traces**
   - Check PostHog for LLM trace events
   - Verify they all have anonymous distinct_ids
   - Verify no custom user_id or phone_number identification

## Rollback Plan

If you need to restore user identification:
1. Revert this commit
2. Redeploy frontend and backend
3. Test the previous identification flow

## Notes

- The PostHog SDK is still initialized and working correctly
- Events are still being captured, just with anonymous IDs
- Session tracking still works (events grouped by session)
- The `internal_user` filtering is also removed (was part of identification logic)

## Files Modified

### Frontend
- `src/pages/SignIn.jsx`
- `src/pages/Callback.jsx`
- `src/components/welcome/WelcomeForm.jsx`
- `src/context/AuthContext.jsx`

### Backend
- `lambdas/chat/agent_service.py`

## Next Steps

1. Deploy changes to staging
2. Test all user flows (see Testing Plan above)
3. Monitor PostHog to verify events are being captured
4. Deploy to production once validated

