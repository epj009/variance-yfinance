"""
Specification Filtering Step
"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from variance.models.market_specs import (
    CorrelationSpec,
    DataIntegritySpec,
    LiquiditySpec,
    LowVolTrapSpec,
    SectorExclusionSpec,
    VrpStructuralSpec,
)
from variance.models.specs import Specification


def apply_specifications(
    raw_data: Dict[str, Any],
    config: Any,
    rules: Dict[str, Any],
    market_config: Dict[str, Any],
    portfolio_returns: Optional[np.ndarray] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Applies composable filters to the candidate pool."""

    # 1. Setup Counters
    counters = {
        "low_bias_skipped_count": 0,
        "missing_bias_count": 0,
        "sector_skipped_count": 0,
        "illiquid_skipped_count": 0,
        "data_integrity_skipped_count": 0,
        "correlation_skipped_count": 0,
        "bats_efficiency_zone_count": 0,
    }

    # 2. Compose Specs
    structural_threshold = float(
        rules.get("vrp_structural_threshold", 0.85)
        if config.min_vrp_structural is None else config.min_vrp_structural
    )
    hv_floor_absolute = float(rules.get("hv_floor_percent", 5.0))

    main_spec: Specification[dict[str, Any]] = DataIntegritySpec()

    show_all = config.min_vrp_structural is not None and config.min_vrp_structural <= 0
    if not show_all:
        main_spec &= VrpStructuralSpec(structural_threshold)
        main_spec &= LowVolTrapSpec(hv_floor_absolute)

    if config.exclude_sectors:
        main_spec &= SectorExclusionSpec(config.exclude_sectors)

    if not config.allow_illiquid:
        main_spec &= LiquiditySpec(
            max_slippage=float(rules.get("max_slippage_pct", 0.05)),
            min_vol=int(rules.get("min_atm_volume", 500))
        )

    # 4. Correlation Guard (RFC 013)
    if portfolio_returns is not None and not show_all:
        max_corr = float(rules.get("max_portfolio_correlation", 0.70))
        main_spec &= CorrelationSpec(portfolio_returns, max_corr)

    # 3. Apply Gate
    candidates = []
    for sym, metrics in raw_data.items():
        if "error" in metrics:
            continue

        # Normalize keys to lowercase for internal consistency
        metrics_dict = {str(k).lower(): v for k, v in metrics.items()}
        metrics_dict["symbol"] = sym

        if not main_spec.is_satisfied_by(metrics_dict):
            _update_counters(sym, metrics_dict, config, rules, counters, structural_threshold, portfolio_returns)
            continue

        candidates.append(metrics_dict)

    return candidates, counters


def _update_counters(sym, metrics, config, rules, counters, threshold, portfolio_returns):
    """Internal helper for reporting accuracy."""
    sector = str(metrics.get("sector", "Unknown"))
    if config.exclude_sectors and sector in config.exclude_sectors:
        counters["sector_skipped_count"] += 1

    # Re-import locally to avoid cycle
    from variance.vol_screener import _is_illiquid
    is_illiquid, _ = _is_illiquid(sym, metrics, rules)
    if is_illiquid and not config.allow_illiquid:
        counters["illiquid_skipped_count"] += 1

    if metrics.get("vrp_structural") is None:
        counters["missing_bias_count"] += 1
    elif float(metrics.get("vrp_structural", 0)) <= threshold:
        counters["low_bias_skipped_count"] += 1

    # Check for correlation skip specifically
    if portfolio_returns is not None:
        from variance.models.market_specs import CorrelationSpec
        max_corr = float(rules.get("max_portfolio_correlation", 0.70))
        spec = CorrelationSpec(portfolio_returns, max_corr)
        if not spec.is_satisfied_by(metrics):
            counters["correlation_skipped_count"] += 1
