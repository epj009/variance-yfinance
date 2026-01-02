#!/usr/bin/env python3
"""
Integration test for DXLink + HV Calculator.

Tests the complete flow:
1. OAuth authentication
2. DXLink credential retrieval
3. WebSocket connection
4. Historical candle retrieval
5. HV30/HV90 calculation

This validates the production implementation before integrating
into MarketDataService.

Usage:
    python scripts/test_dxlink_hv_integration.py
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import requests

# Add project root
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# Configure logging - DEBUG level to see all WebSocket messages
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Now import our modules
from variance.market_data.dxlink_client import DXLinkClient
from variance.market_data.hv_calculator import calculate_hv_metrics


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


load_env_file(project_root / ".env.tastytrade")


def get_oauth_access_token():
    """Get OAuth access token using refresh token."""
    client_id = os.getenv("TT_CLIENT_ID")
    client_secret = os.getenv("TT_CLIENT_SECRET")
    refresh_token = os.getenv("TT_REFRESH_TOKEN")
    base_url = os.getenv("API_BASE_URL", "https://api.tastytrade.com")

    if not all([client_id, client_secret, refresh_token]):
        raise ValueError("Missing OAuth credentials in .env.tastytrade")

    logger.info("Authenticating with OAuth...")

    response = requests.post(
        f"{base_url}/oauth/token",
        json={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=10,
    )

    if response.ok:
        data = response.json()
        logger.info("✅ OAuth access token obtained")
        return data["access_token"]
    else:
        raise Exception(f"OAuth failed: {response.status_code} - {response.text}")


def get_dxlink_credentials(access_token):
    """Get DXLink WebSocket credentials."""
    base_url = os.getenv("API_BASE_URL", "https://api.tastytrade.com")

    logger.info("Fetching DXLink credentials...")

    response = requests.get(
        f"{base_url}/api-quote-tokens",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )

    if response.ok:
        data = response.json()
        # Handle both possible response formats
        dxlink_data = data.get("data", data)

        logger.info("✅ DXLink credentials obtained")
        logger.info(f"   URL: {dxlink_data.get('dxlink-url', 'N/A')}")
        logger.info(f"   Level: {dxlink_data.get('level', 'N/A')}")
        expires = dxlink_data.get("expires-at", "N/A")
        logger.info(f"   Expires: {expires}")

        return dxlink_data
    else:
        raise Exception(f"DXLink credentials failed: {response.status_code} - {response.text}")


async def test_symbol(client: DXLinkClient, symbol: str):
    """Test HV calculation for a single symbol."""
    print(f"\n{'=' * 60}")
    print(f"Testing: {symbol}")
    print(f"{'=' * 60}")

    try:
        # Fetch 120 days of daily candles
        candles = await client.get_historical_candles(
            symbol=symbol, days=120, interval="1d", max_candles=150
        )

        if not candles:
            print(f"❌ No candles received for {symbol}")
            return None

        print(f"✅ Received {len(candles)} candles")

        # Show first and last candle
        if candles:
            first = candles[0]
            last = candles[-1]
            print(f"\nFirst candle: {datetime.fromtimestamp(first.time / 1000)}")
            print(f"  O={first.open} H={first.high} L={first.low} C={first.close}")
            print(f"Last candle:  {datetime.fromtimestamp(last.time / 1000)}")
            print(f"  O={last.open} H={last.high} L={last.low} C={last.close}")

        # Calculate HV metrics
        print("\nCalculating HV metrics...")
        hv_metrics = calculate_hv_metrics(candles)

        result = {"symbol": symbol, "candles": len(candles), **hv_metrics}

        if hv_metrics["hv30"] is not None:
            print(f"✅ HV30: {hv_metrics['hv30']:.4f} ({hv_metrics['hv30'] * 100:.2f}%)")
        else:
            print("⚠️  HV30: Could not calculate (need 31 candles)")

        if hv_metrics["hv90"] is not None:
            print(f"✅ HV90: {hv_metrics['hv90']:.4f} ({hv_metrics['hv90'] * 100:.2f}%)")
        else:
            print("⚠️  HV90: Could not calculate (need 91 candles)")

        return result

    except Exception as e:
        print(f"❌ Error processing {symbol}: {e}")
        logger.exception(f"Detailed error for {symbol}")
        return None


async def main():
    """Run integration test."""
    print("\n" + "=" * 60)
    print("DXLINK + HV CALCULATOR INTEGRATION TEST")
    print("=" * 60)
    print("\nTesting complete flow:")
    print("1. OAuth authentication")
    print("2. DXLink credential retrieval")
    print("3. WebSocket connection")
    print("4. Historical candle retrieval")
    print("5. HV30/HV90 calculation")

    # Step 1: OAuth
    try:
        access_token = get_oauth_access_token()
    except Exception as e:
        print(f"\n❌ OAuth authentication failed: {e}")
        return False

    # Step 2: DXLink credentials
    try:
        dxlink_creds = get_dxlink_credentials(access_token)
        dxlink_url = dxlink_creds.get("dxlink-url")
        dxlink_token = dxlink_creds.get("token")

        if not dxlink_url or not dxlink_token:
            print("\n❌ Missing DXLink URL or token in response")
            return False

    except Exception as e:
        print(f"\n❌ DXLink credential retrieval failed: {e}")
        return False

    # Step 3-5: WebSocket + Candles + HV
    test_symbols = ["AAPL", "SPY", "/ES"]

    results = []

    try:
        async with DXLinkClient(dxlink_url, dxlink_token, timeout=30.0) as client:
            print("\n✅ Connected to DXLink")

            for symbol in test_symbols:
                result = await test_symbol(client, symbol)
                if result:
                    results.append(result)

    except Exception as e:
        print(f"\n❌ DXLink client error: {e}")
        logger.exception("Detailed error")
        return False

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}\n")

    success_count = sum(
        1 for r in results if r.get("hv30") is not None and r.get("hv90") is not None
    )

    print(f"Symbols tested: {len(test_symbols)}")
    print(f"Successfully processed: {len(results)}")
    print(f"HV30/HV90 calculated: {success_count}\n")

    for result in results:
        symbol = result["symbol"]
        candles = result["candles"]
        hv30 = result.get("hv30")
        hv90 = result.get("hv90")

        status = "✅" if (hv30 and hv90) else "⚠️ "
        print(f"{status} {symbol:8} {candles:3} candles", end="")

        if hv30:
            print(f"  HV30={hv30:.4f}", end="")
        if hv90:
            print(f"  HV90={hv90:.4f}", end="")
        print()

    # Verdict
    print(f"\n{'=' * 60}")
    print("VERDICT")
    print(f"{'=' * 60}\n")

    if success_count == len(test_symbols):
        print("✅ ✅ ✅  ALL TESTS PASSED!  ✅ ✅ ✅\n")
        print("DXLink integration is working correctly!")
        print("Historical candles can be retrieved and HV calculated.\n")
        print("Next steps:")
        print("1. Integrate into MarketDataService with REST fallback")
        print("2. Test against full watchlist")
        print("3. Deploy to production\n")
        return True
    elif success_count > 0:
        print(f"⚠️  PARTIAL SUCCESS ({success_count}/{len(test_symbols)})\n")
        print("Some symbols worked but not all.")
        print("Review errors above for failed symbols.\n")
        return False
    else:
        print("❌ ALL TESTS FAILED\n")
        print("DXLink integration needs troubleshooting.")
        print("Review errors above.\n")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
