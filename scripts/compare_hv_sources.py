#!/usr/bin/env python3
"""
Compare HV90 vs HV252 for VRP calculations.

This script helps you decide which volatility window is better for your strategy
by comparing candidate lists and VRP distributions.
"""

import sys
from pathlib import Path
from typing import TypedDict

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


from variance.get_market_data import TastytradeProvider


class VrpComparison(TypedDict):
    """VRP comparison result."""

    symbol: str
    iv: float
    hv90: float
    hv252: float
    vrp_hv90: float
    vrp_hv252: float
    diff: float
    ratio: float


def analyze_vrp_sources(symbols: list[str]) -> None:
    """
    Compare VRP calculations using HV90 vs HV252 for the same symbols.

    Args:
        symbols: List of tickers to analyze
    """
    provider = TastytradeProvider()

    print("=" * 80)
    print("VRP SOURCE COMPARISON: HV90 vs HV252")
    print("=" * 80)
    print()

    results: list[VrpComparison] = []

    for symbol in symbols:
        try:
            data = provider.get_market_data([symbol])
            if not data or symbol not in data:
                continue

            metrics = data[symbol]
            iv_raw = metrics.get("iv")
            hv90_raw = metrics.get("hv90")
            hv252_raw = metrics.get("hv252")

            if not iv_raw or not hv90_raw or not hv252_raw:
                continue

            # Cast to float for type safety
            iv = float(iv_raw)
            hv90 = float(hv90_raw)
            hv252 = float(hv252_raw)

            if hv90 <= 0 or hv252 <= 0:
                continue

            vrp_hv90 = iv / hv90
            vrp_hv252 = iv / hv252

            results.append(
                {
                    "symbol": symbol,
                    "iv": iv,
                    "hv90": hv90,
                    "hv252": hv252,
                    "vrp_hv90": vrp_hv90,
                    "vrp_hv252": vrp_hv252,
                    "diff": vrp_hv90 - vrp_hv252,
                    "ratio": vrp_hv90 / vrp_hv252,
                }
            )
        except Exception as e:
            print(f"Error processing {symbol}: {e}")
            continue

    if not results:
        print("No data available for comparison.")
        return

    # Sort by difference (biggest impact first)
    results.sort(key=lambda x: abs(x["diff"]), reverse=True)

    # Print table
    print(
        f"{'Symbol':<8} {'IV':>6} {'HV90':>6} {'HV252':>6} {'VRP(90)':>8} {'VRP(252)':>8} {'Diff':>6} {'Ratio':>6}"
    )
    print("-" * 80)

    for r in results:
        print(
            f"{r['symbol']:<8} "
            f"{r['iv']:>6.2f} "
            f"{r['hv90']:>6.2f} "
            f"{r['hv252']:>6.2f} "
            f"{r['vrp_hv90']:>8.3f} "
            f"{r['vrp_hv252']:>8.3f} "
            f"{r['diff']:>+6.3f} "
            f"{r['ratio']:>6.2f}x"
        )

    # Summary statistics
    print()
    print("=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)

    avg_vrp_90 = sum(r["vrp_hv90"] for r in results) / len(results)
    avg_vrp_252 = sum(r["vrp_hv252"] for r in results) / len(results)
    avg_ratio = sum(r["ratio"] for r in results) / len(results)

    print(f"Average VRP (HV90):  {avg_vrp_90:.3f}")
    print(f"Average VRP (HV252): {avg_vrp_252:.3f}")
    print(f"Average Ratio:       {avg_ratio:.2f}x")
    print()

    # Threshold analysis
    threshold = 0.85
    candidates_hv90 = sum(1 for r in results if r["vrp_hv90"] > threshold)
    candidates_hv252 = sum(1 for r in results if r["vrp_hv252"] > threshold)

    print(f"Candidates > {threshold} threshold:")
    print(
        f"  - Using HV90:  {candidates_hv90}/{len(results)} ({100 * candidates_hv90 / len(results):.1f}%)"
    )
    print(
        f"  - Using HV252: {candidates_hv252}/{len(results)} ({100 * candidates_hv252 / len(results):.1f}%)"
    )
    print()

    # Disagreements (one passes, other fails)
    disagree = [r for r in results if (r["vrp_hv90"] > threshold) != (r["vrp_hv252"] > threshold)]

    if disagree:
        print(f"DISAGREEMENTS ({len(disagree)} symbols):")
        print("These symbols pass one filter but not the other:")
        print()
        for r in disagree:
            if r["vrp_hv90"] > threshold:
                print(
                    f"  {r['symbol']}: HV90 says RICH ({r['vrp_hv90']:.3f}), HV252 says NOT ({r['vrp_hv252']:.3f})"
                )
            else:
                print(
                    f"  {r['symbol']}: HV252 says RICH ({r['vrp_hv252']:.3f}), HV90 says NOT ({r['vrp_hv90']:.3f})"
                )

    print()
    print("=" * 80)
    print("INTERPRETATION")
    print("=" * 80)
    print()
    if avg_ratio > 1.5:
        print("⚠️  HV90-based VRP is significantly HIGHER than HV252-based VRP")
        print("    → You're getting MORE candidates with HV90")
        print("    → Consider raising thresholds if using HV90")
    elif avg_ratio < 0.8:
        print("⚠️  HV90-based VRP is significantly LOWER than HV252-based VRP")
        print("    → You're getting FEWER candidates with HV90")
        print("    → Current market is in low-vol regime")
    else:
        print("✓ HV90 and HV252 are relatively aligned")
        print("  → Similar candidate counts expected")

    print()


if __name__ == "__main__":
    # Test with common symbols
    test_symbols = [
        "AAPL",
        "MSFT",
        "GOOGL",
        "AMZN",
        "TSLA",
        "SPY",
        "QQQ",
        "IWM",
        "NVDA",
        "META",
        "NFLX",
        "XLE",
        "XLF",
        "XLK",
    ]

    print("Fetching data for", len(test_symbols), "symbols...")
    print("This may take 30-60 seconds...")
    print()

    analyze_vrp_sources(test_symbols)
