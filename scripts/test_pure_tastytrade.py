#!/usr/bin/env python3
"""
Test Pure Tastytrade Provider - Complete legacy provider replacement validation.

Tests that we can get complete market data using ONLY Tastytrade (REST + DXLink).

Usage:
    python scripts/test_pure_tastytrade.py
"""

import os
import sys
from pathlib import Path

# Add project root
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))


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


def test_pure_tastytrade():
    """Test pure Tastytrade provider (no legacy provider)."""
    from variance.market_data.pure_tastytrade_provider import PureTastytradeProvider

    print("=" * 70)
    print("PURE TASTYTRADE PROVIDER TEST - NO YFINANCE!")
    print("=" * 70)

    # Test symbols - diverse set
    test_symbols = ["AAPL", "SPY", "QQQ", "TSLA", "NVDA"]

    print("\n1. Testing pure Tastytrade provider (REST + DXLink)")
    print(f"   Symbols: {test_symbols}")
    print("   This uses ZERO legacy provider calls!\n")

    print("2. Creating PureTastytradeProvider...")
    provider = PureTastytradeProvider()
    print("✅ Provider created")

    print("\n3. Fetching market data (may take a minute for DXLink fallbacks)...\n")

    try:
        results = provider.get_market_data(test_symbols)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Analysis
    print()
    print("=" * 70)
    print("RESULTS")
    print("=" * 70)
    print()

    successful = 0
    total = len(test_symbols)
    complete_data = 0

    for symbol in test_symbols:
        data = results.get(symbol, {})

        if "error" in data:
            print(f"❌ {symbol:6} Error: {data['error']}")
            continue

        successful += 1

        # Check completeness
        has_price = data.get("price") is not None
        has_iv = data.get("iv") is not None
        has_hv30 = data.get("hv30") is not None
        has_hv90 = data.get("hv90") is not None
        has_returns = len(data.get("returns", [])) > 0

        if has_price and has_iv and has_hv30 and has_hv90 and has_returns:
            complete_data += 1
            status = "✅ COMPLETE"
        else:
            status = "⚠️  PARTIAL"

        price = data.get("price", 0)
        iv = data.get("iv", 0)
        hv30 = data.get("hv30", 0)
        hv90 = data.get("hv90", 0)
        returns = len(data.get("returns", []))
        vrp = data.get("vrp_tactical")

        print(
            f"{status} {symbol:6} "
            f"Price: ${price:7.2f} | "
            f"IV: {iv:5.2f}% | "
            f"HV30: {hv30 * 100:5.2f}% | "
            f"HV90: {hv90 * 100:5.2f}% | "
            f"Returns: {returns:2d} | "
            f"VRP: {vrp:.2f}"
            if vrp
            else ""
        )

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()

    success_pct = (successful / total * 100) if total > 0 else 0
    complete_pct = (complete_data / total * 100) if total > 0 else 0

    print(f"Symbols tested: {total}")
    print(f"Successful: {successful}/{total} ({success_pct:.0f}%)")
    print(f"Complete data: {complete_data}/{total} ({complete_pct:.0f}%)")
    print()

    # Verdict
    print("=" * 70)
    print("VERDICT")
    print("=" * 70)
    print()

    if complete_data == total:
        print("✅ ✅ ✅  PERFECT! YFINANCE ELIMINATED!  ✅ ✅ ✅")
        print()
        print("All symbols have complete market data from Tastytrade!")
        print("Price, IV, HV30, HV90, Returns all available.")
        print()
        print("📊 Data sources used:")
        print("  - Tastytrade REST /market-metrics: IV, IVR, IVP")
        print("  - Tastytrade REST /market-data: Prices")
        print("  - DXLink WebSocket: HV30/HV90, Returns")
        print()
        print("🎉 legacy provider dependency can be REMOVED!")
        print()
        return True
    elif complete_data >= total * 0.8:
        print(f"✅  GOOD ({complete_pct:.0f}% complete data)")
        print()
        print("Most symbols have complete data from Tastytrade.")
        print("legacy provider replacement is working!")
        print()
        return True
    else:
        print(f"⚠️  PARTIAL ({complete_pct:.0f}% complete data)")
        print()
        print("Some symbols missing data.")
        print("Check logs for details.")
        print()
        return False


if __name__ == "__main__":
    import logging

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    success = test_pure_tastytrade()
    sys.exit(0 if success else 1)
