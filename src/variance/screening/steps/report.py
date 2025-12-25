"""
Report Construction Step
"""

from datetime import datetime
from typing import Any


def build_report(
    candidates: list[dict[str, Any]],
    counters: dict[str, int],
    config: Any,
    rules: dict[str, Any],
    market_data_diagnostics: dict[str, int],
) -> dict[str, Any]:
    """Constructs the final serialized report."""
    from variance.common import map_sector_to_asset_class

    # 1. Final Summary Formatting
    structural_threshold = float(rules.get("vrp_structural_threshold", 0.85))
    if config.min_vrp_structural is not None:
        structural_threshold = float(config.min_vrp_structural)

    bias_note = f"VRP Structural (IV / HV) > {structural_threshold}"
    if config.min_vrp_structural is not None and config.min_vrp_structural <= 0:
        bias_note = "All symbols (no bias filter)"

    liq_mode = rules.get("liquidity_mode", "volume")
    if config.allow_illiquid:
        liquidity_note = "Illiquid included"
    else:
        liquidity_note = f"Illiquid filtered ({liq_mode} check)"

    summary = {
        "scanned_symbols_count": len(candidates)
        + sum(v for k, v in counters.items() if "skipped" in k),
        "candidates_count": len(candidates),
        "filter_note": f"{bias_note}; {liquidity_note}",
        "correlation_max": float(rules.get("max_portfolio_correlation", 0.95)),
        "correlation_skipped_count": counters.get("correlation_skipped_count", 0),
        **counters,
    }

    held_symbols = set(s.upper() for s in config.held_symbols)
    display_candidates = []
    for candidate in candidates:
        display = dict(candidate)
        display["Symbol"] = candidate.get("symbol")
        display["Price"] = candidate.get("price", 0.0)
        asset_class = candidate.get("asset_class") or map_sector_to_asset_class(
            str(candidate.get("sector", "Unknown"))
        )
        display["Asset Class"] = asset_class
        display["is_held"] = str(candidate.get("symbol", "")).upper() in held_symbols

        # Ensure IV Percentile is visible in the final report
        ivp = candidate.get("iv_percentile")
        if ivp is not None:
            # Tastytrade returns 0-1 (e.g. 0.53), convert to 0-100 for display
            try:
                display["IV Percentile"] = float(ivp) * 100.0
            except (ValueError, TypeError):
                display["IV Percentile"] = None
        else:
            display["IV Percentile"] = None

        display_candidates.append(display)

    return {
        "candidates": display_candidates,
        "summary": summary,
        "meta": {
            "scan_timestamp": datetime.now().isoformat(),
            "profile": getattr(config, "profile", "default"),
            "market_data_diagnostics": market_data_diagnostics,
        },
    }
