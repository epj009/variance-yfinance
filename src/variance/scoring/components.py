"""Variance Score Components - Individual scoring functions."""

from typing import Any, Optional


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Convert value to float safely."""
    try:
        if val is None:
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


def _neutral_score() -> float:
    """Return neutral score value."""
    return 50.0


def _normalize_score(value: Optional[float], floor: float, ceiling: float) -> float:
    """Normalize a value to 0-100 scale."""
    if value is None or ceiling <= floor:
        return 0.0
    raw = (value - floor) / (ceiling - floor) * 100.0
    return max(0.0, min(100.0, raw))


def _variance_component(bias: float, rules: dict[str, Any]) -> float:
    """Calculate variance component from bias."""
    if bias == -1.0:
        return 0.0
    multiplier = _safe_float(rules.get("variance_score_dislocation_multiplier", 200))
    dislocation = abs(bias - 1.0) * multiplier
    return max(0.0, min(100.0, dislocation))


def _compute_yield(metrics: dict[str, Any]) -> Optional[float]:
    """Calculate estimated premium yield."""
    price_raw = metrics.get("price")
    if price_raw is None:
        return None
    try:
        price = float(price_raw)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None

    call_bid = metrics.get("call_bid")
    call_ask = metrics.get("call_ask")
    put_bid = metrics.get("put_bid")
    put_ask = metrics.get("put_ask")

    if all(v is None for v in [call_bid, call_ask, put_bid, put_ask]):
        bid = _safe_float(metrics.get("atm_bid"), 0.0)
        ask = _safe_float(metrics.get("atm_ask"), 0.0)
    else:
        bid = _safe_float(call_bid, 0.0) + _safe_float(put_bid, 0.0)
        ask = _safe_float(call_ask, 0.0) + _safe_float(put_ask, 0.0)

    mid = (bid + ask) / 2
    if mid <= 0:
        return None

    bpr_est = price * 0.20
    if bpr_est <= 0:
        return None

    return (mid / bpr_est) * (30.0 / 45.0) * 100.0


def _max_leg_slippage(metrics: dict[str, Any]) -> tuple[bool, float]:
    """Calculate maximum slippage across call/put legs."""
    call_bid = metrics.get("call_bid")
    call_ask = metrics.get("call_ask")
    put_bid = metrics.get("put_bid")
    put_ask = metrics.get("put_ask")

    max_found = 0.0
    has_quote = False
    for bid, ask in [(call_bid, call_ask), (put_bid, put_ask)]:
        if bid is not None and ask is not None:
            try:
                f_bid = float(bid)
                f_ask = float(ask)
            except (TypeError, ValueError):
                continue
            mid = (f_bid + f_ask) / 2
            if mid > 0:
                has_quote = True
                max_found = max(max_found, (f_ask - f_bid) / mid)
    return has_quote, max_found


def score_volatility_momentum(metrics: dict[str, Any], rules: dict[str, Any]) -> float:
    """Score based on HV30/HV90 ratio (volatility momentum)."""
    hv30 = metrics.get("hv30")
    hv90 = metrics.get("hv90")
    if hv30 is None or hv90 is None:
        return _neutral_score()
    try:
        hv90_f = float(hv90)
        if hv90_f <= 0:
            return _neutral_score()
        ratio = float(hv30) / hv90_f
    except (TypeError, ValueError, ZeroDivisionError):
        return _neutral_score()

    floor = _safe_float(rules.get("volatility_momentum_min_ratio", 0.85), 0.85)
    ceiling = _safe_float(rules.get("variance_score_momentum_ceiling", 1.20), 1.20)
    return _normalize_score(ratio, floor, ceiling)


def score_hv_rank(metrics: dict[str, Any], rules: dict[str, Any]) -> float:
    """Score based on HV rank for rich VRP positions."""
    vrp_structural = _safe_float(metrics.get("vrp_structural"), -1.0)
    rich_threshold = _safe_float(rules.get("vrp_structural_rich_threshold", 1.30), 1.30)
    if vrp_structural <= rich_threshold:
        return _neutral_score()

    hv_rank = metrics.get("hv_rank")
    if hv_rank is None:
        return _neutral_score()
    try:
        hv_rank_f = float(hv_rank)
    except (TypeError, ValueError):
        return _neutral_score()

    floor = _safe_float(rules.get("hv_rank_trap_threshold", 15.0), 15.0)
    ceiling = _safe_float(rules.get("variance_score_hv_rank_ceiling", 100.0), 100.0)
    return _normalize_score(hv_rank_f, floor, ceiling)


def score_iv_percentile(
    metrics: dict[str, Any], rules: dict[str, Any], config: Optional[Any]
) -> float:
    """Score based on IV percentile."""
    min_ivp = rules.get("min_iv_percentile", 0.0)
    if config is not None and getattr(config, "min_iv_percentile", None) is not None:
        min_ivp = config.min_iv_percentile

    try:
        min_ivp_f = float(min_ivp)
    except (TypeError, ValueError):
        min_ivp_f = 0.0

    if min_ivp_f <= 0:
        return _neutral_score()

    ivp = metrics.get("iv_percentile")
    if ivp is None:
        return 0.0
    try:
        ivp_f = float(ivp)
    except (TypeError, ValueError):
        return 0.0

    ceiling = _safe_float(rules.get("variance_score_iv_percentile_ceiling", 100.0), 100.0)
    return _normalize_score(ivp_f, min_ivp_f, ceiling)


def score_yield(metrics: dict[str, Any], rules: dict[str, Any]) -> float:
    """Score based on estimated premium yield."""
    min_yield = _safe_float(rules.get("min_yield_percent", 0.0), 0.0)
    if min_yield <= 0:
        return _neutral_score()

    yield_pct = _compute_yield(metrics)
    if yield_pct is None:
        return 0.0

    ceiling = _safe_float(rules.get("variance_score_yield_ceiling", 15.0), 15.0)
    return _normalize_score(yield_pct, min_yield, ceiling)


def score_retail_efficiency(
    metrics: dict[str, Any], rules: dict[str, Any], config: Optional[Any]
) -> float:
    """Score based on price and slippage for retail traders."""
    symbol = str(metrics.get("symbol", ""))
    if symbol.startswith("/"):
        return _neutral_score()

    min_price = rules.get("retail_min_price", 25.0)
    if config is not None and getattr(config, "retail_min_price", None) is not None:
        min_price = config.retail_min_price
    min_price_f = _safe_float(min_price, 25.0)

    price = metrics.get("price")
    price_f = _safe_float(price, 0.0)
    price_ceiling = _safe_float(rules.get("variance_score_retail_price_ceiling", 100.0), 100.0)
    price_score = _normalize_score(price_f, min_price_f, price_ceiling)

    max_slippage = _safe_float(rules.get("retail_max_slippage", 0.05), 0.05)
    has_quote, slip = _max_leg_slippage(metrics)
    if not has_quote:
        slippage_score = _neutral_score()
    elif max_slippage <= 0:
        slippage_score = 0.0
    else:
        slippage_score = max(0.0, min(100.0, (max_slippage - slip) / max_slippage * 100.0))

    return (price_score + slippage_score) / 2


def score_liquidity(metrics: dict[str, Any], rules: dict[str, Any], config: Optional[Any]) -> float:
    """Score based on liquidity metrics (TT rating, volume, slippage)."""
    if config is not None and getattr(config, "allow_illiquid", False):
        return _neutral_score()

    tt_rating = metrics.get("liquidity_rating")
    min_rating = _safe_float(rules.get("min_tt_liquidity_rating", 4), 4.0)
    if tt_rating is not None:
        rating_f = _safe_float(tt_rating, 0.0)
        return _normalize_score(rating_f, min_rating, 5.0)

    max_slippage = _safe_float(rules.get("max_slippage_pct", 0.05), 0.05)
    has_quote, slip = _max_leg_slippage(metrics)
    if not has_quote:
        slippage_score = _neutral_score()
    elif max_slippage <= 0:
        slippage_score = 0.0
    else:
        slippage_score = max(0.0, min(100.0, (max_slippage - slip) / max_slippage * 100.0))

    vol_raw = metrics.get("option_volume", metrics.get("atm_volume"))
    if vol_raw is None:
        volume_score = _neutral_score()
    else:
        vol = _safe_float(vol_raw, 0.0)
        min_vol = _safe_float(rules.get("min_atm_volume", 500), 500.0)
        mult = _safe_float(rules.get("variance_score_volume_ceiling_multiplier", 5.0), 5.0)
        ceiling = min_vol * mult if min_vol > 0 else 0.0
        if ceiling <= min_vol:
            volume_score = _normalize_score(vol, min_vol, min_vol + 1.0)
        else:
            volume_score = _normalize_score(vol, min_vol, ceiling)

    return (slippage_score + volume_score) / 2
