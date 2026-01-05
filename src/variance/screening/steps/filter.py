"""
Specification Filtering Step
"""

import logging
from typing import TYPE_CHECKING, Any, Optional

import numpy as np

from variance.diagnostics import ScreenerDiagnostics
from variance.models.market_specs import (
    CorrelationSpec,
    DataIntegritySpec,
    IVPercentileSpec,
    LiquiditySpec,
    RetailEfficiencySpec,
    ScalableGateSpec,
    SectorExclusionSpec,
    SlippageSpec,
    VolatilityMomentumSpec,
    VolatilityTrapSpec,
    VrpStructuralSpec,
    VrpTacticalSpec,
    YieldSpec,
)
from variance.models.specs import Specification

if TYPE_CHECKING:
    from variance.vol_screener import ScreenerConfig

logger = logging.getLogger(__name__)


def apply_specifications(
    raw_data: dict[str, Any],
    config: "ScreenerConfig",
    rules: dict[str, Any],
    market_config: dict[str, Any],
    portfolio_returns: Optional[np.ndarray] = None,
    rejections: Optional[dict[str, str]] = None,
) -> tuple[list[dict[str, Any]], dict[str, int], list[dict[str, Any]]]:
    """
    Applies composable filters to the candidate pool.

    Returns:
        - candidates: List of symbols that passed all filters
        - diagnostics: Counter dictionary with filter statistics
        - scanned_symbols: List of ALL symbols with their metrics and filter results

    Note: This function signature is maintained for backwards compatibility.
    Internally, we use the data passed in parameters.
    """

    # 1. Setup Counters
    diagnostics = ScreenerDiagnostics.create()

    # 2. Compose Specs
    structural_threshold = float(
        rules.get("vrp_structural_threshold", 1.10)
        if config.min_vrp_structural is None
        else config.min_vrp_structural
    )
    hv_floor_absolute = float(rules.get("hv_floor_percent", 5.0))
    hv_rank_trap_threshold = float(rules.get("hv_rank_trap_threshold", 15.0))
    vrp_rich_threshold = float(rules.get("vrp_structural_rich_threshold", 1.30))
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

    data_integrity_spec = DataIntegritySpec()
    vrp_structural_spec = VrpStructuralSpec(structural_threshold)
    vol_trap_spec = VolatilityTrapSpec(hv_rank_trap_threshold, vrp_rich_threshold)
    vol_momentum_spec = VolatilityMomentumSpec(volatility_momentum_min_ratio)
    retail_spec = RetailEfficiencySpec(retail_min_price)
    slippage_spec = SlippageSpec(retail_max_slippage)
    iv_percentile_spec = (
        IVPercentileSpec(config.min_iv_percentile)
        if config.min_iv_percentile is not None and config.min_iv_percentile > 0
        else None
    )
    yield_spec = None

    main_spec: Specification[dict[str, Any]] = data_integrity_spec
    corr_spec = None

    # Check if we should bypass all filters (--show-all flag or min_vrp_structural <= 0)
    show_all = getattr(config, "show_all", False) or (
        config.min_vrp_structural is not None and config.min_vrp_structural <= 0
    )
    if not show_all:
        main_spec &= vrp_structural_spec
        main_spec &= vol_trap_spec
        main_spec &= vol_momentum_spec
        main_spec &= retail_spec
        main_spec &= slippage_spec
        # New: IV Percentile Spec
        if iv_percentile_spec is not None:
            main_spec &= iv_percentile_spec

        # New: Yield Spec
        min_yield = float(rules.get("min_yield_percent", 0.0))
        if min_yield > 0:
            yield_spec = YieldSpec(min_yield)
            main_spec &= yield_spec

    tactical_spec = VrpTacticalSpec(hv_floor_absolute, vrp_tactical_threshold)

    if config.exclude_sectors:
        sector_spec = SectorExclusionSpec(config.exclude_sectors)
        main_spec &= sector_spec
    else:
        sector_spec = None

    if not config.allow_illiquid:
        liquidity_spec = LiquiditySpec(
            max_slippage=float(rules.get("max_slippage_pct", 0.05)),
            min_vol=int(rules.get("min_atm_volume", 500)),
            min_tt_liquidity_rating=int(rules.get("min_tt_liquidity_rating", 4)),
        )
        main_spec &= liquidity_spec
    else:
        liquidity_spec = None

    # 4. Correlation Guard (RFC 013)
    if portfolio_returns is not None and not show_all:
        max_corr = float(rules.get("max_portfolio_correlation", 0.95))
        corr_spec = CorrelationSpec(portfolio_returns, max_corr, raw_data)

    # 3. Apply Gate
    candidates = []
    scanned_symbols = []  # Track ALL symbols with their filter results
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

        # Initialize filter tracking for this symbol
        filter_results: dict[str, Any] = {
            "passed": False,
            "rejection_reason": None,
            "filters_passed": [],
            "filters_failed": [],
        }

        # --- ASSET CLASS FILTER ---
        from variance.common import map_sector_to_asset_class

        # For futures (symbols starting with "/"), use SECTOR_OVERRIDES mapping
        sector = metrics_dict.get("sector")
        if sym.startswith("/") and not sector:
            sector_overrides = market_config.get("SECTOR_OVERRIDES", {})
            sector = sector_overrides.get(sym)

        asset_class = map_sector_to_asset_class(str(sector if sector else "Unknown"))
        metrics_dict["asset_class"] = asset_class

        if include_assets and asset_class.lower() not in include_assets:
            diagnostics.incr("asset_class_skipped_count")
            reason = f"Asset Class: {asset_class} not in include list"
            filter_results["rejection_reason"] = reason
            filter_results["filters_failed"].append("asset_class_include")
            _record_rejection(rejections, sym, reason)
            metrics_dict["filter_results"] = filter_results
            scanned_symbols.append(metrics_dict)
            continue
        if exclude_assets and asset_class.lower() in exclude_assets:
            diagnostics.incr("asset_class_skipped_count")
            reason = f"Asset Class: {asset_class} excluded"
            filter_results["rejection_reason"] = reason
            filter_results["filters_failed"].append("asset_class_exclude")
            _record_rejection(rejections, sym, reason)
            metrics_dict["filter_results"] = filter_results
            scanned_symbols.append(metrics_dict)
            continue

        # --- HOLDING FILTER (RFC 013/020) ---
        if sym.upper() in held_roots:
            # Standalone Scalable Gate: Only allow re-entry if edge has surged
            if scalable_spec.is_satisfied_by(metrics_dict):
                metrics_dict["is_scalable_surge"] = True
                filter_results["filters_passed"].append("scalable_gate")
            else:
                reason = _scalable_rejection_reason(metrics_dict, scalable_spec)
                filter_results["rejection_reason"] = reason
                filter_results["filters_failed"].append("scalable_gate")
                _record_rejection(rejections, sym, reason)
                metrics_dict["filter_results"] = filter_results
                scanned_symbols.append(metrics_dict)
                continue

        # Skip main spec filter if show_all is enabled
        if not show_all:
            if not main_spec.is_satisfied_by(metrics_dict):
                reason = _first_failure_reason(
                    metrics_dict,
                    data_integrity_spec,
                    vrp_structural_spec,
                    vol_trap_spec,
                    vol_momentum_spec,
                    retail_spec,
                    slippage_spec,
                    iv_percentile_spec,
                    yield_spec,
                    sector_spec,
                    liquidity_spec,
                )
                if reason:
                    filter_results["rejection_reason"] = reason
                    filter_results["filters_failed"].append("main_spec")
                    _record_rejection(rejections, sym, reason)
                _update_counters(
                    sym,
                    metrics_dict,
                    config,
                    rules,
                    diagnostics,
                    structural_threshold,
                    portfolio_returns,
                    raw_data,
                )
                metrics_dict["filter_results"] = filter_results
                scanned_symbols.append(metrics_dict)
                continue
            else:
                filter_results["filters_passed"].append("main_spec")

        # Skip tactical filter if show_all is enabled
        if not show_all and not tactical_spec.is_satisfied_by(metrics_dict):
            diagnostics.incr("tactical_skipped_count")
            reason = _tactical_rejection_reason(metrics_dict, vrp_tactical_threshold)
            filter_results["rejection_reason"] = reason
            filter_results["filters_failed"].append("tactical")
            _record_rejection(rejections, sym, reason)
            metrics_dict["filter_results"] = filter_results
            scanned_symbols.append(metrics_dict)
            continue
        else:
            if not show_all:
                filter_results["filters_passed"].append("tactical")

        # Skip correlation filter if show_all is enabled
        if not show_all and corr_spec:
            if not corr_spec.is_satisfied_by(metrics_dict):
                diagnostics.incr("correlation_skipped_count")
                reason = _correlation_rejection_reason(corr_spec, metrics_dict)
                filter_results["rejection_reason"] = reason
                filter_results["filters_failed"].append("correlation")
                _record_rejection(rejections, sym, reason)
                metrics_dict["filter_results"] = filter_results
                scanned_symbols.append(metrics_dict)
                continue
            else:
                filter_results["filters_passed"].append("correlation")
            # Enrich with correlation metadata
            corr_spec.enrich(metrics_dict)

        # Symbol passed all filters
        logger.info("ACCEPTED | %s | Passed all filters", sym)
        filter_results["passed"] = True
        metrics_dict["filter_results"] = filter_results
        candidates.append(metrics_dict)
        scanned_symbols.append(metrics_dict)

    return candidates, diagnostics.to_dict(), scanned_symbols


def _record_rejection(rejections: Optional[dict[str, str]], symbol: str, reason: str) -> None:
    if rejections is None or symbol in rejections:
        return
    rejections[symbol] = reason
    logger.info("REJECTED | %s | %s", symbol, reason)


def _first_failure_reason(
    metrics: dict[str, Any],
    data_integrity_spec: DataIntegritySpec,
    vrp_structural_spec: VrpStructuralSpec,
    vol_trap_spec: VolatilityTrapSpec,
    vol_momentum_spec: VolatilityMomentumSpec,
    retail_spec: RetailEfficiencySpec,
    slippage_spec: SlippageSpec,
    iv_percentile_spec: Optional[IVPercentileSpec],
    yield_spec: Optional[YieldSpec],
    sector_spec: Optional[SectorExclusionSpec],
    liquidity_spec: Optional[LiquiditySpec],
) -> str:
    checks: list[tuple[Specification[dict[str, Any]], str]] = [
        (data_integrity_spec, _data_integrity_reason(metrics)),
        (vrp_structural_spec, _vrp_structural_reason(metrics, vrp_structural_spec.threshold)),
        (
            vol_trap_spec,
            _vol_trap_reason(
                metrics, vol_trap_spec.rank_threshold, vol_trap_spec.vrp_rich_threshold
            ),
        ),
        (
            vol_momentum_spec,
            _vol_momentum_reason(metrics, vol_momentum_spec.min_momentum_ratio),
        ),
        (retail_spec, _retail_reason(metrics, retail_spec.min_price)),
        (slippage_spec, _slippage_reason(metrics, slippage_spec.max_slippage)),
    ]

    if iv_percentile_spec is not None:
        checks.append(
            (
                iv_percentile_spec,
                _iv_percentile_reason(metrics, iv_percentile_spec.min_percentile),
            )
        )
    if yield_spec is not None:
        checks.append((yield_spec, _yield_reason(metrics, yield_spec.min_yield)))
    if sector_spec is not None:
        checks.append((sector_spec, _sector_reason(metrics)))
    if liquidity_spec is not None:
        checks.append(
            (
                liquidity_spec,
                _liquidity_reason(
                    metrics,
                    liquidity_spec.max_slippage,
                    liquidity_spec.min_vol,
                    liquidity_spec.min_tt_liquidity_rating,
                ),
            )
        )

    for spec, reason in checks:
        if not spec.is_satisfied_by(metrics):
            return reason

    return "Filtered (unknown reason)"


def _data_integrity_reason(metrics: dict[str, Any]) -> str:
    warning = metrics.get("warning")
    return f"Data Integrity: warning={warning}"


def _vrp_structural_reason(metrics: dict[str, Any], threshold: float) -> str:
    vrp = metrics.get("vrp_structural")
    if vrp is None:
        return "VRP Structural: missing"
    return f"VRP Structural: {float(vrp):.2f} <= {threshold:.2f}"


def _vol_trap_reason(
    metrics: dict[str, Any], rank_threshold: float, vrp_rich_threshold: float
) -> str:
    hv_rank = metrics.get("hv_rank")
    vrp_s = metrics.get("vrp_structural")
    hv_rank_val = float(hv_rank) if hv_rank is not None else 0.0
    vrp_val = float(vrp_s) if vrp_s is not None else 0.0
    return (
        f"Volatility Trap: HV Rank {hv_rank_val:.1f} < {rank_threshold:.1f} "
        f"(VRP {vrp_val:.2f} > {vrp_rich_threshold:.2f})"
    )


def _vol_momentum_reason(metrics: dict[str, Any], min_ratio: float) -> str:
    hv30 = metrics.get("hv30")
    hv90 = metrics.get("hv90")
    try:
        hv30_f = float(hv30) if hv30 is not None else 0.0
        hv90_f = float(hv90) if hv90 is not None else 0.0
        ratio = hv30_f / hv90_f if hv90_f != 0 else 0.0
    except (TypeError, ValueError, ZeroDivisionError):
        ratio = 0.0
    return f"Vol Momentum: {ratio:.2f} < {min_ratio:.2f}"


def _retail_reason(metrics: dict[str, Any], min_price: float) -> str:
    symbol = str(metrics.get("symbol", ""))
    if symbol.startswith("/"):
        return "Retail Efficiency: futures exempt"

    price_raw = metrics.get("price")
    try:
        price = float(price_raw) if price_raw is not None else 0.0
    except (ValueError, TypeError):
        price = 0.0

    if price < min_price:
        return f"Retail Efficiency: price {price:.2f} < {min_price:.2f}"

    return "Retail Efficiency: failed"


def _slippage_reason(metrics: dict[str, Any], max_slippage: float) -> str:
    from variance.liquidity import SlippageCalculator

    has_quote, calculated_slippage = SlippageCalculator.calculate_max_slippage(metrics)
    if has_quote and calculated_slippage > max_slippage:
        return f"Slippage: {calculated_slippage:.2%} > {max_slippage:.2%}"

    return "Slippage: failed"


def _iv_percentile_reason(metrics: dict[str, Any], min_percentile: float) -> str:
    iv_pct = metrics.get("iv_percentile")
    if iv_pct is None:
        return "IV Percentile: missing"
    return f"IV Percentile: {float(iv_pct):.1f} < {min_percentile:.1f}"


def _calculate_yield_percent(metrics: dict[str, Any]) -> Optional[float]:
    try:
        price = float(metrics.get("price") or 0.0)
        if price <= 0:
            return None
        call_bid = metrics.get("call_bid")
        call_ask = metrics.get("call_ask")
        put_bid = metrics.get("put_bid")
        put_ask = metrics.get("put_ask")
        if all(v is None for v in [call_bid, call_ask, put_bid, put_ask]):
            bid = float(metrics.get("atm_bid", 0.0))
            ask = float(metrics.get("atm_ask", 0.0))
        else:
            bid = float(call_bid or 0.0) + float(put_bid or 0.0)
            ask = float(call_ask or 0.0) + float(put_ask or 0.0)
        mid = (bid + ask) / 2
        if mid <= 0:
            return None
        bpr_est = price * 0.20
        if bpr_est <= 0:
            return None
        return (mid / bpr_est) * (30.0 / 45.0) * 100.0
    except (TypeError, ValueError):
        return None


def _yield_reason(metrics: dict[str, Any], min_yield: float) -> str:
    yield_pct = _calculate_yield_percent(metrics)
    if yield_pct is None:
        # Check what's specifically missing
        price = metrics.get("price")
        if not price or float(price) <= 0:
            return "Yield: no underlying price"
        # Check if we have option pricing
        has_options = any(
            metrics.get(k) is not None
            for k in ["call_bid", "call_ask", "put_bid", "put_ask", "atm_bid", "atm_ask"]
        )
        if not has_options:
            return "Yield: no option pricing available"
        return "Yield: insufficient pricing data"
    return f"Yield: {yield_pct:.2f}% < {min_yield:.2f}%"


def _sector_reason(metrics: dict[str, Any]) -> str:
    sector = str(metrics.get("sector", "Unknown"))
    return f"Sector Exclusion: {sector}"


def _liquidity_reason(
    metrics: dict[str, Any],
    max_slippage: float,
    min_vol: int,
    min_tt_liquidity_rating: int,
) -> str:
    from variance.liquidity import SlippageCalculator

    has_quote, max_slip = SlippageCalculator.calculate_max_slippage(metrics)
    tt_rating = metrics.get("liquidity_rating")
    if tt_rating is not None:
        try:
            rating_val = int(tt_rating)
        except (TypeError, ValueError):
            rating_val = 0
        if rating_val < min_tt_liquidity_rating:
            return f"Liquidity: TT rating {rating_val} < {min_tt_liquidity_rating}"
        if has_quote and max_slip > 0.25:
            return f"Liquidity: slippage {max_slip:.2%} > 25%"

    vol_raw = metrics.get("option_volume", metrics.get("atm_volume"))
    vol = int(vol_raw or 0)
    detail = ""
    if has_quote and max_slip > max_slippage:
        detail = f" (slippage {max_slip:.2%} > {max_slippage:.2%})"
    return f"Liquidity: volume {vol} < {min_vol}{detail}"


def _tactical_rejection_reason(metrics: dict[str, Any], threshold: float) -> str:
    vrp_tactical = metrics.get("vrp_tactical")
    if vrp_tactical is not None:
        return f"VRP Tactical: {float(vrp_tactical):.2f} <= {threshold:.2f}"

    iv = metrics.get("iv")
    hv20 = metrics.get("hv20")
    if iv is None or hv20 is None:
        return "VRP Tactical: missing IV/HV20"
    try:
        iv_f = float(iv)
        hv20_f = float(hv20)
    except (TypeError, ValueError):
        return "VRP Tactical: invalid IV/HV20"
    if hv20_f <= 0:
        return "VRP Tactical: HV20 <= 0"
    vrp = iv_f / hv20_f
    return f"VRP Tactical: {vrp:.2f} <= {threshold:.2f}"


def _correlation_rejection_reason(corr_spec: CorrelationSpec, metrics: dict[str, Any]) -> str:
    result = corr_spec.evaluate(metrics)
    if result.correlation is None:
        return "Correlation: missing returns/proxy"
    return f"Correlation: rho {result.correlation:.2f} > {corr_spec.max_correlation:.2f}"


def _scalable_rejection_reason(metrics: dict[str, Any], scalable_spec: ScalableGateSpec) -> str:
    vtm_raw = metrics.get("vrp_tactical_markup")
    vtm = float(vtm_raw) if vtm_raw is not None else 0.0
    vsm_raw = metrics.get("vrp_structural")
    vsm = float(vsm_raw) if vsm_raw is not None else 1.0
    divergence = (vtm + 1.0) / vsm if vsm > 0 else 1.0
    return (
        "Scalable Gate: markup "
        f"{vtm:.2f} < {scalable_spec.markup_threshold:.2f} and divergence "
        f"{divergence:.2f} < {scalable_spec.divergence_threshold:.2f}"
    )


def _update_counters(
    sym: str,
    metrics: dict[str, Any],
    config: "ScreenerConfig",
    rules: dict[str, Any],
    diagnostics: ScreenerDiagnostics,
    threshold: float,
    portfolio_returns: Optional[np.ndarray],
    raw_data: Optional[dict[str, Any]] = None,
) -> None:
    """Internal helper for reporting accuracy."""
    sector = str(metrics.get("sector", "Unknown"))
    if config.exclude_sectors and sector in config.exclude_sectors:
        diagnostics.incr("sector_skipped_count")

    # Re-import locally to avoid cycle
    from variance.liquidity.checker import is_illiquid as _is_illiquid

    is_illiquid, _ = _is_illiquid(sym, metrics, rules, config.min_tt_liquidity_rating)
    if is_illiquid and not config.allow_illiquid:
        diagnostics.incr("illiquid_skipped_count")

    if metrics.get("vrp_structural") is None:
        diagnostics.incr("missing_vrp_structural_count")
    elif float(metrics.get("vrp_structural", 0)) <= threshold:
        diagnostics.incr("low_vrp_structural_count")

    hv_rank = metrics.get("hv_rank")
    rich_threshold = float(rules.get("vrp_structural_rich_threshold", 1.0))
    trap_threshold = float(rules.get("hv_rank_trap_threshold", 15.0))
    vrp_s_raw = metrics.get("vrp_structural")

    vrp_s = float(vrp_s_raw) if vrp_s_raw is not None else 0.0
    hv_rank_f = float(hv_rank) if hv_rank is not None else 100.0

    if vrp_s > rich_threshold and hv_rank is not None and hv_rank_f < trap_threshold:
        diagnostics.incr("hv_rank_trap_skipped_count")

    # Retail Efficiency Skip
    from variance.liquidity import SlippageCalculator

    retail_min_price = float(rules.get("retail_min_price", 25.0))
    retail_max_slippage = float(rules.get("retail_max_slippage", 0.05))
    price = float(metrics.get("price") or 0.0)

    # Check retail efficiency (price floor)
    if price < retail_min_price:
        diagnostics.incr("retail_inefficient_skipped_count")

    # Check slippage separately
    has_quote, max_slippage = SlippageCalculator.calculate_max_slippage(metrics)
    if has_quote and max_slippage > retail_max_slippage:
        diagnostics.incr("slippage_skipped_count")

    # New: IV Percentile Skip
    if config.min_iv_percentile is not None and config.min_iv_percentile > 0:
        iv_pct = metrics.get("iv_percentile")
        if iv_pct is None or float(iv_pct) < config.min_iv_percentile:
            diagnostics.incr("low_iv_percentile_skipped_count")

    # New: Yield Skip
    min_yield = float(rules.get("min_yield_percent", 0.0))
    if min_yield > 0:
        # Re-calc yield locally for diagnostics (duplicate of YieldSpec logic)
        try:
            p = float(metrics.get("price") or 0.0)
            if p > 0:
                bpr = p * 0.20
                cb = metrics.get("call_bid")
                ca = metrics.get("call_ask")
                pb = metrics.get("put_bid")
                pa = metrics.get("put_ask")
                if all(v is None for v in [cb, ca, pb, pa]):
                    b = float(metrics.get("atm_bid", 0.0))
                    a = float(metrics.get("atm_ask", 0.0))
                else:
                    b = float(cb or 0) + float(pb or 0)
                    a = float(ca or 0) + float(pa or 0)
                m = (b + a) / 2
                y = (m / bpr) * (30.0 / 45.0) * 100.0
                if y < min_yield:
                    diagnostics.incr("low_yield_skipped_count")
        except (ValueError, TypeError):
            pass

    warning = metrics.get("warning")
    soft_warnings = [
        "iv_scale_corrected",
        "iv_scale_assumed_decimal",
        "after_hours_stale",
        "tastytrade_fallback",
        "market_data_unavailable_cached",
        None,
    ]
    if warning not in soft_warnings:
        diagnostics.incr("data_integrity_skipped_count")

    # Correlation count handled after main spec pass
