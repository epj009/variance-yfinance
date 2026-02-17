#!/usr/bin/env python3
"""
Test DXLink with futures symbols to determine correct symbol format.

Usage:
    python scripts/test_futures_dxlink.py
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


def test_futures_symbols():
    """Test various futures symbol formats with DXLink."""
    from tastytrade import Session

    from variance.market_data.dxlink_hv_provider import DXLinkHVProvider

    print("=" * 70)
    print("FUTURES DXLINK SYMBOL FORMAT TEST")
    print("=" * 70)
    print()

    # Test different symbol formats
    test_cases = [
        ("/ES", "Variance format (with slash)"),
        ("ES", "Without slash"),
        ("/ES:XCME", "With exchange"),
        ("ES:XCME", "Without slash, with exchange"),
    ]

    client_secret = os.getenv("TT_CLIENT_SECRET")
    refresh_token = os.getenv("TT_REFRESH_TOKEN")

    if not client_secret or not refresh_token:
        print("❌ Missing TT_CLIENT_SECRET or TT_REFRESH_TOKEN")
        return False

    print("Creating Tastytrade session...")
    session = Session(provider_secret=client_secret, refresh_token=refresh_token)
    print("✅ Session created\n")

    print("Creating DXLinkHVProvider...")
    provider = DXLinkHVProvider(session)
    print("✅ Provider created\n")

    results = {}

    for symbol_format, description in test_cases:
        print(f"Testing: {symbol_format:15} ({description})")
        print("-" * 70)

        try:
            data = provider.get_market_data_sync(symbol_format, timeout=10.0)

            price = data.get("price")
            hv30 = data.get("hv30")
            hv90 = data.get("hv90")
            returns_count = len(data.get("returns", []))

            if price and hv30 and hv90:
                results[symbol_format] = "✅ SUCCESS"
                print(
                    f"✅ SUCCESS: Price=${price:.2f}, HV30={hv30 * 100:.2f}%, HV90={hv90 * 100:.2f}%, Returns={returns_count}"
                )
            elif price:
                results[symbol_format] = "⚠️  PARTIAL"
                print(
                    f"⚠️  PARTIAL: Price=${price:.2f}, HV30={hv30}, HV90={hv90}, Returns={returns_count}"
                )
            else:
                results[symbol_format] = "❌ FAILED"
                print("❌ FAILED: No data received")

        except Exception as e:
            results[symbol_format] = f"❌ ERROR: {str(e)[:50]}"
            print(f"❌ ERROR: {e}")

        print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()

    for symbol_format, result in results.items():
        print(f"{symbol_format:15} {result}")

    print()

    # Recommendation
    success_formats = [k for k, v in results.items() if "SUCCESS" in v]
    if success_formats:
        print(f"✅ RECOMMENDED FORMAT: {success_formats[0]}")
        return True
    else:
        print("⚠️  No format worked - futures may need front-month contract specification")
        return False


if __name__ == "__main__":
    import logging

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    success = test_futures_symbols()
    sys.exit(0 if success else 1)
