"""Variance Score Calculator - Composite scoring for trading opportunities."""

from typing import Any, Optional

from .components import (
    _safe_float,
    _variance_component,
    score_hv_rank,
    score_iv_percentile,
    score_liquidity,
    score_retail_efficiency,
    score_volatility_momentum,
    score_yield,
)


def calculate_variance_score(
    metrics: dict[str, Any], rules: dict[str, Any], config: Optional[Any] = None
) -> float:
    """
    Calculates a composite 'Variance Score' (0-100) to rank trading opportunities.

    The score blends hard-gate metrics into a single composite. Each component
    is normalized to 0-100 and combined using configurable weights.

    Args:
        metrics: Market data metrics for the symbol
        rules: Trading rules from config
        config: Optional screener config for overrides

    Returns:
        float: Composite score between 0-100
    """
    weights_cfg = rules.get("variance_score_weights", {})
    default_weights = {
        "structural_vrp": 0.2,
        "tactical_vrp": 0.2,
        "volatility_momentum": 0.1,
        "hv_rank": 0.0,  # DEPRECATED (2026-01-04): Tastytrade provides IV Rank not HV Rank
        "iv_percentile": 0.1,
        "yield": 0.1,
        "retail_efficiency": 0.1,
        "liquidity": 0.1,
    }
    weights = {
        key: _safe_float(weights_cfg.get(key, default), default)
        for key, default in default_weights.items()
    }

    total_weight = sum(max(0.0, w) for w in weights.values())
    if total_weight <= 0:
        return 0.0

    structural_score = _variance_component(_safe_float(metrics.get("vrp_structural"), -1.0), rules)
    tactical_raw = _safe_float(metrics.get("vrp_tactical"), -1.0)
    if tactical_raw == -1.0:
        tactical_score = structural_score
    else:
        tactical_score = _variance_component(tactical_raw, rules)

    momentum_score = score_volatility_momentum(metrics, rules)
    hv_rank_score = score_hv_rank(metrics, rules)
    ivp_score = score_iv_percentile(metrics, rules, config)
    yield_score = score_yield(metrics, rules)
    retail_score = score_retail_efficiency(metrics, rules, config)
    liquidity_score = score_liquidity(metrics, rules, config)

    weighted_sum = (
        structural_score * weights["structural_vrp"]
        + tactical_score * weights["tactical_vrp"]
        + momentum_score * weights["volatility_momentum"]
        + hv_rank_score * weights["hv_rank"]
        + ivp_score * weights["iv_percentile"]
        + yield_score * weights["yield"]
        + retail_score * weights["retail_efficiency"]
        + liquidity_score * weights["liquidity"]
    )

    score = weighted_sum / total_weight
    return round(float(max(0.0, min(100.0, score))), 1)
