from collections.abc import Callable
from typing import Any, Optional

from ..config_loader import load_runtime_config
from ..interfaces import MarketData
from ..tastytrade_client import TastytradeAuthError
from .cache import MarketCache
from .cache import cache as default_cache
from .providers import TastytradeProvider, YFinanceProvider


class MarketDataFactory:
    @staticmethod
    def get_provider(provider_type: str = "tastytrade") -> YFinanceProvider | TastytradeProvider:
        provider_lower = provider_type.lower()

        if provider_lower == "tastytrade":
            try:
                return TastytradeProvider()
            except TastytradeAuthError:
                return YFinanceProvider()

        if provider_lower == "yfinance":
            return YFinanceProvider()

        raise ValueError(f"Unknown provider type: {provider_type}")


class MarketDataService:
    def __init__(
        self,
        cache: Optional[MarketCache] = None,
        *,
        ticker_factory: Optional[Callable[..., Any]] = None,
        market_open_fn: Optional[Callable[[], bool]] = None,
    ):
        self._cache: MarketCache = cache if cache else default_cache
        allow_after_hours_fetch = cache is not None

        try:
            runtime_config = load_runtime_config()
            tt_config = runtime_config.get("tastytrade", {})
            use_tastytrade = tt_config.get("enabled", False)
        except Exception:
            use_tastytrade = False

        self.provider: TastytradeProvider | YFinanceProvider
        if use_tastytrade:
            self.provider = TastytradeProvider(
                cache_instance=self.cache,
                allow_after_hours_fetch=allow_after_hours_fetch,
                ticker_factory=ticker_factory,
                market_open_fn=market_open_fn,
            )
        else:
            self.provider = YFinanceProvider(
                cache_instance=self.cache,
                allow_after_hours_fetch=allow_after_hours_fetch,
                ticker_factory=ticker_factory,
                market_open_fn=market_open_fn,
            )

    @property
    def cache(self) -> MarketCache:
        return self._cache

    def get_market_data(self, symbols: list[str]) -> dict[str, MarketData]:
        return self.provider.get_market_data(symbols)


_default_service: Optional[MarketDataService] = None


def _get_default_service() -> MarketDataService:
    global _default_service
    if not _default_service:
        _default_service = MarketDataService()
    return _default_service


def get_market_data(
    symbols: list[str], _service: Optional[MarketDataService] = None
) -> dict[str, MarketData]:
    service = _service or _get_default_service()
    return service.get_market_data(symbols)


def _reset_default_service() -> None:
    global _default_service
    _default_service = None


__all__ = [
    "MarketDataFactory",
    "MarketDataService",
    "get_market_data",
    "_reset_default_service",
]
