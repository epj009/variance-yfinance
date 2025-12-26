#!/usr/bin/env python3
"""
Symbol Screening Diagnostic Tool

Analyzes why a symbol passes or fails each filter in the screening pipeline.
Useful for troubleshooting and understanding filter behavior.

Usage:
    ./scripts/diagnose_symbol.py AAPL
    ./scripts/diagnose_symbol.py /ES /CL /ZN
    ./scripts/diagnose_symbol.py --held TSLA
    ./scripts/diagnose_symbol.py --json NVDA > output.json
"""

import argparse
import json
from typing import Any

from variance.config_loader import load_config_bundle
from variance.get_market_data import get_market_data
from variance.models.market_specs import (
    DataIntegritySpec,
    IVPercentileSpec,
    LowVolTrapSpec,
    RetailEfficiencySpec,
    ScalableGateSpec,
    VolatilityMomentumSpec,
    VolatilityTrapSpec,
    VrpStructuralSpec,
)


def diagnose_symbol(
    symbol: str, rules: dict[str, Any], is_held: bool = False, json_output: bool = False
) -> dict[str, Any]:
    """Diagnose all filters for a single symbol."""

    # Fetch data
    data_dict = get_market_data([symbol])
    raw_data = data_dict.get(symbol, {})

    # Add symbol to metrics (filter.py does this at line 104)
    raw_data["symbol"] = symbol

    # Check for fetch errors
    if "error" in raw_data:
        if json_output:
            return {
                "symbol": symbol,
                "status": "ERROR",
                "error": raw_data.get("error"),
                "warning": raw_data.get("warning"),
            }
        print(f"\n{'=' * 80}")
        print(f"DIAGNOSING: {symbol}")
        print(f"{'=' * 80}")
        print(f"❌ FETCH ERROR: {raw_data.get('error')}")
        print(f"   Warning: {raw_data.get('warning', 'N/A')}")
        return {"symbol": symbol, "status": "ERROR"}

    # Extract key metrics
    metrics = {
        "price": raw_data.get("price"),
        "iv": raw_data.get("iv"),
        "hv30": raw_data.get("hv30"),
        "hv90": raw_data.get("hv90"),
        "hv252": raw_data.get("hv252"),
        "hv_rank": raw_data.get("hv_rank"),
        "vrp_structural": raw_data.get("vrp_structural"),
        "vrp_tactical": raw_data.get("vrp_tactical"),
        "vrp_tactical_markup": raw_data.get("vrp_tactical_markup"),
        "iv_percentile": raw_data.get("iv_percentile"),
        "liquidity_rating": raw_data.get("liquidity_rating"),
        "call_bid": raw_data.get("call_bid"),
        "call_ask": raw_data.get("call_ask"),
        "put_bid": raw_data.get("put_bid"),
        "put_ask": raw_data.get("put_ask"),
    }

    # Test each filter
    results = {}

    # 1. Data Integrity
    spec = DataIntegritySpec()
    passed = spec.is_satisfied_by(raw_data)
    results["DataIntegrity"] = {
        "passed": passed,
        "reason": f"Warning: {raw_data.get('warning')}" if not passed else None,
    }

    # 2. VRP Structural
    threshold = float(rules.get("vrp_structural_threshold", 1.10))
    spec = VrpStructuralSpec(threshold)
    passed = spec.is_satisfied_by(raw_data)
    vrp = raw_data.get("vrp_structural")
    results["VrpStructural"] = {
        "passed": passed,
        "threshold": threshold,
        "value": float(vrp) if vrp else None,
        "reason": f"VRP {vrp} {'>' if passed else '<='} {threshold}" if vrp else "Missing VRP",
    }

    # 3. Low Vol Trap
    hv_floor = float(rules.get("hv_floor_percent", 5.0))
    spec = LowVolTrapSpec(hv_floor)
    passed = spec.is_satisfied_by(raw_data)
    hv252 = raw_data.get("hv252")
    results["LowVolTrap"] = {
        "passed": passed,
        "threshold": hv_floor,
        "value": float(hv252) if hv252 else None,
        "reason": f"HV252 {hv252} {'>=' if passed else '<'} {hv_floor}"
        if hv252
        else "Missing HV252",
    }

    # 4. Volatility Trap (Positional)
    rank_threshold = float(rules.get("hv_rank_trap_threshold", 15.0))
    vrp_rich = float(rules.get("vrp_structural_rich_threshold", 1.30))
    spec = VolatilityTrapSpec(rank_threshold, vrp_rich)
    passed = spec.is_satisfied_by(raw_data)
    hv_rank = raw_data.get("hv_rank")
    vrp_val = float(vrp) if vrp else 0
    applies = vrp_val > vrp_rich
    results["VolatilityTrap"] = {
        "passed": passed,
        "applies": applies,
        "hv_rank_threshold": rank_threshold,
        "vrp_rich_threshold": vrp_rich,
        "hv_rank": float(hv_rank) if hv_rank else None,
        "reason": f"VRP {vrp_val:.2f} {'>' if applies else '<='} {vrp_rich}, HV Rank check {'applies' if applies else 'skipped'}",
    }

    # 5. Volatility Momentum (NEW)
    momentum_ratio = float(rules.get("volatility_momentum_min_ratio", 0.85))
    spec = VolatilityMomentumSpec(momentum_ratio)
    passed = spec.is_satisfied_by(raw_data)
    hv30 = raw_data.get("hv30")
    hv90 = raw_data.get("hv90")
    if hv30 and hv90 and float(hv90) > 0:
        ratio = float(hv30) / float(hv90)
        results["VolatilityMomentum"] = {
            "passed": passed,
            "threshold": momentum_ratio,
            "value": ratio,
            "reason": f"HV30/HV90 {ratio:.3f} {'>=' if passed else '<'} {momentum_ratio}",
        }
    else:
        results["VolatilityMomentum"] = {
            "passed": passed,
            "reason": "Missing HV30/HV90 data (pass-through)",
        }

    # 6. Retail Efficiency
    min_price = float(rules.get("retail_min_price", 25.0))
    max_slippage = float(rules.get("retail_max_slippage", 0.05))
    spec = RetailEfficiencySpec(min_price, max_slippage)
    passed = spec.is_satisfied_by(raw_data)
    price = float(metrics["price"]) if metrics["price"] else 0
    results["RetailEfficiency"] = {
        "passed": passed,
        "min_price": min_price,
        "price": price,
        "reason": f"Price ${price:.2f} {'>=' if price >= min_price else '<'} ${min_price}",
    }

    # 7. IV Percentile
    min_ivp = float(rules.get("min_iv_percentile", 20.0))
    spec = IVPercentileSpec(min_ivp)
    passed = spec.is_satisfied_by(raw_data)
    ivp = raw_data.get("iv_percentile")
    is_future = symbol.startswith("/")
    results["IVPercentile"] = {
        "passed": passed,
        "threshold": min_ivp,
        "value": float(ivp) if ivp else None,
        "futures_exemption": is_future,
        "reason": "Futures exempted"
        if is_future
        else (f"IVP {ivp} {'>=' if passed else '<'} {min_ivp}" if ivp else "Missing IV Percentile"),
    }

    # 8. Liquidity (simplified check)
    min_rating = int(rules.get("min_tt_liquidity_rating", 4))
    rating = raw_data.get("liquidity_rating")
    if rating is not None:
        passed = int(rating) >= min_rating
        results["Liquidity"] = {
            "passed": passed,
            "threshold": min_rating,
            "value": int(rating),
            "reason": f"Liquidity Rating {rating} {'>=' if passed else '<'} {min_rating}",
        }
    else:
        results["Liquidity"] = {
            "passed": True,  # Simplified - would check volume/slippage
            "reason": "No Tastytrade rating (fallback check not shown)",
        }

    # 9. Scalability (if held)
    if is_held:
        markup_threshold = float(rules.get("vrp_scalable_threshold", 1.35))
        divergence_threshold = float(rules.get("scalable_divergence_threshold", 1.10))
        spec = ScalableGateSpec(markup_threshold, divergence_threshold)
        passed = spec.is_satisfied_by(raw_data)

        vtm = float(raw_data.get("vrp_tactical_markup", 0))
        vsm = float(raw_data.get("vrp_structural", 1.0))
        divergence = (vtm + 1.0) / vsm if vsm > 0 else 1.0

        results["ScalableGate"] = {
            "passed": passed,
            "markup_threshold": markup_threshold,
            "divergence_threshold": divergence_threshold,
            "vrp_tactical_markup": vtm,
            "divergence": divergence,
            "reason": f"VTM {vtm:.3f} {'≥' if vtm >= markup_threshold else '<'} {markup_threshold} OR Divergence {divergence:.3f} {'≥' if divergence >= divergence_threshold else '<'} {divergence_threshold}",
        }

    # Summary
    all_passed = all(r["passed"] for r in results.values())
    failed_filters = [k for k, v in results.items() if not v["passed"]]

    # JSON output
    if json_output:
        return {
            "symbol": symbol,
            "status": "PASS" if all_passed else "REJECT",
            "is_held": is_held,
            "metrics": metrics,
            "filters": results,
            "failed_filters": failed_filters,
        }

    # Human-readable output
    print(f"\n{'=' * 80}")
    print(f"DIAGNOSING: {symbol}{' (HELD POSITION)' if is_held else ''}")
    print(f"{'=' * 80}")

    print("\n📊 Key Metrics:")
    for key, value in metrics.items():
        if value is not None:
            print(f"   {key}: {value}")

    print("\n🔍 Filter Results:")
    for filter_name, result in results.items():
        icon = "✅" if result["passed"] else "❌"
        print(f"{icon} {filter_name}: {result['passed']}")
        print(f"   {result['reason']}")

    print(f"\n{'=' * 80}")
    if all_passed:
        print(f"✅ RESULT: {symbol} PASSES all filters")
    else:
        print(f"❌ RESULT: {symbol} REJECTED by: {', '.join(failed_filters)}")
    print(f"{'=' * 80}")

    return {"symbol": symbol, "status": "PASS" if all_passed else "REJECT"}


def main():
    parser = argparse.ArgumentParser(
        description="Diagnose why symbols pass or fail screening filters",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s AAPL                    # Diagnose single symbol
  %(prog)s /ES /CL /ZN             # Diagnose multiple futures
  %(prog)s --held TSLA             # Check if held position is scalable
  %(prog)s --json NVDA             # JSON output
  %(prog)s AAPL SPY > report.txt   # Save to file
        """,
    )
    parser.add_argument("symbols", nargs="+", help="Symbol(s) to diagnose")
    parser.add_argument(
        "--held", action="store_true", help="Treat symbol(s) as held positions (check scalability)"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    # Load config
    bundle = load_config_bundle(strict=False)
    rules = bundle["trading_rules"]

    # Process symbols
    results = []
    for symbol in args.symbols:
        result = diagnose_symbol(symbol, rules, is_held=args.held, json_output=args.json)
        results.append(result)

    # JSON output mode
    if args.json:
        print(
            json.dumps(
                {
                    "symbols": results,
                    "config_thresholds": {
                        "vrp_structural_threshold": rules.get("vrp_structural_threshold"),
                        "vrp_rich_threshold": rules.get("vrp_structural_rich_threshold"),
                        "hv_floor": rules.get("hv_floor_percent"),
                        "volatility_momentum_min_ratio": rules.get("volatility_momentum_min_ratio"),
                        "min_iv_percentile": rules.get("min_iv_percentile"),
                        "retail_min_price": rules.get("retail_min_price"),
                    },
                },
                indent=2,
            )
        )
    else:
        # Summary for multiple symbols
        if len(args.symbols) > 1:
            passed = sum(1 for r in results if r.get("status") == "PASS")
            print(f"\n\n{'=' * 80}")
            print(f"📊 SUMMARY: {passed}/{len(results)} symbols passed all filters")
            print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
