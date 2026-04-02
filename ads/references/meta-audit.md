# Meta Ads Audit Checklist (46 Checks)

Version: 1.0 | Last Updated: 2026-03-18

This checklist covers all critical aspects of Meta Ads performance across Facebook and Instagram. Each check includes pass/warning/fail criteria and severity multipliers for scoring.

---

## Category 1: Pixel & CAPI Health (30% Weight)

### M01: Meta Pixel Installation ⚠️ CRITICAL
**Severity**: 5.0x | **Fix Time**: 30-60 min

**Pass**: Pixel installed, firing on all key pages (home, product, checkout, thank you)
**Warning**: Pixel installed but missing on 1-2 key pages
**Fail**: No pixel installed OR pixel not firing on most pages

**Why It Matters**: Without pixel, you have zero conversion tracking and Meta cannot optimize.

**How to Check**:
- Install Meta Pixel Helper Chrome extension
- Visit key pages and verify green checkmark
- Events Manager > Data Sources > Your Pixel > Test Events

---

### M02: Conversions API (CAPI) Active ⚠️ CRITICAL
**Severity**: 5.0x | **Fix Time**: 2-4 hours

**Pass**: CAPI active, sending server-side events for all key conversions
**Warning**: CAPI partially implemented (missing some events)
**Fail**: No CAPI implementation

**Why It Matters**: iOS 14.5+ blocks 30-40% of pixel data. CAPI bypasses this by sending events server-side. Without CAPI, you're flying blind on iOS users.

**How to Check**:
- Events Manager > Data Sources > Your Pixel > Settings > Conversions API
- Look for "Active" status and recent events
- Check "Event Match Quality" score (covered in M04)

**Quick Win**: Use partner integrations (Shopify, WooCommerce) for fast CAPI setup.

---

### M03: Event Deduplication (event_id) ⚠️ CRITICAL
**Severity**: 5.0x | **Fix Time**: 15-30 min

**Pass**: Deduplication rate ≥90% (pixel and CAPI using matching event_id)
**Warning**: Deduplication rate 70-90%
**Fail**: Deduplication rate <70% OR no event_id implemented

**Why It Matters**: Without deduplication, Meta counts the same conversion twice (once from pixel, once from CAPI), inflating costs and confusing the algorithm.

**How to Check**:
- Events Manager > Data Sources > Overview > Event Match Quality section
- Look for "Deduplicated Events" metric
- Calculate: (Deduplicated Events / Total Events) × 100

**How to Fix**:
- Ensure both pixel and CAPI send identical `event_id` for same conversion
- Use order ID, transaction ID, or timestamp-based unique ID
- Example: `event_id: "order_12345"` sent from both pixel and server

---

### M04: Event Match Quality (EMQ) Score ⚠️ CRITICAL
**Severity**: 5.0x | **Fix Time**: 1-2 hours

**Pass**: EMQ ≥8.0 for Purchase/Lead events
**Warning**: EMQ 6.0-7.9
**Fail**: EMQ <6.0

**Why It Matters**: EMQ measures how well Meta can match your events to user profiles. Low EMQ = poor attribution = wasted spend. Post-iOS 14.5, high EMQ is essential.

**How to Check**:
- Events Manager > Data Sources > Your Pixel > Overview
- Click "Event Match Quality" to see score per event

**How to Improve EMQ**:
- Send `em` (hashed email), `ph` (hashed phone), `fn` (first name), `ln` (last name)
- Send `fbc` (Facebook click ID) and `fbp` (Facebook browser ID)
- Use advanced matching in pixel setup
- Implement CAPI with customer data parameters

**Impact**: Increasing EMQ from 5.0 to 8.0 can improve ROAS by 20-30%.

---

### M05: Standard Event Usage
**Severity**: 3.0x | **Fix Time**: 30-60 min

**Pass**: Using standard events (Purchase, Lead, CompleteRegistration, etc.) for all key conversions
**Warning**: Using 1-2 custom events instead of standard events
**Fail**: Primarily using custom events OR tracking clicks instead of conversions

**Why It Matters**: Standard events give Meta more data (cross-advertiser learning) and unlock better optimization. Custom events limit algorithm performance.

**Standard Events You Should Use**:
- **E-commerce**: ViewContent, AddToCart, InitiateCheckout, Purchase
- **Lead Gen**: Lead, CompleteRegistration
- **SaaS**: StartTrial, Subscribe, CompleteRegistration

**How to Check**:
- Events Manager > Data Sources > Your Pixel > Events
- Verify standard events (not custom) for key conversions

---

### M06: Conversion Event Optimization
**Severity**: 4.0x | **Fix Time**: 5 min

**Pass**: Campaign optimized for bottom-funnel conversion event (Purchase, Lead, Subscribe)
**Warning**: Optimizing for mid-funnel event (AddToCart, InitiateCheckout) with <50 conversions/week
**Fail**: Optimizing for top-funnel event (PageView, ViewContent) OR custom click events

**Why It Matters**: Meta's algorithm optimizes for what you tell it to. If you optimize for clicks, you get clicks (not sales). Optimize for the business outcome you want.

**How to Check**:
- Ads Manager > Campaigns > Performance Goal column
- Verify "Conversion Event" matches your business goal

**Red Flag**: Campaign objective is "Traffic" or "Engagement" when you want conversions.

---

### M07: Parameter Passing (value, currency)
**Severity**: 2.0x | **Fix Time**: 30 min

**Pass**: Purchase events include `value` and `currency` parameters; Lead events include estimated lead value
**Warning**: Purchase events missing `value` or `currency`
**Fail**: No value parameters passed for any events

**Why It Matters**: Without value data, Meta cannot optimize for ROAS (Return on Ad Spend). You're leaving money on the table.

**How to Check**:
- Events Manager > Data Sources > Your Pixel > Test Events
- Trigger a test purchase and verify `value` and `currency` appear

**Example**:
```javascript
fbq('track', 'Purchase', {
  value: 99.99,
  currency: 'USD',
  content_ids: ['product_123'],
  content_type: 'product'
});
```

---

### M08: Domain Verification
**Severity**: 2.0x | **Fix Time**: 15 min

**Pass**: Domain verified in Business Manager
**Warning**: Domain verified but missing meta-tag on some subdomains
**Fail**: Domain not verified

**Why It Matters**: iOS 14.5+ limits unverified domains to 8 conversion events. Verification unlocks all events and improves tracking.

**How to Check**:
- Business Settings > Brand Safety > Domains
- Look for green checkmark next to your domain

**How to Fix**:
- Add DNS TXT record or meta tag to website
- Follow Meta's verification wizard

---

### M09: iOS 14.5+ Aggregated Event Measurement (AEM)
**Severity**: 3.0x | **Fix Time**: 15 min

**Pass**: 8 conversion events prioritized in correct order (Purchase/Lead first)
**Warning**: Events prioritized but wrong order (e.g., AddToCart ranked higher than Purchase)
**Fail**: Events not prioritized OR default ordering used

**Why It Matters**: iOS 14.5+ limits attribution to 8 events per domain. If you don't prioritize correctly, Meta may optimize for the wrong event.

**How to Check**:
- Events Manager > Aggregated Event Measurement
- Verify your top conversion event is ranked #1

**Best Practice Ranking**:
1. Purchase / Lead / Subscribe (your primary conversion)
2. InitiateCheckout / CompleteRegistration
3. AddToCart
4. ViewContent
5. PageView
6-8. Secondary events

---

### M10: First-Party Data Collection
**Severity**: 2.0x | **Fix Time**: Varies

**Pass**: Collecting emails/phones at multiple touchpoints; syncing to Meta via CAPI or Offline Conversions
**Warning**: Collecting data but not syncing to Meta
**Fail**: Minimal first-party data collection

**Why It Matters**: First-party data improves EMQ, enables better Custom Audiences, and future-proofs against privacy changes.

**Tactics**:
- Lead magnets, newsletter signups, account creation
- Upload customer lists via Offline Conversions API
- Use Customer List Custom Audiences for retargeting

---

## Category 2: Creative (Diversity & Fatigue) (30% Weight)

### M25: Creative Format Diversity ⚠️ CRITICAL
**Severity**: 5.0x | **Fix Time**: 1-3 hours

**Pass**: ≥3 creative formats active (e.g., single image, carousel, video)
**Warning**: 2 formats active
**Fail**: Only 1 format (e.g., only single images)

**Why It Matters**: Different formats perform better for different audiences. Meta's algorithm needs variety to test and optimize placement.

**How to Check**:
- Ads Manager > Ads > Group by Format
- Count unique formats with active delivery

**Recommended Formats**:
- Single Image (quick production, good for direct response)
- Carousel (showcase multiple products/features)
- Video (higher engagement, better storytelling)
- Collection (mobile-optimized shopping experience)

---

### M26: Creatives Per Ad Set
**Severity**: 3.0x | **Fix Time**: 1-2 hours

**Pass**: ≥5 active creatives per ad set (3-5 images, 2-3 videos ideal)
**Warning**: 3-4 creatives per ad set
**Fail**: <3 creatives per ad set (especially only 1-2)

**Why It Matters**: More creative variety gives Meta's algorithm more options to test and optimize. Single-creative ad sets fatigue quickly.

**How to Check**:
- Ads Manager > Ad Sets > Delivery column
- Click into each ad set and count active ads

**Best Practice**: Use Advantage+ Creative (dynamic creative testing) to auto-test combinations.

---

### M27: Creative Refresh Cadence
**Severity**: 2.0x | **Fix Time**: Ongoing

**Pass**: New creatives added every 2-4 weeks (before fatigue sets in)
**Warning**: New creatives added every 4-8 weeks
**Fail**: No creative refreshes in 8+ weeks OR same creatives running for months

**Why It Matters**: Creative fatigue is the #1 reason for declining performance. Fresh creative = sustained results.

**How to Check**:
- Ads Manager > Ads > Creation Date column
- Look for ads older than 60 days still delivering

**Recommendation**: Build a creative production pipeline (UGC, templates, AI tools).

---

### M28: Creative Fatigue Detection ⚠️ CRITICAL
**Severity**: 5.0x | **Fix Time**: Immediate (pause/replace)

**Pass**: CTR stable or increasing over last 14 days
**Warning**: CTR declining 10-20% over last 14 days
**Fail**: CTR declining >20% over last 14 days OR frequency >5.0 for prospecting

**Why It Matters**: Fatigued creatives = wasted spend. If CTR drops >20%, your creative is burned out.

**How to Check**:
- Ads Manager > Compare date ranges (last 7 days vs. previous 7 days)
- Check CTR and Frequency columns
- Set up automated rule: "Pause ad if CTR decreases by >25% over 7 days"

**Frequency Benchmarks**:
- Prospecting: <3.0 (healthy), 3.0-5.0 (warning), >5.0 (fatigued)
- Retargeting: <8.0 (healthy), 8.0-12.0 (warning), >12.0 (fatigued)

---

### M29: Video Creative Best Practices
**Severity**: 2.0x | **Fix Time**: 1-2 hours per video

**Pass**: Videos are 15-30 seconds, hook in first 3 seconds, captions included, mobile-optimized (9:16 or 4:5)
**Warning**: Missing 1-2 best practices (e.g., no captions)
**Fail**: Videos >60 seconds, no hook, desktop-oriented (16:9)

**Why It Matters**: 85% of Facebook video is watched without sound. No captions = no engagement.

**Best Practices**:
- Hook: Show value prop in first 3 seconds
- Length: 15-30 seconds for feed (up to 60s for Stories)
- Aspect ratio: 9:16 (Stories), 4:5 (Feed), 1:1 (Square)
- Captions: Always include (use Meta's auto-captioning)

---

### M30: Ad Copy Quality
**Severity**: 2.0x | **Fix Time**: 30 min

**Pass**: Clear value prop, direct CTA, benefit-focused, <125 characters primary text
**Warning**: Copy is clear but generic or too long (>200 characters)
**Fail**: Vague copy, no CTA, or overly salesy/spammy

**Why It Matters**: Great creative + weak copy = poor performance. Copy should complement visual and drive action.

**Best Practices**:
- Lead with benefit (not feature)
- Use specific numbers ("Save 30%" vs. "Save money")
- Include urgency/scarcity when appropriate
- Test multiple copy angles (pain, gain, fear, trust)

---

### M31: Mobile-First Creative
**Severity**: 2.0x | **Fix Time**: 1-2 hours

**Pass**: All creatives designed mobile-first (vertical/square, large text, single focal point)
**Warning**: Mix of mobile and desktop-oriented creatives
**Fail**: Primarily desktop-oriented (horizontal 16:9, small text)

**Why It Matters**: 98% of Facebook users access via mobile. Desktop-oriented creative = wasted impressions.

**How to Check**:
- Ads Manager > Breakdown > Platform
- Check mobile vs. desktop performance split

**Recommendation**: Design for mobile first, adapt for desktop (not vice versa).

---

### M32: Advantage+ Creative Enhancements
**Severity**: 2.0x | **Fix Time**: 5 min (toggle on)

**Pass**: Advantage+ Creative enabled (brightness/contrast optimization, cropping, music for Reels)
**Warning**: Partially enabled (only some enhancements)
**Fail**: Disabled

**Why It Matters**: Free performance lift (Meta reports 5-15% better results on average).

**How to Enable**:
- Ad creation > Advantage+ Creative section
- Toggle on "Enhancements" (brightness, contrast, music)
- Toggle on "Creative optimizations" (auto-cropping per placement)

---

### M-CR1: Image Quality Standards
**Severity**: 1.5x | **Fix Time**: 30-60 min

**Pass**: High-resolution images (≥1080px), no pixelation, professional or high-quality UGC
**Warning**: Acceptable quality but inconsistent
**Fail**: Low-resolution, pixelated, or stock photos that look generic

**Why It Matters**: Stops the scroll. Poor quality = instant skip.

**Specs**:
- Feed: 1080 x 1080px (1:1) or 1080 x 1350px (4:5)
- Stories: 1080 x 1920px (9:16)
- File size: <30MB
- Format: JPG or PNG

---

### M-CR2: UGC (User-Generated Content) Testing
**Severity**: 2.0x | **Fix Time**: Varies

**Pass**: Testing UGC creatives (customer testimonials, creator content) alongside branded content
**Warning**: Minimal UGC testing
**Fail**: 100% branded content only

**Why It Matters**: UGC often outperforms branded content by 2-3x (higher trust, native feel).

**Tactics**:
- Source from customers (reviews, photos)
- Use UGC platforms (Billo, Insense, Superfiliate)
- Test creator content vs. polished brand assets

---

### M-CR3: A/B Testing Creative Elements
**Severity**: 2.0x | **Fix Time**: Ongoing

**Pass**: Systematic creative testing (1 variable at a time: image vs. copy vs. CTA)
**Warning**: Testing multiple creatives but changing too many variables
**Fail**: No creative testing (same ads running indefinitely)

**How to Test**:
- Use Meta's A/B Test feature (Campaign level)
- Test one variable: Image A vs. Image B (same copy)
- Run until statistical significance (≥500 conversions per variant)

---

### M-CR4: Creative Performance Analysis
**Severity**: 2.0x | **Fix Time**: 30 min weekly

**Pass**: Weekly review of creative performance; pausing underperformers; scaling winners
**Warning**: Monthly review only
**Fail**: No systematic creative performance review

**How to Analyze**:
- Sort ads by CPA (ascending) or ROAS (descending)
- Pause ads with CPA >1.5x account average (after 3-5 days minimum)
- Scale winning creatives (increase budget or duplicate into new ad sets)

---

## Category 3: Account Structure (20% Weight)

### M11: Campaign Architecture
**Severity**: 3.0x | **Fix Time**: 2-4 hours (restructure)

**Pass**: Clear funnel structure (prospecting, retargeting, retention) with distinct campaigns
**Warning**: Some segmentation but mixed objectives in same campaign
**Fail**: Single campaign OR chaotic structure (no clear strategy)

**Best Practice Structure**:
```
Campaign 1: Prospecting - Broad Audiences (Sales/Conversions)
  ↳ Ad Set 1: Advantage+ Audience (Broad)
  ↳ Ad Set 2: Interest Targeting (if testing)

Campaign 2: Retargeting - Warm Audiences (Sales/Conversions)
  ↳ Ad Set 1: Website Visitors (30 days)
  ↳ Ad Set 2: Engaged Social (90 days)
  ↳ Ad Set 3: Abandoned Carts (7 days)

Campaign 3: Retention - Existing Customers (Sales/Conversions)
  ↳ Ad Set 1: Past Purchasers (90-365 days)
```

**Why It Matters**: Proper structure allows budget allocation by funnel stage and clearer performance analysis.

---

### M13: Learning Phase Management ⚠️ CRITICAL
**Severity**: 5.0x | **Fix Time**: Varies (consolidation or budget increase)

**Pass**: <30% of ad sets in "Learning Limited" status
**Warning**: 30-50% in Learning Limited
**Fail**: >50% in Learning Limited OR frequent restarts causing re-learning

**Why It Matters**: Learning Limited = Meta can't optimize properly = wasted spend. Requires 50 conversions/week per ad set to exit learning.

**How to Check**:
- Ads Manager > Ad Sets > Delivery column
- Look for "Learning Limited" or "Learning" status

**How to Fix**:
- Consolidate ad sets (fewer ad sets with higher budgets)
- Increase budgets to reach 50 conversions/week
- Use Campaign Budget Optimization (CBO) to pool budget
- Avoid editing ad sets mid-learning (pauses learning)

**Calculation**: Need 50 conversions/week = 7.14/day
- If your CPA is $10, you need $71.40/day minimum per ad set
- If your CPA is $5, you need $35.70/day minimum per ad set

---

### M15: Advantage+ Shopping Campaigns (ASC)
**Severity**: 3.0x | **Fix Time**: 1-2 hours

**Pass**: ASC active and delivering (for e-commerce with product catalog)
**Warning**: ASC created but not scaled OR not using catalog features
**Fail**: No ASC (if e-commerce) OR ASC not applicable (lead gen/SaaS)

**Why It Matters**: ASC uses machine learning to auto-optimize audiences, placements, and creative. Meta reports 20% better performance vs. manual campaigns (on average).

**When to Use ASC**:
- E-commerce with product catalog (≥50 products)
- Minimum $200/day budget (for best results)
- Not ideal for lead gen or single-product businesses

**How to Set Up**:
- Campaigns > Create > Sales > Advantage+ Shopping Campaign
- Connect product catalog
- Upload 10+ creative assets (images/videos)
- Let Meta's algorithm combine and optimize

---

### M33: Advantage+ Placements
**Severity**: 2.0x | **Fix Time**: 5 min

**Pass**: Advantage+ Placements enabled (automatic placement across Facebook, Instagram, Messenger, Audience Network)
**Warning**: Advantage+ enabled but excluding 1-2 placements
**Fail**: Manual placements (selecting specific placements only)

**Why It Matters**: Meta's algorithm finds the cheapest placements. Manual placement selection limits reach and increases costs.

**How to Check**:
- Ad Set > Placements section
- Look for "Advantage+ Placements (Automatic)" selected

**Exception**: Exclude placements only if creative is incompatible (e.g., vertical video not suited for desktop feed).

---

### M34: Ad Set Budgets vs. CPA
**Severity**: 3.0x | **Fix Time**: 5 min (adjust budgets)

**Pass**: Daily budget ≥5x target CPA per ad set
**Warning**: Budget 2-5x CPA
**Fail**: Budget <2x CPA

**Why It Matters**: Insufficient budget = can't exit learning phase = poor performance.

**Example**:
- Target CPA: $20
- Minimum daily budget per ad set: $100 (5x CPA)
- Ideal: $200/day (10x CPA for faster learning)

**How to Check**:
- Calculate: Budget / CPA ratio per ad set
- Ads Manager > Ad Sets > Budget column vs. CPA column

---

### M35: Campaign Budget Optimization (CBO)
**Severity**: 2.0x | **Fix Time**: 5 min (toggle on)

**Pass**: CBO enabled for campaigns with 2+ ad sets
**Warning**: CBO enabled but spending unevenly (1 ad set getting 80%+ budget)
**Fail**: CBO disabled (using ad set budgets only)

**Why It Matters**: CBO pools budget at campaign level and allocates to best-performing ad sets automatically. Reduces Learning Limited issues.

**How to Enable**:
- Campaign level > Budget > Campaign Budget Optimization
- Set daily or lifetime budget
- (Optional) Set ad set spend limits if needed

**When to Use Ad Set Budgets Instead**:
- Testing new audiences (want equal spend for fair test)
- Need strict control over spend per audience

---

### M36: Ad Set Naming Conventions
**Severity**: 1.0x | **Fix Time**: 15 min (rename)

**Pass**: Clear, consistent naming (e.g., "Prospecting_Broad_US_18-65_Desktop+Mobile")
**Warning**: Naming exists but inconsistent
**Fail**: Generic names ("Ad Set 1", "New Campaign")

**Why It Matters**: Proper naming enables faster analysis and reporting. Critical for scaling.

**Recommended Format**:
```
[Campaign Type]_[Audience]_[Geo]_[Age]_[Placement]_[Other]

Examples:
Prospecting_AdvantagePlus_US_25-54_Auto_v1
Retargeting_WebVisitors_US_18-65_Auto_Test
```

---

### M-ST1: Campaign Consolidation (Avoiding Fragmentation)
**Severity**: 3.0x | **Fix Time**: 2-4 hours

**Pass**: ≤5 active campaigns; budgets concentrated in top performers
**Warning**: 6-10 active campaigns
**Fail**: >10 active campaigns OR budgets spread thin across many campaigns

**Why It Matters**: Fragmentation = each campaign/ad set has insufficient budget to learn. Consolidation = faster learning, better performance.

**How to Fix**:
- Pause underperforming campaigns (CPA >1.5x target)
- Consolidate audiences into fewer ad sets (use Advantage+ Audience)
- Increase budgets on remaining campaigns

---

### M-ST2: Vertical Consolidation (Avoiding Audience Overlap)
**Severity**: 2.0x | **Fix Time**: 1-2 hours

**Pass**: Minimal audience overlap (<20% between ad sets)
**Warning**: 20-40% overlap
**Fail**: >40% overlap (ad sets competing against each other in auction)

**Why It Matters**: Overlapping audiences = your ads compete against each other = higher CPMs.

**How to Check**:
- Audiences > Select 2+ audiences > Actions > Show Audience Overlap

**How to Fix**:
- Use audience exclusions (exclude retargeting audiences from prospecting)
- Consolidate overlapping audiences into single ad set

---

## Category 4: Audience & Targeting (20% Weight)

### M19: Retargeting Audiences Active
**Severity**: 3.0x | **Fix Time**: 30-60 min

**Pass**: Active retargeting campaigns for website visitors (30d), engaged social (90d), and cart abandoners (7d)
**Warning**: 1-2 retargeting audiences active
**Fail**: No retargeting OR retargeting paused

**Why It Matters**: Retargeting has 3-5x higher conversion rates than prospecting. Low-hanging fruit.

**Must-Have Retargeting Audiences**:
1. Website Visitors (30 days) - exclude purchasers
2. Engaged Social (90 days) - video views, page engagement
3. Cart Abandoners (7 days) - viewed product or added to cart, no purchase

**How to Create**:
- Audiences > Create Custom Audience > Website / Engagement
- Set lookback window (7d, 30d, 90d based on audience)

---

### M22: Advantage+ Audience Testing
**Severity**: 3.0x | **Fix Time**: 1-2 hours

**Pass**: Testing Advantage+ Audience (broad targeting) alongside manual interest targeting
**Warning**: Using Advantage+ but not testing against manual OR using manual only
**Fail**: No prospecting OR only narrow interest targeting (limiting reach)

**Why It Matters**: Advantage+ Audience often outperforms manual targeting (Meta's algorithm finds converters you wouldn't manually target). But test both.

**How to Test**:
- Ad Set A: Advantage+ Audience (broad - location and age only)
- Ad Set B: Manual interest targeting (specific interests)
- Run for 7-14 days, compare CPA and ROAS

**When to Use Advantage+ Audience**:
- You have strong pixel data (≥100 conversions/week)
- You want to scale beyond narrow interests
- Your product has broad appeal

---

### M20: Lookalike Audience Usage
**Severity**: 2.0x | **Fix Time**: 30 min

**Pass**: Testing Lookalike Audiences (1%, 2-3%, 5-10% based on budget) seeded from purchasers or high-value customers
**Warning**: Lookalikes created but not active OR seeded from low-quality source
**Fail**: No Lookalikes tested

**Why It Matters**: Lookalikes scale prospecting beyond interest targeting. 1% Lookalikes often perform close to retargeting.

**Best Practice**:
- Seed from purchasers (not just website visitors)
- Start with 1% (most similar)
- Scale to 2-3% then 5-10% as budget increases
- Minimum 1,000 source audience size (ideally 10,000+)

**How to Create**:
- Audiences > Create Lookalike > Choose source (Customer List or Website Custom Audience) > Select 1% > Choose location

---

### M21: Audience Exclusions
**Severity**: 2.0x | **Fix Time**: 15 min

**Pass**: Prospecting campaigns exclude existing customers and recent converters
**Warning**: Some exclusions but incomplete
**Fail**: No exclusions (wasting spend on existing customers)

**How to Set Up**:
- Ad Set > Audience > Exclusions > Add Custom Audience (Purchasers - Last 180 Days)

**Best Practice Exclusions**:
- Prospecting: Exclude customers (180d), cart abandoners (7d)
- Retargeting: Exclude recent purchasers (7-14d)

---

### M23: Geo-Targeting Optimization
**Severity**: 2.0x | **Fix Time**: 30 min

**Pass**: Testing geo performance; scaling top regions; cutting poor performers
**Warning**: Running nationwide but not analyzing geo performance
**Fail**: Targeting too narrow (single city) OR too broad (worldwide) without analysis

**How to Check**:
- Ads Manager > Breakdown > Region
- Compare CPA by state/region

**Recommendation**: Start broad (nationwide), then create separate ad sets for top 3-5 states.

---

### M24: Age & Gender Targeting
**Severity**: 2.0x | **Fix Time**: 15 min

**Pass**: Testing age/gender performance; adjusting targeting based on data
**Warning**: Running broad age/gender but not analyzing
**Fail**: Targeting too narrow (18-24 only) without testing OR ignoring gender skew

**How to Check**:
- Ads Manager > Breakdown > Age / Gender
- Look for age brackets with ≥2x better CPA

**Recommendation**: Start broad (18-65+, all genders), then optimize based on data.

---

## Category 5: Budget & Bidding (Covered in Structure)

### M39: Bid Strategy Selection
**Severity**: 3.0x | **Fix Time**: 5 min

**Pass**: Using appropriate bid strategy (Lowest Cost for most, Cost Cap if CPA target needed, Bid Cap for advanced)
**Warning**: Using Bid Cap or Cost Cap without sufficient data
**Fail**: Using wrong bid strategy (e.g., Bid Cap on new account with no conversions)

**Bid Strategy Guide**:
- **Lowest Cost (default)**: Best for most advertisers, especially starting out
- **Cost Cap**: Set max CPA; use once you have 50+ conversions/week and stable CPA
- **Bid Cap**: Advanced; set max bid per auction; risk underdelivery
- **ROAS Goal**: Use if optimizing for value (requires Purchase event with value parameter)

**How to Check**:
- Ad Set > Optimization & Delivery > Bid Strategy

---

### M40: Budget Pacing
**Severity**: 2.0x | **Fix Time**: Monitor daily

**Pass**: Budget spending evenly throughout day (not front-loaded or exhausted early)
**Warning**: Budget exhausted by mid-day on some days
**Fail**: Frequent budget exhaustion or erratic pacing

**How to Check**:
- Ads Manager > Delivery column > "Limited by Budget" indicator
- Use Facebook Ads Report > Breakdown > Hourly to see spend pacing

**How to Fix**:
- Increase budget if performance is good
- Switch to Lifetime Budget (instead of Daily) for smoother pacing

---

### M41: Minimum Budget Requirements
**Severity**: 3.0x | **Fix Time**: Immediate (increase budget or pause)

**Pass**: Budget meets Meta's learning requirements (≥$50/day per ad set for most verticals)
**Warning**: $20-50/day per ad set
**Fail**: <$20/day per ad set

**Why It Matters**: Under-budgeted ad sets stay in Learning Limited and never optimize.

**Minimum Budgets by Objective**:
- Lead Gen (low-ticket): $30-50/day per ad set
- E-commerce (mid-ticket): $50-100/day per ad set
- High-ticket (SaaS, B2B): $100-200/day per ad set

---

### M42: Budget Scaling Strategy
**Severity**: 2.0x | **Fix Time**: Ongoing

**Pass**: Scaling budgets gradually (20% every 3-5 days) on winning ad sets
**Warning**: Scaling too fast (>50% increases) causing performance drops
**Fail**: Not scaling winners OR aggressive scaling (doubling budgets overnight)

**Best Practice**:
- Wait for 50 conversions before scaling
- Increase budget by 20% every 3-5 days (avoids re-entering learning)
- If performance drops after scaling, revert to previous budget

---

## Category 6: Attribution & Settings

### M43: Attribution Window Selection
**Severity**: 2.0x | **Fix Time**: 5 min

**Pass**: Using 7-day click, 1-day view (standard) OR adjusted based on sales cycle
**Warning**: Using non-standard window without rationale
**Fail**: Using 1-day click (under-reporting) OR 28-day view (over-reporting)

**How to Check**:
- Ad Account Settings > Attribution Setting
- Default: 7-day click, 1-day view

**Adjust Based on Sales Cycle**:
- Impulse purchase (fast fashion): 1-day click OK
- Considered purchase (furniture, SaaS): 7-day click or longer

---

### M44: Conversion Lift Studies (Advanced)
**Severity**: 1.0x | **Fix Time**: N/A

**Pass**: Running Conversion Lift studies quarterly (for large accounts)
**Warning**: Ran once, not ongoing
**Fail**: Never run (or account too small - requires $30k+ spend)

**Why It Matters**: Measures incremental lift (true impact) vs. attributed conversions. Validates ROAS accuracy.

**Minimum Requirements**: $30k+ monthly spend, ≥500 conversions/week

---

### M45: Special Ad Categories Compliance
**Severity**: 5.0x (if applicable) | **Fix Time**: Immediate

**Pass**: If running housing, employment, credit, or social issue ads, Special Ad Category is declared
**Warning**: N/A
**Fail**: Running restricted category ads without declaring (account ban risk)

**How to Check**:
- Ad Set > Special Ad Category dropdown
- If your ad is in restricted category, must select appropriate category

**Restrictions**:
- No age targeting (18-65+ only)
- No ZIP code targeting
- No Lookalike Audiences

---

### M46: Account Quality (Policy Violations)
**Severity**: 4.0x | **Fix Time**: Varies

**Pass**: No policy violations in last 90 days; account in good standing
**Warning**: 1-2 minor violations (ads rejected but account OK)
**Fail**: Multiple violations or account restrictions

**How to Check**:
- Account Quality > Policy section
- Look for "Account Status" indicator

**Common Violations**:
- Before/after images (health/weight loss)
- Misleading claims
- Prohibited content (tobacco, weapons, adult)
- Landing page issues (broken links, misleading content)

---

## Summary Table: 46 Checks by Category

| Category | Checks | Weight |
|----------|--------|--------|
| Pixel & CAPI Health | M01-M10 (10 checks) | 30% |
| Creative (Diversity & Fatigue) | M25-M32, M-CR1 to M-CR4 (12 checks) | 30% |
| Account Structure | M11, M13, M15, M33-M36, M-ST1, M-ST2 (9 checks) | 20% |
| Audience & Targeting | M19-M24 (6 checks) | 20% |
| Budget & Bidding | M39-M42 (4 checks) | Included in Structure 20% |
| Attribution & Settings | M43-M46 (4 checks) | Included in Pixel 30% |
| **Total** | **46 checks** | **100%** |

---

## Quick Reference: Critical Checks (Severity 5.0x)

Evaluate these first - they have the highest impact on performance:

1. **M01**: Meta Pixel installed and firing
2. **M02**: CAPI active (30-40% data loss without it)
3. **M03**: Event deduplication (≥90% dedup rate)
4. **M04**: Event Match Quality ≥8.0
5. **M25**: Creative format diversity (≥3 formats)
6. **M28**: Creative fatigue (CTR drop >20% = FAIL)
7. **M13**: Learning phase (<30% ad sets in Learning Limited)
8. **M45**: Special Ad Categories compliance (if applicable)

---

## Benchmark Thresholds (Quick Reference)

| Metric | Pass | Warning | Fail |
|--------|------|---------|------|
| EMQ (Purchase) | ≥8.0 | 6.0-7.9 | <6.0 |
| Dedup rate | ≥90% | 70-90% | <70% |
| Creative formats | ≥3 | 2 | 1 |
| Creatives/ad set | ≥5 | 3-4 | <3 |
| Prospecting frequency (7d) | <3.0 | 3.0-5.0 | >5.0 |
| Retargeting frequency (7d) | <8.0 | 8.0-12.0 | >12.0 |
| CTR (Link Click) | ≥1.0% | 0.5-1.0% | <0.5% |
| Learning Limited % | <30% | 30-50% | >50% |
| Budget per ad set | ≥5x CPA | 2-5x CPA | <2x CPA |
| Campaign count (active) | ≤5 | 6-10 | >10 |

---

**Next Step**: Use `scoring-system.md` to calculate weighted scores and `benchmarks.md` for industry-specific targets.
