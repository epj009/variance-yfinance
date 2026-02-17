#!/usr/bin/env python3
"""
Test futures support with PureTastytradeProvider.

Usage:
    python scripts/test_futures_pure_tastytrade.py
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


def test_futures():
    """Test futures with PureTastytradeProvider."""
    from variance.market_data.pure_tastytrade_provider import PureTastytradeProvider

    print("=" * 70)
    print("FUTURES SUPPORT TEST - PURE TASTYTRADE")
    print("=" * 70)
    print()

    # Test both equities and futures
    test_symbols = ["AAPL", "SPY", "/ES", "/NQ", "/CL"]

    print(f"Testing {len(test_symbols)} symbols (equities + futures)")
    print(f"Symbols: {test_symbols}")
    print()

    print("Creating PureTastytradeProvider...")
    provider = PureTastytradeProvider()
    print("✅ Provider created\n")

    print("Fetching market data...")
    print()

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
    complete = 0
    futures_count = 0
    futures_success = 0

    for symbol in test_symbols:
        data = results.get(symbol, {})
        is_future = symbol.startswith("/")

        if is_future:
            futures_count += 1

        if "error" in data:
            print(f"❌ {symbol:6} Error: {data['error']}")
            continue

        successful += 1
        if is_future:
            futures_success += 1

        # Check completeness
        has_price = data.get("price") is not None
        has_iv = data.get("iv") is not None
        has_hv30 = data.get("hv30") is not None
        has_hv90 = data.get("hv90") is not None
        has_returns = len(data.get("returns", [])) > 0

        if has_price and has_iv and has_hv30 and has_hv90 and has_returns:
            complete += 1
            status = "✅ COMPLETE"
        elif has_price and has_hv30 and has_hv90:
            status = "✅ GOOD   "
        else:
            status = "⚠️  PARTIAL"

        price = data.get("price")
        iv = data.get("iv")
        hv30 = data.get("hv30")
        hv90 = data.get("hv90")
        returns = len(data.get("returns", []))

        price_str = f"${price:7.2f}" if price is not None else "   None"
        iv_str = f"{iv:5.2f}%" if iv is not None else "  None"
        hv30_str = f"{hv30 * 100:5.2f}%" if hv30 is not None else "  None"
        hv90_str = f"{hv90 * 100:5.2f}%" if hv90 is not None else "  None"

        print(
            f"{status} {symbol:6} "
            f"Price: {price_str} | "
            f"IV: {iv_str} | "
            f"HV30: {hv30_str} | "
            f"HV90: {hv90_str} | "
            f"Returns: {returns:2d}"
        )

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()

    print(f"Total symbols: {len(test_symbols)}")
    print(
        f"Successful: {successful}/{len(test_symbols)} ({successful / len(test_symbols) * 100:.0f}%)"
    )
    print(
        f"Complete data: {complete}/{len(test_symbols)} ({complete / len(test_symbols) * 100:.0f}%)"
    )
    print()
    print(f"Futures tested: {futures_count}")
    print(
        f"Futures successful: {futures_success}/{futures_count} ({futures_success / futures_count * 100:.0f}%)"
    )
    print()

    # Verdict
    if futures_success == futures_count and complete >= len(test_symbols) * 0.8:
        print("✅ ✅ ✅  SUCCESS! FUTURES SUPPORT WORKING!  ✅ ✅ ✅")
        print()
        print("All futures symbols have complete data from Tastytrade!")
        print("DXLink integration is working for both equities and futures.")
        print()
        return True
    elif futures_success >= futures_count * 0.6:
        print(f"✅  GOOD - Most futures working ({futures_success}/{futures_count})")
        return True
    else:
        print(f"⚠️  PARTIAL - Some futures failed ({futures_success}/{futures_count})")
        return False


if __name__ == "__main__":
    import logging

    logging.basicConfig(
        level=logging.DEBUG, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    success = test_futures()
    sys.exit(0 if success else 1)
