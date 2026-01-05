#!/usr/bin/env python3
"""
Fetch /CL (Crude Oil) futures options chain for February expiration.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import json

from variance.tastytrade import TastytradeClient


def main():
    print("Fetching /CL futures option chain...")
    client = TastytradeClient()

    # Fetch full chain
    chain_items = client.get_futures_option_chain("/CL")

    if not chain_items:
        print("No chain data available")
        return

    # Group by expiration and filter for February
    expirations = {}
    for item in chain_items:
        exp_date = item.get("expiration-date", "")
        if exp_date.startswith("2026-02"):  # February expirations
            if exp_date not in expirations:
                expirations[exp_date] = []
            expirations[exp_date].append(item)

    print(f"\nFound {len(expirations)} February expirations")

    # Show available expirations
    for exp_date in sorted(expirations.keys()):
        options = expirations[exp_date]
        dte = options[0].get("days-to-expiration", "?")
        print(f"\n{exp_date} ({dte} DTE): {len(options)} options")

        # Get unique strikes
        strikes = sorted(
            set(float(opt.get("strike-price", 0)) for opt in options if opt.get("strike-price"))
        )

        print(f"  Strikes: {min(strikes):.2f} to {max(strikes):.2f}")
        print(f"  Strike count: {len(strikes)}")

    # Export full data for analysis
    output_file = Path(__file__).parent.parent / "reports" / "cl_chain_data.json"
    with open(output_file, "w") as f:
        json.dump({"symbol": "/CL", "expirations": expirations}, f, indent=2, default=str)

    print(f"\nFull chain data saved to: {output_file}")

    # Now fetch quotes for specific strikes around current price (57.41)
    print("\n\nFetching quotes for 16Δ structure (approx 53 put / 62 call)...")

    # Find closest expiration to 45 DTE
    target_dte = 45
    closest_exp = min(
        expirations.items(), key=lambda x: abs(x[1][0].get("days-to-expiration", 999) - target_dte)
    )
    exp_date, exp_options = closest_exp
    dte = exp_options[0].get("days-to-expiration")

    print(f"\nTarget expiration: {exp_date} ({dte} DTE)")

    # Find 16Δ strikes (roughly 53 put, 62 call based on current price 57.41)
    put_strike = 53.0
    call_strike = 62.0

    # Find option symbols
    put_symbol = None
    call_symbol = None

    for opt in exp_options:
        strike = float(opt.get("strike-price", 0))
        opt_type = opt.get("option-type", "")
        symbol = opt.get("symbol")

        if abs(strike - put_strike) < 0.5 and opt_type == "P":
            put_symbol = symbol
        elif abs(strike - call_strike) < 0.5 and opt_type == "C":
            call_symbol = symbol

    if put_symbol and call_symbol:
        print(f"  Put: {put_symbol}")
        print(f"  Call: {call_symbol}")

        # Fetch quotes
        quotes = client.get_option_quotes([], [put_symbol, call_symbol])

        if put_symbol in quotes and call_symbol in quotes:
            put_quote = quotes[put_symbol]
            call_quote = quotes[call_symbol]

            put_mid = (put_quote.get("bid", 0) + put_quote.get("ask", 0)) / 2
            call_mid = (call_quote.get("bid", 0) + call_quote.get("ask", 0)) / 2
            total_credit = put_mid + call_mid

            print("\nQuotes:")
            print(
                f"  {put_strike} Put:  ${put_quote.get('bid'):.2f} / ${put_quote.get('ask'):.2f} (mid: ${put_mid:.2f})"
            )
            print(
                f"  {call_strike} Call: ${call_quote.get('bid'):.2f} / ${call_quote.get('ask'):.2f} (mid: ${call_mid:.2f})"
            )
            print(f"  Total Credit: ${total_credit:.2f} per contract")
            print(f"  Annual Yield: {(total_credit / 57.41) * (365 / dte) * 100:.1f}%")
        else:
            print("  Quotes not available")
    else:
        print(f"  Could not find options at strikes {put_strike}/{call_strike}")


if __name__ == "__main__":
    main()
