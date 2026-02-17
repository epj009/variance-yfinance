"""
Report Construction Step
"""

from typing import TYPE_CHECKING, Any

from variance.market_data.clock import get_eastern_timestamp

if TYPE_CHECKING:
    from variance.vol_screener import ScreenerConfig


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def _determine_vote(candidate: dict[str, Any], is_held: bool) -> str:
    score = _safe_float(candidate.get("score"))
    rho = _safe_float(candidate.get("portfolio_rho"))
    vtr_raw = candidate.get("Volatility Trend Ratio")
    vtr = _safe_float(vtr_raw, default=1.0) if vtr_raw is not None else 1.0

    vote = "WATCH"
    if is_held:
        return "SCALE" if candidate.get("is_scalable_surge") else "HOLD"
    if vtr < 0.60:
        return "AVOID (COILED)"
    if vtr < 0.75:
        if score >= 70 and rho <= 0.50:
            return "LEAN"
        return "WATCH"
    if vtr > 1.30:
        if score >= 60 and rho <= 0.60:
            return "STRONG BUY"
        return "BUY"
    if vtr > 1.15:
        if score >= 70 and rho <= 0.50:
            return "BUY"
        if score >= 60 and rho <= 0.65:
            return "LEAN"
        if rho > 0.70:
            return "AVOID"
        return "WATCH"
    if score >= 70 and rho <= 0.50:
        return "BUY"
    if score >= 60 and rho <= 0.65:
        return "LEAN"
    if rho > 0.70:
        return "AVOID"
    return vote


def build_report(
    candidates: list[dict[str, Any]],
    counters: dict[str, int],
    config: "ScreenerConfig",
    rules: dict[str, Any],
    market_data_diagnostics: dict[str, int],
    debug_rejections: dict[str, str],
    scanned_symbols: list[dict[str, Any]],
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
        "scanned_symbols_count": market_data_diagnostics.get("symbols_total", 0),
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

        display["Price"] = _safe_float(candidate.get("price"))
        if candidate.get("hv90_source") == "proxy_dxlink":
            proxy_symbol = candidate.get("proxy")
            proxy_note = f" via {proxy_symbol}" if proxy_symbol else ""
            display["warning_message"] = (
                f"HV90 proxy{proxy_note} affects HV90, HV252, VRP Structural, Compression Ratio."
            )
            display["warning_detail"] = {
                "type": "proxy_hv90",
                "source": "proxy_dxlink",
                "proxy_symbol": proxy_symbol,
                "attributes": ["hv90", "hv252", "vrp_structural", "compression_ratio"],
            }

        asset_class = candidate.get("asset_class") or map_sector_to_asset_class(
            str(candidate.get("sector", "Unknown"))
        )
        display["Asset Class"] = asset_class
        is_held = str(candidate.get("symbol", "")).upper() in held_symbols
        display["is_held"] = is_held

        # 1. Capacity (Liquidity Value in USD)
        display["Capacity"] = _safe_float(candidate.get("liquidity_value"))

        # 2. Yield (%) - Normalized to 30 days
        # Formula: (Straddle Mid / (Price * 0.20)) * (30 / 45)
        # We use 45 as the DTE denominator for normalization.
        price = _safe_float(candidate.get("price"))
        bid = _safe_float(candidate.get("atm_bid"))
        ask = _safe_float(candidate.get("atm_ask"))
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
        display["Vote"] = _determine_vote(candidate, is_held)

        # Ensure IV Percentile is visible in the final report
        ivp_raw = candidate.get("iv_percentile")
        if ivp_raw is not None:
            # Tastytrade client already normalizes to 0-100 range
            try:
                display["IV Percentile"] = _safe_float(ivp_raw)
            except (ValueError, TypeError):
                display["IV Percentile"] = None
        else:
            display["IV Percentile"] = None

        # Prefer new key, fall back to old key for backward compatibility
        vtr = candidate.get("Volatility Trend Ratio") or candidate.get("Compression Ratio")
        if vtr is not None:
            try:
                display["VTR"] = _safe_float(vtr)
            except (ValueError, TypeError):
                display["VTR"] = None
        else:
            display["VTR"] = None

        display_candidates.append(display)

    meta = {
        "scan_timestamp": get_eastern_timestamp(),
        "profile": getattr(config, "profile", "default"),
        "market_data_diagnostics": market_data_diagnostics,
    }
    if debug_rejections:
        meta["filter_rejections"] = debug_rejections

    # Format scanned_symbols for output (include key metrics and filter results)
    formatted_scanned = []
    for symbol_data in scanned_symbols:
        # Calculate VTR directly from hv30/hv90 (don't rely on enriched field)
        hv30 = symbol_data.get("hv30")
        hv90 = symbol_data.get("hv90")
        vtr = None
        if hv30 is not None and hv90 is not None:
            try:
                hv30_f = float(hv30)
                hv90_f = float(hv90)
                # Treat hv30 <= 0 as invalid data (HV cannot be truly zero)
                if hv30_f > 0 and hv90_f > 0:
                    vtr = max(0.50, min(hv30_f / hv90_f, 2.0))  # Clamp to [0.5, 2.0]
            except (ValueError, TypeError, ZeroDivisionError):
                pass

        formatted = {
            "symbol": symbol_data.get("symbol"),
            "price": _safe_float(symbol_data.get("price")),
            "vrp_structural": _safe_float(symbol_data.get("vrp_structural")),
            "vrp_tactical": _safe_float(symbol_data.get("vrp_tactical")),
            "iv_percentile": _safe_float(symbol_data.get("iv_percentile")),
            "vtr": vtr,  # Can be None if data missing
            "score": _safe_float(symbol_data.get("score")),
            "sector": symbol_data.get("sector"),
            "asset_class": symbol_data.get("asset_class"),
            "filter_results": symbol_data.get("filter_results", {}),
        }
        formatted_scanned.append(formatted)

    return {
        "candidates": display_candidates,
        "scanned_symbols": formatted_scanned,
        "summary": summary,
        "meta": meta,
    }
