#!/usr/bin/env python3
"""
Compare /GC (gold futures) vs GLD (gold ETF) options for 16Δ strangle opportunities.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from variance.tastytrade_client import TastytradeClient


def estimate_16delta_strikes(spot, iv_percent, dte):
    """
    Estimate 16Δ strikes (roughly 1 standard deviation OTM).
    """
    iv_decimal = iv_percent / 100.0
    t = dte / 365.0
    sigma = iv_decimal * (t**0.5)

    # 16Δ ≈ 1 std dev
    put_strike = spot * (1 - sigma)
    call_strike = spot * (1 + sigma)

    return put_strike, call_strike


def analyze_futures_chain(client, symbol, spot, iv, dte_target=45):
    """Analyze futures option chain."""
    print(f"\n{'=' * 60}")
    print(f"ANALYZING: {symbol} Futures")
    print(f"{'=' * 60}")

    chain_items = client.get_futures_option_chain(symbol)

    if not chain_items:
        print(f"No chain data available for {symbol}")
        return None

    # Group by expiration
    expirations = {}
    for item in chain_items:
        exp_date = item.get("expiration-date", "")
        dte = item.get("days-to-expiration")

        # Filter for target DTE range (30-60 days)
        if dte and 30 <= dte <= 60:
            if exp_date not in expirations:
                expirations[exp_date] = []
            expirations[exp_date].append(item)

    if not expirations:
        print("No expirations in 30-60 DTE range")
        return None

    # Find closest to target DTE
    closest_exp = min(
        expirations.items(), key=lambda x: abs(x[1][0].get("days-to-expiration", 999) - dte_target)
    )
    exp_date, exp_options = closest_exp
    dte = exp_options[0].get("days-to-expiration")

    print(f"\nSpot: ${spot}")
    print(f"IV: {iv}%")
    print(f"Target Expiration: {exp_date} ({dte} DTE)")

    # Estimate 16Δ strikes
    put_target, call_target = estimate_16delta_strikes(spot, iv, dte)

    print("\nEstimated 16Δ strikes:")
    print(f"  Put: ~${put_target:.2f} ({((put_target / spot) - 1) * 100:.1f}% OTM)")
    print(f"  Call: ~${call_target:.2f} ({((call_target / spot) - 1) * 100:.1f}% OTM)")

    # Find available strikes
    strikes = sorted(
        set(float(opt.get("strike-price", 0)) for opt in exp_options if opt.get("strike-price"))
    )

    put_strike = min(strikes, key=lambda s: abs(s - put_target))
    call_strike = min(strikes, key=lambda s: abs(s - call_target))

    print("\nActual strikes:")
    print(f"  Put: ${put_strike} ({((put_strike / spot) - 1) * 100:.1f}% OTM)")
    print(f"  Call: ${call_strike} ({((call_strike / spot) - 1) * 100:.1f}% OTM)")

    # Find option symbols
    put_symbol = None
    call_symbol = None

    for opt in exp_options:
        strike = float(opt.get("strike-price", 0))
        opt_type = opt.get("option-type", "")
        sym = opt.get("symbol")

        if abs(strike - put_strike) < 0.5 and opt_type == "P":
            put_symbol = sym
        elif abs(strike - call_strike) < 0.5 and opt_type == "C":
            call_symbol = sym

    if not (put_symbol and call_symbol):
        print("  Could not find option symbols")
        return None

    # Fetch quotes
    quotes = client.get_option_quotes([], [put_symbol, call_symbol])

    if put_symbol not in quotes or call_symbol not in quotes:
        print("  Quotes not available")
        return None

    put_quote = quotes[put_symbol]
    call_quote = quotes[call_symbol]

    put_bid = put_quote.get("bid", 0) or 0
    put_ask = put_quote.get("ask", 0) or 0
    call_bid = call_quote.get("bid", 0) or 0
    call_ask = call_quote.get("ask", 0) or 0

    put_mid = (put_bid + put_ask) / 2 if put_bid and put_ask else 0
    call_mid = (call_bid + call_ask) / 2 if call_bid and call_ask else 0
    total_credit = put_mid + call_mid

    print("\nQuotes:")
    print(f"  ${put_strike} Put:  ${put_bid:.2f} / ${put_ask:.2f} (mid: ${put_mid:.2f})")
    print(f"  ${call_strike} Call: ${call_bid:.2f} / ${call_ask:.2f} (mid: ${call_mid:.2f})")
    print(f"\n  Total Credit: ${total_credit:.2f} per contract")

    if total_credit > 0:
        annual_yield = (total_credit / spot) * (365 / dte) * 100
        be_put = put_strike - total_credit
        be_call = call_strike + total_credit

        print(f"  Breakevens: ${be_put:.2f} / ${be_call:.2f}")
        print(f"  Annual Yield: {annual_yield:.1f}%")
        print(
            f"  BE Distance: {abs((be_put - spot) / spot) * 100:.1f}% / {abs((be_call - spot) / spot) * 100:.1f}%"
        )

    return {
        "symbol": symbol,
        "type": "futures",
        "spot": spot,
        "dte": dte,
        "put_strike": put_strike,
        "call_strike": call_strike,
        "credit": total_credit,
        "yield_annual": (total_credit / spot) * (365 / dte) * 100 if total_credit > 0 else 0,
    }


def analyze_equity_chain(client, symbol):
    """Analyze equity option chain."""
    print(f"\n{'=' * 60}")
    print(f"ANALYZING: {symbol} (Equity ETF)")
    print(f"{'=' * 60}")

    # Get market data first
    market_data = client.get_market_data([symbol])
    if symbol not in market_data:
        print(f"No market data for {symbol}")
        return None

    spot = market_data[symbol].get("price")
    if not spot:
        print(f"No price data for {symbol}")
        return None

    # Get market metrics for IV
    metrics = client.get_market_metrics([symbol])
    iv = metrics.get(symbol, {}).get("iv", 20.0)  # Default to 20% if missing

    print(f"\nSpot: ${spot:.2f}")
    print(f"IV: {iv:.1f}%")

    # Fetch option chain
    chains = client.get_option_chains_compact([symbol])
    if symbol not in chains:
        print(f"No option chain for {symbol}")
        return None

    chain = chains[symbol]

    # Find 45 DTE expiration
    result = client.find_atm_options(symbol, chain, spot, target_dte=45, dte_min=30, dte_max=60)

    if not result:
        print("No suitable expiration found (30-60 DTE)")
        return None

    call_symbol_atm, put_symbol_atm = result

    # Parse DTE from OCC symbol (YYMMDD at positions 6-12)
    exp_str = call_symbol_atm[6:12]
    from datetime import date, datetime

    exp_date = datetime.strptime(f"20{exp_str}", "%Y%m%d").date()
    dte = (exp_date - date.today()).days

    print(f"Target Expiration: {exp_date} ({dte} DTE)")

    # Estimate 16Δ strikes
    put_target, call_target = estimate_16delta_strikes(spot, iv, dte)

    print("\nEstimated 16Δ strikes:")
    print(f"  Put: ~${put_target:.2f} ({((put_target / spot) - 1) * 100:.1f}% OTM)")
    print(f"  Call: ~${call_target:.2f} ({((call_target / spot) - 1) * 100:.1f}% OTM)")

    # Find available strikes from chain
    expirations = chain.get("expirations", [])
    target_exp = None
    for exp in expirations:
        exp_dte = exp.get("days-to-expiration")
        if exp_dte and 30 <= exp_dte <= 60:
            if target_exp is None or abs(exp_dte - 45) < abs(
                target_exp.get("days-to-expiration", 999) - 45
            ):
                target_exp = exp

    if not target_exp:
        print("Could not find target expiration")
        return None

    # Get strikes
    strikes_raw = target_exp.get("strikes") or target_exp.get("strike-prices") or []
    if isinstance(strikes_raw, list):
        strikes = sorted([float(s) for s in strikes_raw if s])
    else:
        print("No strikes available")
        return None

    put_strike = min(strikes, key=lambda s: abs(s - put_target))
    call_strike = min(strikes, key=lambda s: abs(s - call_target))

    print("\nActual strikes:")
    print(f"  Put: ${put_strike:.2f} ({((put_strike / spot) - 1) * 100:.1f}% OTM)")
    print(f"  Call: ${call_strike:.2f} ({((call_strike / spot) - 1) * 100:.1f}% OTM)")

    # Build OCC symbols
    root = chain.get("root_symbol") or symbol
    put_symbol = client.build_occ_symbol(root, exp_date, put_strike, "P")
    call_symbol = client.build_occ_symbol(root, exp_date, call_strike, "C")

    # Fetch quotes
    quotes = client.get_option_quotes([put_symbol, call_symbol], [])

    if put_symbol not in quotes or call_symbol not in quotes:
        print("  Quotes not available")
        return None

    put_quote = quotes[put_symbol]
    call_quote = quotes[call_symbol]

    put_bid = put_quote.get("bid", 0) or 0
    put_ask = put_quote.get("ask", 0) or 0
    call_bid = call_quote.get("bid", 0) or 0
    call_ask = call_quote.get("ask", 0) or 0

    put_mid = (put_bid + put_ask) / 2 if put_bid and put_ask else 0
    call_mid = (call_bid + call_ask) / 2 if call_bid and call_ask else 0
    total_credit = put_mid + call_mid

    print("\nQuotes:")
    print(f"  ${put_strike:.2f} Put:  ${put_bid:.2f} / ${put_ask:.2f} (mid: ${put_mid:.2f})")
    print(f"  ${call_strike:.2f} Call: ${call_bid:.2f} / ${call_ask:.2f} (mid: ${call_mid:.2f})")
    print(f"\n  Total Credit: ${total_credit:.2f} per contract")

    if total_credit > 0:
        annual_yield = (total_credit / spot) * (365 / dte) * 100
        be_put = put_strike - total_credit
        be_call = call_strike + total_credit

        print(f"  Breakevens: ${be_put:.2f} / ${be_call:.2f}")
        print(f"  Annual Yield: {annual_yield:.1f}%")
        print(
            f"  BE Distance: {abs((be_put - spot) / spot) * 100:.1f}% / {abs((be_call - spot) / spot) * 100:.1f}%"
        )

    return {
        "symbol": symbol,
        "type": "equity",
        "spot": spot,
        "dte": dte,
        "put_strike": put_strike,
        "call_strike": call_strike,
        "credit": total_credit,
        "yield_annual": (total_credit / spot) * (365 / dte) * 100 if total_credit > 0 else 0,
    }


def main():
    client = TastytradeClient()

    # Analyze /GC (gold futures)
    # Spot: ~$2650, IV: ~14% (typical for gold)
    gc_result = analyze_futures_chain(client, "/GC", spot=2650, iv=14.0, dte_target=45)

    # Analyze GLD (gold ETF)
    gld_result = analyze_equity_chain(client, "GLD")

    # Comparison
    print(f"\n{'=' * 60}")
    print("COMPARISON")
    print(f"{'=' * 60}")

    if gc_result and gld_result:
        print(f"\n{'Metric':<20} {'/GC (Futures)':<20} {'GLD (ETF)':<20}")
        print(f"{'-' * 60}")
        print(f"{'Spot':<20} ${gc_result['spot']:<19.2f} ${gld_result['spot']:<19.2f}")
        print(f"{'DTE':<20} {gc_result['dte']:<20} {gld_result['dte']:<20}")
        print(f"{'Credit':<20} ${gc_result['credit']:<19.2f} ${gld_result['credit']:<19.2f}")
        print(
            f"{'Annual Yield':<20} {gc_result['yield_annual']:<19.1f}% {gld_result['yield_annual']:<19.1f}%"
        )
        print(
            f"{'Put Strike':<20} ${gc_result['put_strike']:<19.2f} ${gld_result['put_strike']:<19.2f}"
        )
        print(
            f"{'Call Strike':<20} ${gc_result['call_strike']:<19.2f} ${gld_result['call_strike']:<19.2f}"
        )

        print("\n🏆 Winner:")
        if gc_result["yield_annual"] > gld_result["yield_annual"]:
            print(
                f"  /GC: {gc_result['yield_annual']:.1f}% vs GLD: {gld_result['yield_annual']:.1f}%"
            )
        else:
            print(
                f"  GLD: {gld_result['yield_annual']:.1f}% vs /GC: {gc_result['yield_annual']:.1f}%"
            )


if __name__ == "__main__":
    main()
