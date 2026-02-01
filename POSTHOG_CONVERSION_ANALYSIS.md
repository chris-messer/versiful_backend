# PostHog Conversion Analysis Guide

## Quick Start - Run the Analysis

```bash
cd /Users/christopher.messer/PycharmProjects/versiful-backend

# Install requests if needed
pip install requests

# Set your PostHog credentials
export POSTHOG_API_KEY="phc_your_key_here"
export POSTHOG_PROJECT_ID="your_project_id"

# Run the analysis
python scripts/analyze_posthog_conversion.py
```

## How to Get Your PostHog Credentials

### 1. API Key
1. Go to https://app.posthog.com/project/settings
2. Look for **"Project API Key"** (starts with `phc_...`)
3. Copy it

### 2. Project ID
1. In PostHog, look at your URL: `https://app.posthog.com/project/[PROJECT_ID]/...`
2. The PROJECT_ID is the number in the URL
3. Or find it in Project Settings

## Expected Funnel for Versiful

```
Landing Page (/)
    ↓
Sign In/Sign Up (/signin)
    ↓
Welcome/Onboarding (/welcome)
    ↓
Subscription Selection (/subscription)
    ↓
Completed Setup (/settings)
```

## Common Drop-Off Points to Investigate

### 1. Landing Page → Sign In (Typical: 5-20%)
**Low conversion indicates:**
- CTA not prominent enough
- Value proposition unclear
- Poor mobile experience
- Too much friction

**Solutions:**
- Make "Get Started" button larger/more prominent
- Add urgency ("Start your free trial today")
- Add social proof (testimonials, user count)
- Simplify messaging

### 2. Sign In → Account Created (Typical: 30-70%)
**Low conversion indicates:**
- Sign-up form too complex
- Password requirements too strict
- No Google OAuth option visible
- Trust issues

**Solutions:**
- Make Google sign-in more prominent
- Reduce form fields
- Add "Already have account?" toggle
- Show security badges

### 3. Welcome → Subscription (Typical: 40-70%)
**Low conversion indicates:**
- Onboarding too long
- Users confused about next steps
- Phone verification issues

**Solutions:**
- Shorten onboarding flow
- Make "Continue" CTA clearer
- Allow skipping optional steps

### 4. Subscription Page → Payment (Typical: 10-30%)
**Most critical drop-off point!**

**Low conversion indicates:**
- Price too high
- Unclear value
- No free trial option
- Payment process seems complex

**Solutions:**
- Add 7-day free trial
- Show money-back guarantee
- Add monthly vs annual comparison
- Show feature breakdown
- Add testimonials on pricing page
- Offer limited-time discount

## Key Metrics to Track

### Page Views
- `/` - Landing page traffic
- `/signin` - Sign-up intent
- `/subscription` - Payment intent
- `/settings` - Successful conversion

### Custom Events (Recommended to Add)
Currently, you're only tracking pageviews. You should add:

1. **Landing Page:**
   - `cta_clicked` - "Get Started" button
   - `phone_number_clicked` - SMS link
   - `scroll_depth` - How far users scroll

2. **Sign In Page:**
   - `signup_attempted` - Form submitted
   - `signup_succeeded` - Account created
   - `signup_failed` - Error occurred
   - `google_oauth_clicked` - Google button clicked

3. **Welcome/Onboarding:**
   - `onboarding_started`
   - `phone_number_added`
   - `preferences_saved`
   - `onboarding_completed`

4. **Subscription Page:**
   - `subscription_page_viewed`
   - `plan_selected` (with plan type)
   - `checkout_started`
   - `checkout_completed`
   - `checkout_abandoned`

5. **Payment:**
   - `stripe_checkout_opened`
   - `payment_succeeded`
   - `payment_failed`

## PostHog Dashboard Filters

When analyzing data in PostHog, use these filters:

### Production Traffic Only
```
environment = 'prod'
```

### Exclude Internal Users
```
internal_user != true
```

### Recent Traffic (Last 30 Days)
```
timestamp > now() - interval '30 days'
```

## Setting Up Funnels in PostHog

1. Go to **Insights** → **New Insight** → **Funnel**

2. Create this funnel:
   ```
   Step 1: $pageview where $current_url contains "/"
   Step 2: $pageview where $current_url contains "/signin"
   Step 3: $pageview where $current_url contains "/subscription"
   Step 4: $pageview where $current_url contains "/settings"
   ```

3. Add filters:
   - `environment = 'prod'`
   - `internal_user != true`

4. Set time range: Last 30 days

5. Save as "Main Conversion Funnel"

## Recommended Actions Based on Common Issues

### If Landing Page Traffic is High But Sign-ups Low:

1. **Audit your landing page:**
   - Is CTA visible above the fold?
   - Is value proposition clear?
   - Are there testimonials/social proof?
   - Does it load fast on mobile?

2. **Add tracking to identify friction:**
   ```javascript
   // In LandingPage.jsx
   posthog.capture('landing_cta_clicked', {
     cta_location: 'hero' // or 'bottom', 'middle'
   })
   ```

### If Sign-In Page Has High Bounce:

1. **Check form usability:**
   - Is Google OAuth prominent?
   - Are error messages clear?
   - Is mobile experience good?

2. **Add tracking:**
   ```javascript
   posthog.capture('signup_started')
   posthog.capture('signup_failed', { error: errorMessage })
   posthog.capture('signup_succeeded')
   ```

### If Subscription Page Has High Drop-off:

**This is your biggest opportunity!**

1. **Price sensitivity test:**
   - Add free trial option
   - Show annual savings more prominently
   - Add payment plan

2. **Add trust signals:**
   - "Cancel anytime" in bold
   - Money-back guarantee
   - Testimonials
   - Feature comparison table

3. **Track plan interactions:**
   ```javascript
   posthog.capture('plan_viewed', { plan: 'monthly' })
   posthog.capture('checkout_started', { plan: 'monthly', price: 9.99 })
   ```

## Next Steps

1. **Run the analysis script** to get current baseline metrics
2. **Set up the funnel in PostHog dashboard**
3. **Add custom event tracking** to your frontend (see below)
4. **A/B test** high-friction areas
5. **Re-run analysis weekly** to track improvements

## Quick Wins to Implement Now

### High Impact, Low Effort:

1. **Add free trial** - Can increase conversions by 50-200%
2. **Make CTAs more prominent** - Larger buttons, contrasting colors
3. **Add testimonials** on subscription page
4. **Simplify onboarding** - Remove optional steps
5. **Add exit-intent popup** on pricing page with discount

### Medium Impact, Medium Effort:

1. **A/B test pricing** - Try $6.99/month vs $9.99
2. **Add live chat** support on subscription page
3. **Create comparison table** showing free vs paid features
4. **Add progress indicator** in signup flow
5. **Implement email follow-up** for abandoned carts

---

## Need Help?

Run the analysis script and share the output - I can provide specific recommendations based on your data!

