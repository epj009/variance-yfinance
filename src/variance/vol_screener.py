import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Union

# Import common utilities
from .common import warn_if_not_venv
from .config_loader import ConfigBundle, load_config_bundle
from .errors import build_error, error_lines


@dataclass
class ScreenerConfig:
    limit: Optional[int] = None
    min_vrp_structural: Optional[float] = None
    min_variance_score: Optional[float] = None
    min_iv_percentile: Optional[float] = None  # New
    allow_illiquid: bool = False
    exclude_sectors: list[str] = field(default_factory=list)
    include_asset_classes: list[str] = field(default_factory=list)
    exclude_asset_classes: list[str] = field(default_factory=list)
    exclude_symbols: list[str] = field(default_factory=list)
    held_symbols: list[str] = field(default_factory=list)


def load_profile_config(
    profile_name: str,
    *,
    config_bundle: Optional[ConfigBundle] = None,
    config_dir: Optional[str] = None,
    strict: Optional[bool] = None,
) -> ScreenerConfig:
    if config_bundle is None:
        config_bundle = load_config_bundle(config_dir=config_dir, strict=strict)
    profiles = config_bundle.get("screener_profiles", {})
    rules = config_bundle.get("trading_rules", {})
    profile_key = profile_name.lower()
    profile_data = profiles.get(profile_key)
    if not isinstance(profile_data, dict):
        available = ", ".join(sorted(profiles.keys()))
        raise ValueError(f"Unknown profile '{profile_name}'. Available profiles: {available}")

    return ScreenerConfig(
        limit=None,
        min_vrp_structural=profile_data.get("min_vrp_structural"),
        min_variance_score=profile_data.get(
            "min_variance_score", rules.get("min_variance_score", 10.0)
        ),
        min_iv_percentile=profile_data.get("min_iv_percentile", 0.0),  # Default to 0 if missing
        allow_illiquid=profile_data.get("allow_illiquid", False),
        exclude_sectors=list(profile_data.get("exclude_sectors", []) or []),
        include_asset_classes=list(profile_data.get("include_asset_classes", []) or []),
        exclude_asset_classes=list(profile_data.get("exclude_asset_classes", []) or []),
        exclude_symbols=list(profile_data.get("exclude_symbols", []) or []),
        held_symbols=list(profile_data.get("held_symbols", []) or []),
    )


def get_days_to_date(date_str: Optional[str]) -> Union[int, str]:
    """
    Calculate the number of days from today until the given date string (ISO format).

    Args:
        date_str: ISO format date string or "Unavailable".

    Returns:
        Number of days as integer, or "N/A" if date is unavailable or invalid.
    """
    if not date_str or date_str == "Unavailable":
        return "N/A"  # Return a string for unavailable
    try:
        target = datetime.fromisoformat(date_str).date()
        today = datetime.now().date()
        delta = (target - today).days
        return delta
    except (ValueError, TypeError):
        return "N/A"


def _is_illiquid(symbol: str, metrics: dict[str, Any], rules: dict[str, Any]) -> tuple[bool, bool]:
    """
    Checks if a symbol fails the liquidity rules.
    Returns: (is_illiquid, is_implied_pass)
    """
    if _is_futures_symbol(symbol):
        return False, False

    if _fails_tt_liquidity_rating(metrics, rules):
        return True, False

    implied_pass, is_implied = _check_implied_liquidity(metrics, rules)
    if implied_pass:
        return False, is_implied

    if _fails_activity_gate(metrics, rules):
        return True, False

    return True, False


def _is_futures_symbol(symbol: str) -> bool:
    return symbol.startswith("/")


def _fails_tt_liquidity_rating(metrics: dict[str, Any], rules: dict[str, Any]) -> bool:
    tt_rating = metrics.get("liquidity_rating")
    if tt_rating is None:
        return False
    try:
        min_rating = int(rules.get("min_tt_liquidity_rating", 4))
        return int(tt_rating) < min_rating
    except (TypeError, ValueError):
        return False


def _check_implied_liquidity(metrics: dict[str, Any], rules: dict[str, Any]) -> tuple[bool, bool]:
    legs = [
        ("call", metrics.get("call_bid"), metrics.get("call_ask")),
        ("put", metrics.get("put_bid"), metrics.get("put_ask")),
    ]

    has_valid_quote = False
    max_slippage_found = 0.0

    for _side, bid, ask in legs:
        if bid is None or ask is None:
            continue
        f_bid, f_ask = float(bid), float(ask)
        mid = (f_bid + f_ask) / 2
        if mid > 0:
            has_valid_quote = True
            slippage = (f_ask - f_bid) / mid
            if slippage > max_slippage_found:
                max_slippage_found = slippage

    max_slippage_pct = float(rules.get("max_slippage_pct", 0.05))
    if has_valid_quote and max_slippage_found <= max_slippage_pct:
        vol = metrics.get("atm_volume", 0) or 0
        is_implied = int(vol) == 0
        return True, is_implied

    return False, False


def _fails_activity_gate(metrics: dict[str, Any], rules: dict[str, Any]) -> bool:
    mode = rules.get("liquidity_mode", "volume")
    min_atm_volume = int(rules.get("min_atm_volume", 0))
    min_atm_open_interest = int(rules.get("min_atm_open_interest", 500))
    if mode == "open_interest":
        atm_oi_val = _safe_float(metrics.get("atm_open_interest"), default=-1.0)
        if atm_oi_val < 0:
            atm_volume_val = _safe_float(metrics.get("atm_volume"), default=-1.0)
            return atm_volume_val >= 0 and atm_volume_val < min_atm_volume
        return atm_oi_val < min_atm_open_interest

    atm_volume_val = _safe_float(metrics.get("atm_volume"), default=-1.0)
    return atm_volume_val >= 0 and atm_volume_val < min_atm_volume


def _create_candidate_flags(
    vrp_structural: Optional[float],
    days_to_earnings: Union[int, str],
    compression_ratio: Optional[float],
    vrp_t_markup: Optional[float],
    hv20: Optional[float],
    hv60: Optional[float],
    rules: dict[str, Any],
) -> dict[str, bool]:
    """Creates a dictionary of boolean flags for a candidate."""

    # Coiled Logic: Requires BOTH long-term compression (vs 252) and medium-term compression (vs 60)
    # to avoid flagging "new normal" low vol regimes as coiled.
    is_coiled_long = compression_ratio is not None and compression_ratio < rules.get(
        "compression_coiled_threshold", 0.75
    )
    is_coiled_medium = True  # Default to true if missing data
    if hv60 and hv60 > 0 and hv20:
        is_coiled_medium = (hv20 / hv60) < 0.85

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
        "is_coiled": bool(is_coiled_long and is_coiled_medium),
        "is_expanding": bool(
            compression_ratio is not None
            and compression_ratio > rules.get("compression_expanding_threshold", 1.25)
        ),
        "is_cheap": bool(
            vrp_t_markup is not None
            and vrp_t_markup < rules.get("vrp_tactical_cheap_threshold", -0.10)
        ),
    }


def _determine_signal_type(
    flags: dict[str, bool],
    vrp_t_markup: Optional[float],
    rules: dict[str, Any],
    iv_percentile: Optional[float] = None,
) -> str:
    """
    Synthesizes multiple metrics into a single 'Signal Type' for the TUI.
    Hierarchy: EVENT > DISCOUNT > RICH > BOUND > FAIR
    """
    if flags["is_earnings_soon"]:
        return "EVENT"

    # Statistical Extreme Check (The /NG Paradox Fix)
    # If IV is at statistical extremes (>80% of last year), it is RICH regardless of tactical discount
    if iv_percentile is not None and iv_percentile > 0.80:
        return "RICH"

    if flags.get("is_cheap"):  # VRP Tactical Markup < -10%
        return "DISCOUNT"

    # Rich Logic: High markup takes precedence over Coiled state
    # Priority 1: Tactical VRP Markup > 20%
    if vrp_t_markup is not None and vrp_t_markup > 0.20:
        return "RICH"

    # Priority 2: Structural VRP (Fallback if Tactical is missing/flat)
    if flags.get("is_rich"):
        return "RICH"

    if flags["is_coiled"]:  # Ratio < 0.75
        return "BOUND"

    return "FAIR"


def _determine_regime_type(flags: dict[str, bool]) -> str:
    """
    Determines the Volatility Regime based on compression flags.
    """
    if flags["is_coiled"]:
        return "COILED"
    if flags["is_expanding"]:
        return "EXPANDING"
    return "NORMAL"


def _get_recommended_environment(signal_type: str) -> str:
    """Maps Signal Type to a recommended market environment for strategy selection."""
    if signal_type == "BOUND":
        return "High IV / Neutral (Defined)"
    elif signal_type == "RICH":
        return "High IV / Neutral (Undefined)"
    elif signal_type == "DISCOUNT":
        return "Low IV / Vol Expansion"
    elif signal_type == "EVENT":
        return "Binary Risk"
    return "Neutral / Fair Value"


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        if val is None:
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


def _calculate_variance_score(metrics: dict[str, Any], rules: dict[str, Any]) -> float:
    """
    Calculates a composite 'Variance Score' (0-100) to rank trading opportunities.

    Weights:
    - VRP Structural (Baseline): 50%
    - VRP Tactical (Current): 50%

    The score measures the ABSOLUTE distance from Fair Value (1.0).
    Significant dislocation in either direction (Rich or Cheap) results in a high score.
    """
    score = 0.0

    bias = _safe_float(metrics.get("vrp_structural"), -1.0)
    bias_score = _variance_component(bias, rules)
    if bias != -1.0:
        score += bias_score * 0.50

    bias20 = _safe_float(metrics.get("vrp_tactical"), -1.0)
    bias20_score = _variance_component(bias20, rules)
    if bias20 != -1.0:
        score += bias20_score * 0.50
    elif bias != -1.0:
        score += bias_score * 0.50

    score = _apply_trap_penalty(score, metrics, rules)
    return round(float(score), 1)


def _variance_component(bias: float, rules: dict[str, Any]) -> float:
    if bias == -1.0:
        return 0.0
    multiplier = _safe_float(rules.get("variance_score_dislocation_multiplier", 200))
    dislocation = abs(bias - 1.0) * multiplier
    return max(0.0, min(100.0, dislocation))


def _apply_trap_penalty(score: float, metrics: dict[str, Any], rules: dict[str, Any]) -> float:
    hv_rank = _safe_float(metrics.get("hv_rank"), -1.0)
    hv_rank_trap = _safe_float(rules.get("hv_rank_trap_threshold", 15.0), 15.0)
    if hv_rank != -1.0 and hv_rank < hv_rank_trap:
        return score * 0.50
    return score


import numpy as np


def screen_volatility(
    config: ScreenerConfig,
    *,
    config_bundle: Optional[ConfigBundle] = None,
    config_dir: Optional[str] = None,
    strict: Optional[bool] = None,
    portfolio_returns: Optional[np.ndarray] = None,
) -> dict[str, Any]:
    """
    Scan the watchlist for high-volatility trading opportunities using the Screening Pipeline.
    """
    if config_bundle is None:
        config_bundle = load_config_bundle(config_dir=config_dir, strict=strict)

    from .screening.pipeline import ScreeningPipeline

    pipeline = ScreeningPipeline(config, config_bundle, portfolio_returns=portfolio_returns)
    return pipeline.execute()


def main() -> None:
    warn_if_not_venv()

    parser = argparse.ArgumentParser(description="Screen for high volatility opportunities.")
    parser.add_argument(
        "limit", type=int, nargs="?", help="Limit the number of symbols to scan (optional)"
    )
    parser.add_argument(
        "--profile",
        type=str,
        default="balanced",
        help="Profile name from config/runtime_config.json (screener_profiles)",
    )
    parser.add_argument(
        "--exclude-sectors",
        type=str,
        help='Comma-separated list of sectors to exclude (e.g., "Financial Services,Technology")',
    )
    parser.add_argument(
        "--include-asset-classes",
        type=str,
        help='Comma-separated list of asset classes to include (e.g., "Commodity,FX"). Options: Equity, Commodity, Fixed Income, FX, Index',
    )
    parser.add_argument(
        "--exclude-asset-classes",
        type=str,
        help='Comma-separated list of asset classes to exclude (e.g., "Equity"). Options: Equity, Commodity, Fixed Income, FX, Index',
    )
    parser.add_argument(
        "--exclude-symbols",
        type=str,
        help='Comma-separated list of symbols to exclude (e.g., "NVDA,TSLA,AMD")',
    )
    parser.add_argument(
        "--held-symbols",
        type=str,
        help="Comma-separated list of symbols currently in portfolio (will be flagged as held, not excluded)",
    )

    args = parser.parse_args()
    config_bundle = load_config_bundle()
    try:
        config = load_profile_config(args.profile, config_bundle=config_bundle)
    except ValueError as exc:
        payload = build_error(
            "Invalid screener profile.",
            details=str(exc),
            hint="Use --profile with a name from config/runtime_config.json (screener_profiles).",
        )
        for line in error_lines(payload):
            print(line, file=sys.stderr)
        print(json.dumps(payload, indent=2), file=sys.stderr)
        sys.exit(2)

    if args.limit is not None:
        config.limit = args.limit

    exclude_list = None
    if args.exclude_sectors:
        exclude_list = [s.strip() for s in args.exclude_sectors.split(",")]

    include_assets = None
    if args.include_asset_classes:
        include_assets = [s.strip() for s in args.include_asset_classes.split(",")]

    exclude_assets = None
    if args.exclude_asset_classes:
        exclude_assets = [s.strip() for s in args.exclude_asset_classes.split(",")]

    exclude_symbols_list = None
    if args.exclude_symbols:
        exclude_symbols_list = [
            s.strip().upper() for s in args.exclude_symbols.split(",") if s.strip()
        ]

    held_symbols_list = None
    if args.held_symbols:
        held_symbols_list = [s.strip().upper() for s in args.held_symbols.split(",") if s.strip()]

    if exclude_list:
        config.exclude_sectors = exclude_list
    if include_assets:
        config.include_asset_classes = include_assets
    if exclude_assets:
        config.exclude_asset_classes = exclude_assets
    if exclude_symbols_list:
        config.exclude_symbols = exclude_symbols_list
    if held_symbols_list:
        config.held_symbols = held_symbols_list

    report_data = screen_volatility(config, config_bundle=config_bundle)

    if "error" in report_data:
        for line in error_lines(report_data):
            print(line, file=sys.stderr)
        print(json.dumps(report_data, indent=2), file=sys.stderr)
        sys.exit(1)

    print(json.dumps(report_data, indent=2))


if __name__ == "__main__":
    main()
