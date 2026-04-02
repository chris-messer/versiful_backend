# Meta Ads Health Score: Weighted Scoring System

Version: 1.0 | Last Updated: 2026-03-18

This document explains how to calculate the Meta Ads Health Score (0-100) using weighted categories and severity multipliers.

---

## Scoring Overview

The Meta Ads Health Score is calculated using:
1. **Category Weights** (how important each category is to overall performance)
2. **Severity Multipliers** (how critical each individual check is)
3. **Pass/Warning/Fail Status** (performance against benchmarks)

**Final Score Range**: 0-100
**Grading Scale**: A+ (90-100), A (80-89), B (70-79), C (60-69), D (50-59), F (<50)

---

## Category Weights

| Category | Weight | Rationale |
|----------|--------|-----------|
| **Pixel & CAPI Health** | 30% | Foundation of tracking; without data, nothing else matters |
| **Creative (Diversity & Fatigue)** | 30% | #1 performance driver; creative quality determines CTR/CVR |
| **Account Structure** | 20% | Enables learning phase, budget efficiency, and scale |
| **Audience & Targeting** | 20% | Right message to right person; determines CPA efficiency |
| **Total** | 100% | |

---

## Severity Multipliers

Each check has a severity multiplier that weights its importance within its category.

| Severity Level | Multiplier | Impact |
|----------------|------------|--------|
| **Critical** | 5.0x | Account-breaking issues (e.g., no pixel, no CAPI, learning phase issues) |
| **High** | 3.0x | Major performance limiters (e.g., wrong objective, creative fatigue) |
| **Medium** | 2.0x | Noticeable impact on efficiency (e.g., no retargeting, poor creative diversity) |
| **Low** | 1.0x | Nice-to-haves, minor optimizations (e.g., naming conventions) |

---

## Check Status Values

Each check is evaluated as PASS, WARNING, or FAIL, with corresponding point values:

| Status | Point Value | Description |
|--------|-------------|-------------|
| **PASS** | 100 | Meets or exceeds benchmark |
| **WARNING** | 50 | Acceptable but room for improvement |
| **FAIL** | 0 | Below acceptable threshold; immediate action needed |
| **N/A** | Excluded | Check not applicable (e.g., ASC for non-e-commerce) |

---

## Calculation Method

### Step 1: Score Each Check

For each check:
```
Check Score = Status Points (0, 50, or 100) × Severity Multiplier
```

**Example**:
- **M01 (Pixel Installation)**: FAIL (0 points) × 5.0x severity = 0
- **M25 (Creative Diversity)**: WARNING (50 points) × 5.0x severity = 250
- **M36 (Naming Conventions)**: PASS (100 points) × 1.0x severity = 100

### Step 2: Calculate Category Score

For each category:
```
Category Score = (Sum of Check Scores) / (Sum of Maximum Possible Scores) × 100
```

**Example - Pixel & CAPI Health (10 checks)**:

| Check | Status | Points | Severity | Weighted Score | Max Possible |
|-------|--------|--------|----------|----------------|--------------|
| M01 | FAIL | 0 | 5.0x | 0 | 500 |
| M02 | FAIL | 0 | 5.0x | 0 | 500 |
| M03 | WARNING | 50 | 5.0x | 250 | 500 |
| M04 | WARNING | 50 | 5.0x | 250 | 500 |
| M05 | FAIL | 0 | 3.0x | 0 | 300 |
| M06 | FAIL | 0 | 4.0x | 0 | 400 |
| M07 | FAIL | 0 | 2.0x | 0 | 200 |
| M08 | PASS | 100 | 2.0x | 200 | 200 |
| M09 | PASS | 100 | 3.0x | 300 | 300 |
| M10 | WARNING | 50 | 2.0x | 100 | 200 |

**Total Weighted Score**: 0 + 0 + 250 + 250 + 0 + 0 + 0 + 200 + 300 + 100 = **1,100**
**Max Possible**: 500 + 500 + 500 + 500 + 300 + 400 + 200 + 200 + 300 + 200 = **3,600**

**Category Score**: (1,100 / 3,600) × 100 = **30.6%**

### Step 3: Calculate Overall Health Score

```
Health Score = (Category 1 Score × Weight 1) + (Category 2 Score × Weight 2) + ...
```

**Example**:
- Pixel & CAPI: 30.6% × 30% = 9.2
- Creative: 45.0% × 30% = 13.5
- Structure: 60.0% × 20% = 12.0
- Audience: 70.0% × 20% = 14.0

**Overall Health Score**: 9.2 + 13.5 + 12.0 + 14.0 = **48.7** → **Grade: F**

---

## Severity Multiplier Reference

### Pixel & CAPI Health (30% Category Weight)

| Check | Severity | Multiplier | Rationale |
|-------|----------|------------|-----------|
| M01: Pixel Installation | Critical | 5.0x | No pixel = no tracking at all |
| M02: CAPI Active | Critical | 5.0x | 30-40% data loss without CAPI post-iOS 14.5 |
| M03: Event Deduplication | Critical | 5.0x | Prevents double-counting, critical for accuracy |
| M04: Event Match Quality | Critical | 5.0x | Poor EMQ = poor attribution = wasted spend |
| M05: Standard Event Usage | High | 3.0x | Custom events limit optimization |
| M06: Conversion Event Optimization | High | 4.0x | Wrong objective = optimizing for wrong outcome |
| M07: Parameter Passing | Medium | 2.0x | Needed for ROAS optimization |
| M08: Domain Verification | Medium | 2.0x | Unlocks all events, improves tracking |
| M09: iOS 14.5+ AEM | High | 3.0x | Event prioritization matters for iOS |
| M10: First-Party Data | Medium | 2.0x | Improves EMQ and future-proofs |

**Total Maximum Points**: 3,600

---

### Creative (30% Category Weight)

| Check | Severity | Multiplier | Rationale |
|-------|----------|------------|-----------|
| M25: Format Diversity | Critical | 5.0x | Single format = limited reach and optimization |
| M26: Creatives Per Ad Set | High | 3.0x | More variants = better testing and optimization |
| M27: Creative Refresh Cadence | Medium | 2.0x | Proactive fatigue prevention |
| M28: Creative Fatigue Detection | Critical | 5.0x | Fatigued creative = wasted spend immediately |
| M29: Video Best Practices | Medium | 2.0x | Video quality impacts engagement |
| M30: Ad Copy Quality | Medium | 2.0x | Copy complements creative |
| M31: Mobile-First Creative | Medium | 2.0x | 98% of users on mobile |
| M32: Advantage+ Creative | Medium | 2.0x | Free performance lift |
| M-CR1: Image Quality | Low | 1.5x | Quality matters but not critical |
| M-CR2: UGC Testing | Medium | 2.0x | UGC often outperforms branded |
| M-CR3: A/B Testing | Medium | 2.0x | Systematic testing improves results |
| M-CR4: Performance Analysis | Medium | 2.0x | Data-driven decisions |

**Total Maximum Points**: 3,350

---

### Account Structure (20% Category Weight)

| Check | Severity | Multiplier | Rationale |
|-------|----------|------------|-----------|
| M11: Campaign Architecture | High | 3.0x | Proper structure enables optimization |
| M13: Learning Phase Management | Critical | 5.0x | Learning Limited = poor performance |
| M15: Advantage+ Shopping (ASC) | High | 3.0x | Significant lift for e-commerce (if applicable) |
| M33: Advantage+ Placements | Medium | 2.0x | Automatic placements reduce costs |
| M34: Ad Set Budgets vs CPA | High | 3.0x | Under-budgeting prevents learning |
| M35: Campaign Budget Optimization | Medium | 2.0x | CBO improves budget allocation |
| M36: Naming Conventions | Low | 1.0x | Organizational, not performance |
| M-ST1: Campaign Consolidation | High | 3.0x | Fragmentation wastes budget |
| M-ST2: Audience Overlap | Medium | 2.0x | Overlap increases CPMs |
| M39: Bid Strategy | High | 3.0x | Wrong bid strategy limits delivery |
| M40: Budget Pacing | Medium | 2.0x | Pacing issues = missed opportunities |
| M41: Minimum Budget Requirements | High | 3.0x | Under-budget = stuck in learning |
| M42: Budget Scaling Strategy | Medium | 2.0x | Proper scaling maintains performance |

**Total Maximum Points**: 3,400

---

### Audience & Targeting (20% Category Weight)

| Check | Severity | Multiplier | Rationale |
|-------|----------|------------|-----------|
| M19: Retargeting Audiences | High | 3.0x | Retargeting = low-hanging fruit (3-5x CVR) |
| M22: Advantage+ Audience Testing | High | 3.0x | Broad targeting often outperforms manual |
| M20: Lookalike Audiences | Medium | 2.0x | Scales prospecting efficiently |
| M21: Audience Exclusions | Medium | 2.0x | Prevents wasting spend on converters |
| M23: Geo-Targeting Optimization | Medium | 2.0x | Regional performance varies |
| M24: Age/Gender Targeting | Medium | 2.0x | Demographic performance varies |

**Total Maximum Points**: 1,600

---

### Attribution & Settings (Included in Pixel 30%)

| Check | Severity | Multiplier | Rationale |
|-------|----------|------------|-----------|
| M43: Attribution Window | Medium | 2.0x | Affects reported conversions |
| M44: Conversion Lift Studies | Low | 1.0x | Advanced, not required for most |
| M45: Special Ad Categories | Critical | 5.0x | Non-compliance = account ban |
| M46: Account Quality | High | 4.0x | Policy violations hurt delivery |

**Total Maximum Points**: 1,200 (if all applicable; M45 only for restricted categories)

---

## Grading Scale

| Score Range | Grade | Interpretation |
|-------------|-------|----------------|
| **90-100** | A+ | Elite account; best-in-class performance across all areas |
| **80-89** | A | Strong performance; minor optimizations available |
| **70-79** | B | Good performance; some gaps to address for improvement |
| **60-69** | C | Average performance; needs attention in multiple areas |
| **50-59** | D | Below average; significant issues requiring immediate action |
| **40-49** | F+ | Poor performance; major restructuring needed |
| **30-39** | F | Critical issues; account may not be viable without major fixes |
| **<30** | F- | Severe problems; consider pausing and rebuilding from scratch |

---

## Performance Impact Estimates

Based on historical audit data, improving score ranges correlates with these performance changes:

| Score Improvement | Estimated CPA Reduction | Estimated ROAS Lift |
|-------------------|------------------------|---------------------|
| F (40) → D (55) | 15-25% | 10-20% |
| D (55) → C (65) | 10-15% | 10-15% |
| C (65) → B (75) | 10-20% | 15-25% |
| B (75) → A (85) | 5-10% | 10-15% |
| A (85) → A+ (95) | 3-5% | 5-10% |

**Example**: An account scoring 42 (F) improving to 75 (B) could see:
- CPA reduction: 35-60% cumulative
- ROAS lift: 35-60% cumulative

**Note**: These are estimates based on typical accounts. Individual results vary based on industry, creative quality, product-market fit, and market conditions.

---

## Quick Wins Priority

When prioritizing fixes, focus on:

1. **High Severity + FAIL Status** (Critical issues, maximum impact)
2. **High Severity + WARNING Status** (Major issues, moderate impact)
3. **Medium Severity + FAIL Status** (Important issues)
4. **Low Fix Time + High Impact** (Quick wins)

**Quick Win Formula**:
```
Priority Score = (Severity Multiplier × Points Lost) / Fix Time (hours)
```

**Example**:
- **M02 (CAPI)**: FAIL, Severity 5.0x, 500 points lost, Fix Time 3 hours
  - Priority: (5.0 × 500) / 3 = **833 priority score**
- **M36 (Naming)**: FAIL, Severity 1.0x, 100 points lost, Fix Time 0.25 hours
  - Priority: (1.0 × 100) / 0.25 = **400 priority score**

**Recommendation**: Tackle M02 first despite longer fix time (higher impact).

---

## Output Template for Audit Results

When writing audit results, include:

### 1. Overall Score
```
Meta Ads Health Score: 48.7 / 100
Grade: F
Status: Critical issues requiring immediate action
```

### 2. Category Breakdown
```
| Category | Score | Weight | Weighted Contribution | Grade |
|----------|-------|--------|----------------------|-------|
| Pixel & CAPI Health | 30.6% | 30% | 9.2 | F |
| Creative | 45.0% | 30% | 13.5 | F |
| Account Structure | 60.0% | 20% | 12.0 | D |
| Audience & Targeting | 70.0% | 20% | 14.0 | C |
| **Overall** | **48.7** | **100%** | **48.7** | **F** |
```

### 3. Critical Issues (Severity 5.0x FAILS)
- List all critical failures first
- Include impact and recommended fix

### 4. Quick Wins
- Sort by Priority Score (descending)
- Focus on high-impact, low-effort fixes

### 5. Detailed Check Results
- Table with all 46 checks, status, findings, and recommendations

---

## Example Calculation (Versiful)

**Pixel & CAPI Health** (10 checks, 3,600 max points):

| Check | Status | Base Points | Severity | Weighted Score | Max |
|-------|--------|-------------|----------|----------------|-----|
| M01: Pixel | PASS | 100 | 5.0x | 500 | 500 |
| M02: CAPI | FAIL | 0 | 5.0x | 0 | 500 |
| M03: Dedup | FAIL | 0 | 5.0x | 0 | 500 |
| M04: EMQ | FAIL | 0 | 5.0x | 0 | 500 |
| M05: Standard Events | FAIL | 0 | 3.0x | 0 | 300 |
| M06: Conversion Optimization | FAIL | 0 | 4.0x | 0 | 400 |
| M07: Parameters | WARNING | 50 | 2.0x | 100 | 200 |
| M08: Domain Verification | UNKNOWN | 50 | 2.0x | 100 | 200 |
| M09: AEM | UNKNOWN | 50 | 3.0x | 150 | 300 |
| M10: First-Party Data | WARNING | 50 | 2.0x | 100 | 200 |

**Total**: 950 / 3,600 = **26.4%** → Grade: F

**Creative** (12 checks, 3,350 max points):
- Estimated: 40% (only 2 creatives, limited formats, no refresh cadence)

**Structure** (13 checks, 3,400 max points):
- Estimated: 35% (Learning Limited, under-budgeted, single campaign)

**Audience** (6 checks, 1,600 max points):
- Estimated: 60% (Advantage+ used, but no retargeting, no exclusions)

**Overall Score**:
(26.4 × 0.30) + (40.0 × 0.30) + (35.0 × 0.20) + (60.0 × 0.20)
= 7.9 + 12.0 + 7.0 + 12.0
= **38.9** → **Grade: F**

---

**Next Step**: Apply this scoring system to Versiful's actual data in the audit results document.
