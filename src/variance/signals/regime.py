"""Volatility Regime Detection - Determine the market volatility state."""

from typing import Any, Optional


def determine_regime_type(
    compression_ratio: Optional[float],
    hv20: Optional[float],
    hv60: Optional[float],
    rules: dict[str, Any],
) -> str:
    """
    Determines the Volatility Regime based on compression ratio thresholds.

    Args:
        compression_ratio: IV/HV compression ratio (hv252/iv)
        hv20: 20-day historical volatility
        hv60: 60-day historical volatility
        rules: Trading rules configuration

    Returns:
        Regime classification: "COILED", "EXPANDING", or "NORMAL"
    """
    if compression_ratio is not None:
        coiled_threshold = float(rules.get("compression_coiled_threshold", 0.75))
        is_coiled_long = compression_ratio < coiled_threshold
        is_coiled_medium = True
        if hv60 and hv60 > 0 and hv20:
            is_coiled_medium = (hv20 / hv60) < 0.85
        if is_coiled_long and is_coiled_medium:
            return "COILED"
        if compression_ratio > 1.15:
            return "EXPANDING"
    return "NORMAL"
