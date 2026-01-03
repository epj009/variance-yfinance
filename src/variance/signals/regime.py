"""Volatility Regime Detection - Determine the market volatility state."""

from typing import Any, Optional


def determine_regime_type(
    vol_trend_ratio: Optional[float],
    hv20: Optional[float],
    hv60: Optional[float],
    rules: dict[str, Any],
) -> str:
    """
    Determines the Volatility Regime based on Volatility Trend Ratio thresholds.

    Args:
        vol_trend_ratio: Volatility trend ratio (HV30/HV90)
        hv20: 20-day historical volatility
        hv60: 60-day historical volatility
        rules: Trading rules configuration

    Returns:
        Regime classification: "COILED", "EXPANDING", or "NORMAL"
    """
    if vol_trend_ratio is not None:
        from variance.config_migration import get_config_value

        coiled_threshold = float(
            get_config_value(rules, "vtr_coiled_threshold", "compression_coiled_threshold", 0.75)
        )
        is_coiled_long = vol_trend_ratio < coiled_threshold
        is_coiled_medium = True
        if hv60 and hv60 > 0 and hv20:
            is_coiled_medium = (hv20 / hv60) < 0.85
        if is_coiled_long and is_coiled_medium:
            return "COILED"
        if vol_trend_ratio > 1.15:
            return "EXPANDING"
    return "NORMAL"
