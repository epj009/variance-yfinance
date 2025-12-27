#!/usr/bin/env python3
# type: ignore
# mypy: ignore-errors
"""
Diagnostic: Why are futures being filtered out?

Checks each filter step-by-step for futures symbols.
"""

from typing import Any

from variance.config_loader import load_config_bundle
from variance.errors import warning_detail_message
from variance.get_market_data import get_market_data
from variance.models.market_specs import (
    DataIntegritySpec,
    IVPercentileSpec,
    LowVolTrapSpec,
    RetailEfficiencySpec,
    VolatilityMomentumSpec,
    VolatilityTrapSpec,
    VrpStructuralSpec,
)

# Test futures symbols
FUTURES_TO_TEST = ["/ES", "/CL", "/GC", "/ZN", "/NG"]


def diagnose_symbol(symbol: str, rules: dict[str, Any]) -> None:
    """Check each filter for a single symbol."""
    print(f"\n{'=' * 80}")
    print(f"DIAGNOSING: {symbol}")
    print(f"{'=' * 80}")

    # Fetch data
    data_dict = get_market_data([symbol])
    raw_data_typed = data_dict.get(symbol, {})

    # Convert to mutable dict[str, Any] for filter compatibility
    raw_data: dict[str, Any] = dict(raw_data_typed)
    raw_data["symbol"] = symbol

    if "error" in raw_data:
        print(f"❌ FETCH ERROR: {raw_data.get('error')}")
        print(f"   Warning: {raw_data.get('warning', 'N/A')}")
        detail_message = warning_detail_message(raw_data)
        if detail_message:
            print(f"   Detail: {detail_message}")
        return

    # Print key metrics
    print("\n📊 Key Metrics:")
    print(f"   Price: {raw_data.get('price', 'N/A')}")
    print(f"   IV: {raw_data.get('iv', 'N/A')}")
    print(f"   HV30: {raw_data.get('hv30', 'N/A')}")
    print(f"   HV90: {raw_data.get('hv90', 'N/A')}")
    print(f"   HV252: {raw_data.get('hv252', 'N/A')}")
    print(f"   HV Rank: {raw_data.get('hv_rank', 'N/A')}")
    print(f"   VRP Structural: {raw_data.get('vrp_structural', 'N/A')}")
    print(f"   IV Percentile: {raw_data.get('iv_percentile', 'N/A')}")
    print(f"   Liquidity Rating: {raw_data.get('liquidity_rating', 'N/A')}")

    # Check each filter
    results: dict[str, bool] = {}

    # 1. Data Integrity
    spec_data_integrity = DataIntegritySpec()
    passed = spec_data_integrity.is_satisfied_by(raw_data)
    results["DataIntegrity"] = passed
    print(f"\n{'✅' if passed else '❌'} DataIntegritySpec: {passed}")
    if not passed:
        print(f"   Warning: {raw_data.get('warning')}")

    # 2. VRP Structural
    threshold = float(rules.get("vrp_structural_threshold", 1.10))
    spec_vrp = VrpStructuralSpec(threshold)
    passed = spec_vrp.is_satisfied_by(raw_data)
    results["VrpStructural"] = passed
    vrp = raw_data.get("vrp_structural")
    print(f"{'✅' if passed else '❌'} VrpStructuralSpec (>{threshold}): {passed}")
    print(f"   VRP: {vrp} {'>' if vrp and float(vrp) > threshold else '<='} {threshold}")

    # 3. Low Vol Trap
    hv_floor = float(rules.get("hv_floor_percent", 5.0))
    spec_low_vol = LowVolTrapSpec(hv_floor)
    passed = spec_low_vol.is_satisfied_by(raw_data)
    results["LowVolTrap"] = passed
    hv252 = raw_data.get("hv252")
    print(f"{'✅' if passed else '❌'} LowVolTrapSpec (HV252>{hv_floor}): {passed}")
    print(f"   HV252: {hv252}")

    # 4. Volatility Trap (Positional)
    rank_threshold = float(rules.get("hv_rank_trap_threshold", 15.0))
    vrp_rich = float(rules.get("vrp_structural_rich_threshold", 1.30))
    spec_vol_trap = VolatilityTrapSpec(rank_threshold, vrp_rich)
    passed = spec_vol_trap.is_satisfied_by(raw_data)
    results["VolatilityTrap"] = passed
    print(
        f"{'✅' if passed else '❌'} VolatilityTrapSpec (HVRank>{rank_threshold} if VRP>{vrp_rich}): {passed}"
    )
    print(f"   HV Rank: {raw_data.get('hv_rank')}")

    # 5. Volatility Momentum (NEW)
    momentum_ratio = float(rules.get("volatility_momentum_min_ratio", 0.85))
    spec_vol_momentum = VolatilityMomentumSpec(momentum_ratio)
    passed = spec_vol_momentum.is_satisfied_by(raw_data)
    results["VolatilityMomentum"] = passed
    hv30 = raw_data.get("hv30")
    hv90 = raw_data.get("hv90")
    if hv30 and hv90 and float(hv90) > 0:
        ratio = float(hv30) / float(hv90)
        print(
            f"{'✅' if passed else '❌'} VolatilityMomentumSpec (HV30/HV90>{momentum_ratio}): {passed}"
        )
        print(
            f"   HV30/HV90: {ratio:.3f} {'>' if ratio >= momentum_ratio else '<'} {momentum_ratio}"
        )
    else:
        print(
            f"{'✅' if passed else '❌'} VolatilityMomentumSpec: {passed} (missing data, pass-through)"
        )

    # 6. Retail Efficiency
    min_price = float(rules.get("retail_min_price", 25.0))
    max_slippage = float(rules.get("retail_max_slippage", 0.05))
    spec_retail = RetailEfficiencySpec(min_price, max_slippage)
    passed = spec_retail.is_satisfied_by(raw_data)
    results["RetailEfficiency"] = passed
    price = raw_data.get("price", 0)
    print(f"{'✅' if passed else '❌'} RetailEfficiencySpec (price>{min_price}): {passed}")
    print(f"   Price: {price}")

    # 7. IV Percentile
    min_ivp = 20.0  # From config
    spec_ivp = IVPercentileSpec(min_ivp)
    passed = spec_ivp.is_satisfied_by(raw_data)
    results["IVPercentile"] = passed
    ivp = raw_data.get("iv_percentile")
    print(f"{'✅' if passed else '❌'} IVPercentileSpec (IVP>{min_ivp}): {passed}")
    print(f"   IV Percentile: {ivp}")

    # Summary
    all_passed = all(results.values())
    failed_filters = [k for k, v in results.items() if not v]

    print(f"\n{'=' * 80}")
    if all_passed:
        print(f"✅ RESULT: {symbol} PASSES all filters")
    else:
        print(f"❌ RESULT: {symbol} REJECTED by: {', '.join(failed_filters)}")
    print(f"{'=' * 80}")


def main() -> None:
    bundle = load_config_bundle(strict=False)
    rules = bundle["trading_rules"]

    print("\n🔍 FUTURES FILTERING DIAGNOSTIC")
    print(f"Testing {len(FUTURES_TO_TEST)} futures symbols...")
    print("\nCurrent Thresholds:")
    print(f"   VRP Structural: {rules.get('vrp_structural_threshold', 1.10)}")
    print(f"   VRP Rich: {rules.get('vrp_structural_rich_threshold', 1.30)}")
    print(f"   HV Floor: {rules.get('hv_floor_percent', 5.0)}%")
    print(f"   HV Rank Trap: {rules.get('hv_rank_trap_threshold', 15.0)}")
    print(f"   Volatility Momentum: {rules.get('volatility_momentum_min_ratio', 0.85)}")
    print(f"   Min IV Percentile: {rules.get('min_iv_percentile', 20.0)}")
    print(f"   Retail Min Price: ${rules.get('retail_min_price', 25.0)}")

    for symbol in FUTURES_TO_TEST:
        diagnose_symbol(symbol, rules)

    print(f"\n\n{'=' * 80}")
    print("💡 RECOMMENDATIONS:")
    print("   1. Check if futures have IV Percentile data from Tastytrade")
    print("   2. Verify VRP thresholds aren't too high for futures")
    print("   3. Consider futures exemptions for certain filters")
    print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
