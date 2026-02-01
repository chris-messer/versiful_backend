#!/bin/bash
# Weekly Conversion Analysis Script
# Run this every week to track conversion improvements

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "=============================================="
echo "  VERSIFUL WEEKLY CONVERSION ANALYSIS"
echo "=============================================="
echo ""
echo "📅 Analysis Date: $(date +"%B %d, %Y")"
echo ""

# Check if CSV exists
if [ ! -f "results/posthog-analytics.csv" ]; then
    echo "❌ Error: posthog-analytics.csv not found"
    echo ""
    echo "Please export data from PostHog:"
    echo "  1. Go to PostHog → Events → Export"
    echo "  2. Filter: environment = 'prod'"
    echo "  3. Date range: Last 7-30 days"
    echo "  4. Save as: conversion_analysis/results/posthog-analytics.csv"
    echo ""
    exit 1
fi

# Archive previous results
ARCHIVE_DIR="results/archive/$(date +%Y-%m-%d)"
if [ -f "results/analysis_output.txt" ]; then
    echo "📦 Archiving previous results to: $ARCHIVE_DIR"
    mkdir -p "$ARCHIVE_DIR"
    cp results/analysis_output.txt "$ARCHIVE_DIR/" 2>/dev/null || true
    cp results/*.csv "$ARCHIVE_DIR/" 2>/dev/null || true
    echo "   ✅ Archived"
    echo ""
fi

# Run analysis
echo "🔍 Running conversion analysis..."
echo ""
python scripts/conversion_analysis.py

# Check if analysis succeeded
if [ $? -eq 0 ]; then
    echo ""
    echo "=============================================="
    echo "  ✅ ANALYSIS COMPLETE"
    echo "=============================================="
    echo ""
    echo "📊 Results saved to:"
    echo "   - results/analysis_output.txt"
    echo "   - results/*.png (visualizations)"
    echo "   - results/*.csv (data exports)"
    echo ""
    
    # Display key metrics
    echo "=== KEY METRICS ==="
    echo ""
    grep -A 10 "CONVERSION FUNNEL ANALYSIS" results/analysis_output.txt | grep -v "^$"
    echo ""
    
    # Display top recommendations
    echo "=== TOP RECOMMENDATIONS ==="
    echo ""
    grep -A 15 "KEY INSIGHTS & RECOMMENDATIONS" results/analysis_output.txt | grep "🔴\|🟡" | head -6
    echo ""
    
    # Compare with last week if available
    LAST_WEEK=$(ls -td results/archive/*/conversion_funnel.csv 2>/dev/null | head -1)
    if [ -n "$LAST_WEEK" ]; then
        echo "=== WEEK-OVER-WEEK COMPARISON ==="
        echo ""
        echo "Comparing with: $(dirname "$LAST_WEEK" | xargs basename)"
        echo ""
        
        # Simple comparison
        python3 << 'EOF'
import pandas as pd
import sys

try:
    current = pd.read_csv('results/conversion_funnel.csv')
    previous = pd.read_csv(sys.argv[1])
    
    print(f"{'Step':<20} {'Previous':>10} {'Current':>10} {'Change':>10}")
    print("-" * 55)
    
    for i, row in current.iterrows():
        step = row['Step']
        curr_pct = row['Overall %']
        
        if i < len(previous):
            prev_pct = previous.iloc[i]['Overall %']
            change = curr_pct - prev_pct
            change_str = f"{change:+.1f}%"
            
            if abs(change) < 0.5:
                emoji = "  "
            elif change > 0:
                emoji = "📈"
            else:
                emoji = "📉"
            
            print(f"{step:<20} {prev_pct:>9.1f}% {curr_pct:>9.1f}% {change_str:>9} {emoji}")
        else:
            print(f"{step:<20} {'N/A':>10} {curr_pct:>9.1f}% {'NEW':>10}")
            
except Exception as e:
    print(f"Could not compare: {e}")
EOF
        echo ""
    fi
    
    echo "=============================================="
    echo ""
    echo "💡 Next Steps:"
    echo "   1. Review full analysis: cat results/analysis_output.txt"
    echo "   2. View visualizations: open results/*.png"
    echo "   3. Implement top recommendations"
    echo "   4. Run again next week to measure impact"
    echo ""
    echo "📚 Documentation: cat README.md"
    echo ""
else
    echo ""
    echo "❌ Analysis failed. Check error messages above."
    exit 1
fi

