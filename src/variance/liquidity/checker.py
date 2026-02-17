"""Liquidity Checker - Determines if a symbol meets liquidity requirements."""

from typing import Any, Optional


def _is_futures_symbol(symbol: str) -> bool:
    """Check if symbol is a futures contract."""
    return symbol.startswith("/")


def _has_tastytrade_liquidity(metrics: dict[str, Any]) -> bool:
    """Check if Tastytrade liquidity data is available."""
    return metrics.get("option_volume") is not None or metrics.get("liquidity_rating") is not None


def _fails_tt_liquidity_rating(metrics: dict[str, Any], rules: dict[str, Any]) -> bool:
    """Check if symbol fails Tastytrade liquidity rating threshold."""
    tt_rating = metrics.get("liquidity_rating")
    if tt_rating is None:
        return False
    try:
        min_rating = int(rules.get("min_tt_liquidity_rating", 4))
        return int(tt_rating) < min_rating
    except (TypeError, ValueError):
        return False


def _check_implied_liquidity(metrics: dict[str, Any], rules: dict[str, Any]) -> tuple[bool, bool]:
    """Check if symbol passes implied liquidity via tight bid/ask spreads."""
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


def _get_activity_volume(metrics: dict[str, Any]) -> Any:
    """Get activity volume from metrics (prefer option_volume, fallback to atm_volume)."""
    return metrics.get("option_volume", metrics.get("atm_volume"))


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Convert value to float safely."""
    try:
        if val is None:
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


def _fails_activity_gate(metrics: dict[str, Any], rules: dict[str, Any]) -> bool:
    """Check if symbol fails minimum activity (volume or open interest) gate."""
    mode = rules.get("liquidity_mode", "volume")
    min_atm_volume = int(rules.get("min_atm_volume", 0))
    min_atm_open_interest = int(rules.get("min_atm_open_interest", 500))
    if mode == "open_interest":
        atm_oi_val = _safe_float(
            metrics.get("atm_open_interest", metrics.get("atm_oi")), default=-1.0
        )
        if atm_oi_val < 0:
            atm_volume_val = _safe_float(_get_activity_volume(metrics), default=-1.0)
            return atm_volume_val >= 0 and atm_volume_val < min_atm_volume
        return atm_oi_val < min_atm_open_interest

    atm_volume_val = _safe_float(_get_activity_volume(metrics), default=-1.0)
    return atm_volume_val >= 0 and atm_volume_val < min_atm_volume


def is_illiquid(
    symbol: str,
    metrics: dict[str, Any],
    rules: dict[str, Any],
    profile_min_rating: Optional[int] = None,
) -> tuple[bool, bool]:
    """
    Checks if a symbol fails the liquidity rules.
    Returns: (is_illiquid, is_implied_pass)

    Args:
        symbol: The symbol to check
        metrics: Market data metrics for the symbol
        rules: Trading rules from config
        profile_min_rating: Optional profile-level override for min TT liquidity rating
    """
    if _is_futures_symbol(symbol) and not _has_tastytrade_liquidity(metrics):
        return False, False

    # Check Tastytrade rating first (most reliable)
    tt_rating = metrics.get("liquidity_rating")
    if tt_rating is not None:
        # Use profile override if present, otherwise fall back to rules
        min_rating = (
            profile_min_rating
            if profile_min_rating is not None
            else int(rules.get("min_tt_liquidity_rating", 4))
        )
        if int(tt_rating) >= min_rating:
            # Trust Tastytrade rating - skip OI/volume checks
            return False, False
        else:
            # TT rating below threshold
            return True, False

    # No TT rating - use bid/ask and activity checks
    implied_pass, is_implied = _check_implied_liquidity(metrics, rules)
    if implied_pass:
        return False, is_implied

    if _fails_activity_gate(metrics, rules):
        return True, False

    return False, False
