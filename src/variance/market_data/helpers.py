from collections.abc import MutableMapping
from typing import Any, Optional, cast

from ..variance_logger import logger
from .cache import MarketCache
from .clock import is_market_open
from .settings import AFTER_HOURS_TTL, TTL


def get_dynamic_ttl(data_type: str, default: int) -> int:
    """
    Returns appropriate TTL based on market hours.

    During market hours: Uses DEFAULT_TTL values (shorter TTLs for fresh data).
    After hours: Uses AFTER_HOURS_TTL values (extended TTLs since data is static).

    Args:
        data_type: Type of data being cached (e.g., "iv", "market_data", "option_chain")
        default: Fallback TTL if data_type not found in configuration

    Returns:
        TTL in seconds appropriate for current market state
    """
    if is_market_open():
        return int(TTL.get(data_type, default))
    else:
        return int(AFTER_HOURS_TTL.get(data_type, TTL.get(data_type, default)))


def make_cache_key(prefix: str, symbol: str) -> str:
    return f"{prefix}_{symbol}"


def market_data_cache_keys(symbol: str) -> tuple[str, str]:
    return make_cache_key("market_data", symbol), make_cache_key("md", symbol)


def _get_cached_market_data(
    local_cache: MarketCache, raw_symbol: str, *, allow_expired: bool
) -> Optional[dict[str, Any]]:
    keys = market_data_cache_keys(raw_symbol)
    for key in keys:
        cached = local_cache.get_any(key) if allow_expired else local_cache.get(key)
        if cached:
            return cast(dict[str, Any], cached)
    return None


def _fallback_to_cached_market_data(
    local_cache: MarketCache,
    raw_symbol: str,
    *,
    warning: str,
    provider: str,
    reason: str,
) -> Optional[dict[str, Any]]:
    cached_fallback = _get_cached_market_data(local_cache, raw_symbol, allow_expired=True)
    if cached_fallback:
        cached_fallback["is_stale"] = True
        apply_warning(
            cached_fallback,
            warning,
            provider=provider,
            reason=reason,
            cached=True,
        )
        cached_fallback.setdefault("data_source", provider)
        _log_provider_fallback(provider, raw_symbol, cached=True, reason=reason)
        return cached_fallback
    return None


def _apply_provider_fallback(
    data: MutableMapping[str, Any],
    *,
    symbol: str,
    warning: str,
    provider: str,
    reason: str,
    cached: bool,
) -> MutableMapping[str, Any]:
    apply_warning(
        data,
        warning,
        provider=provider,
        reason=reason,
        cached=cached,
    )
    data["data_source"] = provider
    _log_provider_fallback(provider, symbol, cached=cached, reason=reason)
    return data


def apply_warning(
    data: MutableMapping[str, Any],
    code: str,
    *,
    message: Optional[str] = None,
    severity: str = "warning",
    provider: Optional[str] = None,
    reason: Optional[str] = None,
    cached: Optional[bool] = None,
) -> None:
    data["warning"] = code
    detail: dict[str, Any] = {"code": code, "severity": severity}
    if message:
        detail["message"] = message
    if provider:
        detail["provider"] = provider
    if reason:
        detail["reason"] = reason
    if cached is not None:
        detail["cached"] = cached
    data["warning_detail"] = detail
    if message:
        data["warning_message"] = message


def _log_provider_fallback(provider: str, symbol: str, *, cached: bool, reason: str) -> None:
    logger.warning(
        "provider_fallback provider=%s symbol=%s cached=%s reason=%s",
        provider,
        symbol,
        cached,
        reason,
    )


__all__ = [
    "get_dynamic_ttl",
    "make_cache_key",
    "market_data_cache_keys",
    "_get_cached_market_data",
    "_fallback_to_cached_market_data",
    "_apply_provider_fallback",
    "apply_warning",
    "_log_provider_fallback",
]
