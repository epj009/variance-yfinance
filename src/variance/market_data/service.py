import warnings
from collections.abc import Callable
from typing import Optional

from ..interfaces import IMarketDataProvider, MarketData
from .cache import MarketCache
from .cache import cache as default_cache
from .pure_tastytrade_provider import PureTastytradeProvider


class MarketDataFactory:
    @staticmethod
    def get_provider(
        provider_type: str = "tastytrade",
    ) -> IMarketDataProvider:
        provider_lower = provider_type.lower()

        if provider_lower == "tastytrade":
            return PureTastytradeProvider()

        raise ValueError(f"Unknown provider type: {provider_type}")


class MarketDataService:
    def __init__(
        self,
        cache: Optional[MarketCache] = None,
        *,
        market_open_fn: Optional[Callable[[], bool]] = None,
    ):
        self._cache: MarketCache = cache if cache else default_cache
        allow_after_hours_fetch = cache is not None

        # Use pure Tastytrade provider (REST + DXLink)
        self.provider = PureTastytradeProvider(
            cache_instance=self.cache,
            allow_after_hours_fetch=allow_after_hours_fetch,
            market_open_fn=market_open_fn,
        )

    @property
    def cache(self) -> MarketCache:
        return self._cache

    def get_market_data(
        self,
        symbols: list[str],
        *,
        include_returns: bool = False,
        include_option_quotes: bool = False,
    ) -> dict[str, MarketData]:
        return self.provider.get_market_data(
            symbols,
            include_returns=include_returns,
            include_option_quotes=include_option_quotes,
        )


_default_service: Optional[MarketDataService] = None


def _get_default_service() -> MarketDataService:
    """
    DEPRECATED: Returns module-level singleton instance.

    This function uses global mutable state and can cause test pollution.
    Prefer explicit dependency injection by creating MarketDataService directly.

    Example:
        service = MarketDataService()  # Good - explicit
        data = service.get_market_data(symbols)

    Returns:
        MarketDataService singleton instance
    """
    warnings.warn(
        "_get_default_service() is deprecated. "
        "Create MarketDataService explicitly to avoid test pollution.",
        DeprecationWarning,
        stacklevel=2,
    )
    global _default_service
    if not _default_service:
        _default_service = MarketDataService()
    return _default_service


def get_market_data(
    symbols: list[str],
    _service: Optional[MarketDataService] = None,
    *,
    include_returns: bool = False,
    include_option_quotes: bool = False,
) -> dict[str, MarketData]:
    service = _service or _get_default_service()
    return service.get_market_data(
        symbols,
        include_returns=include_returns,
        include_option_quotes=include_option_quotes,
    )


def _reset_default_service() -> None:
    global _default_service
    _default_service = None


__all__ = [
    "MarketDataFactory",
    "MarketDataService",
    "get_market_data",
    "_reset_default_service",
]
