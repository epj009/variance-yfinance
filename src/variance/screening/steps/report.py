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

    def _safe_f(val: Any, default: float = 0.0) -> float:
        try:
            return float(val) if val is not None else default
        except (ValueError, TypeError):
            return default

    for candidate in candidates:
        display = dict(candidate)
        display["Symbol"] = candidate.get("symbol")

        display["Price"] = _safe_f(candidate.get("price"))

        asset_class = candidate.get("asset_class") or map_sector_to_asset_class(
            str(candidate.get("sector", "Unknown"))
        )
        display["Asset Class"] = asset_class
        is_held = str(candidate.get("symbol", "")).upper() in held_symbols
        display["is_held"] = is_held

        # 1. Capacity (Liquidity Value in USD)
        display["Capacity"] = _safe_f(candidate.get("liquidity_value"))

        # 2. Yield (%) - Normalized to 30 days
        # Formula: (Straddle Mid / (Price * 0.20)) * (30 / 45)
        # We use 45 as the DTE denominator for normalization.
        price = _safe_f(candidate.get("price"))
        bid = _safe_f(candidate.get("atm_bid"))
        ask = _safe_f(candidate.get("atm_ask"))
        mid = (bid + ask) / 2 if (bid + ask) > 0 else 0.0

        yield_pct = 0.0
        if price > 0:
            bpr_est = price * 0.20
            if bpr_est > 0:
                # 30-day normalized yield
                yield_pct = (mid / bpr_est) * (30.0 / 45.0) * 100.0
        display["Yield"] = yield_pct

        # 3. Earnings In
        from variance.vol_screener import get_days_to_date

        display["Earnings"] = get_days_to_date(candidate.get("earnings_date"))

        # 2. Allocation Vote Logic
        score = _safe_f(candidate.get("score"))
        rho = _safe_f(candidate.get("portfolio_rho"))

        vote = "WATCH"
        if is_held:
            # Scale if setup passed the Standalone Scalable Gate
            vote = "SCALE" if candidate.get("is_scalable_surge") else "HOLD"
        elif score >= 70 and rho <= 0.50:
            vote = "BUY"
        elif score >= 60 and rho <= 0.65:
            vote = "LEAN"
        elif rho > 0.70:
            vote = "AVOID"

        display["Vote"] = vote

        # Ensure IV Percentile is visible in the final report
        ivp_raw = candidate.get("iv_percentile")
        if ivp_raw is not None:
            # Tastytrade returns 0-1 (e.g. 0.53), convert to 0-100 for display
            try:
                display["IV Percentile"] = _safe_f(ivp_raw) * 100.0
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
