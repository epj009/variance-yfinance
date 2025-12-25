import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Union

# Import common utilities
from .common import warn_if_not_venv
from .config_loader import ConfigBundle, load_config_bundle


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
    # Futures exemption: Yahoo data for futures options volume is unreliable
    if symbol.startswith("/"):
        return False, False

    # 1. Check Implied Liquidity (Bid/Ask Spread) FIRST
    legs = [
        ("call", metrics.get("call_bid"), metrics.get("call_ask"), metrics.get("call_vol")),
        ("put", metrics.get("put_bid"), metrics.get("put_ask"), metrics.get("put_vol")),
    ]

    has_valid_quote = False
    max_slippage_found = 0.0

    for _side, bid, ask, _vol in legs:
        if bid is not None and ask is not None:
            f_bid, f_ask = float(bid), float(ask)
            mid = (f_bid + f_ask) / 2
            if mid > 0:
                has_valid_quote = True
                slippage = (f_ask - f_bid) / mid
                if slippage > max_slippage_found:
                    max_slippage_found = slippage

    # GATE: If we have valid quotes and spreads are tight, PASS as "Implied Liquidity"
    max_slippage_pct = float(rules.get("max_slippage_pct", 0.05))
    if has_valid_quote and max_slippage_found <= max_slippage_pct:
        # If volume is 0 but spread is tight, this is an implied pass
        vol = metrics.get("atm_volume", 0) or 0
        is_implied = int(vol) == 0
        return False, is_implied

    # 2. Fallback: Check Reported Activity (Volume or OI)
    mode = rules.get("liquidity_mode", "volume")

    if mode == "open_interest":
        atm_oi = metrics.get("atm_open_interest", 0)
        if atm_oi is None:
            atm_volume = metrics.get("atm_volume", 0)
            if atm_volume is not None and atm_volume < rules["min_atm_volume"]:
                return True, False
        elif atm_oi < rules.get("min_atm_open_interest", 500):
            return True, False
    else:
        # Default: Volume Mode
        atm_volume = metrics.get("atm_volume", 0)
        if atm_volume is not None and atm_volume < rules["min_atm_volume"]:
            return True, False

    return True, False


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
    flags: dict[str, bool], vrp_t_markup: Optional[float], rules: dict[str, Any]
) -> str:
    """
    Synthesizes multiple metrics into a single 'Signal Type' for the TUI.
    Hierarchy: EVENT > DISCOUNT > RICH > BOUND > FAIR
    """
    if flags["is_earnings_soon"]:
        return "EVENT"

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


def _calculate_variance_score(metrics: dict[str, Any], rules: dict[str, Any]) -> float:
    """
    Calculates a composite 'Variance Score' (0-100) to rank trading opportunities.

    Weights:
    - VRP Structural Dislocation (Structural Edge): 37.5%
    - VRP Tactical Dislocation (Tactical Edge): 37.5%
    - IV Percentile (Statistical Edge): 25%

    The score measures the ABSOLUTE distance from Fair Value (1.0).
    Significant dislocation in either direction (Rich or Cheap) results in a high score.

    Penalties:
    - HV Rank Trap: -50% score if Short Vol Trap detected.
    """
    score = 0.0

    # 1. VRP Structural Component (Absolute Dislocation)
    # Target: |Bias - 1.0| * 200. Max 100.
    # Example: 1.5 -> 0.5 * 200 = 100. 0.5 -> 0.5 * 200 = 100.
    bias = metrics.get("vrp_structural")
    bias_score = 0.0
    if bias is not None:
        bias_dislocation = abs(float(bias) - 1.0) * float(
            rules.get("variance_score_dislocation_multiplier", 200)
        )
        bias_score = max(0.0, min(100.0, bias_dislocation))
        score += bias_score * 0.375

    # 2. VRP Tactical Component (Absolute Dislocation)
    bias20 = metrics.get("vrp_tactical")
    if bias20 is not None:
        bias20_dislocation = abs(float(bias20) - 1.0) * float(
            rules.get("variance_score_dislocation_multiplier", 200)
        )
        bias20_score = max(0.0, min(100.0, bias20_dislocation))
        score += bias20_score * 0.375
    elif bias is not None:  # Fallback
        score += bias_score * 0.375

    # 3. IV Percentile Component (0-100)
    # Adds direct weight to statistical extremes
    iv_pct = metrics.get("iv_percentile")
    ivp_score = 0.0
    if iv_pct is not None:
        # iv_percentile is 0.0-1.0 from Tastytrade, 0-100 for score
        ivp_score = float(iv_pct) * 100.0
        score += ivp_score * 0.25

    # 4. Penalties
    # HV Rank Trap: High VRP Structural but extremely low realized vol
    hv_rank = metrics.get("hv_rank")
    trap_threshold = float(rules.get("hv_rank_trap_threshold", 15.0))
    rich_threshold = float(rules.get("vrp_structural_rich_threshold", 1.0))

    if (
        bias is not None
        and float(bias) > rich_threshold
        and hv_rank is not None
        and float(hv_rank) < trap_threshold
    ):
        score *= 0.50  # Slash score by half for traps

    # 4. Regime Penalties (Dev Mode)
    # Coiled Penalty: Recent movement is unsustainably low.
    # High markup may be an artifact of a shrinking denominator.
    # Apply a 20% haircut to Coiled signals to favor Normal/Expanding regimes.
    if metrics.get("regime_type") == "COILED" or metrics.get("is_coiled"):
        score *= 0.80

    return round(float(score), 1)


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
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
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
        print(json.dumps(report_data, indent=2))
        sys.exit(1)

    print(json.dumps(report_data, indent=2))


if __name__ == "__main__":
    main()
