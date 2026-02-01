# Conversion Analysis

Analyze PostHog user behavior data to identify conversion bottlenecks and optimize the funnel.

## Directory Structure

```
conversion_analysis/
├── scripts/           # Analysis scripts
│   └── conversion_analysis.py
├── results/          # Generated outputs (gitignored)
│   ├── *.png        # Visualizations
│   ├── *.csv        # Data exports
│   └── analysis_output.txt
├── docs/            # Documentation
│   └── README.md    # This file
└── data/            # Input data (gitignored)
    └── posthog-analytics.csv
```

## Quick Start

### 1. Export Data from PostHog

1. Go to your PostHog dashboard
2. Navigate to Events → Export
3. Select date range (e.g., last 30 days)
4. Select "Production" environment only
5. Download as CSV
6. Save as `conversion_analysis/results/posthog-analytics.csv`

### 2. Run Analysis

```bash
cd /Users/christopher.messer/PycharmProjects/versiful-backend/conversion_analysis

# Run the analysis
python scripts/conversion_analysis.py

# View results
cat results/analysis_output.txt
open results/*.png  # View visualizations
```

### 3. Review Results

The analysis generates:

**Text Output:**
- `results/analysis_output.txt` - Complete analysis with recommendations

**Visualizations:**
- `conversion_funnel.png` - User drop-off at each step
- `page_views_analysis.png` - Top pages by traffic
- `time_on_page_analysis.png` - User engagement by page
- `drop_off_analysis.png` - Critical friction points
- `traffic_patterns.png` - Traffic by day/hour
- `device_browser_analysis.png` - Device/browser breakdown

**Data Exports:**
- `conversion_funnel.csv` - Funnel metrics
- `drop_off_rates.csv` - Drop-off analysis
- `time_on_page_by_page.csv` - Engagement metrics

## What It Analyzes

### 1. Traffic Filtering
- **Production environment only** (excludes dev/staging)
- **PAID TRAFFIC ONLY** (Facebook/Instagram ads)
  - Filters for events with `fbclid` (Facebook ads)
  - Filters for events with `utm_source=fb` or `utm_source=ig`
  - **EXCLUDES direct visits** (dev friends, organic traffic)
- This ensures you're analyzing actual customer behavior from your ads

### 2. Page View Analysis
- Which pages get the most traffic
- Unique visitors per page
- Average views per user

### 3. Time on Page
- How long users spend on each page
- Identifies pages with high/low engagement
- Calculated from pageview + pageleave events

### 4. Conversion Funnel
- Tracks users through the entire journey:
  - Landing page → Sign in → Welcome → Subscription → Settings
- Identifies where users drop off
- Calculates conversion rates at each step

### 5. User Behavior Patterns
- Traffic by day of week
- Traffic by hour of day
- Device distribution (Mobile vs Desktop vs Tablet)
- Browser breakdown

### 6. Recommendations
- Data-driven suggestions based on YOUR actual metrics
- Prioritized by potential impact
- Specific implementation guidance

## Key Metrics to Track

### Current Baseline (Jan 2026 - PAID TRAFFIC ONLY):
- **Paid Ad Visitors:** 275 unique users
- **Total Paid Events:** 536 events
- **Sign-In Clicks:** 7 (2.5% of visitors)
- **Bounce Rate:** 97.5%
- **Median Time on Page:** 9 seconds
- **Registered Users (all sources):** 15
- **Paying Customers:** 3 (from DynamoDB)
- **Monthly Revenue:** ~$30

### Target Metrics (30 Days):
- **Landing → Get Started:** 5%+ (from 2.5%)
- **Bounce Rate:** <85% (from 97.5%)
- **Median Time on Page:** 20s+ (from 9s)
- **Overall Conversion:** 1-2% (from 0%)
- **Monthly Revenue:** $60+ (from $30)

## Running Regular Analysis

### Weekly Analysis (Recommended)

```bash
#!/bin/bash
# Save as: conversion_analysis/scripts/weekly_analysis.sh

cd /Users/christopher.messer/PycharmProjects/versiful-backend/conversion_analysis

# Archive previous results
mkdir -p results/archive/$(date +%Y-%m-%d)
cp results/*.txt results/*.csv results/archive/$(date +%Y-%m-%d)/ 2>/dev/null

# Run new analysis
python scripts/conversion_analysis.py

# Display summary
echo ""
echo "=== WEEKLY SUMMARY ==="
grep -A 10 "CONVERSION FUNNEL ANALYSIS" results/analysis_output.txt
grep -A 5 "KEY INSIGHTS" results/analysis_output.txt
```

Make executable:
```bash
chmod +x scripts/weekly_analysis.sh
```

### Compare Week-over-Week

```bash
# Compare current vs last week
diff results/archive/2026-01-24/conversion_funnel.csv results/conversion_funnel.csv
```

## Troubleshooting

### "No events found"
- Check that CSV file exists in `results/` directory
- Verify you exported production data only
- Check date range (events must be within analysis period)

### "Not enough pageleave events"
- PostHog may not be tracking pageleave events
- Check `PostHogContext.jsx`: ensure `capture_pageleave: true`
- Time on page analysis requires both pageview + pageleave

### "ModuleNotFoundError: pandas"
```bash
pip install pandas matplotlib seaborn
```

### "Timestamp parsing error"
The script uses `format='ISO8601'` which handles mixed formats.
If you still get errors, check your CSV timestamp format.

## Customization

### Change Funnel Steps

Edit `conversion_analysis.py` line ~150:

```python
funnel_pages = {
    'Landing': '/',
    'Sign In': '/signin',
    'Welcome': '/welcome',
    'Subscription': '/subscription',
    'Settings': '/settings'
}
```

### Adjust Time Filters

Edit line ~125:

```python
# Filter unrealistic times (< 1 sec or > 30 min)
if 1 <= time_diff <= 1800:  # Change 1800 (30 min) as needed
```

### Add Custom Analysis

Add your own analysis sections after line ~450:

```python
# Custom analysis example
print("\n9. CUSTOM ANALYSIS...")
# Your code here
```

## Best Practices

### 1. Export Data Weekly
- Consistent time range (e.g., every Monday for previous 7 days)
- Always filter to production environment
- Keep date range consistent for comparison

### 2. Archive Results
- Save results before re-running analysis
- Compare week-over-week to track improvements
- Store in `results/archive/YYYY-MM-DD/`

### 3. Verify with Database
- Cross-check registered users with DynamoDB
- Cross-check paying customers with Stripe
- Use PostHog data for behavior, DB for ground truth

```bash
# Check actual registered users
aws dynamodb scan --table-name prod-versiful-users --select COUNT

# Check paying customers
aws dynamodb scan --table-name prod-versiful-users --projection-expression "isSubscribed" | grep -c "true"
```

### 4. Track Implementation Impact
- Run baseline analysis BEFORE changes
- Implement ONE change at a time
- Run analysis 7 days after each change
- Measure impact before next change

## Integration with PostHog Dashboard

### Create Matching Funnel in PostHog

1. Go to PostHog → Insights → New Insight → Funnel
2. Add steps:
   - Step 1: `$pageview` where `$current_url` contains `/`
   - Step 2: `$pageview` where `$current_url` contains `/signin`
   - Step 3: `$pageview` where `$current_url` contains `/subscription`
   - Step 4: `$pageview` where `$current_url` contains `/settings`
3. Add filters:
   - `environment = 'prod'`
   - `internal_user != true`
4. Save as "Main Conversion Funnel"

This gives you live tracking in PostHog dashboard!

## Related Documentation

- **Key Insights:** See `docs/ANALYSIS_INSIGHTS.md` for detailed findings
- **Frontend Implementation Plan:** See `/versiful-frontend/PAID_TRAFFIC_CONVERSION_PLAN.md`
- **Tracking Setup:** See `/versiful-frontend/TRACKING_IMPLEMENTATION_GUIDE.md`
- **PostHog Setup:** See `/versiful-backend/POSTHOG_ANALYTICS.md`

## Questions?

Common questions and answers:

**Q: How often should I run this?**
A: Weekly is ideal. Gives enough data to see trends without waiting too long.

**Q: What's a good conversion rate?**
A: For SaaS:
- Landing → Sign up: 10-30%
- Sign up → Paying: 20-40%
- Overall: 2-5%

**Q: Should I trust PostHog or database?**
A: Both! PostHog shows behavior (views, clicks). Database shows results (accounts, payments).

**Q: Can I automate this?**
A: Yes! Set up a weekly cron job or GitHub Action to:
1. Export PostHog data via API
2. Run analysis script
3. Email results or post to Slack

---

**Last Updated:** January 31, 2026  
**Baseline Analysis:** Jan 13-31, 2026  
**Next Review:** February 7, 2026

