"""
Specification Filtering Step
"""

from typing import Any, Optional

import numpy as np

from variance.diagnostics import ScreenerDiagnostics
from variance.models.market_specs import (
    CorrelationSpec,
    DataIntegritySpec,
    IVPercentileSpec,
    LiquiditySpec,
    LowVolTrapSpec,
    RetailEfficiencySpec,
    ScalableGateSpec,
    SectorExclusionSpec,
    VolatilityMomentumSpec,
    VolatilityTrapSpec,
    VrpStructuralSpec,
    VrpTacticalSpec,
)
from variance.models.specs import Specification


def apply_specifications(
    raw_data: dict[str, Any],
    config: Any,
    rules: dict[str, Any],
    market_config: dict[str, Any],
    portfolio_returns: Optional[np.ndarray] = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Applies composable filters to the candidate pool."""

    # 1. Setup Counters
    diagnostics = ScreenerDiagnostics.create()

    # 2. Compose Specs
    structural_threshold = float(
        rules.get("vrp_structural_threshold", 0.85)
        if config.min_vrp_structural is None
        else config.min_vrp_structural
    )
    hv_floor_absolute = float(rules.get("hv_floor_percent", 5.0))
    hv_rank_trap_threshold = float(rules.get("hv_rank_trap_threshold", 15.0))
    vrp_rich_threshold = float(rules.get("vrp_structural_rich_threshold", 1.0))
    vrp_tactical_threshold = float(rules.get("vrp_tactical_threshold", 1.15))
    volatility_momentum_min_ratio = float(rules.get("volatility_momentum_min_ratio", 0.85))

    # Retail Efficiency Params (profile can override global setting)
    retail_min_price = float(
        config.retail_min_price
        if config.retail_min_price is not None
        else rules.get("retail_min_price", 25.0)
    )
    retail_max_slippage = float(rules.get("retail_max_slippage", 0.05))

    scalable_spec = ScalableGateSpec(
        markup_threshold=float(rules.get("vrp_scalable_threshold", 1.35)),
        divergence_threshold=float(rules.get("scalable_divergence_threshold", 1.10)),
    )

    main_spec: Specification[dict[str, Any]] = DataIntegritySpec()
    corr_spec = None

    # Check if we should bypass all filters (--show-all flag or min_vrp_structural <= 0)
    show_all = getattr(config, "show_all", False) or (
        config.min_vrp_structural is not None and config.min_vrp_structural <= 0
    )
    if not show_all:
        main_spec &= VrpStructuralSpec(structural_threshold)
        main_spec &= LowVolTrapSpec(hv_floor_absolute)
        main_spec &= VolatilityTrapSpec(hv_rank_trap_threshold, vrp_rich_threshold)
        main_spec &= VolatilityMomentumSpec(volatility_momentum_min_ratio)
        main_spec &= RetailEfficiencySpec(retail_min_price, retail_max_slippage)
        # New: IV Percentile Spec
        if config.min_iv_percentile is not None and config.min_iv_percentile > 0:
            main_spec &= IVPercentileSpec(config.min_iv_percentile)

    tactical_spec = VrpTacticalSpec(hv_floor_absolute, vrp_tactical_threshold)

    if config.exclude_sectors:
        main_spec &= SectorExclusionSpec(config.exclude_sectors)

    if not config.allow_illiquid:
        main_spec &= LiquiditySpec(
            max_slippage=float(rules.get("max_slippage_pct", 0.05)),
            min_vol=int(rules.get("min_atm_volume", 500)),
            min_tt_liquidity_rating=int(rules.get("min_tt_liquidity_rating", 4)),
        )

    # 4. Correlation Guard (RFC 013)
    if portfolio_returns is not None and not show_all:
        max_corr = float(rules.get("max_portfolio_correlation", 0.95))
        corr_spec = CorrelationSpec(portfolio_returns, max_corr, raw_data)

    # 3. Apply Gate
    candidates = []
    held_roots = set(str(s).upper() for s in getattr(config, "held_symbols", []))
    include_assets = [s.lower() for s in getattr(config, "include_asset_classes", [])]
    exclude_assets = [s.lower() for s in getattr(config, "exclude_asset_classes", [])]

    for sym, metrics in raw_data.items():
        error = metrics.get("error")
        if error:
            diagnostics.record_market_data_error(error)
            continue

        # Normalize keys to lowercase for internal consistency
        metrics_dict = {str(k).lower(): v for k, v in metrics.items()}
        metrics_dict["symbol"] = sym

        # --- ASSET CLASS FILTER ---
        from variance.common import map_sector_to_asset_class

        asset_class = map_sector_to_asset_class(str(metrics_dict.get("sector", "Unknown")))
        metrics_dict["asset_class"] = asset_class

        if include_assets and asset_class.lower() not in include_assets:
            diagnostics.incr("asset_class_skipped_count")
            continue
        if exclude_assets and asset_class.lower() in exclude_assets:
            diagnostics.incr("asset_class_skipped_count")
            continue

        # --- HOLDING FILTER (RFC 013/020) ---
        if sym.upper() in held_roots:
            # Standalone Scalable Gate: Only allow re-entry if edge has surged
            if scalable_spec.is_satisfied_by(metrics_dict):
                metrics_dict["is_scalable_surge"] = True
            else:
                continue

        # Skip main spec filter if show_all is enabled
        if not show_all:
            if not main_spec.is_satisfied_by(metrics_dict):
                _update_counters(
                    sym,
                    metrics_dict,
                    config,
                    rules,
                    diagnostics,
                    structural_threshold,
                    hv_floor_absolute,
                    portfolio_returns,
                    raw_data,
                )
                continue

        # Skip tactical filter if show_all is enabled
        if not show_all and not tactical_spec.is_satisfied_by(metrics_dict):
            diagnostics.incr("tactical_skipped_count")
            continue

        # Skip correlation filter if show_all is enabled
        if not show_all and corr_spec:
            corr_result = corr_spec.evaluate(metrics_dict)
            if not corr_result.passed:
                diagnostics.incr("correlation_skipped_count")
                continue
            if corr_result.used_proxy:
                metrics_dict["correlation_via_proxy"] = True
            if corr_result.correlation is not None:
                metrics_dict["portfolio_rho"] = corr_result.correlation

        candidates.append(metrics_dict)

    return candidates, diagnostics.to_dict()


def _update_counters(
    sym: str,
    metrics: dict[str, Any],
    config: Any,
    rules: dict[str, Any],
    diagnostics: ScreenerDiagnostics,
    threshold: float,
    hv_floor: float,
    portfolio_returns: Optional[np.ndarray],
    raw_data: Optional[dict[str, Any]] = None,
) -> None:
    """Internal helper for reporting accuracy."""
    sector = str(metrics.get("sector", "Unknown"))
    if config.exclude_sectors and sector in config.exclude_sectors:
        diagnostics.incr("sector_skipped_count")

    # Re-import locally to avoid cycle
    from variance.vol_screener import _is_illiquid

    is_illiquid, _ = _is_illiquid(sym, metrics, rules, config.min_tt_liquidity_rating)
    if is_illiquid and not config.allow_illiquid:
        diagnostics.incr("illiquid_skipped_count")

    if metrics.get("vrp_structural") is None:
        diagnostics.incr("missing_vrp_structural_count")
    elif float(metrics.get("vrp_structural", 0)) <= threshold:
        diagnostics.incr("low_vrp_structural_count")

    hv252 = metrics.get("hv252")
    if hv252 is not None and float(hv252) < hv_floor:
        diagnostics.incr("low_vol_trap_skipped_count")

    hv_rank = metrics.get("hv_rank")
    rich_threshold = float(rules.get("vrp_structural_rich_threshold", 1.0))
    trap_threshold = float(rules.get("hv_rank_trap_threshold", 15.0))
    vrp_s_raw = metrics.get("vrp_structural")

    vrp_s = float(vrp_s_raw) if vrp_s_raw is not None else 0.0
    hv_rank_f = float(hv_rank) if hv_rank is not None else 100.0

    if vrp_s > rich_threshold and hv_rank is not None and hv_rank_f < trap_threshold:
        diagnostics.incr("hv_rank_trap_skipped_count")

    # Retail Efficiency Skip
    retail_min_price = float(rules.get("retail_min_price", 25.0))
    retail_max_slippage = float(rules.get("retail_max_slippage", 0.05))
    price = float(metrics.get("price") or 0.0)

    if price < retail_min_price:
        diagnostics.incr("retail_inefficient_skipped_count")
    else:
        # Check slippage for counter
        call_bid = metrics.get("call_bid")
        call_ask = metrics.get("call_ask")
        put_bid = metrics.get("put_bid")
        put_ask = metrics.get("put_ask")
        max_s = 0.0
        for b, a in [(call_bid, call_ask), (put_bid, put_ask)]:
            if b is not None and a is not None:
                m = (float(b) + float(a)) / 2
                if m > 0:
                    s = (float(a) - float(b)) / m
                    if s > max_s:
                        max_s = s
        if max_s > retail_max_slippage:
            diagnostics.incr("retail_inefficient_skipped_count")

    # New: IV Percentile Skip
    if config.min_iv_percentile is not None and config.min_iv_percentile > 0:
        iv_pct = metrics.get("iv_percentile")
        if iv_pct is None or float(iv_pct) < config.min_iv_percentile:
            diagnostics.incr("low_iv_percentile_skipped_count")

    warning = metrics.get("warning")
    soft_warnings = [
        "iv_scale_corrected",
        "iv_scale_assumed_decimal",
        "after_hours_stale",
        "tastytrade_fallback",
        "yfinance_unavailable_cached",
        None,
    ]
    if warning not in soft_warnings:
        diagnostics.incr("data_integrity_skipped_count")

    # Correlation count handled after main spec pass
