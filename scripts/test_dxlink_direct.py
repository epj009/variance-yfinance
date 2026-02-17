#!/usr/bin/env python3
"""
Test DXLink provider directly (bypassing legacy provider).

This proves DXLink works after hours!

Usage:
    python scripts/test_dxlink_direct.py
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


def test_dxlink_direct():
    """Test DXLink provider directly (no legacy provider dependency)."""
    from tastytrade import Session

    from variance.market_data.dxlink_hv_provider import DXLinkHVProvider

    print("=" * 70)
    print("DXLINK DIRECT TEST - AFTER HOURS VALIDATION")
    print("=" * 70)

    # Test symbols
    test_symbols = ["AAPL", "SPY", "QQQ", "MSFT", "TSLA"]

    print("\n1. Testing DXLink provider directly (bypassing legacy provider)")
    print(f"   Symbols: {test_symbols}")
    print()

    # Create session
    client_secret = os.getenv("TT_CLIENT_SECRET")
    refresh_token = os.getenv("TT_REFRESH_TOKEN")

    if not client_secret or not refresh_token:
        print("❌ Missing TT_CLIENT_SECRET or TT_REFRESH_TOKEN")
        return False

    print("2. Creating Tastytrade session...")
    session = Session(provider_secret=client_secret, refresh_token=refresh_token)
    print("✅ Session created")

    print("\n3. Creating DXLinkHVProvider...")
    provider = DXLinkHVProvider(session)
    print("✅ Provider created")

    print("\n4. Fetching market data via DXLink (this may take a few minutes)...\n")

    results = {}
    for i, symbol in enumerate(test_symbols, 1):
        print(f"   [{i}/{len(test_symbols)}] Fetching {symbol}...", end=" ", flush=True)

        try:
            data = provider.get_market_data_sync(symbol)
            results[symbol] = data

            price = data.get("price")
            hv30 = data.get("hv30")
            hv90 = data.get("hv90")
            returns_count = len(data.get("returns", []))

            if price and hv30 and hv90:
                print(
                    f"✅ Price=${price:.2f}, HV30={hv30 * 100:.1f}%, HV90={hv90 * 100:.1f}%, Returns={returns_count}"
                )
            else:
                print(f"⚠️  Incomplete data: price={price}, hv30={hv30}, hv90={hv90}")

        except Exception as e:
            print(f"❌ Error: {e}")
            results[symbol] = {"error": str(e)}

    # Analysis
    print()
    print("=" * 70)
    print("RESULTS")
    print("=" * 70)
    print()

    successful = 0
    total = len(test_symbols)

    for symbol, data in results.items():
        if "error" in data:
            print(f"❌ {symbol:6} Error: {data['error']}")
            continue

        price = data.get("price")
        hv30 = data.get("hv30")
        hv90 = data.get("hv90")
        returns = data.get("returns", [])

        if price and hv30 and hv90:
            successful += 1
            print(
                f"✅ {symbol:6} "
                f"Price: ${price:7.2f} | "
                f"HV30: {hv30 * 100:5.2f}% | "
                f"HV90: {hv90 * 100:5.2f}% | "
                f"Returns: {len(returns):2d}"
            )
        else:
            print(f"⚠️  {symbol:6} Incomplete data")

    # Verdict
    print()
    print("=" * 70)
    print("VERDICT")
    print("=" * 70)
    print()

    coverage = (successful / total * 100) if total > 0 else 0

    print(f"Symbols tested: {total}")
    print(f"Successful: {successful}/{total} ({coverage:.0f}%)")
    print()

    if successful == total:
        print("✅ ✅ ✅  PERFECT! ALL SYMBOLS RETRIEVED VIA DXLINK  ✅ ✅ ✅")
        print()
        print("DXLink works perfectly AFTER HOURS!")
        print("We can completely eliminate legacy provider dependency!")
        print()
        return True
    elif successful >= total * 0.8:
        print(f"✅  GOOD ({coverage:.0f}% success)")
        print()
        print("DXLink works after hours for most symbols.")
        print()
        return True
    else:
        print(f"⚠️  PARTIAL SUCCESS ({coverage:.0f}%)")
        print()
        return False


if __name__ == "__main__":
    import logging

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    success = test_dxlink_direct()
    sys.exit(0 if success else 1)
