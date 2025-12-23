import csv
import os
import sys

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from variance.config_loader import load_config_bundle
from variance.get_market_data import MarketDataFactory
from variance.vol_screener import _is_illiquid


def run_shadow_diagnostic():
    print("🔬 VARIANCE RESEARCH: Data Integrity Impact Study")
    print(
        "Hypothesis: Allowing 'iv_scale_corrected' will expand the tradable universe without compromising math."
    )
    print("-" * 60)

    config_bundle = load_config_bundle()
    rules = config_bundle["trading_rules"]
    watchlist_path = config_bundle["system_config"].get(
        "watchlist_path", "watchlists/default-watchlist.csv"
    )

    symbols = []
    with open(watchlist_path) as f:
        reader = csv.reader(f)
        for row in reader:
            if row and row[0] != "Symbol":
                symbols.append(row[0])

    print(f"Fetching data for {len(symbols)} symbols...")
    provider = MarketDataFactory.get_provider()
    market_data = provider.get_market_data(symbols)

    stats = {
        "PRODUCTION_PASSED": 0,
        "SHADOW_RECOVERED": 0,
        "FATAL_DROPS": 0,
        "RECOVERED_SYMBOLS": [],
    }

    SOFT_WARNINGS = ["iv_scale_corrected", "iv_scale_assumed_decimal"]

    for sym in symbols:
        data = market_data.get(sym, {})
        if not data or "error" in data:
            continue

        # 1. Run Production Logic (Strict)
        prod_dropped = False
        if data.get("warning"):
            prod_dropped = True

        # 2. Run Shadow Logic (Smart)
        warning = data.get("warning")
        shadow_dropped = False
        if warning and warning not in SOFT_WARNINGS:
            shadow_dropped = True

        # 3. Check other filters (Liquidity/VRP) to see if they'd pass anyway
        is_liquid = not _is_illiquid(sym, data, rules)
        vrp_s = data.get("vrp_structural", 0) or 0
        is_rich = vrp_s > rules.get("vrp_structural_threshold", 0.85)

        if is_liquid and is_rich:
            if not prod_dropped:
                stats["PRODUCTION_PASSED"] += 1
            elif not shadow_dropped:
                stats["SHADOW_RECOVERED"] += 1
                stats["RECOVERED_SYMBOLS"].append(f"{sym} (VRP: {vrp_s:.2f})")

        if shadow_dropped:
            stats["FATAL_DROPS"] += 1

    print("\n" + "=" * 40)
    print("      INTEGRITY IMPACT REPORT")
    print("=" * 40)
    print(f"✅ Currently Passing:   {stats['PRODUCTION_PASSED']}")
    print(
        f"➕ Shadow Recovered:    {stats['SHADOW_RECOVERED']}  <-- High Quality candidates currently blocked"
    )
    print(f"💀 Fatal Data Errors:   {stats['FATAL_DROPS']}")
    print("-" * 40)
    print("Top 10 Recovered Candidates:")
    for sym in stats["RECOVERED_SYMBOLS"][:10]:
        print(f"  - {sym}")


if __name__ == "__main__":
    run_shadow_diagnostic()
