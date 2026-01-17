# PostHog Multi-Environment Tracking

## Overview

PostHog now tracks user activity across **all environments** (dev, staging, production) with environment filtering. This provides better debugging, development experience, and eliminates the need to deploy to production just to test PostHog features.

## What Changed

### Before (Prod-Only Tracking)
```javascript
opt_out_capturing_by_default: config.environment !== 'prod'
```
- Only production was tracked
- Testing PostHog required deploying to prod
- Debugging issues in dev/staging was impossible

### After (Multi-Environment Tracking)
```javascript
opt_out_capturing_by_default: false
```
- All environments tracked (dev/staging/prod)
- Each event tagged with `environment` and `domain` properties
- Filter in PostHog dashboard to view specific environments

## Event Properties

Every event now includes these super properties:

| Property | Type | Example | Description |
|----------|------|---------|-------------|
| `environment` | String | `prod`, `staging`, `dev` | Environment from config.json |
| `domain` | String | `versiful.io`, `staging.versiful.io`, `dev.versiful.io` | Full hostname |
| `internal_user` | Boolean | `true`, `false` | Internal team member flag (optional) |
| `user_type` | String | `internal` | Type of user (optional) |
| `testing_environment` | String | `localhost` | Set when running locally (optional) |

## Filtering in PostHog

### View Production Only
In any insight, cohort, or dashboard:
```
Filter: environment = 'prod'
```

### View Staging Only
```
Filter: environment = 'staging'
```

### View Development Activity
```
Filter: environment = 'dev'
```

### Exclude Internal Users
```
Filter: internal_user != true
```

### Production Users Only (No Internal)
```
Filter: environment = 'prod' AND internal_user != true
```

## Console Logging

When PostHog initializes, you'll see in the browser console:
```javascript
📊 PostHog initialized - Environment: prod
```

This confirms which environment is being tracked.

## Benefits

### 1. Better Development Experience
- Test PostHog features in dev without deploying to prod
- Verify user identification works before going live
- Debug issues in safe environments

### 2. Faster Iteration
- No need to wait for prod deployments to test analytics
- Catch issues early in dev/staging
- Rapid prototyping of new tracking

### 3. Comprehensive Testing
- Test user flows across environments
- Verify funnel tracking in staging
- Validate cohort logic before production

### 4. Single Source of Truth
- All user analytics in one place
- Compare behavior across environments
- Spot environment-specific issues

## Example: Testing New Feature

**Before** (Prod-Only Tracking):
1. Implement feature in dev
2. Deploy to staging (no PostHog data)
3. Deploy to prod
4. Hope it works
5. Debug issues in prod (risky!)

**After** (Multi-Environment Tracking):
1. Implement feature in dev
2. Test PostHog tracking in dev ✅
3. Deploy to staging
4. Verify tracking in staging ✅
5. Deploy to prod with confidence! ✅

## Internal User Tagging

Mark yourself as internal to filter your activity:

### In Browser Console
```javascript
// Mark as internal (persists in localStorage)
window.markAsInternal()

// Remove internal flag
window.unmarkAsInternal()
```

### Manual Flag
```javascript
localStorage.setItem('versiful_internal', 'true')
// Refresh page
```

Internal users get these properties:
```javascript
{
  internal_user: true,
  user_type: 'internal'
}
```

## Dashboard Setup

### Production Dashboard
Create a dashboard filtered to production only:

1. Create new dashboard: "Production Metrics"
2. Add global filter: `environment = 'prod' AND internal_user != true`
3. All insights automatically filtered

### Development Dashboard
Track development activity:

1. Create dashboard: "Dev/Staging Activity"
2. Add global filter: `environment IN ['dev', 'staging']`
3. Monitor testing and development usage

### Combined Dashboard
See all environments side-by-side:

1. Create dashboard: "Cross-Environment Comparison"
2. Create insights with breakdown by `environment`
3. Compare metrics across dev/staging/prod

## Example Insights

### User Signups by Environment
```
Event: user_signed_up
Breakdown by: environment
```

### Production Active Users (No Internal)
```
Event: any event
Filters: 
  - environment = 'prod'
  - internal_user != true
Unique users: distinct_id
```

### Feature Adoption Across Environments
```
Event: feature_used
Breakdown by: environment
Show: unique users
```

## Cost Considerations

### PostHog Free Tier
- **Before**: ~100K events/month (prod only)
- **After**: ~300K events/month (all environments)
- **Free tier**: 1M events/month ✅

Most dev/staging activity is from internal testing, so actual increase is minimal.

### Filtering Internal Users
If cost becomes a concern, opt out internal users:
```javascript
// In posthogHelpers.js
export const optOutInternalUsers = (posthog, userEmail) => {
  if (isInternalEmail(userEmail)) {
    posthog.opt_out_capturing();
  }
};
```

## Migration Notes

### Existing Users
Users who were previously tracked in prod will continue working seamlessly. Their person profiles are preserved.

### New Environments
When deploying to dev/staging for the first time:
1. Events will start flowing immediately
2. Use filters to isolate production data
3. Set up environment-specific dashboards

## Troubleshooting

### Events Not Showing for Dev/Staging

**Check**:
1. Browser console: `posthog.get_distinct_id()` - should return ID
2. Console: Look for `📊 PostHog initialized - Environment: dev`
3. Network tab: Check for requests to `us.i.posthog.com`

**Fix**:
- Clear browser cache
- Check `/config.json` has correct environment
- Verify PostHog API key in config

### Too Many Events in Dashboard

**Filter**:
- Add `environment = 'prod'` filter to insights
- Use internal_user filter to exclude team
- Create environment-specific dashboards

### Localhost Events

Localhost automatically tagged with:
```javascript
{
  testing_environment: 'localhost',
  domain: 'localhost'
}
```

Filter out: `domain != 'localhost'`

## Best Practices

### 1. Use Environment Filters
Always add environment filter when creating production insights:
```
environment = 'prod'
```

### 2. Create Environment Dashboards
Separate dashboards for each environment avoids confusion

### 3. Mark Yourself as Internal
Use `window.markAsInternal()` to exclude your testing from metrics

### 4. Document Custom Events
Add environment context when capturing custom events:
```javascript
posthog.capture('custom_event', {
  // environment automatically included
  custom_property: value
});
```

### 5. Test Before Production
Verify tracking works in dev/staging before deploying

## Related Documentation

- [PostHog User Identification](./POSTHOG_USER_IDENTIFICATION.md) - How users are identified
- [PostHog LLM Tracing](./POSTHOG_LLM_TRACING.md) - Backend LLM analytics
- [PostHog Official Docs](https://posthog.com/docs) - Official documentation

## Changelog

**2026-01-17**: Enabled multi-environment tracking
- Changed `opt_out_capturing_by_default` to `false`
- Added `environment` and `domain` super properties
- Added environment logging
- Updated documentation

---

**Implementation Date**: 2026-01-17  
**Status**: ✅ Live in All Environments  
**Deployment**: Followed dev → staging → prod workflow

