#!/usr/bin/env python3
"""
Test DXLink Candle event subscription for historical data.

Based on official Tastytrade documentation:
https://developer.tastytrade.com/streaming-market-data/#dxlink-streamer

Tests:
1. Can we subscribe to Candle events?
2. Can we retrieve historical OHLC data?
3. Can we calculate HV30/HV90 from candles?

Usage:
    pip install tastytrade
    python scripts/test_dxlink_candles.py
"""

import asyncio
import math
import os
import statistics
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


load_env_file(project_root / ".env.tastytrade")


async def test_dxlink_candles():
    """Test DXLink Candle event subscription."""
    print("=" * 60)
    print("DXLINK CANDLE EVENT TEST")
    print("=" * 60)

    try:
        from tastytrade import DXLinkStreamer, Session

        print("✅ Tastytrade SDK imported")
    except ImportError:
        print("❌ tastytrade package not installed")
        print("Install with: pip install tastytrade")
        return

    # Try to import Candle event type
    try:
        from tastytrade.dxfeed import Candle

        print("✅ Candle event type available")
    except ImportError:
        print("❌ Candle event type not found in tastytrade.dxfeed")
        print("Checking alternative import paths...")

        # Try alternative paths
        try:
            import tastytrade.dxfeed as dxfeed

            print(f"Available event types: {dir(dxfeed)}")
        except:
            pass
        return

    # Login
    username = os.getenv("TT_USERNAME")
    password = os.getenv("TT_PASSWORD")

    if not username or password:
        print("❌ Missing TT_USERNAME or TT_PASSWORD in .env.tastytrade")
        print("Note: OAuth tokens don't work for Session login")
        print("You need actual username/password for tastytrade SDK")
        return

    print(f"\nLogging in as {username}...")

    try:
        session = Session.login(username, password)
        print("✅ Logged into Tastytrade")
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return

    # Test symbols
    test_symbols = ["SPY", "/ES", "AAPL"]

    print(f"\nTesting Candle subscriptions for: {test_symbols}")

    try:
        async with DXLinkStreamer(session) as streamer:
            print("✅ Connected to DXLink WebSocket")

            # Subscribe to Candle events
            # According to docs, can specify period like "1d" for daily candles
            print("\nSubscribing to daily Candle events...")

            try:
                await streamer.subscribe(Candle, test_symbols)
                print(f"✅ Subscribed to Candles for {test_symbols}")
            except Exception as e:
                print(f"❌ Subscription failed: {e}")
                print(f"Error type: {type(e).__name__}")
                return

            # Listen for candle events
            print("\nListening for Candle events (30 seconds)...")
            candles_received = {}

            try:

                async def listen_with_timeout():
                    count = 0
                    async for event in streamer.listen(Candle):
                        symbol = event.eventSymbol

                        if symbol not in candles_received:
                            candles_received[symbol] = []

                        candles_received[symbol].append(
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
                                f"  {symbol}: O={event.open} H={event.high} L={event.low} C={event.close} V={event.volume}"
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

                for symbol, candles in candles_received.items():
                    print(f"{symbol}:")
                    print(f"  Candles received: {len(candles)}")

                    if len(candles) >= 30:
                        # Calculate HV30
                        hv30 = calculate_hv_from_candles(candles, window=30)
                        if hv30:
                            print(f"  ✅ HV30: {hv30:.4f} ({hv30 * 100:.2f}%)")

                        if len(candles) >= 90:
                            hv90 = calculate_hv_from_candles(candles, window=90)
                            if hv90:
                                print(f"  ✅ HV90: {hv90:.4f} ({hv90 * 100:.2f}%)")
                    else:
                        print(f"  ⚠️  Need more candles for HV calculation (have {len(candles)})")

                    print()

                print("=" * 60)
                print("VERDICT: ✅ CANDLE EVENTS WORK!")
                print("=" * 60)
                print("\nDXLink can provide historical candles for HV calculation!")
                print("No need for IBKR or other paid providers.")

            else:
                print("\n⚠️  No candle events received")
                print("\nPossible reasons:")
                print("1. Candle events require specific subscription format")
                print("2. May need to specify time period (e.g., '1d' for daily)")
                print("3. Check tastytrade SDK documentation for Candle subscription")

    except Exception as e:
        print(f"\n❌ Error during streaming: {e}")
        import traceback

        traceback.print_exc()


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


if __name__ == "__main__":
    print("\nNote: This requires the tastytrade Python SDK")
    print("Install with: pip install tastytrade\n")

    asyncio.run(test_dxlink_candles())
