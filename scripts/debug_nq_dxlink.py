#!/usr/bin/env python3
"""
Debug /NQ futures symbol with DXLink.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
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


async def test_nq_direct():
    """Test /NQ with direct DXLink subscription."""
    from tastytrade import DXLinkStreamer, Session
    from tastytrade.dxfeed import Candle

    from variance.tastytrade_client import TastytradeClient

    client_secret = os.getenv("TT_CLIENT_SECRET")
    refresh_token = os.getenv("TT_REFRESH_TOKEN")

    print("=" * 70)
    print("DIRECT DXLINK TEST FOR /NQ")
    print("=" * 70)
    print()

    # Test different symbol formats
    test_symbols = [
        ("NQ", "Without slash"),
        ("/NQ", "With slash (our format)"),
        ("NQ1!", "Front month explicit"),
        ("@NQ", "Root symbol"),
    ]

    session = Session(provider_secret=client_secret, refresh_token=refresh_token)
    tt_client = TastytradeClient()
    resolved = tt_client.resolve_dxlink_symbol("/NQ")
    if resolved:
        test_symbols.append((resolved, "Resolved streamer symbol"))
        print(f"Resolved /NQ streamer-symbol: {resolved}\n")

    for symbol, description in test_symbols:
        print(f"Testing symbol: '{symbol}' ({description})")
        print("-" * 70)

        try:
            async with DXLinkStreamer(session) as streamer:
                start_time = datetime.now() - timedelta(days=150)

                print(f"Subscribing to candles for '{symbol}'...")
                await streamer.subscribe_candle(
                    symbols=[symbol], interval="1d", start_time=start_time
                )

                # Collect candles with timeout
                candles = []
                timeout_seconds = 10.0
                start = datetime.now()

                print(f"Listening for candles (timeout: {timeout_seconds}s)...")

                async def collect(candles_list=candles):
                    count = 0
                    async for candle in streamer.listen(Candle):
                        count += 1
                        if count <= 5:  # Print first 5
                            print(
                                f"  Candle {count}: {candle.event_symbol} - close={candle.close}, time={candle.time}"
                            )
                        candles_list.append(candle)
                        if len(candles_list) >= 100:
                            break

                try:
                    await asyncio.wait_for(collect(), timeout=timeout_seconds)
                except asyncio.TimeoutError:
                    elapsed = (datetime.now() - start).total_seconds()
                    print(f"  Timeout after {elapsed:.1f}s")

                # Unsubscribe
                await streamer.unsubscribe(Candle, [f"{symbol}{{=1d}}"])

                if candles:
                    print(f"✅ SUCCESS: Received {len(candles)} candles")
                    print(f"  First: {candles[0].time} @ ${candles[0].close}")
                    print(f"  Last:  {candles[-1].time} @ ${candles[-1].close}")
                else:
                    print("❌ FAILED: No candles received")

        except Exception as e:
            print(f"❌ ERROR: {e}")
            import traceback

            traceback.print_exc()

        print()


if __name__ == "__main__":
    import logging

    logging.basicConfig(
        level=logging.DEBUG, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    asyncio.run(test_nq_direct())
