"""Signal Classification - Synthesize metrics into actionable signals."""

from typing import Any, Optional, Union


def create_candidate_flags(
    vrp_structural: Optional[float],
    days_to_earnings: Union[int, str],
    vrp_t_markup: Optional[float],
    rules: dict[str, Any],
) -> dict[str, bool]:
    """Creates a dictionary of boolean flags for a candidate."""

    return {
        "is_rich": bool(
            vrp_structural is not None
            and vrp_structural > rules.get("vrp_structural_rich_threshold", 1.0)
        ),
        "is_fair": bool(
            vrp_structural is not None
            and rules["vrp_structural_threshold"]
            < vrp_structural
            <= rules.get("vrp_structural_rich_threshold", 1.0)
        ),
        "is_earnings_soon": bool(
            isinstance(days_to_earnings, int)
            and 0 <= days_to_earnings <= rules["earnings_days_threshold"]
        ),
        "is_cheap": bool(
            vrp_t_markup is not None
            and vrp_t_markup < rules.get("vrp_tactical_cheap_threshold", -0.10)
        ),
    }


def determine_signal_type(
    flags: dict[str, bool],
    vrp_t_markup: Optional[float],
    rules: dict[str, Any],
    iv_percentile: Optional[float] = None,
    compression_ratio: Optional[float] = None,
    hv20: Optional[float] = None,
    hv60: Optional[float] = None,
) -> str:
    """
    Synthesizes multiple metrics into a single 'Signal Type' for the TUI.
    Hierarchy: EVENT > RICH > COMPRESSION > DISCOUNT > FAIR
    """
    if flags["is_earnings_soon"]:
        return "EVENT"

    # Statistical Extreme Check (The /NG Paradox Fix)
    # If IV is at statistical extremes (>80% of last year), it is RICH regardless of tactical discount
    iv_pct_rich = float(rules.get("iv_percentile_rich_threshold", 80.0))
    if iv_percentile is not None and iv_percentile > iv_pct_rich:
        return "RICH"

    # Rich Logic: High markup takes precedence over Coiled state
    # Priority 1: Tactical VRP Markup > 20%
    tactical_rich = float(rules.get("vrp_tactical_rich_threshold", 0.20))
    if vrp_t_markup is not None and vrp_t_markup > tactical_rich:
        return "RICH"

    # Priority 2: Structural VRP (Fallback if Tactical is missing/flat)
    if flags.get("is_rich"):
        return "RICH"

    if compression_ratio is not None:
        coiled_threshold = float(rules.get("compression_coiled_threshold", 0.75))
        is_coiled_long = compression_ratio < coiled_threshold
        is_coiled_medium = True
        if hv60 and hv60 > 0 and hv20:
            is_coiled_medium = (hv20 / hv60) < 0.85

        if is_coiled_long and is_coiled_medium:
            if compression_ratio < 0.60:
                return "COILED-SEVERE"
            return "COILED-MILD"

        if compression_ratio > 1.30:
            return "EXPANDING-SEVERE"
        if compression_ratio > 1.15:
            return "EXPANDING-MILD"

    if flags.get("is_cheap"):  # VRP Tactical Markup < -10%
        return "DISCOUNT"

    return "FAIR"
