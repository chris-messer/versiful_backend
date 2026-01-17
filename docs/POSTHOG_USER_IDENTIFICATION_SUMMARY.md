# PostHog User Identification - Implementation Summary

## Overview
Implemented proper user identification in PostHog so users appear with meaningful identifiers (email, name) instead of anonymous UUIDs. Now all user activity across web and SMS is properly tracked and linked.

## Problem Solved
**Before**: Users showed up as random UUIDs in PostHog even when logged in
**After**: Users identified by Cognito userId with full profile data (email, name, subscription, preferences)

## Changes Made

### Frontend Changes

#### 1. AuthContext.jsx (`versiful-frontend/src/context/AuthContext.jsx`)
**Updated `checkLoginState()` function**:
- Added `posthog.identify()` call when user data is loaded
- Uses `userData.userId` as distinct_id (Cognito user ID)
- Sets person properties: email, name, phone, subscription, preferences

**Added `logout()` function**:
- Calls `posthog.reset()` to unlink future events from logged-out user
- Critical for shared devices to prevent data leakage

**Exported new values**:
- Added `logout` and `user` to context provider

#### 2. posthogHelpers.js (`versiful-frontend/src/utils/posthogHelpers.js`)
**Added `identifyUser()` function**:
- Reusable function for identifying users across the app
- Builds person properties from userData object
- Handles optional fields gracefully

**Updated `identifyInternalUser()` function**:
- Now only sets internal_user flag (doesn't duplicate identify call)
- Simplified to avoid double identification

#### 3. Navbar.jsx (`versiful-frontend/src/components/Navbar.jsx`)
**Updated logout handler**:
- Now uses `logout()` from AuthContext
- Ensures PostHog reset happens consistently

### Backend Changes

**No changes needed!** 

Backend already properly configured:
- `agent_service.py` prioritizes userId over phone number for distinct_id
- SMS handler passes userId to chat handler when available
- LLM tracing already links events to correct user

## User Identification Strategy

| Context | Distinct ID | Example |
|---------|-------------|---------|
| **Logged-in web user** | Cognito `userId` | `google_123456` |
| **SMS user (registered)** | Cognito `userId` (via phone lookup) | `google_123456` |
| **SMS user (unregistered)** | Phone number (digits only) | `15551234567` |
| **Anonymous visitor** | Auto-generated UUID | `1a2b3c4d-...` |

**Key**: Always use Cognito userId when available to link activity across channels.

## Person Properties

All identified users have these properties in PostHog:

**Core Properties**:
- `email` - User's email address
- `is_subscribed` - Boolean subscription status
- `plan` - Subscription plan (free/monthly/annual)

**Optional Properties** (when available):
- `phone_number` - E.164 format (e.g., +15551234567)
- `first_name`, `last_name` - User's name
- `bible_version` - Preferred Bible translation (NIV, KJV, etc.)
- `response_style` - Preferred response style
- `internal_user` - Boolean flag for filtering team members

## Testing

### Manual Test (Web)

1. **Open browser console and log in**:
   ```javascript
   // After login, check distinct_id
   posthog.get_distinct_id()
   // Should return Cognito userId (e.g., "google_123456")
   ```

2. **Verify in PostHog**:
   - Go to PostHog dashboard → Persons
   - Search by your email
   - Should see person profile with all properties
   - Events should be linked to this person

3. **Test logout reset**:
   ```javascript
   // Before logout
   posthog.get_distinct_id() // → "google_123456"
   
   // After logout
   posthog.get_distinct_id() // → New UUID (e.g., "1a2b3c4d...")
   ```

### Manual Test (SMS)

1. **Register an account with phone number** via web
2. **Send SMS** from that phone number
3. **Check PostHog** → Search by phone or email
4. **Verify** both web and SMS events are linked to same person

### Expected Results

✅ **In PostHog Persons tab**:
- Users show with email addresses instead of UUIDs
- Person profiles have full property data
- Events grouped correctly by person

✅ **Cross-platform tracking**:
- SMS and web activity linked for registered users
- Same distinct_id used across all channels

✅ **Logout behavior**:
- New distinct_id generated after logout
- Previous user's events not linked to new anonymous session

## Deployment

### Frontend Deployment

Changes are frontend-only, no backend deployment needed:

```bash
cd /Users/christopher.messer/WebstormProjects/versiful-frontend

# Test locally first
npm run dev
# Visit http://localhost:5173, log in, check console

# Deploy to dev
git add src/context/AuthContext.jsx src/components/Navbar.jsx src/utils/posthogHelpers.js
git commit -m "feat: Implement proper PostHog user identification"
git push origin dev

# Amplify will auto-deploy
```

### Verification Steps

1. **Deploy to dev environment**
2. **Log in with test account**
3. **Check browser console**: `posthog.get_distinct_id()`
4. **Navigate in app** (trigger some events)
5. **Check PostHog dashboard**:
   - Go to Persons → Search by test email
   - Verify person profile exists with properties
   - Verify recent events linked to this person
6. **Test logout**: Check distinct_id changes
7. **If working in dev**: Deploy to staging → prod

## Privacy & Compliance

### Data Collected
- Cognito userId (anonymous to external parties)
- Email address (for identification)
- Phone number (if provided by user)
- Name (if provided by user)
- Subscription and preference data

### User Rights
Users can:
- Request data deletion (remove person from PostHog)
- Opt out of tracking (future feature)

### Data Retention
- Events retained indefinitely (PostHog free tier)
- Person profiles can be manually deleted if user requests

## Troubleshooting

### Issue: Users still showing as UUIDs

**Check**:
1. Is `posthog.identify()` being called in AuthContext?
2. Does `userData.userId` exist in the API response?
3. Is PostHog initialized before identify is called?

**Debug**:
```javascript
// In AuthContext.jsx, add logging
console.log('userData:', userData);
console.log('posthog:', posthog);
console.log('calling identify with userId:', userData.userId);
```

### Issue: Identify not happening on page load

**Check**:
1. AuthContext useEffect depends on `[posthog]`
2. PostHog loads before AuthContext runs
3. Auth cookies are present (check Network tab)

**Fix**: Ensure `checkLoginState()` is called after PostHog initializes

### Issue: Events duplicated or linked to wrong user

**Check**:
1. Is `posthog.reset()` called on logout?
2. Are cookies cleared properly?
3. Is identify called multiple times unnecessarily?

## Files Changed

### Frontend
- ✅ `versiful-frontend/src/context/AuthContext.jsx`
- ✅ `versiful-frontend/src/components/Navbar.jsx`
- ✅ `versiful-frontend/src/utils/posthogHelpers.js`

### Backend
- ℹ️ No changes (already properly configured)

### Documentation
- 📄 `versiful-backend/docs/POSTHOG_USER_IDENTIFICATION.md` (comprehensive guide)
- 📄 `versiful-backend/docs/POSTHOG_USER_IDENTIFICATION_SUMMARY.md` (this file)

## Related Documentation

- [PostHog User Identification Guide](./POSTHOG_USER_IDENTIFICATION.md) - Detailed technical guide
- [PostHog LLM Tracing](./POSTHOG_LLM_TRACING.md) - Backend LLM analytics
- [PostHog Official Docs - Identify](https://posthog.com/docs/product-analytics/identify)

## Next Steps

1. **Deploy to dev** and test with real account
2. **Verify** users appear correctly in PostHog dashboard
3. **Monitor** for 24-48 hours to ensure no issues
4. **Deploy to staging** → test again
5. **Deploy to production** when confident

## Success Metrics

After deployment, you should see:
- ✅ 90%+ of events tied to identified users (not UUIDs)
- ✅ Person profiles with complete property data
- ✅ SMS and web activity properly linked for registered users
- ✅ Clean separation after logout (no data leakage)

---

**Implementation Date**: 2026-01-17  
**Status**: ✅ Complete - Ready for Testing  
**Testing Required**: Yes (manual testing in dev environment)

