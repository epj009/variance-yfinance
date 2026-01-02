#!/usr/bin/env python3
"""
Test DXLink Candle event subscription using OAuth authentication.

This version uses OAuth tokens (not username/password) since that's what
we have configured and what will be used in production.

Based on official Tastytrade documentation:
https://developer.tastytrade.com/streaming-market-data/#dxlink-streamer

Tests:
1. Can we authenticate with OAuth and get DXLink token?
2. Can we subscribe to Candle events?
3. Can we retrieve historical OHLC data?
4. Can we calculate HV30/HV90 from candles?

Usage:
    python scripts/test_dxlink_candles_oauth.py
"""

import asyncio
import math
import os
import statistics
import sys
from pathlib import Path

import requests

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


load_env_file(project_root / ".env.tastytrade")


def get_oauth_access_token():
    """Get OAuth access token using refresh token."""
    client_id = os.getenv("TT_CLIENT_ID")
    client_secret = os.getenv("TT_CLIENT_SECRET")
    refresh_token = os.getenv("TT_REFRESH_TOKEN")
    base_url = os.getenv("API_BASE_URL", "https://api.tastytrade.com")

    if not all([client_id, client_secret, refresh_token]):
        print("❌ Missing OAuth credentials in .env.tastytrade")
        return None

    print("Authenticating with OAuth...")

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
        token = data["access_token"]
        print("✅ OAuth access token obtained")
        return token
    else:
        print(f"❌ OAuth failed: {response.status_code}")
        print(f"Response: {response.text}")
        return None


def get_dxlink_credentials(access_token):
    """Get DXLink WebSocket credentials."""
    base_url = os.getenv("API_BASE_URL", "https://api.tastytrade.com")

    print("Fetching DXLink credentials...")

    response = requests.get(
        f"{base_url}/api-quote-tokens",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )

    if response.ok:
        data = response.json()
        # Handle both possible response formats
        if "data" in data:
            dxlink_data = data["data"]
        else:
            dxlink_data = data

        print("✅ DXLink credentials obtained")
        print(f"   URL: {dxlink_data.get('dxlink-url', 'N/A')}")
        print(f"   Level: {dxlink_data.get('level', 'N/A')}")
        print(f"   Expires: {dxlink_data.get('expires-at', 'N/A')}")
        return dxlink_data
    else:
        print(f"❌ DXLink credentials failed: {response.status_code}")
        print(f"Response: {response.text}")
        return None


async def test_dxlink_candles_with_session():
    """Test DXLink Candle events using Session-based authentication."""
    print("\n" + "=" * 60)
    print("DXLINK CANDLE EVENT TEST (Session Method)")
    print("=" * 60)

    try:
        from tastytrade import DXLinkStreamer, Session
        from tastytrade.dxfeed import Candle

        print("✅ Tastytrade SDK imported")
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False

    # Get OAuth token
    access_token = get_oauth_access_token()
    if not access_token:
        return False

    # Get DXLink credentials
    dxlink_creds = get_dxlink_credentials(access_token)
    if not dxlink_creds:
        return False

    # Try to create a Session object from token
    # The tastytrade SDK Session class has a from_token() method
    try:
        session = Session.from_token(access_token)
        print("✅ Session created from OAuth token")
    except Exception as e:
        print(f"❌ Session creation failed: {e}")
        print("\nNote: The tastytrade SDK may require username/password login")
        print("Falling back to manual WebSocket connection...")
        return False

    # Test symbols
    test_symbols = ["AAPL", "SPY", "/ES"]

    print(f"\nTesting Candle subscriptions for: {test_symbols}")
    print("Requesting 120 days of daily (1d) candles...")

    try:
        async with DXLinkStreamer(session) as streamer:
            print("✅ Connected to DXLink WebSocket")

            # Subscribe to daily candles
            candle_symbols = [f"{sym}{{=1d}}" for sym in test_symbols]
            print(f"\nSubscribing to daily Candle events: {candle_symbols}")

            try:
                await streamer.subscribe(Candle, candle_symbols)
                print("✅ Subscribed to Candles")
            except Exception as e:
                print(f"❌ Subscription failed: {e}")
                print(f"Error type: {type(e).__name__}")
                return False

            # Listen for candle events
            print("\nListening for Candle events (30 seconds)...")
            candles_received = {}

            try:

                async def listen_with_timeout():
                    count = 0
                    async for event in streamer.listen(Candle):
                        # Extract base symbol (remove {=1d} suffix)
                        event_symbol = event.eventSymbol
                        base_symbol = (
                            event_symbol.split("{")[0] if "{" in event_symbol else event_symbol
                        )

                        if base_symbol not in candles_received:
                            candles_received[base_symbol] = []

                        candles_received[base_symbol].append(
                            {
                                "time": event.time,
                                "open": event.open,
                                "high": event.high,
                                "low": event.low,
                                "close": event.close,
                                "volume": event.volume,
                            }
                        )

                        count += 1
                        if count <= 10:  # Show first 10 events
                            print(
                                f"  {base_symbol}: O={event.open} H={event.high} L={event.low} C={event.close} V={event.volume}"
                            )

                await asyncio.wait_for(listen_with_timeout(), timeout=30.0)

            except asyncio.TimeoutError:
                print("\n⏱️  Timeout after 30 seconds")

            # Results
            print(f"\n{'=' * 60}")
            print("RESULTS")
            print(f"{'=' * 60}")

            if candles_received:
                print(f"\n✅ Received candles for {len(candles_received)} symbols:\n")

                success = False
                for symbol, candles in candles_received.items():
                    print(f"{symbol}:")
                    print(f"  Candles received: {len(candles)}")

                    if len(candles) >= 30:
                        # Calculate HV30
                        hv30 = calculate_hv_from_candles(candles, window=30)
                        if hv30:
                            print(f"  ✅ HV30: {hv30:.4f} ({hv30 * 100:.2f}%)")
                            success = True

                        if len(candles) >= 90:
                            hv90 = calculate_hv_from_candles(candles, window=90)
                            if hv90:
                                print(f"  ✅ HV90: {hv90:.4f} ({hv90 * 100:.2f}%)")
                    else:
                        print(f"  ⚠️  Need more candles for HV calculation (have {len(candles)})")

                    print()

                if success:
                    print("=" * 60)
                    print("VERDICT: ✅ CANDLE EVENTS WORK!")
                    print("=" * 60)
                    print("\nDXLink can provide historical candles for HV calculation!")
                    print("No need for IBKR or other paid providers.")
                    return True
                else:
                    print("⚠️  Received candles but not enough for HV calculation")
                    return False

            else:
                print("\n⚠️  No candle events received")
                print("\nPossible reasons:")
                print("1. Candle events require specific subscription format")
                print("2. May need to specify fromTime parameter for historical data")
                print("3. Check tastytrade SDK documentation for Candle subscription")
                return False

    except Exception as e:
        print(f"\n❌ Error during streaming: {e}")
        import traceback

        traceback.print_exc()
        return False


def calculate_hv_from_candles(candles, window=30):
    """Calculate HV from candle data."""
    if len(candles) < window + 1:
        return None

    closes = [c["close"] for c in candles[-(window + 1) :]]

    returns = []
    for i in range(1, len(closes)):
        ret = math.log(closes[i] / closes[i - 1])
        returns.append(ret)

    if len(returns) < window:
        return None

    std_dev = statistics.stdev(returns)
    hv = std_dev * math.sqrt(252)

    return hv


async def main():
    """Run the test."""
    print("\n" + "=" * 60)
    print("DXLINK CANDLE EVENT TEST - OAuth Authentication")
    print("=" * 60)
    print("\nThis test uses OAuth tokens (not username/password)")
    print("Testing historical OHLC data retrieval via DXLink Candles\n")

    success = await test_dxlink_candles_with_session()

    if success:
        print("\n" + "=" * 60)
        print("NEXT STEPS")
        print("=" * 60)
        print("\n1. Implement DXLink client in src/variance/market_data/dxlink_client.py")
        print("2. Implement HV calculator in src/variance/market_data/hv_calculator.py")
        print("3. Integrate into MarketDataService with fallback logic")
        print("4. Test coverage across full watchlist")
        print("\nEstimated effort: 8-12 hours")
    else:
        print("\n" + "=" * 60)
        print("TROUBLESHOOTING")
        print("=" * 60)
        print("\nThe test did not succeed. Possible issues:")
        print("1. SDK version compatibility - try: pip install --upgrade tastytrade")
        print("2. OAuth token permissions - verify account has market data access")
        print("3. Symbol format - may need different syntax for historical data")
        print("\nRefer to: https://developer.tastytrade.com/streaming-market-data/")


if __name__ == "__main__":
    asyncio.run(main())
