#!/usr/bin/env python3
"""
Test Tastytrade candles endpoint for HV calculation feasibility.

Tests:
1. Can we access /market-data/candles endpoint?
2. Does it return historical bars for various symbols?
3. Can we calculate HV30/HV90 from the data?
4. Test with: equity, futures, small cap

Usage:
    python scripts/test_tastytrade_candles.py
"""

import math
import os
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))


def load_env_file(filepath):
    """Manually load environment variables from .env file."""
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


# Load credentials
load_env_file(project_root / ".env.tastytrade")

TT_BASE = "https://api.tastytrade.com"


def get_oauth_token():
    """Get OAuth access token."""
    client_id = os.getenv("TT_CLIENT_ID")
    client_secret = os.getenv("TT_CLIENT_SECRET")
    refresh_token = os.getenv("TT_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        print("❌ Missing Tastytrade credentials")
        return None

    response = requests.post(
        f"{TT_BASE}/oauth/token",
        json={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=10,
    )

    if response.ok:
        return response.json()["access_token"]
    else:
        print(f"❌ OAuth failed: {response.status_code}")
        return None


def test_candles_endpoint(token, symbol, days=100):
    """
    Test fetching historical candles from Tastytrade.

    Args:
        token: OAuth access token
        symbol: Symbol to test
        days: Days of history to fetch

    Returns:
        List of candle dicts or None if failed
    """
    print(f"\n{'=' * 60}")
    print(f"Testing: {symbol}")
    print(f"{'=' * 60}")

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    # Try different endpoint patterns
    endpoints = [
        f"/market-data/candles/{symbol}",
        f"/instruments/equity-options/{symbol}/candles",
        f"/instruments/futures/{symbol}/candles",
        f"/candles/{symbol}",
    ]

    params = {
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "interval": "1d",
    }

    for endpoint in endpoints:
        print(f"\nTrying endpoint: {endpoint}")

        response = requests.get(
            f"{TT_BASE}{endpoint}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=10,
        )

        print(f"Status: {response.status_code}")

        if response.ok:
            data = response.json()

            # Print raw response structure
            print(f"Response keys: {list(data.keys())}")

            # Try to find the candles
            candles = None
            if "data" in data:
                candles = data["data"]
            elif isinstance(data, list):
                candles = data

            if candles:
                print(f"✅ SUCCESS! Retrieved {len(candles)} candles")

                # Show sample candle
                if candles:
                    sample = candles[0]
                    print("\nSample candle structure:")
                    print(f"  Keys: {list(sample.keys())}")
                    print(f"  Sample: {sample}")

                return candles
            else:
                print("⚠️  Response OK but no candles found")
                print(f"Raw response: {data}")
        else:
            print(f"❌ Failed: {response.text[:200]}")

    print(f"\n❌ All endpoints failed for {symbol}")
    return None


def calculate_hv_from_candles(candles, window=30):
    """
    Calculate historical volatility from candles.

    Args:
        candles: List of candle dicts
        window: Rolling window (30 or 90)

    Returns:
        Annualized HV or None
    """
    if len(candles) < window + 1:
        print(f"⚠️  Insufficient data: {len(candles)} candles, need {window + 1}")
        return None

    # Try different possible field names for close price
    close_fields = ["close", "Close", "close_price", "closePrice"]

    closes = []
    close_field = None

    for field in close_fields:
        if field in candles[0]:
            close_field = field
            break

    if not close_field:
        print(f"❌ Cannot find close price field. Available: {list(candles[0].keys())}")
        return None

    # Extract closes
    for candle in candles[-(window + 1) :]:
        closes.append(float(candle[close_field]))

    # Calculate log returns
    returns = []
    for i in range(1, len(closes)):
        ret = math.log(closes[i] / closes[i - 1])
        returns.append(ret)

    if len(returns) < window:
        return None

    # Standard deviation
    std_dev = statistics.stdev(returns)

    # Annualize (252 trading days)
    hv = std_dev * math.sqrt(252)

    return hv


def main():
    """Run feasibility tests."""
    print("=" * 60)
    print("TASTYTRADE CANDLES ENDPOINT FEASIBILITY TEST")
    print("=" * 60)
    print("\nTesting whether we can:")
    print("1. Access /market-data/candles endpoint")
    print("2. Get historical bars for various symbols")
    print("3. Calculate HV30/HV90 from the data")

    # Get token
    token = get_oauth_token()
    if not token:
        print("\n❌ Cannot proceed - authentication failed")
        return

    print("\n✅ OAuth token obtained")

    # Test symbols
    test_cases = [
        ("SPY", "Large cap equity"),
        ("/ES", "S&P 500 futures"),
        ("AAPL", "Popular equity"),
        ("/CL", "Crude oil futures"),
        ("RKLB", "Small cap equity"),  # Rocket Lab - small cap
    ]

    results = {}

    for symbol, description in test_cases:
        candles = test_candles_endpoint(token, symbol, days=100)

        if candles:
            # Try to calculate HV30
            hv30 = calculate_hv_from_candles(candles, window=30)
            hv90 = calculate_hv_from_candles(candles, window=90)

            results[symbol] = {
                "description": description,
                "candles_count": len(candles),
                "hv30": hv30,
                "hv90": hv90,
                "success": hv30 is not None and hv90 is not None,
            }

            if hv30 and hv90:
                print("\n✅ Calculated HV:")
                print(f"   HV30: {hv30:.4f} ({hv30 * 100:.2f}%)")
                print(f"   HV90: {hv90:.4f} ({hv90 * 100:.2f}%)")
            else:
                print("\n⚠️  Could not calculate HV")
        else:
            results[symbol] = {
                "description": description,
                "success": False,
                "error": "No candles retrieved",
            }

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    success_count = sum(1 for r in results.values() if r.get("success"))
    total_count = len(results)

    print(f"\nResults: {success_count}/{total_count} symbols successful\n")

    for symbol, result in results.items():
        status = "✅" if result.get("success") else "❌"
        desc = result["description"]
        print(f"{status} {symbol:8} ({desc})")

        if result.get("success"):
            print(
                f"        {result['candles_count']} candles, "
                f"HV30={result['hv30']:.4f}, HV90={result['hv90']:.4f}"
            )
        else:
            print(f"        Error: {result.get('error', 'Unknown')}")

    # Final verdict
    print("\n" + "=" * 60)
    print("FEASIBILITY VERDICT")
    print("=" * 60)

    if success_count >= total_count * 0.8:  # 80%+ success rate
        print("\n✅ FEASIBLE - Candles endpoint works for most symbols")
        print("\nRecommendation: Implement HV calculator using candles endpoint")
        print("Expected coverage: 95%+ (current: ~80%)")
    elif success_count > 0:
        print("\n⚠️  PARTIAL - Works for some symbols but not all")
        print(
            f"\nSuccess rate: {success_count}/{total_count} ({success_count / total_count * 100:.0f}%)"
        )
        print("May still be worth implementing with fallbacks")
    else:
        print("\n❌ NOT FEASIBLE - Candles endpoint not accessible")
        print("\nAlternative: Consider IBKR API or other data provider")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
