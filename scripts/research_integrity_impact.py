import csv
import os
import sys
from typing import Any, cast

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from variance.config_loader import load_config_bundle
from variance.market_data.service import MarketDataFactory
from variance.vol_screener import _is_illiquid


def run_shadow_diagnostic() -> None:
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

    symbols: list[str] = []
    with open(watchlist_path) as f:
        reader = csv.reader(f)
        for row in reader:
            if row and row[0] != "Symbol":
                symbols.append(row[0])

    print(f"Fetching data for {len(symbols)} symbols...")
    provider = MarketDataFactory.get_provider()
    market_data = cast(dict[str, dict[str, Any]], provider.get_market_data(symbols))

    production_passed = 0
    shadow_recovered = 0
    fatal_drops = 0
    recovered_symbols: list[str] = []

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
        illiquid, _implied = _is_illiquid(sym, data, rules)
        is_liquid = not illiquid
        vrp_s = float(data.get("vrp_structural", 0) or 0)
        is_rich = vrp_s > float(rules.get("vrp_structural_threshold", 0.85))

        if is_liquid and is_rich:
            if not prod_dropped:
                production_passed += 1
            elif not shadow_dropped:
                shadow_recovered += 1
                recovered_symbols.append(f"{sym} (VRP: {vrp_s:.2f})")

        if shadow_dropped:
            fatal_drops += 1

    print("\n" + "=" * 40)
    print("      INTEGRITY IMPACT REPORT")
    print("=" * 40)
    print(f"✅ Currently Passing:   {production_passed}")
    print(
        f"➕ Shadow Recovered:    {shadow_recovered}  <-- High Quality candidates currently blocked"
    )
    print(f"💀 Fatal Data Errors:   {fatal_drops}")
    print("-" * 40)
    print("Top 10 Recovered Candidates:")
    for sym in recovered_symbols[:10]:
        print(f"  - {sym}")


if __name__ == "__main__":
    run_shadow_diagnostic()
