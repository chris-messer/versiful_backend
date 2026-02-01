"""
Versiful Conversion Analysis - PostHog Data Analysis
Run this script or convert to Jupyter notebook with: jupytext --to notebook conversion_analysis.py
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
import json
from datetime import datetime, timedelta
from urllib.parse import urlparse
import warnings
warnings.filterwarnings('ignore')

# Styling
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette('husl')

# Display settings
pd.set_option('display.max_columns', None)
pd.set_option('display.max_colwidth', 100)

print("="*80)
print(" " * 20 + "VERSIFUL CONVERSION ANALYSIS")
print("="*80)

# %% Load Data
print("\n1. LOADING DATA...")

# Try multiple possible locations for the CSV file
import os

csv_locations = [
    os.path.join(os.path.dirname(__file__), '../results/posthog-analytics.csv'),  # Run from scripts/
    'results/posthog-analytics.csv',  # Run from conversion_analysis/
    'conversion_analysis/results/posthog-analytics.csv',  # Run from project root
    'posthog-analytics.csv',  # Run from results/
]

df = None
csv_used = None
for csv_path in csv_locations:
    try:
        df = pd.read_csv(csv_path)
        csv_used = csv_path
        print(f"✅ Loaded data from: {csv_path}")
        break
    except (FileNotFoundError, OSError):
        continue

if df is None:
    print("❌ Error: Could not find posthog-analytics.csv")
    print("\nLooked in:")
    for loc in csv_locations:
        print(f"  - {loc}")
    print("\nPlease export PostHog data and save as:")
    print("  conversion_analysis/results/posthog-analytics.csv")
    exit(1)

print(f"✅ Loaded {len(df):,} events")
print(f"📅 Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
print(f"\n🎯 Event types:\n{df['event'].value_counts()}")

# %% Preprocess
print("\n2. PREPROCESSING...")

def safe_json_parse(x):
    try:
        return json.loads(x) if pd.notna(x) else {}
    except:
        return {}

df['props'] = df['properties'].apply(safe_json_parse)
df['timestamp'] = pd.to_datetime(df['timestamp'], format='ISO8601')
df['date'] = df['timestamp'].dt.date
df['hour'] = df['timestamp'].dt.hour
df['day_of_week'] = df['timestamp'].dt.day_name()

# Extract key properties
df['environment'] = df['props'].apply(lambda x: x.get('environment', 'unknown'))
df['current_url'] = df['props'].apply(lambda x: x.get('$current_url', x.get('$pathname', '')))
df['pathname'] = df['props'].apply(lambda x: x.get('$pathname', ''))
df['referrer'] = df['props'].apply(lambda x: x.get('$referrer', ''))
df['device_type'] = df['props'].apply(lambda x: x.get('$device_type', 'unknown'))
df['browser'] = df['props'].apply(lambda x: x.get('$browser', 'unknown'))
df['os'] = df['props'].apply(lambda x: x.get('$os', 'unknown'))

def extract_path(url):
    if not url:
        return '/'
    try:
        if url.startswith('http'):
            return urlparse(url).path or '/'
        return url if url.startswith('/') else '/'
    except:
        return '/'

df['clean_path'] = df['current_url'].apply(extract_path)
df['clean_path'] = df['clean_path'].fillna(df['pathname'])
df['clean_path'] = df['clean_path'].replace('', '/')

print("✅ Data preprocessed")
print(f"🌍 Environments: {df['environment'].value_counts().to_dict()}")

# %% Filter Production
print("\n3. FILTERING TO PRODUCTION DATA...")
df_prod = df[df['environment'] == 'prod'].copy()

print(f"✅ Production events: {len(df_prod):,} ({len(df_prod)/len(df)*100:.1f}% of total)")
print(f"👥 Unique users: {df_prod['distinct_id'].nunique():,}")
print(f"📅 Production date range: {df_prod['timestamp'].min()} to {df_prod['timestamp'].max()}")

# %% Filter to PAID TRAFFIC ONLY
print("\n" + "="*80)
print("CRITICAL FILTER: PAID TRAFFIC ONLY (EXCLUDING DIRECT VISITS FROM DEV/FRIENDS)")
print("="*80)

# Extract traffic source markers
df_prod['current_url'] = df_prod['props'].apply(lambda x: x.get('$current_url', ''))
df_prod['referring_domain'] = df_prod['props'].apply(lambda x: x.get('$referring_domain', ''))
df_prod['utm_source'] = df_prod['props'].apply(lambda x: x.get('utm_source', ''))
df_prod['fbclid'] = df_prod['props'].apply(lambda x: x.get('fbclid', ''))

# Define PAID TRAFFIC: Facebook/Instagram ads with tracking parameters
df_prod['is_paid_traffic'] = (
    (df_prod['current_url'].str.contains('fbclid|gclid|utm_source=fb|utm_source=ig', na=False)) |
    (df_prod['fbclid'].notna() & (df_prod['fbclid'] != '')) |
    (df_prod['utm_source'].isin(['fb', 'ig']))
)

total_before = len(df_prod)
paid_count = df_prod['is_paid_traffic'].sum()
direct_count = (~df_prod['is_paid_traffic']).sum()

print(f"📊 Traffic Breakdown:")
print(f"   Total prod events: {total_before:,}")
print(f"   ✅ PAID (ads) - keeping: {paid_count:,} ({paid_count/total_before*100:.1f}%)")
print(f"   ❌ DIRECT/REF - excluding: {direct_count:,} ({direct_count/total_before*100:.1f}%)")

# Show sample of direct traffic being excluded
direct_sample = df_prod[~df_prod['is_paid_traffic']][['event', 'referring_domain', 'current_url']].head(5)
if len(direct_sample) > 0:
    print(f"\n🔍 Sample of EXCLUDED direct traffic:")
    for idx, row in direct_sample.iterrows():
        ref = row['referring_domain'] if row['referring_domain'] != '$direct' else 'DIRECT'
        print(f"   - {row['event'][:20]:20s} from {ref}")

# Filter to paid traffic only
df_prod = df_prod[df_prod['is_paid_traffic']].copy()
print(f"\n✅ NOW ANALYZING PAID TRAFFIC ONLY: {len(df_prod):,} events from {df_prod['distinct_id'].nunique():,} users")

# %% Page View Analysis
print("\n4. PAGE VIEW ANALYSIS...")
pageviews = df_prod[df_prod['event'] == '$pageview'].copy()

print(f"📄 Total Pageviews: {len(pageviews):,}")
print(f"👥 Unique visitors: {pageviews['distinct_id'].nunique():,}")

page_counts = pageviews['clean_path'].value_counts().head(20)
page_unique = pageviews.groupby('clean_path')['distinct_id'].nunique().sort_values(ascending=False).head(20)

# Visualization
fig, axes = plt.subplots(1, 2, figsize=(18, 8))

page_counts.plot(kind='barh', ax=axes[0], color='coral')
axes[0].set_title('Top 20 Pages by Total Views', fontsize=14, fontweight='bold')
axes[0].set_xlabel('Total Pageviews')

page_unique.plot(kind='barh', ax=axes[1], color='teal')
axes[1].set_title('Top 20 Pages by Unique Visitors', fontsize=14, fontweight='bold')
axes[1].set_xlabel('Unique Visitors')

plt.tight_layout()
plt.savefig('page_views_analysis.png', dpi=300, bbox_inches='tight')
print("✅ Saved: page_views_analysis.png")
plt.close()

print("\n📊 Top Pages:")
top_pages = pd.DataFrame({
    'Total Views': page_counts.head(10),
    'Unique Visitors': page_unique.head(10),
    'Avg Views/User': (page_counts / page_unique).head(10).round(2)
})
print(top_pages)

# %% Time on Page Analysis
print("\n5. TIME ON PAGE ANALYSIS...")
page_events = df_prod[df_prod['event'].isin(['$pageview', '$pageleave'])].copy()
page_events = page_events.sort_values(['distinct_id', 'timestamp'])

time_on_page_data = []

for user_id in page_events['distinct_id'].unique():
    user_events = page_events[page_events['distinct_id'] == user_id].sort_values('timestamp')
    
    pageviews_u = user_events[user_events['event'] == '$pageview']
    pageleaves_u = user_events[user_events['event'] == '$pageleave']
    
    for idx, pv in pageviews_u.iterrows():
        future_leaves = pageleaves_u[
            (pageleaves_u['timestamp'] > pv['timestamp']) & 
            (pageleaves_u['clean_path'] == pv['clean_path'])
        ]
        
        if len(future_leaves) > 0:
            next_leave = future_leaves.iloc[0]
            time_diff = (next_leave['timestamp'] - pv['timestamp']).total_seconds()
            
            if 1 <= time_diff <= 1800:  # Between 1 sec and 30 min
                time_on_page_data.append({
                    'user_id': user_id,
                    'page': pv['clean_path'],
                    'time_seconds': time_diff,
                    'timestamp': pv['timestamp']
                })

time_on_page_df = pd.DataFrame(time_on_page_data)

print(f"⏱️  Calculated time on page for {len(time_on_page_df):,} pageviews")

if len(time_on_page_df) > 0:
    time_summary = time_on_page_df.groupby('page').agg({
        'time_seconds': ['mean', 'median', 'count']
    }).round(1)
    time_summary.columns = ['Avg Time (sec)', 'Median Time (sec)', 'Sample Size']
    time_summary = time_summary.sort_values('Avg Time (sec)', ascending=False)
    
    print("\n⏱️  Time on Page by Page:")
    print(time_summary.head(15))
    
    # Visualization
    fig, axes = plt.subplots(1, 2, figsize=(18, 6))
    
    top_pages_time = time_summary.nlargest(10, 'Avg Time (sec)')
    axes[0].barh(range(len(top_pages_time)), top_pages_time['Avg Time (sec)'], color='skyblue')
    axes[0].set_yticks(range(len(top_pages_time)))
    axes[0].set_yticklabels(top_pages_time.index)
    axes[0].set_xlabel('Average Time (seconds)')
    axes[0].set_title('Pages with Longest Average Time', fontsize=14, fontweight='bold')
    axes[0].invert_yaxis()
    
    axes[1].hist(time_on_page_df['time_seconds'], bins=50, color='lightcoral', edgecolor='black')
    axes[1].axvline(time_on_page_df['time_seconds'].median(), color='red', linestyle='--', 
                    label=f"Median: {time_on_page_df['time_seconds'].median():.1f}s")
    axes[1].set_xlabel('Time on Page (seconds)')
    axes[1].set_ylabel('Frequency')
    axes[1].set_title('Distribution of Time on Page', fontsize=14, fontweight='bold')
    axes[1].legend()
    
    plt.tight_layout()
    plt.savefig('time_on_page_analysis.png', dpi=300, bbox_inches='tight')
    print("✅ Saved: time_on_page_analysis.png")
    plt.show()
    
    # Save to CSV
    time_summary.to_csv('time_on_page_by_page.csv')
    print("✅ Saved: time_on_page_by_page.csv")
else:
    print("⚠️  Not enough pageleave events to calculate time on page")

# %% Conversion Funnel
print("\n6. CONVERSION FUNNEL ANALYSIS...")

funnel_pages = {
    'Landing': '/',
    'Sign In': '/signin',
    'Welcome': '/welcome',
    'Subscription': '/subscription',
    'Settings': '/settings'
}

funnel_users = {}
for step_name, page_path in funnel_pages.items():
    users = pageviews[pageviews['clean_path'] == page_path]['distinct_id'].unique()
    funnel_users[step_name] = set(users)

funnel_data = []
total_users = len(funnel_users.get('Landing', set()))

prev_count = total_users
for step_name in funnel_pages.keys():
    count = len(funnel_users.get(step_name, set()))
    drop_off = prev_count - count
    conversion = (count / total_users * 100) if total_users > 0 else 0
    step_conversion = (count / prev_count * 100) if prev_count > 0 else 0
    
    funnel_data.append({
        'Step': step_name,
        'Users': count,
        'Drop-off': drop_off,
        'Overall %': conversion,
        'Step %': step_conversion
    })
    
    prev_count = count

funnel_df = pd.DataFrame(funnel_data)

print("\n🔍 CONVERSION FUNNEL ANALYSIS")
print("=" * 70)
print(funnel_df.to_string(index=False))
print("=" * 70)

if total_users > 0:
    final_conversion = (funnel_df.iloc[-1]['Users'] / total_users * 100)
    print(f"\n💡 Overall Conversion Rate: {final_conversion:.2f}%")
    print(f"   ({funnel_df.iloc[-1]['Users']} conversions from {total_users} landing page visitors)")

# Visualization
fig, axes = plt.subplots(1, 2, figsize=(18, 6))

colors = ['#2ecc71', '#f39c12', '#e74c3c', '#9b59b6', '#3498db']
axes[0].barh(funnel_df['Step'], funnel_df['Users'], color=colors)
axes[0].set_xlabel('Number of Users')
axes[0].set_title('Conversion Funnel - User Count', fontsize=14, fontweight='bold')
axes[0].invert_yaxis()

for i, (count, pct) in enumerate(zip(funnel_df['Users'], funnel_df['Overall %'])):
    axes[0].text(count, i, f' {count} ({pct:.1f}%)', va='center', fontweight='bold')

axes[1].plot(funnel_df['Step'], funnel_df['Step %'], marker='o', linewidth=2, markersize=10, color='crimson')
axes[1].set_ylabel('Conversion Rate (%)')
axes[1].set_title('Step-to-Step Conversion Rate', fontsize=14, fontweight='bold')
axes[1].grid(True, alpha=0.3)
axes[1].set_ylim(0, 105)

for i, (step, pct) in enumerate(zip(funnel_df['Step'], funnel_df['Step %'])):
    axes[1].text(i, pct + 3, f'{pct:.1f}%', ha='center', fontweight='bold')

plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig('conversion_funnel.png', dpi=300, bbox_inches='tight')
print("✅ Saved: conversion_funnel.png")
plt.show()

# Save funnel data
funnel_df.to_csv('conversion_funnel.csv', index=False)
print("✅ Saved: conversion_funnel.csv")

# %% Drop-off Analysis
print("\n7. DROP-OFF ANALYSIS...")

drop_offs = []
for i in range(len(funnel_df) - 1):
    from_step = funnel_df.iloc[i]
    to_step = funnel_df.iloc[i + 1]
    
    drop_off_count = from_step['Users'] - to_step['Users']
    drop_off_rate = (drop_off_count / from_step['Users'] * 100) if from_step['Users'] > 0 else 0
    
    drop_offs.append({
        'Transition': f"{from_step['Step']} → {to_step['Step']}",
        'Lost Users': drop_off_count,
        'Drop-off Rate': drop_off_rate
    })

drop_off_df = pd.DataFrame(drop_offs).sort_values('Drop-off Rate', ascending=False)

print("\n🚨 CRITICAL DROP-OFF POINTS")
print("=" * 60)
print(drop_off_df.to_string(index=False))
print("=" * 60)

# Visualization
fig, ax = plt.subplots(figsize=(12, 6))
colors_drop = ['#e74c3c' if rate > 70 else '#f39c12' if rate > 50 else '#2ecc71' 
               for rate in drop_off_df['Drop-off Rate']]

ax.barh(drop_off_df['Transition'], drop_off_df['Drop-off Rate'], color=colors_drop)
ax.set_xlabel('Drop-off Rate (%)')
ax.set_title('Drop-off Rates Between Funnel Steps', fontsize=14, fontweight='bold')
ax.axvline(50, color='orange', linestyle='--', alpha=0.7, label='50% threshold')
ax.axvline(70, color='red', linestyle='--', alpha=0.7, label='70% threshold')
ax.legend()
ax.invert_yaxis()

for i, (transition, rate) in enumerate(zip(drop_off_df['Transition'], drop_off_df['Drop-off Rate'])):
    ax.text(rate + 1, i, f'{rate:.1f}%', va='center', fontweight='bold')

plt.tight_layout()
plt.savefig('drop_off_analysis.png', dpi=300, bbox_inches='tight')
print("✅ Saved: drop_off_analysis.png")
plt.show()

# Save drop-off data
drop_off_df.to_csv('drop_off_rates.csv', index=False)
print("✅ Saved: drop_off_rates.csv")

# %% User Behavior
print("\n8. USER BEHAVIOR PATTERNS...")

# Traffic by day of week
traffic_by_day = df_prod.groupby('day_of_week')['distinct_id'].count()
day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
traffic_by_day = traffic_by_day.reindex(day_order)

# Traffic by hour
traffic_by_hour = df_prod.groupby('hour')['distinct_id'].count()

fig, axes = plt.subplots(1, 2, figsize=(18, 6))

traffic_by_day.plot(kind='bar', ax=axes[0], color='mediumseagreen')
axes[0].set_title('Traffic by Day of Week', fontsize=14, fontweight='bold')
axes[0].set_xlabel('Day')
axes[0].set_ylabel('Event Count')
axes[0].tick_params(axis='x', rotation=45)

traffic_by_hour.plot(kind='line', ax=axes[1], marker='o', color='royalblue', linewidth=2)
axes[1].set_title('Traffic by Hour of Day', fontsize=14, fontweight='bold')
axes[1].set_xlabel('Hour (24h)')
axes[1].set_ylabel('Event Count')
axes[1].grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('traffic_patterns.png', dpi=300, bbox_inches='tight')
print("✅ Saved: traffic_patterns.png")
plt.show()

print(f"\n📊 Peak traffic day: {traffic_by_day.idxmax()} ({traffic_by_day.max():,} events)")
print(f"📊 Peak traffic hour: {traffic_by_hour.idxmax()}:00 ({traffic_by_hour.max():,} events)")

# Device and browser
device_dist = df_prod['device_type'].value_counts()
browser_dist = df_prod['browser'].value_counts().head(10)

fig, axes = plt.subplots(1, 2, figsize=(16, 6))

device_dist.plot(kind='pie', ax=axes[0], autopct='%1.1f%%', startangle=90)
axes[0].set_title('Traffic by Device Type', fontsize=14, fontweight='bold')
axes[0].set_ylabel('')

browser_dist.plot(kind='barh', ax=axes[1], color='purple')
axes[1].set_title('Top 10 Browsers', fontsize=14, fontweight='bold')
axes[1].set_xlabel('Event Count')

plt.tight_layout()
plt.savefig('device_browser_analysis.png', dpi=300, bbox_inches='tight')
print("✅ Saved: device_browser_analysis.png")
plt.show()

print(f"\n📱 Device distribution:\n{device_dist}")
print(f"\n🌐 Top browsers:\n{browser_dist.head(5)}")

# %% Key Insights
print("\n" + "="*80)
print(" " * 25 + "KEY INSIGHTS & RECOMMENDATIONS")
print("="*80)

landing_to_signin = funnel_df[funnel_df['Step'] == 'Sign In']['Step %'].values[0] if len(funnel_df) > 1 else 0
signin_to_subscription = funnel_df[funnel_df['Step'] == 'Subscription']['Step %'].values[0] if len(funnel_df) > 2 else 0
subscription_to_settings = funnel_df[funnel_df['Step'] == 'Settings']['Step %'].values[0] if len(funnel_df) > 3 else 0

recommendations = []

# Landing page conversion
if landing_to_signin < 20:
    recommendations.append({
        'Priority': '🔴 CRITICAL',
        'Area': 'Landing Page → Sign In',
        'Issue': f'Only {landing_to_signin:.1f}% of visitors click Get Started',
        'Impact': 'HIGH - First impression matters most',
        'Solutions': [
            '• Make CTA buttons 2x larger and more prominent',
            '• Add urgency: "Start your free trial today"',
            '• Place CTA above the fold on mobile',
            '• Add social proof (testimonials, user count)',
            '• Simplify value proposition messaging'
        ]
    })

# Subscription page
if subscription_to_settings < 30:
    recommendations.append({
        'Priority': '🔴 CRITICAL',
        'Area': 'Subscription Page → Payment',
        'Issue': f'Only {subscription_to_settings:.1f}% complete payment',
        'Impact': 'HIGHEST - This is where money is lost',
        'Solutions': [
            '• Add 7-day FREE TRIAL (no credit card required)',
            '• Show "Cancel anytime" more prominently',
            '• Add money-back guarantee badge',
            '• Include customer testimonials on pricing page',
            '• Test lower pricing ($6.99 vs $9.99)',
            '• Add exit-intent popup with 20% discount'
        ]
    })

# Time on page
if len(time_on_page_df) > 0:
    subscription_time = time_on_page_df[time_on_page_df['page'] == '/subscription']['time_seconds'].median() if len(time_on_page_df[time_on_page_df['page'] == '/subscription']) > 0 else 0
    if subscription_time < 30:
        recommendations.append({
            'Priority': '🟡 IMPORTANT',
            'Area': 'Subscription Page Engagement',
            'Issue': f'Users spend only {subscription_time:.0f} seconds on pricing page',
            'Impact': 'MEDIUM - Not enough time to convince',
            'Solutions': [
                '• Add feature comparison table',
                '• Include FAQ section on pricing page',
                '• Add video testimonial',
                '• Show value calculator (cost per message)',
            ]
        })

# Mobile optimization
mobile_traffic = device_dist.get('Mobile', 0) / device_dist.sum() * 100
if mobile_traffic > 30:
    recommendations.append({
        'Priority': '🟡 IMPORTANT',
        'Area': 'Mobile Experience',
        'Issue': f'{mobile_traffic:.0f}% of traffic is mobile',
        'Impact': 'MEDIUM - Large user segment',
        'Solutions': [
            '• Optimize mobile checkout flow',
            '• Make CTAs thumb-friendly (larger tap targets)',
            '• Reduce form fields on mobile',
            '• Test mobile-specific landing page'
        ]
    })

# Quick wins
recommendations.append({
    'Priority': '🟢 QUICK WIN',
    'Area': 'Immediate Improvements',
    'Issue': 'Low-hanging fruit for conversion boost',
    'Impact': 'LOW EFFORT, HIGH RETURN',
    'Solutions': [
        '• Add live chat support widget',
        '• Include phone number prominently',
        '• Add trust badges (SSL, payment security)',
        '• Show limited-time offer banner',
        '• Add progress indicator in signup flow'
    ]
})

# Print recommendations
for i, rec in enumerate(recommendations, 1):
    print(f"\n{rec['Priority']} #{i}: {rec['Area']}")
    print("-" * 80)
    print(f"Issue: {rec['Issue']}")
    print(f"Impact: {rec['Impact']}")
    print(f"\nRecommended Solutions:")
    for solution in rec['Solutions']:
        print(f"  {solution}")

print("\n" + "="*80)
print(" " * 30 + "ANALYSIS COMPLETE")
print("="*80)
print("\n📁 Generated Files:")
print("   • page_views_analysis.png")
print("   • time_on_page_analysis.png") if len(time_on_page_df) > 0 else None
print("   • conversion_funnel.png")
print("   • drop_off_analysis.png")
print("   • traffic_patterns.png")
print("   • device_browser_analysis.png")
print("   • conversion_funnel.csv")
print("   • drop_off_rates.csv")
print("   • time_on_page_by_page.csv") if len(time_on_page_df) > 0 else None
print("\n✅ Run complete!")

