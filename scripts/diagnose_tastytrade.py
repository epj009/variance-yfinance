#!/usr/bin/env python3
"""
Diagnostic script for Tastytrade API integration.
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

try:
    from variance.tastytrade_client import TastytradeAuthError, TastytradeClient
except ImportError:
    print(
        "Error: Could not import variance.tastytrade_client. Make sure you are in the project root."
    )
    sys.exit(1)


def run_diagnostics(symbols: list[str] | None = None) -> None:
    if symbols is None:
        symbols = ["SPY", "AAPL"]
    print("Running Tastytrade API Diagnostics...")
    print("-------------------------------------")

    # 1. Check Environment Variables
    required_vars = ["TT_CLIENT_ID", "TT_CLIENT_SECRET", "TT_REFRESH_TOKEN"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        print(f"❌ Missing Environment Variables: {', '.join(missing_vars)}")
        print("Please set these variables to use the Tastytrade API.")
        return
    else:
        print("✅ Environment Variables Present")

    # 2. Instantiate Client
    try:
        client = TastytradeClient()
        print("✅ TastytradeClient Instantiated")
    except TastytradeAuthError as e:
        print(f"❌ TastytradeClient Authentication Failed: {e}")
        return
    except Exception as e:
        print(f"❌ TastytradeClient Initialization Failed: {e}")
        return

    # 3. Fetch Metrics
    print(f"Attempting to fetch metrics for: {', '.join(symbols)}...")
    try:
        metrics = client.get_market_metrics(symbols)

        if not metrics:
            print("⚠️ No metrics returned. This might indicate an issue with the API or symbols.")
        else:
            print(f"✅ Metrics Received for {len(metrics)} symbols.")
            for sym, data in metrics.items():
                print(
                    f"  - {sym}: IV={data.get('iv', 'N/A')}%, HV30={data.get('hv30', 'N/A')}%, Rank={data.get('iv_rank', 'N/A')}"
                )

    except Exception as e:
        print(f"❌ Fetching Metrics Failed: {e}")
        return

    print("-------------------------------------")
    print("Diagnostics Complete.")


if __name__ == "__main__":
    symbols_arg = sys.argv[1:] if len(sys.argv) > 1 else ["SPY", "AAPL"]
    run_diagnostics(symbols_arg)
