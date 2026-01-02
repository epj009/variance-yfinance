import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Optional, Union

# Import common utilities
from .common import warn_if_not_venv
from .config_loader import ConfigBundle, load_config_bundle
from .errors import build_error, error_lines

# Re-export extracted functions for backward compatibility with existing code
from .liquidity.checker import is_illiquid as _is_illiquid  # noqa: F401
from .logging_config import audit_log, generate_session_id, set_session_id, setup_logging
from .scoring.calculator import calculate_variance_score as _calculate_variance_score  # noqa: F401
from .signals.classifier import (  # noqa: F401
    create_candidate_flags as _create_candidate_flags,
)
from .signals.environment import (  # noqa: F401
    get_recommended_environment as _get_recommended_environment,
)


@dataclass(frozen=True)
class ScreenerConfig:
    limit: Optional[int] = None
    min_vrp_structural: Optional[float] = None
    min_variance_score: Optional[float] = None
    min_iv_percentile: Optional[float] = None  # New
    retail_min_price: Optional[float] = None  # Profile-level override for retail price floor
    min_tt_liquidity_rating: Optional[int] = None  # Profile-level override for TT liquidity rating
    allow_illiquid: bool = False
    show_all: bool = False  # Bypass all filters, show entire watchlist
    exclude_sectors: list[str] = field(default_factory=list)
    include_asset_classes: list[str] = field(default_factory=list)
    exclude_asset_classes: list[str] = field(default_factory=list)
    exclude_symbols: list[str] = field(default_factory=list)
    held_symbols: list[str] = field(default_factory=list)
    debug: bool = False


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
        retail_min_price=profile_data.get("retail_min_price"),  # Profile-level override
        min_tt_liquidity_rating=profile_data.get(
            "min_tt_liquidity_rating"
        ),  # Profile-level override
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

    console_level = os.getenv("VARIANCE_LOG_LEVEL", "INFO")
    file_level = os.getenv("VARIANCE_FILE_LOG_LEVEL", "DEBUG")
    enable_debug = os.getenv("VARIANCE_DEBUG", "").lower() in ("1", "true", "yes")
    json_logs = os.getenv("VARIANCE_JSON_LOGS", "").lower() in ("1", "true", "yes")
    setup_logging(
        console_level=console_level,
        file_level=file_level,
        enable_debug_file=enable_debug,
        json_format=json_logs,
    )
    session_id = generate_session_id()
    set_session_id(session_id)
    logger = logging.getLogger(__name__)
    logger.info("Vol screener started: session_id=%s", session_id)

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
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="Bypass all filters and show entire watchlist (useful for debugging)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Include per-symbol rejection reasons in the output",
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

    updates: dict[str, Any] = {}
    if args.limit is not None:
        updates["limit"] = args.limit
    if args.show_all:
        updates["show_all"] = True
    if args.debug:
        updates["debug"] = True

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
        updates["exclude_sectors"] = exclude_list
    if include_assets:
        updates["include_asset_classes"] = include_assets
    if exclude_assets:
        updates["exclude_asset_classes"] = exclude_assets
    if exclude_symbols_list:
        updates["exclude_symbols"] = exclude_symbols_list
    if held_symbols_list:
        updates["held_symbols"] = held_symbols_list
    if updates:
        config = replace(config, **updates)

    audit_log(
        "Screening started",
        session_id=session_id,
        profile=args.profile,
        limit=args.limit,
        show_all=args.show_all,
        debug=args.debug,
    )

    try:
        report_data = screen_volatility(config, config_bundle=config_bundle)

        if "error" in report_data:
            audit_log(
                "Screening failed",
                session_id=session_id,
                error=report_data.get("message", "Unknown error"),
            )
            for line in error_lines(report_data):
                print(line, file=sys.stderr)
            print(json.dumps(report_data, indent=2), file=sys.stderr)
            sys.exit(1)

        summary = report_data.get("summary", {})
        audit_log(
            "Screening completed",
            session_id=session_id,
            scanned=summary.get("scanned_symbols_count"),
            candidates=summary.get("candidates_count"),
        )

        print(json.dumps(report_data, indent=2))
    except Exception as exc:
        logger.exception("Unhandled exception in vol_screener")
        audit_log("Screening crashed", session_id=session_id, error=str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
