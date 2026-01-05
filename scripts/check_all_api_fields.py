#!/usr/bin/env python3
"""
Script to inspect ALL raw fields from Tastytrade API response.
"""

import os
import pprint
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

try:
    from variance.tastytrade import TastytradeClient
except ImportError:
    print("Error: Could not import variance.tastytrade.")
    sys.exit(1)


def check_all_fields(symbols: list[str] | None = None) -> None:
    if symbols is None:
        symbols = ["SPY", "AAPL"]
    print("Fetching raw Tastytrade metrics for a few symbols...")

    try:
        client = TastytradeClient()
        token = client._ensure_valid_token()
        url = f"{client.api_base_url}/market-metrics"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        params = {"symbols": ",".join(symbols)}

        data = client._fetch_api_data(url, headers, params)
        if not data:
            print("No data returned.")
            return

        items = data.get("data", {}).get("items", [])
        if items:
            print(f"\n--- Raw Item Keys for {items[0].get('symbol')} ---")
            pprint.pprint(items[0])
        else:
            print("No items in data.")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    symbols_arg = sys.argv[1:] if len(sys.argv) > 1 else ["SPY", "AAPL"]
    check_all_fields(symbols_arg)
