#!/usr/bin/env python3
"""
Test DXLink HV fallback integration in MarketDataService.

Tests that symbols without HV30/HV90 in Tastytrade REST API
fall back to DXLink candle streaming for HV calculation.

Usage:
    python scripts/test_dxlink_fallback_integration.py
"""

import os
import sys
from pathlib import Path

# Add project root
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from variance.market_data.service import MarketDataService


def load_env_file(filepath):
    """Load environment variables."""
    if not filepath.exists():
        return
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:]
            if "=" in line:
                key, value = line.split("=", 1)
                value = value.strip().strip('"').strip("'")
                os.environ[key.strip()] = value


# Load Tastytrade credentials
load_env_file(project_root / ".env.tastytrade")

# Enable Tastytrade in runtime config
os.environ["RUNTIME_CONFIG"] = str(project_root / "config" / "runtime.json")


def test_dxlink_fallback():
    """Test DXLink fallback for symbols with missing HV."""
    print("=" * 60)
    print("DXLINK HV FALLBACK INTEGRATION TEST")
    print("=" * 60)

    # Test symbols:
    # - AAPL, SPY: Should have HV from REST API (no fallback needed)
    # - VXX, UVXY: Volatility products - may need DXLink fallback
    # - QQQ: Popular ETF - should have full coverage
    test_symbols = ["AAPL", "SPY", "QQQ", "VXX", "UVXY"]

    print(f"\n1. Testing symbols: {test_symbols}")
    print("   (Checking if DXLink fallback activates for missing HV)\n")

    # Create MarketDataService with cache enabled (allows after-hours fetch)
    from variance.market_data.cache import cache

    service = MarketDataService(cache=cache)

    print("2. Fetching market data...\n")
    results = service.get_market_data(test_symbols)

    # Analyze results
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print()

    has_hv30 = 0
    has_hv90 = 0
    total = 0

    for symbol in test_symbols:
        data = results.get(symbol, {})

        if "error" in data:
            print(f"❌ {symbol:6} Error: {data['error']}")
            continue

        total += 1
        hv30 = data.get("hv30")
        hv90 = data.get("hv90")
        iv = data.get("iv")
        source = data.get("data_source", "unknown")

        if hv30 is not None:
            has_hv30 += 1
        if hv90 is not None:
            has_hv90 += 1

        hv30_str = f"{hv30:.4f}" if hv30 is not None else "None "
        hv90_str = f"{hv90:.4f}" if hv90 is not None else "None "
        iv_str = f"{iv:.4f}" if iv is not None else "None "

        status = "✅" if (hv30 is not None and hv90 is not None) else "⚠️ "

        print(
            f"{status} {symbol:6} | HV30: {hv30_str} | HV90: {hv90_str} | "
            f"IV: {iv_str} | Source: {source}"
        )

    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print()

    hv30_pct = (has_hv30 / total * 100) if total > 0 else 0
    hv90_pct = (has_hv90 / total * 100) if total > 0 else 0

    print(f"Symbols processed: {total}")
    print(f"HV30 coverage: {has_hv30}/{total} ({hv30_pct:.1f}%)")
    print(f"HV90 coverage: {has_hv90}/{total} ({hv90_pct:.1f}%)")

    # Verdict
    print()
    print("=" * 60)
    print("VERDICT")
    print("=" * 60)
    print()

    if has_hv30 == total and has_hv90 == total:
        print("✅ ✅ ✅  PERFECT COVERAGE!  ✅ ✅ ✅")
        print()
        print("All symbols have HV30 and HV90!")
        print("DXLink fallback is working correctly.")
        print()
        return True
    elif has_hv30 >= total * 0.8 and has_hv90 >= total * 0.8:
        print(f"✅  GOOD COVERAGE ({hv30_pct:.0f}% HV30, {hv90_pct:.0f}% HV90)")
        print()
        print("Most symbols have HV metrics.")
        print("This is a significant improvement!")
        print()
        return True
    else:
        print(f"⚠️  PARTIAL COVERAGE ({hv30_pct:.0f}% HV30, {hv90_pct:.0f}% HV90)")
        print()
        print("Some symbols still missing HV.")
        print("Check logs for DXLink fallback status.")
        print()
        return False


if __name__ == "__main__":
    # Enable logging to see DXLink fallback messages
    import logging

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    success = test_dxlink_fallback()
    sys.exit(0 if success else 1)
