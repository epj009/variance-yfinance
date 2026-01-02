#!/usr/bin/env python3
"""
Find true 16Δ strikes for /CL using proper delta calculation or wider OTM strikes.
"""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from variance.tastytrade_client import TastytradeClient


def estimate_delta_distance(iv_percent, dte, target_delta=16):
    """
    Rough estimate of how far OTM a strike needs to be for target delta.
    For 16Δ, typically 1-1.5 standard deviations away.

    Args:
        iv_percent: IV in percent (e.g., 33.0)
        dte: Days to expiration
        target_delta: Target delta (e.g., 16 for 16Δ)

    Returns:
        Approximate % distance from spot
    """
    # Convert to decimal
    iv_decimal = iv_percent / 100.0

    # Annualize time
    t = dte / 365.0

    # For ~16Δ, we need about 1 standard deviation
    # Standard deviation = spot * iv * sqrt(t)
    # For 16Δ: roughly 1.0-1.2 std devs
    std_dev_multiplier = 1.0  # Conservative estimate for 16Δ

    sigma = iv_decimal * (t**0.5)
    distance_pct = std_dev_multiplier * sigma

    return distance_pct


def main():
    print("Finding true 16Δ strikes for /CL Feb 17 expiration...")

    # Load chain data
    chain_file = Path(__file__).parent.parent / "reports" / "cl_chain_data.json"
    with open(chain_file) as f:
        data = json.load(f)

    # Get Feb 17 expiration (47 DTE)
    feb17_options = data["expirations"]["2026-02-17"]

    spot = 57.41
    iv = 33.0  # IV percent
    dte = 47

    # Estimate distances for 16Δ
    distance_pct = estimate_delta_distance(iv, dte, target_delta=16)

    print(f"\nUnderlying: ${spot}")
    print(f"IV: {iv}%")
    print(f"DTE: {dte}")
    print(f"Estimated 1σ distance: {distance_pct * 100:.1f}%")

    # Calculate target strikes (16Δ ≈ 1 std dev)
    put_target = spot * (1 - distance_pct)
    call_target = spot * (1 + distance_pct)

    print("\nEstimated 16Δ strikes:")
    print(f"  Put: ~${put_target:.2f} ({((put_target / spot) - 1) * 100:.1f}% OTM)")
    print(f"  Call: ~${call_target:.2f} ({((call_target / spot) - 1) * 100:.1f}% OTM)")

    # Find actual strikes in chain
    strikes = sorted(
        set(float(opt.get("strike-price", 0)) for opt in feb17_options if opt.get("strike-price"))
    )

    # Find closest strikes to our targets
    put_strike = min(strikes, key=lambda s: abs(s - put_target))
    call_strike = min(strikes, key=lambda s: abs(s - call_target))

    print("\nActual strikes available:")
    print(f"  Put: ${put_strike} ({((put_strike / spot) - 1) * 100:.1f}% OTM)")
    print(f"  Call: ${call_strike} ({((call_strike / spot) - 1) * 100:.1f}% OTM)")

    # Find option symbols
    put_symbol = None
    call_symbol = None

    for opt in feb17_options:
        strike = float(opt.get("strike-price", 0))
        opt_type = opt.get("option-type", "")
        symbol = opt.get("symbol")

        if abs(strike - put_strike) < 0.1 and opt_type == "P":
            put_symbol = symbol
        elif abs(strike - call_strike) < 0.1 and opt_type == "C":
            call_symbol = symbol

    if put_symbol and call_symbol:
        print("\nOption symbols:")
        print(f"  Put: {put_symbol}")
        print(f"  Call: {call_symbol}")

        # Fetch quotes
        client = TastytradeClient()
        quotes = client.get_option_quotes([], [put_symbol, call_symbol])

        if put_symbol in quotes and call_symbol in quotes:
            put_quote = quotes[put_symbol]
            call_quote = quotes[call_symbol]

            put_bid = put_quote.get("bid", 0)
            put_ask = put_quote.get("ask", 0)
            call_bid = call_quote.get("bid", 0)
            call_ask = call_quote.get("ask", 0)

            put_mid = (put_bid + put_ask) / 2 if put_bid and put_ask else 0
            call_mid = (call_bid + call_ask) / 2 if call_bid and call_ask else 0
            total_credit = put_mid + call_mid

            print("\nQuotes:")
            print(f"  ${put_strike} Put:  ${put_bid:.2f} / ${put_ask:.2f} (mid: ${put_mid:.2f})")
            print(
                f"  ${call_strike} Call: ${call_bid:.2f} / ${call_ask:.2f} (mid: ${call_mid:.2f})"
            )
            print(f"\n  Total Credit: ${total_credit:.2f} per contract")
            print(
                f"  Breakevens: ${put_strike - total_credit:.2f} / ${call_strike + total_credit:.2f}"
            )

            if total_credit > 0:
                annual_yield = (total_credit / spot) * (365 / dte) * 100
                print(f"  Annual Yield: {annual_yield:.1f}%")

                # Calculate probability of profit (rough estimate)
                be_put_pct = abs((put_strike - total_credit - spot) / spot)
                be_call_pct = abs((call_strike + total_credit - spot) / spot)
                print("\n  Distance to BE:")
                print(f"    Put: {be_put_pct * 100:.1f}% below spot")
                print(f"    Call: {be_call_pct * 100:.1f}% above spot")
        else:
            print("  Quotes not available")
    else:
        print("\n  Could not find options at target strikes")
        print("  Available strikes near targets:")
        nearby_strikes = [s for s in strikes if put_target - 5 <= s <= call_target + 5]
        print(f"    {nearby_strikes}")


if __name__ == "__main__":
    main()
