#!/usr/bin/env python3
"""
Test DXLink Candle retrieval using tastytrade SDK.

Much simpler than manual WebSocket protocol implementation!

Usage:
    python scripts/test_sdk_candles.py
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from tastytrade import DXLinkStreamer, Session
from tastytrade.dxfeed import Candle

from variance.market_data.hv_calculator import CandleData, calculate_hv_metrics


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


async def test_candles_sdk():
    """Test candle retrieval using tastytrade SDK."""
    print("=" * 60)
    print("TASTYTRADE SDK - CANDLE RETRIEVAL TEST")
    print("=" * 60)

    # Create session from refresh token
    client_secret = os.getenv("TT_CLIENT_SECRET")
    refresh_token = os.getenv("TT_REFRESH_TOKEN")

    if not client_secret or not refresh_token:
        print("❌ Missing TT_CLIENT_SECRET or TT_REFRESH_TOKEN")
        return False

    print("\n1. Creating session...")
    session = Session(provider_secret=client_secret, refresh_token=refresh_token)
    print("✅ Session created")

    # Test symbols
    test_symbols = ["AAPL", "SPY", "/ES"]

    print(f"\n2. Testing candles for: {test_symbols}")

    results = {}

    async with DXLinkStreamer(session) as streamer:
        print("✅ Connected to DXLink streamer")

        for symbol in test_symbols:
            print(f"\n{'=' * 60}")
            print(f"Testing: {symbol}")
            print(f"{'=' * 60}")

            # Subscribe to daily candles with historical data
            # Request 150 calendar days to get ~100 trading days for HV90
            start_time = datetime.now() - timedelta(days=150)

            print(f"Subscribing to {symbol} candles (last 150 days)...")

            try:
                await streamer.subscribe_candle(
                    symbols=[symbol], interval="1d", start_time=start_time
                )
                print("✅ Subscribed")

                # Collect candles for a few seconds
                candles = []
                timeout = 15  # seconds

                print(f"Collecting candles for {timeout} seconds...")

                async def collect_candles(sym=symbol, candles_list=candles):
                    async for candle in streamer.listen(Candle):
                        # Check if this is for our symbol
                        if candle.event_symbol.startswith(sym):
                            candles_list.append(
                                CandleData(
                                    symbol=sym,
                                    time=candle.time,
                                    open=candle.open,
                                    high=candle.high,
                                    low=candle.low,
                                    close=candle.close,
                                    volume=candle.volume if hasattr(candle, "volume") else 0.0,
                                )
                            )

                            if len(candles_list) <= 3:
                                print(f"  Candle: time={candle.time} close={candle.close:.2f}")

                            # Stop after getting reasonable amount
                            if len(candles_list) >= 100:
                                break

                try:
                    await asyncio.wait_for(collect_candles(), timeout=timeout)
                except asyncio.TimeoutError:
                    print(f"⏱️  Timeout after {timeout}s")

                # Note: SDK may auto-cleanup on context exit, but unsubscribe explicitly
                # Using the formatted symbol for unsubscribe
                await streamer.unsubscribe(Candle, [f"{symbol}{{=1d}}"])
                print("✅ Unsubscribed")

                # Process results
                print(f"\n📊 Results for {symbol}:")
                print(f"  Candles collected: {len(candles)}")

                if len(candles) >= 31:
                    # Sort by time
                    candles.sort(key=lambda c: c.time)

                    # Calculate HV
                    hv_metrics = calculate_hv_metrics(candles)

                    results[symbol] = {
                        "candles": len(candles),
                        "hv30": hv_metrics["hv30"],
                        "hv90": hv_metrics["hv90"],
                        "success": hv_metrics["hv30"] is not None,
                    }

                    if hv_metrics["hv30"]:
                        print(
                            f"  ✅ HV30: {hv_metrics['hv30']:.4f} ({hv_metrics['hv30'] * 100:.2f}%)"
                        )
                    if hv_metrics["hv90"]:
                        print(
                            f"  ✅ HV90: {hv_metrics['hv90']:.4f} ({hv_metrics['hv90'] * 100:.2f}%)"
                        )
                else:
                    print("  ⚠️  Not enough candles for HV calculation")
                    results[symbol] = {
                        "candles": len(candles),
                        "success": False,
                        "error": "Insufficient data",
                    }

            except Exception as e:
                print(f"❌ Error: {e}")
                results[symbol] = {"success": False, "error": str(e)}

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}\n")

    success_count = sum(1 for r in results.values() if r.get("success"))

    print(f"Symbols tested: {len(test_symbols)}")
    print(f"Successfully calculated HV: {success_count}/{len(test_symbols)}\n")

    for symbol, result in results.items():
        if result.get("success"):
            hv30_str = f"{result['hv30']:.4f}" if result["hv30"] else "N/A"
            hv90_str = f"{result['hv90']:.4f}" if result["hv90"] else "N/A"
            print(f"✅ {symbol:8} {result['candles']:3} candles  HV30={hv30_str}  HV90={hv90_str}")
        else:
            print(f"❌ {symbol:8} {result.get('error', 'Unknown error')}")

    # Verdict
    print(f"\n{'=' * 60}")
    print("VERDICT")
    print(f"{'=' * 60}\n")

    if success_count == len(test_symbols):
        print("✅ ✅ ✅  ALL TESTS PASSED!  ✅ ✅ ✅\n")
        print("Tastytrade SDK DXLinkStreamer works perfectly!")
        print("We can retrieve historical candles and calculate HV.\n")
        print("Next steps:")
        print("1. Wrap SDK in our DXLinkClient for clean interface")
        print("2. Integrate into MarketDataService")
        print("3. Test against full watchlist\n")
        return True
    elif success_count > 0:
        print(f"⚠️  PARTIAL SUCCESS ({success_count}/{len(test_symbols)})\n")
        return False
    else:
        print("❌ ALL TESTS FAILED\n")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_candles_sdk())
    sys.exit(0 if success else 1)
