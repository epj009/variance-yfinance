#!/usr/bin/env python3
"""Format vol_screener JSON output for human-readable terminal display."""

import json
import sys
from datetime import datetime
from typing import Any


def is_market_open_at(dt: datetime) -> bool:
    """Check if US market is open at given datetime (assumes ET timezone)."""
    # Weekend check
    if dt.weekday() >= 5:  # Saturday=5, Sunday=6
        return False

    # Market hours: 9:30 AM - 4:00 PM ET (assume input is in local time = ET)
    hour = dt.hour
    minute = dt.minute

    if hour < 9 or hour >= 16:
        return False
    if hour == 9 and minute < 30:
        return False

    return True


def format_screener_output(data: dict[str, Any]) -> None:
    """Pretty-print screener results to terminal."""

    summary = data.get("summary", {})
    candidates = data.get("candidates", [])
    meta = data.get("meta", {})

    # Header
    print("\n╔════════════════════════════════════════════════════════════════════════════╗")
    print("║                    VARIANCE VOLATILITY SCREENER                            ║")
    print("╚════════════════════════════════════════════════════════════════════════════╝\n")

    # Profile info
    profile = meta.get("profile", "unknown")
    scan_time = meta.get("scan_timestamp", "N/A")
    print(f"Profile: {profile.upper()}")

    constraints = summary.get("active_constraints", {})
    if constraints:
        vrp = constraints.get("min_vrp", 0.0)
        ivp = constraints.get("min_ivp", 0.0)
        yld = constraints.get("min_yield", 0.0)
        prc = constraints.get("min_price", 0.0)
        print(
            f"Active:  VRP > {vrp:.1f} | IVP > {ivp:.0f}% | Yield > {yld:.1f}% | Price > ${prc:.0f}"
        )

    print(f"Time:    {scan_time}")
    print()

    # Summary stats
    print("─" * 80)
    print("SUMMARY")
    print("─" * 80)
    scanned = summary.get("scanned_symbols_count", 0)
    found = summary.get("candidates_count", 0)
    print(f"  Symbols Scanned:  {scanned}")
    print(f"  Candidates Found: {found}")

    if found > 0:
        pct = (found / scanned * 100) if scanned > 0 else 0
        print(f"  Pass Rate:        {pct:.1f}%")
    print()

    # Filter diagnostics
    print("─" * 80)
    print("FILTER DIAGNOSTICS (symbols can fail multiple filters)")
    print("─" * 80)
    filters = [
        ("Low VRP Structural", summary.get("low_vrp_structural_count", 0)),
        ("Low VRP Tactical", summary.get("tactical_skipped_count", 0)),
        ("Low IV Percentile", summary.get("low_iv_percentile_skipped_count", 0)),
        ("Low Vol Momentum", summary.get("vol_momentum_skipped_count", 0)),
        ("Illiquid", summary.get("illiquid_skipped_count", 0)),
        ("Retail Inefficient", summary.get("retail_inefficient_skipped_count", 0)),
        ("High Slippage", summary.get("slippage_skipped_count", 0)),
        ("Low Yield", summary.get("low_yield_skipped_count", 0)),
        ("Correlation", summary.get("correlation_skipped_count", 0)),
        ("Sector Excluded", summary.get("sector_skipped_count", 0)),
    ]

    # Show ALL filters with their counts
    for name, count in filters:
        print(f"  {name:<25} {count:>4} symbols")

    # Show unique rejection count
    total_rejections = scanned - found
    print(f"  {'─' * 35}")
    print(f"  {'Unique Rejections':<25} {total_rejections:>4} symbols")
    print(f"  {'Passed All Filters':<25} {found:>4} symbols")
    print()

    # Rejection details (debug mode)
    rejections = meta.get("filter_rejections", {})
    if rejections:
        print("─" * 80)
        print("REJECTION DETAILS")
        print("─" * 80)
        for symbol in sorted(rejections):
            print(f"  {symbol}: {rejections[symbol]}")
        print()

    # Candidates table
    if candidates:
        print("─" * 80)
        print("CANDIDATES")
        print("─" * 80)
        print()

        # Table header
        header = f"{'Symbol':<8} {'Asset':<10} {'Price':<8} {'VRP S':<7} {'VRP T':<7} {'IV%':<6} {'Signal':<8} {'Score':<6} {'Vote':<8}"
        print(header)
        print("─" * 80)

        # Sort by score descending
        sorted_candidates = sorted(candidates, key=lambda x: x.get("score", 0), reverse=True)

        for c in sorted_candidates:
            sym = c.get("Symbol", "N/A")[:7]
            asset = c.get("Asset Class", "N/A")[:9]
            price = c.get("Price", 0)
            vrp_s = c.get("VRP Structural", 0)
            vrp_t = c.get("vrp_tactical", 0)
            iv_pct = c.get("IV Percentile")
            signal = c.get("Signal", "N/A")[:7]
            score = c.get("score", 0)
            vote = c.get("Vote", "N/A")[:7]

            # Format values
            price_str = (
                f"${price:.2f}" if price and price < 1000 else f"${price:.0f}" if price else "N/A"
            )
            vrp_s_str = f"{vrp_s:.2f}" if vrp_s else "N/A"
            vrp_t_str = f"{vrp_t:.2f}" if vrp_t else "N/A"
            iv_pct_str = f"{iv_pct:.0f}" if iv_pct is not None else "N/A"
            score_str = f"{score:.1f}" if score else "0.0"

            row = f"{sym:<8} {asset:<10} {price_str:<8} {vrp_s_str:<7} {vrp_t_str:<7} {iv_pct_str:<6} {signal:<8} {score_str:<6} {vote:<8}"
            print(row)

        print()
        print("─" * 80)
        print("Legend: VRP S = Structural (IV/HV90), VRP T = Tactical (IV/HV30)")
        print("        Vote: BUY (score > 70), WATCH (50-70), PASS (< 50)")
        print("─" * 80)
    else:
        print("─" * 80)
        print("NO CANDIDATES FOUND")
        print("─" * 80)
        print()
        print("All symbols were filtered out. Consider:")
        print("  • Using --profile broad for lower thresholds")
        print("  • Running during market hours for more volatile opportunities")
        print("  • Reviewing filter diagnostics above to see what filtered symbols")
        print()

    # Market data quality warning
    md = meta.get("market_data_diagnostics", {})
    stale = md.get("stale_count", 0)
    total = md.get("symbols_total", 0)
    errors = md.get("symbols_with_errors", 0)

    # Check actual market hours at scan time
    scan_timestamp = meta.get("scan_timestamp", "")
    market_was_open = True  # Default assumption
    if scan_timestamp:
        try:
            scan_dt = datetime.fromisoformat(scan_timestamp.replace("Z", "+00:00"))
            market_was_open = is_market_open_at(scan_dt)
        except (ValueError, AttributeError):
            pass  # Keep default

    # Check if candidates have rate limiting warnings
    rate_limited_count = 0
    if candidates:
        for c in candidates:
            warning_detail = c.get("warning_detail", {})
            if warning_detail.get("reason") == "price_unavailable" and warning_detail.get("cached"):
                rate_limited_count += 1

    # Display warnings based on ACTUAL conditions
    if rate_limited_count > 0 and market_was_open:
        print("\n⚠️  YAHOO FINANCE RATE LIMITING DETECTED")
        print("─" * 80)
        print(f"  {stale}/{total} symbols using cached price data")
        print("  legacy data source returned 429 (Too Many Requests)")
        print()
        print("  Impact:")
        print("    • Price data: cached (from previous fetch)")
        print("    • Volatility metrics: FRESH from Tastytrade ✅")
        print("    • VRP calculations: accurate (use fresh IV/HV)")
        print()
        print("  Solutions:")
        print("    • Wait 5-10 minutes before running again")
        print("    • Use smaller watchlists (<100 symbols)")
        print("    • Results are still valid (VRP metrics are fresh)")
        print("─" * 80)
    elif not market_was_open:
        print("\nℹ️  MARKET STATUS")
        print("─" * 80)
        print("  Market was closed at scan time")
        print("  Using end-of-day data from last market close")
        print("─" * 80)
    elif errors > 5:
        print("\n⚠️  DATA QUALITY WARNING")
        print("─" * 80)
        print(f"  {errors} symbols had data fetch errors")
        print("  This may indicate API connectivity issues")
        print("─" * 80)

    print()


def main() -> None:
    """Read JSON from stdin and format for terminal."""
    try:
        data = json.load(sys.stdin)
        format_screener_output(data)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON input - {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
