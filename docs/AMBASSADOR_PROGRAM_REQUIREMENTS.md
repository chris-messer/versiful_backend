# Ambassador/Referral Program - Requirements Document

**Version**: 1.0 Draft  
**Date**: January 13, 2026  
**Status**: ✅ Requirements Finalized - Ready for Phase 1 Implementation

---

## Executive Summary

This document outlines requirements for a comprehensive ambassador/referral program that allows influencers to promote Versiful through trackable links and earn compensation for bringing in new users who remain subscribed past 30 days.

### Key Decisions Made
- **Target Audience**: Influencers (social media, content creators)
- **Commission Model**: $5 one-time payment per user who remains subscribed past 30 days
- **Promotion**: First month free for referred users
- **Payout Terms**: Monthly payouts with $25 minimum threshold
- **Implementation**: Phased approach starting with Phase 1 MVP (manual payouts)
- **Analytics**: Track all events in PostHog in addition to internal database

## Table of Contents
1. [User Stories & Requirements](#user-stories--requirements)
2. [Open Questions & Design Decisions](#open-questions--design-decisions)
3. [Technical Architecture Overview](#technical-architecture-overview)
4. [Database Schema](#database-schema)
5. [API Endpoints](#api-endpoints)
6. [Ambassador Portal](#ambassador-portal)
7. [Frontend Tracking](#frontend-tracking)
8. [Promotional Features (Discounts/Free Trials)](#promotional-features-discountsfree-trials)
9. [Stripe Integration for Payouts](#stripe-integration-for-payouts)
10. [Analytics & Reporting](#analytics--reporting)
11. [Security Considerations](#security-considerations)
12. [Implementation Phases](#implementation-phases)

---

## User Stories & Requirements

### US-1: Ambassador Link Generation (Admin)
**As an admin**, I want to easily generate referral links for new ambassadors so they can promote Versiful.

**Acceptance Criteria**:
- [ ] Generate unique ambassador codes/slugs (e.g., `versiful.io/?ref=influencer_name`)
- [ ] Codes can be alphanumeric, human-readable
- [ ] System prevents duplicate codes
- [ ] Set commission rate: $5 per user (paid after 30-day retention)
- [ ] Set promotional offer: "First month free" for all referred users

**✅ Decision Made**: 
- **Pre-registered ambassadors only** (Option B)
- Controlled onboarding ensures quality influencers and prevents abuse
- Each ambassador must be manually added before their link is active

### US-2: Link Tracking & Attribution
**As the system**, I need to track when users arrive via ambassador links and attribute signups correctly.

**Acceptance Criteria**:
- [ ] Track page visits from ambassador links (unique visitors)
- [ ] Store referral code through user journey (landing → signup → subscription)
- [ ] Attribute completed signups to correct ambassador
- [ ] Handle edge cases:
  - User visits from ambassador link but doesn't sign up immediately (cookie expiration)
  - User visits from multiple ambassador links (last-touch attribution?)
  - User manually types URL later without ref parameter

**Technical Approach**:
- Store `ref` parameter in browser cookie/localStorage on landing
- Cookie duration: 30 days (industry standard)
- Last-touch attribution: Most recent ambassador link wins
- On signup, store `referredBy` field in users table

### US-3: Ambassador Metrics & Dashboard
**As an ambassador**, I want to see my performance metrics so I know how much I'll be paid.

**Acceptance Criteria**:
- [ ] Display total unique link clicks
- [ ] Display total signups attributed to me
- [ ] Display conversion rate (signups / clicks)
- [ ] Display paid subscriptions (monthly vs annual)
- [ ] Display pending payout amount
- [ ] Display payout history (past payments)
- [ ] Display current month performance vs previous months

### US-4: Ambassador Authentication & Portal
**As an ambassador**, I want to log in to a portal to view my metrics.

**Acceptance Criteria**:
- [ ] Separate login page for ambassadors (e.g., `versiful.io/ambassador`)
- [ ] Secure authentication
- [ ] Dashboard with metrics
- [ ] Profile page (name, email, payment info)

**✅ Decision Made**:
- **Same Cognito user pool with `role` field** (Option A)
- Add role field: "customer" | "ambassador" | "admin"
- Simpler infrastructure, influencers may also become customers
- Authorization logic checks role on protected endpoints

### US-5: Ambassador Payouts
**As an admin**, I need to pay ambassadors for their referrals.

**Acceptance Criteria**:
- [ ] Calculate commissions based on 30-day retention
- [ ] Commission: $5 per user who remains subscribed past 30 days
- [ ] Track pending vs paid vs void commissions
- [ ] Monthly payout cycle
- [ ] $25 minimum payout threshold

**✅ Decisions Made**:
- **Commission Model**: $5 one-time payment per retained user
- **30-day retention requirement**: User must remain subscribed for 30 days before commission is earned
- **Why 30 days?**: Prevents gaming with free month + cancel strategy; ensures quality referrals
- **Phase 1**: Manual payouts via PayPal/Venmo
- **Phase 4**: Automate with Stripe Connect (if program scales)
- **Payout schedule**: Monthly, on the 1st of each month
- **Minimum threshold**: $25 (5 retained users minimum)

**Commission Logic**:
1. User signs up via ambassador link → No commission yet
2. User subscribes (gets first month free) → Commission status: "pending"
3. User completes 30 days subscribed → Commission status: "earned"
4. User cancels before 30 days → Commission status: "void"
5. Monthly payout runs → Commission status: "paid"

### US-6: Promotional Offers (Discounts, Free Trials)
**As the system**, I need to support promotional offers for referred users.

**Acceptance Criteria**:
- [ ] Support "first month free" for all ambassador-referred users
- [ ] Tie promotion to ambassador codes
- [ ] Display promo messaging in UI ("{Influencer Name} got you 1 month free!")
- [ ] Track which users used promotions

**✅ Decision Made**:
- **Promotion**: First month free (30-day trial)
- **Applied to**: All users who sign up via any ambassador link
- **Messaging**: "Your first month is free, courtesy of {Ambassador Name}!"
- **Implementation**: Stripe trial period (30 days)
- **Future considerations**: May add other promotion types later (discounts, extended SMS trials)

---

## ✅ Design Decisions - FINALIZED

### Decision Matrix

| Question | Decision | Rationale |
|----------|----------|-----------|
| **Target Audience** | **Influencers** | Social media content creators, YouTube, Instagram, TikTok |
| **Ambassador Onboarding** | **Pre-register only** | Quality control, prevent abuse, set terms upfront |
| **Ambassador Auth** | **Same Cognito pool + roles** | Simpler infrastructure, influencers may become customers |
| **Commission Model** | **$5 one-time per 30-day retained user** | Prevents gaming, predictable costs, flexible pricing changes |
| **Promotion** | **First month free** | Strong incentive for signups, aligns with 30-day retention |
| **Payout Method** | **Manual → Stripe Connect** | Phase 1: Manual, Phase 4: Automate if scales |
| **Attribution Window** | **30 days** | Industry standard cookie duration |
| **Minimum Payout** | **$25** | Reasonable threshold (5 retained users) |
| **Payout Frequency** | **Monthly** | 1st of each month |
| **Implementation** | **Phased: Start with Phase 1** | Validate concept before investing in automation |

### Key Business Logic

**30-Day Retention Rule** (Prevents Gaming):
- User signs up via ambassador link with first month free
- Ambassador doesn't get paid immediately
- After 30 days, if user is still subscribed → Ambassador earns $5
- If user cancels before 30 days → No commission (status: "void")
- This prevents influencers from gaming with fake accounts or short-term signups

**Why This Works**:
- You can't lose money on referred users (they pay after free month)
- Influencers are incentivized to bring quality, engaged users
- Pricing model changes don't affect existing commission structure
- Simple, predictable cost structure

---

## Technical Architecture Overview

### High-Level System Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER JOURNEY                              │
└─────────────────────────────────────────────────────────────────┘

Step 1: Discovery
  Influencer shares link: versiful.io/?ref=influencer_name
                              ↓
Step 2: Landing & Tracking
  User clicks → Frontend detects ?ref param
              → Stores in cookie (30 days) + localStorage
              → POST /ambassador/track-visit (log in DynamoDB)
              → GET /ambassador/validate/influencer_name (check valid + get promo)
              → Show banner: "Get first month free from {Influencer}!"
                              ↓
Step 3: Signup
  User signs up (email/Google) → Cognito creates account
                              → Frontend stores referredBy in state
                              → Welcome form → PUT /users (includes referredBy)
                              → DynamoDB users table updated
                              ↓
Step 4: Subscription
  User clicks subscribe → POST /subscription/checkout
                       → Lambda checks user.referredBy
                       → Creates Stripe checkout with 30-day trial
                       → User completes payment
                       → Stripe webhook: checkout.session.completed
                              ↓
Step 5: Commission Creation
  Webhook handler → Creates commission record:
                    - status: "pending"
                    - amount: 500 ($5.00)
                    - retentionDate: today + 30 days
                  → DynamoDB ambassadors-commissions table
                  → PostHog event: 'subscription_started_referred'
                              ↓
Step 6: 30-Day Retention Check (Daily EventBridge)
  Daily at 1 AM UTC → Lambda queries commissions where:
                     - status: "pending"
                     - retentionDate: today
                   → For each commission:
                     - Check if user still subscribed
                     - If yes: status = "earned" ✅
                     - If no: status = "void" ❌
                   → PostHog events: 'commission_earned' or 'commission_voided'
                              ↓
Step 7: Monthly Payout (Monthly EventBridge)
  1st of month, 9 AM UTC → Lambda queries commissions where:
                          - status: "earned"
                        → Groups by ambassadorId
                        → Sums amounts
                        → If total >= $25:
                          - Creates payout record
                          - Generates CSV for manual payment
                          - Updates commissions to status: "paid"
                          - Sends email to admin
                        → PostHog event: 'payout_created'
                              ↓
Step 8: Manual Payment (Phase 1)
  Admin reviews CSV → Pays via PayPal/Venmo
                   → Marks payout as completed in DynamoDB
```

### Database Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                       DynamoDB Tables                         │
└──────────────────────────────────────────────────────────────┘

ambassadors
  PK: ambassadorId
  Attributes: name, email, status, commissionRate, metadata
  GSI 1: email → ambassadorId

ambassador-visits
  PK: ambassadorId
  SK: timestamp
  Attributes: visitorId, ipAddress, userAgent, converted, userId
  GSI 1: visitorId + timestamp (for deduplication)

ambassador-commissions  ← KEY TABLE
  PK: ambassadorId
  SK: commissionId
  Attributes: userId, amount, subscriptionId, status, retentionDate
  GSI 1: status + retentionDate (for daily retention check)
  GSI 2: userId → commissionId

ambassador-payouts
  PK: ambassadorId
  SK: payoutId
  Attributes: amount, commissionIds[], method, status, paidAt

users (existing table, add field)
  PK: userId
  NEW: referredBy (String, optional) ← Ambassador ID
```

### API Endpoint Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      API Gateway Routes                       │
└──────────────────────────────────────────────────────────────┘

PUBLIC (No Auth)
  POST   /ambassador/track-visit          → Log visit to DynamoDB
  GET    /ambassador/validate/{id}        → Check if ambassador valid

PROTECTED (JWT Required, Role: Ambassador)
  GET    /ambassador/dashboard            → Get metrics + payouts
  GET    /ambassador/link                 → Get shareable link
  PUT    /ambassador/profile              → Update profile

ADMIN (JWT Required, Role: Admin)
  POST   /admin/ambassadors               → Create new ambassador
  GET    /admin/ambassadors               → List all ambassadors
  GET    /admin/ambassadors/{id}          → Get ambassador details
  PUT    /admin/ambassadors/{id}          → Update ambassador
  GET    /admin/payouts/export            → Export CSV for payment
  POST   /admin/payouts/{id}/complete     → Mark payout as completed

EXISTING (Update)
  PUT    /users                           → Add referredBy field
  POST   /subscription/checkout           → Add trial logic for referrals
```

### EventBridge Schedule Architecture

```
Daily Retention Check (1:00 AM UTC)
  Rule: rate(1 day)
  Target: ambassador-daily-retention-check Lambda
  Logic: Check commissions with retentionDate = today
         Update status: pending → earned/void

Daily Conversion Sync (2:00 AM UTC)
  Rule: rate(1 day)
  Target: ambassador-daily-conversion-sync Lambda
  Logic: Match visits to signups, update converted flag

Monthly Payout (1st of month, 9:00 AM UTC)
  Rule: cron(0 9 1 * ? *)
  Target: ambassador-monthly-payout Lambda
  Logic: Generate CSV, create payout records
```

---

## Database Schema

### New DynamoDB Tables

#### 1. Ambassadors Table
**Table Name**: `{environment}-versiful-ambassadors`

**Purpose**: Store ambassador profiles and metadata

```
Partition Key: ambassadorId (String) - UUID or slug (e.g., "pastor_john")

Attributes:
- ambassadorId (String) - Unique identifier / referral code
- userId (String, optional) - Cognito user ID if ambassador is also a user
- email (String) - Contact email
- name (String) - Ambassador display name
- commissionRate (Number) - Default: 0.20 (20%)
- status (String) - "active" | "inactive" | "suspended"
- stripeConnectId (String, optional) - For automated payouts
- createdAt (String) - ISO timestamp
- updatedAt (String) - ISO timestamp
- metadata (Map) - {
    phoneNumber: "+1234567890",
    organization: "First Baptist Church",
    notes: "Senior pastor, 5000 member church"
  }
```

**GSI 1**: EmailIndex
- Partition Key: `email`
- Purpose: Look up ambassador by email

**GSI 2**: UserIdIndex
- Partition Key: `userId`
- Purpose: Link ambassador to customer account

#### 2. Ambassador Visits Table
**Table Name**: `{environment}-versiful-ambassador-visits`

**Purpose**: Track page visits from ambassador links

```
Partition Key: ambassadorId (String)
Sort Key: timestamp (String) - ISO timestamp

Attributes:
- ambassadorId (String)
- timestamp (String)
- visitorId (String) - Fingerprint or session ID
- ipAddress (String)
- userAgent (String)
- referer (String, optional)
- landingPage (String) - Which page they landed on
- converted (Boolean) - Did they eventually sign up?
- userId (String, optional) - If they signed up, link to user
```

**GSI 1**: VisitorIdIndex
- Partition Key: `visitorId`
- Sort Key: `timestamp`
- Purpose: Deduplicate visits, track user journey

#### 3. Ambassador Commissions Table
**Table Name**: `{environment}-versiful-ambassadors-commissions`

**Purpose**: Track commission records (one per paid subscription that reaches 30-day retention)

```
Partition Key: ambassadorId (String)
Sort Key: commissionId (String) - UUID

Attributes:
- ambassadorId (String)
- commissionId (String)
- userId (String) - The customer who subscribed
- amount (Number) - Commission amount in cents (500 = $5.00)
- subscriptionId (String) - Stripe subscription ID
- subscriptionPlan (String) - "monthly" | "annual"
- status (String) - "pending" | "earned" | "paid" | "void"
  - "pending": User subscribed, waiting for 30 days
  - "earned": User passed 30-day mark, commission eligible for payout
  - "paid": Commission included in a payout batch
  - "void": User cancelled before 30 days, no commission
- retentionDate (String) - ISO date when user hits 30 days subscribed
- createdAt (String) - When commission was created (subscription start)
- earnedAt (String, optional) - When commission became earned (30 days later)
- paidAt (String, optional) - When commission was paid
- payoutId (String, optional) - Links to payout record when paid
- metadata (Map) - { 
    stripeCustomerId, 
    userEmail, 
    subscriptionStartDate,
    promotionApplied: "first_month_free"
  }
```

**GSI 1**: StatusRetentionIndex
- Partition Key: `status`
- Sort Key: `retentionDate`
- Purpose: Query commissions ready to be marked as "earned" or "paid"

**GSI 2**: UserIdIndex
- Partition Key: `userId`
- Purpose: See which ambassador referred a specific user

**Commission Status Flow**:
```
User subscribes (day 0) → status: "pending", retentionDate: "2026-02-13"
                          ↓
Daily job checks (day 30) → status: "earned"
                          ↓
Monthly payout (day 35) → status: "paid", payoutId: "payout_xyz"

If user cancels (day 15) → status: "void"
```

#### 4. Ambassador Payouts Table
**Table Name**: `{environment}-versiful-ambassadors-payouts`

**Purpose**: Track payout batches to ambassadors

```
Partition Key: ambassadorId (String)
Sort Key: payoutId (String) - UUID

Attributes:
- ambassadorId (String)
- payoutId (String)
- amount (Number) - Total payout in cents
- commissionIds (List<String>) - List of commission IDs included
- method (String) - "stripe_connect" | "manual" | "paypal"
- status (String) - "pending" | "processing" | "completed" | "failed"
- stripePayoutId (String, optional)
- createdAt (String)
- completedAt (String, optional)
- metadata (Map)
```

### Updates to Existing Tables

#### Users Table Updates
```
Add new fields:
- referredBy (String, optional) - Ambassador ID who referred this user
- promotionCode (String, optional) - Specific promo code used
- promotionApplied (Map, optional) - {
    type: "first_month_free" | "discount" | "extended_trial",
    ambassadorId: "pastor_john",
    expiresAt: "2026-02-13T00:00:00Z"
  }
```

---

## API Endpoints

### Public Endpoints (No Auth Required)

#### `POST /ambassador/track-visit`
**Purpose**: Log a page visit from an ambassador link

**Request**:
```json
{
  "ambassadorId": "pastor_john",
  "landingPage": "/",
  "visitorId": "fingerprint-abc123",
  "referer": "https://facebook.com/post/123"
}
```

**Response**:
```json
{
  "success": true,
  "message": "Visit tracked"
}
```

**Logic**:
- Store in `ambassador-visits` table
- Check if visitor has visited before (dedupe unique visitors)
- Return success

#### `GET /ambassador/validate/{ambassadorId}`
**Purpose**: Check if ambassador code is valid, get promo details

**Response**:
```json
{
  "valid": true,
  "ambassadorName": "Pastor John",
  "promotion": {
    "type": "first_month_free",
    "description": "Get your first month free, courtesy of Pastor John!"
  }
}
```

### Ambassador Portal Endpoints (JWT Auth Required, Role: Ambassador)

#### `GET /ambassador/dashboard`
**Purpose**: Get ambassador metrics

**Response**:
```json
{
  "ambassadorId": "influencer_name",
  "stats": {
    "totalVisits": 1250,
    "uniqueVisitors": 890,
    "totalSignups": 45,
    "retainedUsers": 32,           // Users who stayed past 30 days
    "conversionRate": 3.6,          // (signups / visitors) * 100
    "retentionRate": 71.1,          // (retained / signups) * 100
    "pendingCommissions": 3500,     // cents ($35 = 7 users still in 30-day window)
    "earnedCommissions": 16000,     // cents ($160 = 32 earned commissions)
    "lifetimePaid": 12500,          // cents ($125 = 25 commissions already paid)
    "currentMonthSignups": 5,
    "daysUntilNextPayout": 15
  },
  "recentSignups": [
    {
      "userId": "google_123",
      "subscribedAt": "2026-01-10T12:00:00Z",
      "plan": "monthly",
      "status": "pending",          // Still in 30-day window
      "retentionDate": "2026-02-09",
      "commission": 500,            // Will earn $5 if retained
      "daysRemaining": 27
    },
    {
      "userId": "google_456",
      "subscribedAt": "2025-12-20T12:00:00Z",
      "plan": "monthly",
      "status": "earned",           // Passed 30 days
      "retentionDate": "2026-01-19",
      "commission": 500,
      "earnedAt": "2026-01-19T00:00:00Z"
    }
  ],
  "payoutHistory": [
    {
      "payoutId": "payout_123",
      "amount": 12500,              // $125 = 25 retained users
      "commissionsCount": 25,
      "paidAt": "2026-01-01T00:00:00Z",
      "method": "manual"
    }
  ]
}
```

**Note on Metrics**:
- `retainedUsers`: Count of users who stayed subscribed past 30 days
- `pendingCommissions`: Users still in 30-day window (commission not earned yet)
- `earnedCommissions`: Users past 30 days, eligible for next payout
- `lifetimePaid`: Total amount already paid out to ambassador

#### `GET /ambassador/link`
**Purpose**: Get shareable link for ambassador

**Response**:
```json
{
  "link": "https://versiful.io/?ref=influencer_name",
  "qrCode": "data:image/png;base64,..."  // Optional: Generate QR code
}
```

#### `PUT /ambassador/profile`
**Purpose**: Update ambassador profile

**Request**:
```json
{
  "name": "Pastor John Smith",
  "phoneNumber": "+15551234567",
  "paymentMethod": {
    "type": "stripe_connect",
    "accountId": "acct_123"
  }
}
```

### Admin Endpoints (JWT Auth Required, Role: Admin)

#### `POST /admin/ambassadors`
**Purpose**: Create new ambassador

**Request**:
```json
{
  "ambassadorId": "influencer_name",  // Optional, will generate if not provided
  "email": "influencer@example.com",
  "name": "Influencer Name",
  "commissionRate": 500,              // $5.00 in cents (currently fixed)
  "promotion": {
    "type": "first_month_free"
  }
}
```

**Response**:
```json
{
  "ambassadorId": "influencer_name",
  "link": "https://versiful.io/?ref=influencer_name",
  "createdAt": "2026-01-13T12:00:00Z"
}
```

#### `GET /admin/ambassadors`
**Purpose**: List all ambassadors with metrics

**Response**:
```json
{
  "ambassadors": [
    {
      "ambassadorId": "influencer_name",
      "name": "Influencer Name",
      "email": "influencer@example.com",
      "status": "active",
      "stats": {
        "totalSignups": 45,
        "retainedUsers": 32,
        "pendingCommissions": 3500,
        "earnedCommissions": 16000,
        "lifetimePaid": 12500
      }
    }
  ]
}
```

#### `POST /admin/payouts/process`
**Purpose**: Trigger payout processing (also runs on cron)

**Logic**:
1. Query commissions with status "earned" (past 30-day retention)
2. Group by ambassador
3. Sum amounts per ambassador
4. If sum >= $25 minimum → create payout record
5. Mark commissions as "paid"

**Response**:
```json
{
  "processed": 3,
  "totalAmount": 47500,  // cents ($475 total)
  "payouts": [
    {
      "ambassadorId": "influencer_name",
      "amount": 16000,      // $160 = 32 retained users
      "commissionsCount": 32,
      "status": "pending_manual_payment"
    }
  ],
  "skipped": [
    {
      "ambassadorId": "small_influencer",
      "amount": 2000,       // $20 = 4 retained users (below $25 minimum)
      "reason": "Below minimum threshold"
    }
  ]
}
```

---

## Ambassador Portal

### Portal Structure

```
/ambassador
  - Login page (uses Cognito, same as customer login)
  - After login, checks if user has ambassador role
  - If not ambassador → redirect to /settings
  - If ambassador → show portal

/ambassador/dashboard
  - Key metrics cards (visits, signups, earnings)
  - Chart: signups over time
  - Recent signups table
  - Share link + QR code

/ambassador/payouts
  - Pending commissions
  - Payout history
  - Payment method setup (Stripe Connect onboarding)

/ambassador/profile
  - Name, email, phone
  - Organization details
  - Update password
```

### UI Components to Build

#### DashboardCard Component
```jsx
<DashboardCard
  title="Total Visits"
  value={1250}
  change="+15%"
  trend="up"
/>
```

#### ShareLink Component
```jsx
<ShareLink
  link="https://versiful.io/?ref=pastor_john"
  qrCode={qrCodeDataUrl}
  onCopy={() => {}}
/>
```

#### PayoutHistoryTable Component
```jsx
<PayoutHistoryTable
  payouts={[
    { date: "2026-01-01", amount: 62.00, status: "completed" }
  ]}
/>
```

---

## Frontend Tracking

### Landing Page Changes

#### 1. Detect Referral Code
```javascript
// src/utils/referralTracking.js

export const getReferralCode = () => {
  const urlParams = new URLSearchParams(window.location.search);
  return urlParams.get('ref');
};

export const storeReferralCode = (code) => {
  if (!code) return;
  
  // Store in cookie (30 days)
  const expiryDate = new Date();
  expiryDate.setDate(expiryDate.getDate() + 30);
  document.cookie = `referralCode=${code}; expires=${expiryDate.toUTCString()}; path=/`;
  
  // Also store in localStorage as backup
  localStorage.setItem('referralCode', code);
  localStorage.setItem('referralCodeExpiry', expiryDate.toISOString());
};

export const getStoredReferralCode = () => {
  // Try cookie first
  const cookies = document.cookie.split(';');
  for (let cookie of cookies) {
    const [name, value] = cookie.trim().split('=');
    if (name === 'referralCode') return value;
  }
  
  // Fallback to localStorage
  const expiry = localStorage.getItem('referralCodeExpiry');
  if (expiry && new Date(expiry) > new Date()) {
    return localStorage.getItem('referralCode');
  }
  
  return null;
};
```

#### 2. Track Page Visit
```javascript
// src/App.jsx or LandingPage.jsx

useEffect(() => {
  const refCode = getReferralCode();
  if (refCode) {
    storeReferralCode(refCode);
    
    // Track visit
    fetch(`${API_BASE}/ambassador/track-visit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ambassadorId: refCode,
        landingPage: window.location.pathname,
        visitorId: getFingerprint(), // Implement fingerprinting
        referer: document.referrer
      })
    });
    
    // Load promo details
    fetch(`${API_BASE}/ambassador/validate/${refCode}`)
      .then(res => res.json())
      .then(data => {
        if (data.valid && data.promotion) {
          // Show promo banner
          setPromotion(data.promotion);
        }
      });
  }
}, []);
```

#### 3. Show Promotional Banner
```jsx
// src/components/PromotionalBanner.jsx

export const PromotionalBanner = ({ promotion, ambassadorName }) => {
  if (!promotion) return null;
  
  return (
    <div className="bg-gradient-to-r from-blue-500 to-purple-600 text-white p-4 text-center">
      <p className="text-lg font-semibold">
        🎉 {ambassadorName} got you {promotion.description}!
      </p>
    </div>
  );
};
```

#### 4. Include Referral Code on Signup
```javascript
// src/components/welcome/WelcomeForm.jsx

const handleSubmit = async () => {
  const referralCode = getStoredReferralCode();
  
  await fetch(`${API_BASE}/users`, {
    method: 'PUT',
    credentials: 'include',
    body: JSON.stringify({
      phoneNumber: phone,
      bibleVersion: selectedVersion,
      responseStyle: selectedStyle,
      referredBy: referralCode,  // ← Add this
      isRegistered: true
    })
  });
};
```

---

## Promotional Features (Discounts/Free Trials)

### Current Subscription Logic

Your current system:
- `isSubscribed` (Boolean) - User has active paid subscription
- `plan` (String) - "free" | "monthly" | "annual"
- SMS gating checks `isSubscribed` or `plan_monthly_cap`

### New Requirement: First Month Free

**Implementation**: Use Stripe's built-in trial period functionality

**Benefits**:
- No SMS gating changes needed (trial users are still "subscribed")
- Stripe automatically charges after trial ends
- Simple, clean implementation

### Stripe Checkout Implementation

#### Update Subscription Handler

```python
# lambdas/subscription/subscription_handler.py

def create_checkout_session(event, context):
    # ... existing code ...
    
    user = get_user(user_id)
    
    # Check if user was referred by an ambassador
    trial_days = 0
    if user.get("referredBy"):
        ambassador = get_ambassador(user["referredBy"])
        if ambassador and ambassador["status"] == "active":
            # Ambassador referral gets first month free
            trial_days = 30
            logger.info(f"Applying 30-day trial for ambassador referral: {user['referredBy']}")
    
    # Create checkout session
    checkout_config = {
        "customer": customer_id,
        "payment_method_types": ["card"],
        "line_items": [{"price": price_id, "quantity": 1}],
        "mode": "subscription",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": {
            "userId": user_id,
            "referredBy": user.get("referredBy", "")
        }
    }
    
    # Add trial period if applicable
    if trial_days > 0:
        checkout_config["subscription_data"] = {
            "trial_period_days": trial_days,
            "metadata": {
                "referredBy": user["referredBy"]
            }
        }
    
    checkout_session = stripe.checkout.Session.create(**checkout_config)
    
    return {
        "statusCode": 200,
        "body": json.dumps({
            "url": checkout_session.url,
            "sessionId": checkout_session.id,
            "trialDays": trial_days
        })
    }
```

### Webhook Handler Updates

**Create commission when subscription starts (with trial)**

```python
# lambdas/stripe_webhook/webhook_handler.py

def handle_checkout_completed(session):
    """User completed checkout - subscription starting"""
    user_id = session.metadata.get("userId")
    user = get_user(user_id)
    
    # ... existing logic to update user record ...
    
    # Check if user was referred
    if user.get("referredBy"):
        subscription = stripe.Subscription.retrieve(session.subscription)
        
        # Calculate retention date (30 days from now)
        # If trial period exists, retention date is 30 days after trial ends
        if subscription.trial_end:
            # Trial ends at subscription.trial_end (Unix timestamp)
            trial_end_date = datetime.fromtimestamp(subscription.trial_end)
            retention_date = trial_end_date + timedelta(days=30)
        else:
            # No trial, retention date is 30 days from now
            retention_date = datetime.now() + timedelta(days=30)
        
        # Create commission record with "pending" status
        commission = create_commission(
            ambassadorId=user["referredBy"],
            userId=user_id,
            subscriptionId=subscription.id,
            subscriptionPlan=session.metadata.get("plan", "monthly"),
            amount=500,  # $5.00
            status="pending",
            retentionDate=retention_date.date().isoformat(),
            metadata={
                "stripeCustomerId": session.customer,
                "userEmail": user.get("email"),
                "subscriptionStartDate": datetime.now().isoformat(),
                "trialEnd": trial_end_date.isoformat() if subscription.trial_end else None
            }
        )
        
        logger.info(f"Created pending commission: {commission['commissionId']} - Retention date: {retention_date.date()}")

def handle_subscription_deleted(subscription):
    """User cancelled subscription"""
    user = get_user_by_stripe_subscription(subscription.id)
    
    # ... existing logic to update user record ...
    
    # Check if there's a pending commission
    if user.get("referredBy"):
        commission = get_commission_by_subscription(subscription.id)
        
        if commission and commission["status"] == "pending":
            # User cancelled before 30-day retention - void commission
            update_commission(
                commissionId=commission["commissionId"],
                status="void"
            )
            
            posthog.capture('commission_voided', {
                'ambassadorId': user['referredBy'],
                'userId': user['userId'],
                'reason': 'subscription_cancelled_before_retention'
            })
            
            logger.info(f"Voided commission: {commission['commissionId']}")
```

### No SMS Gating Changes Needed!

**Why?** Users on Stripe trial are still considered "subscribed":
- Stripe subscription status during trial: `active` or `trialing`
- Your webhook sets `isSubscribed = true` when subscription starts
- SMS handler checks `isSubscribed` → user gets unlimited SMS during trial
- After trial ends, Stripe charges the card automatically
- If payment fails, Stripe webhook updates `isSubscribed = false`

**This is exactly what you want!** The referred user gets full benefits during the trial period.

---

## Stripe Integration for Payouts

### Option 1: Stripe Connect (Recommended Long-term)

**How it works**:
1. Ambassador signs up, gets redirected to Stripe Connect onboarding
2. Links bank account or debit card
3. Your system creates payouts via Stripe API
4. Stripe handles tax forms (1099), compliance

**Implementation**:
```python
# Create Connected Account
account = stripe.Account.create(
  type="express",
  country="US",
  email="ambassador@example.com",
  capabilities={
    "transfers": {"requested": True}
  }
)

# Create Account Link for onboarding
account_link = stripe.AccountLink.create(
  account=account.id,
  refresh_url="https://versiful.io/ambassador/connect/refresh",
  return_url="https://versiful.io/ambassador/connect/return",
  type="account_onboarding"
)

# Redirect ambassador to account_link.url
```

**Create Payout**:
```python
# Transfer funds to connected account
transfer = stripe.Transfer.create(
  amount=2400,  # $24.00 in cents
  currency="usd",
  destination=ambassador["stripeConnectId"],
  description=f"Commission payout for {current_month}"
)
```

### Option 2: Manual Payouts (MVP)

**Process**:
1. Generate CSV report of pending commissions
2. Manually pay via PayPal, Venmo, Zelle
3. Mark commissions as "paid" in system

**CSV Export**:
```python
# GET /admin/payouts/export

import csv

def export_pending_payouts():
    commissions = query_commissions(status="pending", min_amount=2500)
    
    with open("payouts.csv", "w") as f:
        writer = csv.writer(f)
        writer.writerow(["Ambassador", "Email", "Amount", "PayPal Email"])
        for amb in commissions:
            writer.writerow([
                amb["name"],
                amb["email"],
                f"${amb['amount']/100:.2f}",
                amb.get("paypalEmail", "")
            ])
```

---

## Analytics & Reporting

### PostHog Analytics Integration

**All ambassador-related events should be tracked in PostHog for analytics and attribution.**

#### Events to Track

**1. Ambassador Link Visit**
```javascript
posthog.capture('ambassador_link_visit', {
  ambassadorId: 'influencer_name',
  landingPage: '/',
  referer: 'https://instagram.com/...',
  visitorId: 'fingerprint-abc123'
});
```

**2. Ambassador Link Stored**
```javascript
posthog.capture('ambassador_ref_stored', {
  ambassadorId: 'influencer_name',
  storageMethod: 'cookie',  // or 'localStorage'
  expiryDate: '2026-02-13'
});
```

**3. User Signup with Referral**
```javascript
posthog.capture('user_signup_referred', {
  userId: 'google_123',
  ambassadorId: 'influencer_name',
  signupMethod: 'google',  // or 'email'
  promotionApplied: 'first_month_free'
});
```

**4. User Subscription Start (with referral)**
```javascript
posthog.capture('subscription_started_referred', {
  userId: 'google_123',
  ambassadorId: 'influencer_name',
  plan: 'monthly',
  trialPeriod: 30,
  commissionPending: 500  // cents
});
```

**5. Commission Status Change**
```javascript
// Day 30 - User retained
posthog.capture('commission_earned', {
  commissionId: 'comm_xyz',
  ambassadorId: 'influencer_name',
  userId: 'google_123',
  amount: 500,
  retentionDays: 30
});

// User cancels early
posthog.capture('commission_voided', {
  commissionId: 'comm_xyz',
  ambassadorId: 'influencer_name',
  userId: 'google_123',
  amount: 500,
  cancelledOnDay: 15
});

// Payout processed
posthog.capture('commission_paid', {
  payoutId: 'payout_123',
  ambassadorId: 'influencer_name',
  amount: 16000,  // Total payout
  commissionsCount: 32
});
```

**6. Ambassador Portal Actions**
```javascript
posthog.capture('ambassador_portal_view', {
  ambassadorId: 'influencer_name',
  page: 'dashboard'
});

posthog.capture('ambassador_link_copied', {
  ambassadorId: 'influencer_name',
  copyMethod: 'button'  // or 'qr_code'
});
```

#### PostHog Person Properties

**For Ambassadors**:
```javascript
posthog.identify(userId, {
  role: 'ambassador',
  ambassadorId: 'influencer_name',
  ambassadorStatus: 'active',
  totalReferrals: 45,
  retainedReferrals: 32,
  lifetimeEarnings: 16000
});
```

**For Referred Users**:
```javascript
posthog.identify(userId, {
  referredBy: 'influencer_name',
  promotionApplied: 'first_month_free',
  referralDate: '2026-01-13',
  retentionDate: '2026-02-12'
});
```

#### PostHog Funnels to Create

**Referral Conversion Funnel**:
1. Ambassador Link Visit
2. User Signup (with referral)
3. Subscription Started
4. 30-Day Retention (Commission Earned)

**Ambassador Performance**:
- Group by `ambassadorId` property
- Track conversion rates per ambassador
- Compare retention rates across ambassadors

### Internal Analytics Dashboard

**Metrics to Track**:
- Total unique visitors per ambassador
- Total signups per ambassador
- Total subscriptions per ambassador
- Retention rate (users past 30 days / total subscriptions)
- Conversion rate (signups / visitors)
- Average time to subscription
- Top performing ambassadors
- Revenue attributed to ambassadors
- Commission cost as % of referred revenue

### DynamoDB Query Patterns

**Top ambassadors by retention**:
```python
# Query commissions with status "earned" or "paid"
# Count per ambassadorId
# Sort by count DESC
```

**Conversion funnel per ambassador**:
```python
visits = count_visits(ambassadorId="influencer_name")
signups = count_users(referredBy="influencer_name")
subscriptions = count_commissions(ambassadorId="influencer_name", status=["pending", "earned", "paid", "void"])
retained = count_commissions(ambassadorId="influencer_name", status=["earned", "paid"])

funnel = {
  "visits": visits,
  "signups": signups,
  "subscriptions": subscriptions,
  "retained": retained,
  "visit_to_signup": signups / visits * 100,
  "signup_to_subscription": subscriptions / signups * 100,
  "subscription_to_retention": retained / subscriptions * 100
}
```

### EventBridge Scheduled Jobs

**Daily Job #1**: Check 30-day retention and mark commissions as "earned"
```python
# Lambda: ambassador-daily-retention-check
# Runs: Daily at 1:00 AM UTC

def handler(event, context):
    today = datetime.now().date().isoformat()
    
    # Query commissions with status "pending" and retentionDate = today
    pending_commissions = query_commissions_by_retention_date(
        status="pending",
        retentionDate=today
    )
    
    for commission in pending_commissions:
        user = get_user(commission["userId"])
        
        # Check if user is still subscribed
        if user.get("isSubscribed") and user.get("stripeSubscriptionId"):
            # User retained! Mark commission as earned
            update_commission(
                commissionId=commission["commissionId"],
                status="earned",
                earnedAt=datetime.now().isoformat()
            )
            
            # Track in PostHog
            posthog.capture('commission_earned', {
                'ambassadorId': commission['ambassadorId'],
                'userId': commission['userId'],
                'amount': commission['amount']
            })
            
            logger.info(f"Commission earned: {commission['commissionId']}")
        else:
            # User cancelled before 30 days - void commission
            update_commission(
                commissionId=commission["commissionId"],
                status="void"
            )
            
            # Track in PostHog
            posthog.capture('commission_voided', {
                'ambassadorId': commission['ambassadorId'],
                'userId': commission['userId'],
                'amount': commission['amount']
            })
            
            logger.info(f"Commission voided: {commission['commissionId']}")
```

**Daily Job #2**: Update visit conversion status
```python
# Lambda: ambassador-daily-conversion-sync
# Runs: Daily at 2:00 AM UTC

def handler(event, context):
    # Find visits that converted to signups
    visits = scan_visits(converted=False)
    users = scan_users(where="referredBy IS NOT NULL")
    
    for visit in visits:
        # Match visitor to user (by IP, fingerprint, cookie, etc.)
        matching_user = find_user_by_visitor(visit, users)
        if matching_user:
            update_visit(
                visitId=visit["visitId"],
                converted=True,
                userId=matching_user["userId"]
            )
```

**Monthly Job**: Process payouts
```python
# Lambda: ambassador-monthly-payout
# Runs: 1st of each month at 9:00 AM UTC

def handler(event, context):
    # Query all commissions with status "earned"
    earned_commissions = query_commissions_by_status(status="earned")
    
    # Group by ambassador
    payouts_by_ambassador = {}
    for commission in earned_commissions:
        ambassador_id = commission["ambassadorId"]
        if ambassador_id not in payouts_by_ambassador:
            payouts_by_ambassador[ambassador_id] = []
        payouts_by_ambassador[ambassador_id].append(commission)
    
    # Process payouts
    for ambassador_id, commissions in payouts_by_ambassador.items():
        total_amount = sum(c["amount"] for c in commissions)
        
        # Check minimum threshold
        if total_amount < 2500:  # $25 minimum
            logger.info(f"Skipping {ambassador_id}: ${total_amount/100} below minimum")
            continue
        
        # Create payout record (Phase 1: manual)
        payout = create_payout(
            ambassadorId=ambassador_id,
            amount=total_amount,
            commissionIds=[c["commissionId"] for c in commissions],
            method="manual",
            status="pending"
        )
        
        # Mark commissions as paid
        for commission in commissions:
            update_commission(
                commissionId=commission["commissionId"],
                status="paid",
                paidAt=datetime.now().isoformat(),
                payoutId=payout["payoutId"]
            )
        
        # Track in PostHog
        posthog.capture('payout_created', {
            'ambassadorId': ambassador_id,
            'amount': total_amount,
            'commissionsCount': len(commissions)
        })
        
        # Send notification email to admin
        send_payout_notification_email(ambassador_id, total_amount, payout["payoutId"])
        
        logger.info(f"Payout created: {payout['payoutId']} - ${total_amount/100}")
```

---

## Security Considerations

### 1. Fraud Prevention

**Risks**:
- Ambassador creates fake accounts to earn commissions
- Click fraud (bots visiting links)
- Duplicate signups

**Mitigations**:
- ✅ **30-day retention requirement**: No commission until user stays subscribed 30 days
- ✅ **Stripe payment verification**: User must provide valid payment method
- ✅ **Email verification**: Cognito requires email confirmation
- ✅ **First month free**: No immediate revenue loss from fraudulent signups
- Track IP addresses, user agents (detect suspicious patterns)
- Manual review of high-volume ambassadors (>100 signups/month)
- Minimum payout threshold ($25) prevents micro-fraud
- Rate limiting on signup endpoint

**The 30-day retention requirement is the key fraud prevention mechanism.**

### 2. Commission Clawback (Not Needed!)

**Scenario**: User subscribes, ambassador commission becomes "earned" (day 30), then user cancels on day 35

**Solution**: **No clawback needed** because:
1. User already paid for month 1 (after free trial)
2. Ambassador earned commission after 30 days of retention
3. You've already recouped the $9.99 subscription fee
4. User cancelling after 30 days is acceptable churn

**Alternative Scenario**: User refunds/chargebacks subscription before 30 days

**Solution**: Daily retention job checks `isSubscribed` status
- If user cancelled before retentionDate → commission status stays "pending"
- When retentionDate arrives and user not subscribed → status becomes "void"
- No commission is ever earned or paid

**No clawback mechanism needed** with 30-day retention rule! 🎉

### 3. Ambassador Portal Security

**Measures**:
- JWT authentication (same as customer portal)
- Check user role: `if user.role != "ambassador": return 403`
- Ambassadors can only see their own data (no cross-ambassador access)
- Rate limiting on API endpoints
- CORS restrictions

### 4. PII Protection

**Data to protect**:
- Customer emails (visible to ambassadors?)
- Payment information (never visible to ambassadors)
- IP addresses (admin only)

**Rule**: Ambassadors see:
- ✅ Number of signups
- ✅ Dates of signups
- ✅ Plan type (monthly/annual)
- ✅ Their earnings
- ❌ Customer names (unless opt-in)
- ❌ Customer emails (unless opt-in)
- ❌ Payment details

---

## Implementation Phases

### ✅ PHASE 1: MVP (Manual Process) - **START HERE**
**Goal**: Validate concept with 3-5 pilot influencers  
**Timeline**: 2-3 weeks  
**Investment**: Minimal - mostly backend + basic tracking

#### Scope

**Backend (DynamoDB Tables)**:
- [ ] Create `ambassadors` table
- [ ] Create `ambassador-visits` table
- [ ] Create `ambassador-commissions` table
- [ ] Create `ambassador-payouts` table
- [ ] Add `referredBy` field to `users` table

**Backend (Lambda Functions)**:
- [ ] `POST /ambassador/track-visit` - Log page visits
- [ ] `GET /ambassador/validate/{id}` - Check if ambassador code is valid
- [ ] Update `POST /users` - Store referredBy on signup
- [ ] Update `subscription_handler.py` - Add 30-day trial for referred users
- [ ] Update `webhook_handler.py` - Create pending commission on subscription
- [ ] EventBridge daily job: Check 30-day retention, mark commissions as "earned"
- [ ] EventBridge monthly job: Generate payout report (CSV)

**Backend (Admin Endpoints)**:
- [ ] `POST /admin/ambassadors` - Create new ambassador
- [ ] `GET /admin/ambassadors` - List all ambassadors with stats
- [ ] `GET /admin/payouts/export` - Export CSV for manual payment

**Frontend (Tracking)**:
- [ ] Detect `?ref=X` query parameter on landing
- [ ] Store referral code in cookie (30 days) + localStorage backup
- [ ] Call `/ambassador/track-visit` on landing
- [ ] Call `/ambassador/validate/{id}` to get promo details
- [ ] Show promotional banner ("Get your first month free from {Name}!")
- [ ] Include referredBy in `/users` PUT request
- [ ] Add PostHog tracking for all ambassador events

**PostHog Integration**:
- [ ] Track `ambassador_link_visit`
- [ ] Track `ambassador_ref_stored`
- [ ] Track `user_signup_referred`
- [ ] Track `subscription_started_referred`
- [ ] Track `commission_earned`, `commission_voided`, `commission_paid`
- [ ] Set person properties for ambassadors and referred users
- [ ] Create conversion funnel in PostHog dashboard

**Manual Process (Phase 1)**:
- [ ] Manually onboard ambassadors (create records via API or AWS console)
- [ ] Monthly: Run EventBridge job to generate payout CSV
- [ ] Monthly: Review CSV, pay via PayPal/Venmo/Zelle
- [ ] Monthly: Mark commissions as "paid" in database

**What's NOT in Phase 1**:
- ❌ No ambassador portal (no frontend for ambassadors to login)
- ❌ No automated payouts (manual PayPal/Venmo)
- ❌ No QR code generation
- ❌ No advanced analytics dashboard
- ❌ Ambassadors receive metrics via email (you manually send them)

#### Success Criteria

- [ ] 3-5 influencers onboarded with unique referral links
- [ ] Track link visits, signups, subscriptions in DynamoDB
- [ ] At least 1 commission earned (user retained past 30 days)
- [ ] Successfully process first manual payout
- [ ] PostHog funnel shows conversion data
- [ ] Decision point: Scale to Phase 2 or pivot?

#### Cost: ~$5-15/month
- DynamoDB tables (low traffic)
- Lambda invocations
- EventBridge rules

---

### Phase 2: Ambassador Portal
**Goal**: Self-service dashboard for ambassadors  
**Timeline**: 2-3 weeks  
**When**: After Phase 1 validates the concept

#### Scope

- [ ] Add `role` field to Cognito users
- [ ] Create `/ambassador` route in frontend
- [ ] Build ambassador login flow (reuse existing Cognito)
- [ ] Build dashboard page (metrics, charts)
- [ ] API: `GET /ambassador/dashboard` (JWT protected)
- [ ] API: `GET /ambassador/link`
- [ ] API: `PUT /ambassador/profile`
- [ ] Display: visits, signups, retention, earnings, payout history
- [ ] QR code generation for link sharing
- [ ] "Copy link" button with success toast

**No longer manual**:
- ✅ Ambassadors can view their own metrics
- ✅ Ambassadors can get their link anytime
- ❌ Still manual payouts

---

### Phase 3: Promotions & Variations
**Goal**: Test different promotional offers  
**Timeline**: 1 week  
**When**: After Phase 2, if you want to A/B test

#### Scope

- [ ] Support different trial lengths (30/60/90 days)
- [ ] Support percentage discounts (20% off first month)
- [ ] Support extended free SMS trials (10 messages instead of 5)
- [ ] A/B test different offers per ambassador
- [ ] Track conversion rates by promotion type

---

### Phase 4: Automated Payouts
**Goal**: Stripe Connect integration for automatic payments  
**Timeline**: 2 weeks  
**When**: After scaling to 20+ ambassadors

#### Scope

- [ ] Stripe Connect account creation flow
- [ ] Ambassador onboarding: Link bank account via Stripe
- [ ] Store `stripeConnectId` on ambassadors
- [ ] Monthly EventBridge job: Create Stripe transfers
- [ ] Automated 1099 tax form handling (US ambassadors)
- [ ] Email notifications on payout completion

**Cost**: 0.25% + $0.25 per payout (Stripe Connect fees)

---

### Phase 5: Advanced Analytics
**Goal**: Better insights and optimization  
**Timeline**: 2 weeks  
**When**: After program is mature

#### Scope

- [ ] Time-series graphs (signups over time)
- [ ] Cohort analysis (retention by ambassador)
- [ ] Ambassador leaderboard
- [ ] Geographic breakdown
- [ ] Traffic source analysis (Instagram vs YouTube vs TikTok)
- [ ] Predictive analytics (estimated monthly earnings)
- [ ] Export reports to PDF

---

## Cost Estimates

### Infrastructure Costs (Phase 1)

| Resource | Estimated Cost (Monthly) |
|----------|-------------------------|
| DynamoDB (4 new tables, low traffic) | $5-10 |
| Lambda invocations (tracking, payouts) | $1-5 |
| EventBridge (2 daily + 1 monthly job) | $0.20 |
| **Total Infrastructure** | **$6-15/month** |

### Commission Costs (Your Model)

**$5 per user who stays 30 days**

Example scenarios:
- **Conservative**: 20 referred signups/month, 50% retention = 10 retained = **$50/month**
- **Moderate**: 50 referred signups/month, 60% retention = 30 retained = **$150/month**
- **Aggressive**: 100 referred signups/month, 70% retention = 70 retained = **$350/month**

**Revenue Impact**:
- Each retained user pays $9.99/month after trial
- Conservative example: 10 retained × $9.99 = $99.90 revenue - $50 commission = **$49.90 net** (50% margin)
- This is after the first month; subsequent months are 100% revenue (no more commission)

### Break-Even Analysis

**Scenario**: Referred user subscribes with first month free
- Month 0: User signs up, you owe $0 commission (pending)
- Month 1: User's trial ends, they pay $9.99, commission still pending
- Month 2: User hits 30-day retention, you pay $5 commission
- **Net**: $9.99 - $5.00 = $4.99 profit, plus user continues paying $9.99/month

**You can't lose money** with this model! 🎉

---

## Executive Summary - Quick Reference

### ✅ Finalized Decisions

| Aspect | Decision |
|--------|----------|
| **Target Audience** | Influencers (Instagram, YouTube, TikTok, etc.) |
| **Commission** | $5 one-time per user who stays 30 days |
| **Promotion** | First month free (30-day Stripe trial) |
| **Onboarding** | Pre-registered ambassadors only (controlled) |
| **Authentication** | Same Cognito pool with `role` field |
| **Payout Method** | Phase 1: Manual (PayPal/Venmo), Phase 4: Stripe Connect |
| **Payout Terms** | Monthly on 1st, $25 minimum threshold |
| **Attribution Window** | 30 days (cookie/localStorage) |
| **Analytics** | PostHog + internal DynamoDB tracking |

### 🔑 Key Features

**30-Day Retention Requirement** = Your Fraud Prevention
- User must stay subscribed for 30 days before ambassador gets paid
- Prevents gaming with fake signups
- Ensures you always profit (user pays $9.99, you pay $5 commission)

**Commission Status Flow**:
```
Signup → Subscribe (trial) → status: "pending"
                            ↓
                   Day 30 retention check
                            ↓
         Still subscribed? → status: "earned" → Monthly payout → status: "paid"
         Cancelled?        → status: "void" (no payout)
```

### 📊 Success Metrics (Phase 1)

After 3 months of Phase 1:
- [ ] 5+ influencers actively promoting
- [ ] 50+ referred signups tracked
- [ ] 30+ users retained past 30 days (60% retention)
- [ ] $150+ in commissions paid out
- [ ] PostHog funnel showing clear conversion data
- [ ] **Decision**: Scale to Phase 2 or adjust strategy

### 🚀 Next Steps

1. **Review this document** with your team
2. **Identify 3-5 pilot influencers** to reach out to
3. **Begin Phase 1 implementation** (2-3 weeks)
4. **Test end-to-end** with 1 pilot ambassador
5. **Launch to remaining pilots** and monitor
6. **Evaluate after 30 days**: Did we get our first earned commission?
7. **Decide**: Continue to Phase 2 or pivot?

### 📄 Document Status

- ✅ Requirements finalized
- ✅ Technical architecture defined
- ✅ Database schema designed
- ✅ API endpoints specified
- ✅ Implementation phases outlined
- ✅ PostHog analytics integrated
- ⏭️ **Ready for implementation!**

---

## Appendix

### Example Ambassador Invite Email

```
Subject: Join the Versiful Ambassador Program

Hi [Influencer Name],

I'd love to have you as a Versiful Ambassador! Here's how it works:

**What is Versiful?**
Versiful provides biblical guidance and encouragement via text message for people seeking spiritual support. It's perfect for your faith-focused audience.

**How the Ambassador Program Works:**
1. Share your unique link with your followers: https://versiful.io/?ref=[your_code]
2. They get their first month free when they sign up through your link
3. You earn $5 for each person who stays subscribed past 30 days
4. We pay out monthly via PayPal (minimum $25)

**Why This is Great for Your Audience:**
- Simple way to receive daily biblical encouragement
- Perfect for older adults or anyone who prefers text over apps
- First month completely free (no credit card trial tricks)
- Affordable at $9.99/month after trial

**Getting Started:**
Reply to this email with:
- Your preferred ambassador code (e.g., your Instagram handle)
- Your PayPal email for payouts

I'll send you your unique link and some graphics you can share with your community.

Looking forward to partnering with you!

[Your Name]
Versiful Team
```

### Example Promotional Post (For Influencers)

```
📱 I've been using Versiful to stay connected to Scripture throughout my day, 
and I wanted to share it with you!

Versiful sends personalized biblical guidance and encouragement via text 
message - perfect if you're looking for daily spiritual support without 
another app to download.

💝 Get your first month FREE when you sign up through my link:
versiful.io/?ref=[code]

After the free month, it's just $9.99/month. No commitment, cancel anytime.

Try it out and let me know what you think! 🙏

#Faith #Christianity #BibleStudy #SpiritualGrowth [ad]
```

### Example Customer Banner (Frontend)

```jsx
<PromotionalBanner>
  🎉 Welcome! You've been invited by {ambassadorName}
  
  Sign up now and get your first month of Versiful Premium absolutely free!
  
  [Get Started →]
</PromotionalBanner>
```

---

## Questions or Feedback?

This is a living document. As you implement Phase 1, update this doc with:
- Actual implementation details
- Lessons learned
- Edge cases discovered
- Performance metrics
- Ambassador feedback

**Ready to build!** 🚀

