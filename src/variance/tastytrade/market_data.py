"""
Market Data Fetching for Tastytrade API.

This module provides:
- Market metrics fetching (IV, HV, liquidity)
- Market data fetching (prices, OHLC)
- Option quotes fetching
- Caching and batching support
"""

import logging
import time
from typing import Any, Optional, TypeVar

from ..market_data.cache import MarketCache
from ..market_data.helpers import get_dynamic_ttl, make_cache_key
from .auth import (
    TastytradeCredentials,
    TastytradeMetrics,
    TokenManager,
    _normalize_hv,
    _safe_float,
    _safe_int,
)

logger = logging.getLogger(__name__)


class MarketDataFetcher:
    """
    Fetch market data and metrics from Tastytrade API.

    Handles:
    - Market metrics (IV, HV, liquidity, correlation)
    - Market data (current prices, OHLC)
    - Option quotes (bid/ask/mark)
    - Caching with dynamic TTL
    """

    def __init__(
        self, token_manager: TokenManager, credentials: TastytradeCredentials, cache: MarketCache
    ):
        """
        Initialize market data fetcher.

        Args:
            token_manager: Token manager for authentication
            credentials: OAuth credentials
            cache: Market data cache instance
        """
        self._token_manager = token_manager
        self._credentials = credentials
        self._cache = cache

    def get_market_metrics(self, symbols: list[str]) -> dict[str, TastytradeMetrics]:
        """
        Fetch market metrics for a list of symbols from Tastytrade API.

        This method:
        1. Checks cache for each symbol first
        2. Partitions symbols into cached vs uncached
        3. Fetches only uncached symbols from API
        4. Merges cached + fresh results
        5. Caches fresh results with dynamic TTL (15min market / 8hr after-hours)

        Args:
            symbols: List of ticker symbols (e.g., ['AAPL', 'SPY', 'QQQ'])

        Returns:
            Dictionary mapping symbols to their metrics.
            Symbols with errors will have empty/partial data.

        Raises:
            TastytradeAuthError: If authentication fails
            requests.exceptions.RequestException: If API request fails

        Example:
            >>> fetcher = MarketDataFetcher(token_manager, credentials, cache)
            >>> metrics = fetcher.get_market_metrics(['AAPL', 'SPY'])
            >>> print(metrics['AAPL']['iv'])
            35.4  # Already converted to percent
        """
        if not symbols:
            return {}

        start_time = time.time()

        # Check cache and partition symbols
        cached_results: dict[str, TastytradeMetrics] = {}
        uncached_symbols: list[str] = []

        for symbol in symbols:
            cache_key = make_cache_key("market_metrics", symbol)
            cached = self._cache.get(cache_key)
            if cached:
                cached_results[symbol] = cached
            else:
                uncached_symbols.append(symbol)

        # If all symbols are cached, return early
        if not uncached_symbols:
            logger.debug("Cache hit: all %s symbols cached", len(symbols))
            return cached_results

        logger.debug(
            "Cache partial: %s cached, %s uncached of %s total",
            len(cached_results),
            len(uncached_symbols),
            len(symbols),
        )

        # Fetch uncached symbols from API
        token = self._token_manager.ensure_valid_token()

        symbols_str = ",".join(uncached_symbols)
        url = f"{self._credentials.api_base_url}/market-metrics"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        params = {"symbols": symbols_str}

        # Fetch data from API
        data = self._token_manager.fetch_api_data(url, headers, params)
        if not data:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.warning(
                "API /market-metrics returned no data in %.0fms",
                elapsed_ms,
            )
            return cached_results  # Return whatever we have cached

        # Extract items from response
        items = data.get("data", {}).get("items", []) if isinstance(data, dict) else []
        if not items and isinstance(data, list):
            items = data

        # Parse each item and cache it
        fresh_results: dict[str, TastytradeMetrics] = {}
        ttl = get_dynamic_ttl("market_metrics", 900)

        for item in items:
            metrics = self._parse_metric_item(item)
            if metrics and "symbol" in metrics:
                symbol = metrics["symbol"]
                fresh_results[symbol] = metrics

                # Cache the result
                cache_key = make_cache_key("market_metrics", symbol)
                self._cache.set(cache_key, metrics, ttl_seconds=ttl)

        # Merge cached and fresh results
        all_results = {**cached_results, **fresh_results}

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            "API /market-metrics completed: %s total (%s cached, %s fetched) in %.0fms",
            len(symbols),
            len(cached_results),
            len(fresh_results),
            elapsed_ms,
        )
        return all_results

    def get_market_data(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        """
        Fetch current market data (prices) from Tastytrade /market-data/by-type endpoint.

        Provides:
        - Current prices (bid, ask, last, mark)
        - Today's OHLC
        - Previous close
        - Beta
        - Dividend info
        - Trading status

        Args:
            symbols: List of ticker symbols (e.g., ['AAPL', 'SPY', 'QQQ'])

        Returns:
            Dictionary mapping symbols to their market data.

        Example:
            >>> fetcher = MarketDataFetcher(token_manager, credentials, cache)
            >>> data = fetcher.get_market_data(['AAPL'])
            >>> print(data['AAPL']['last'])  # Last traded price
            271.84
        """
        if not symbols:
            return {}

        start_time = time.time()
        logger.debug("API call: /market-data/by-type symbols=%s", len(symbols))

        token = self._token_manager.ensure_valid_token()

        # Build request (market-data/by-type uses array parameters)
        url = f"{self._credentials.api_base_url}/market-data/by-type"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        T = TypeVar("T")

        def chunked(items: list[T], size: int) -> list[list[T]]:
            return [items[i : i + size] for i in range(0, len(items), size)]

        # Split symbols by type for the API (assumes equities for now)
        # TODO: Handle options, indices, crypto, etc.
        normalized_symbols = [str(s).upper() for s in symbols if s]
        unique_symbols = list(dict.fromkeys(normalized_symbols))
        typed_symbols = [("future" if s.startswith("/") else "equity", s) for s in unique_symbols]

        results: dict[str, dict[str, Any]] = {}
        for batch in chunked(typed_symbols, 100):
            params: dict[str, list[str]] = {}
            for symbol_type, sym in batch:
                params.setdefault(symbol_type, []).append(sym)

            # Fetch data from API (limit: 100 combined symbols)
            data = self._token_manager.fetch_api_data(url, headers, params)
            if not data:
                continue

            # Extract items from response
            items = data.get("data", {}).get("items", []) if isinstance(data, dict) else []
            if not items and isinstance(data, list):
                items = data

            # Parse each item
            for item in items:
                symbol = item.get("symbol", "").upper()
                if not symbol:
                    continue

                # Extract relevant price data
                results[symbol] = {
                    "symbol": symbol,
                    "price": _safe_float(item.get("last")) or _safe_float(item.get("mark")),
                    "bid": _safe_float(item.get("bid")),
                    "ask": _safe_float(item.get("ask")),
                    "last": _safe_float(item.get("last")),
                    "mark": _safe_float(item.get("mark")),
                    "mid": _safe_float(item.get("mid")),
                    "open": _safe_float(item.get("open")),
                    "high": _safe_float(item.get("dayHighPrice")),
                    "low": _safe_float(item.get("dayLowPrice")),
                    "close": _safe_float(item.get("close")),
                    "prev_close": _safe_float(item.get("prevClose")),
                    "volume": _safe_float(item.get("volume")),
                    "beta": _safe_float(item.get("beta")),
                    "updated_at": item.get("updatedAt"),
                }

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            "API /market-data/by-type completed: %s symbols in %.0fms",
            len(unique_symbols),
            elapsed_ms,
        )
        return results

    def get_option_quotes(
        self, equity_options: list[str], future_options: Optional[list[str]] = None
    ) -> dict[str, dict[str, Any]]:
        """
        Fetch quotes for specific option symbols.

        Uses /market-data/by-type with equity-option[] or future-option[] params.

        Args:
            equity_options: List of equity option OCC symbols
            future_options: List of futures option symbols

        Returns:
            Dictionary mapping option symbol to quote data (bid/ask/mark).
        """
        if not equity_options and not future_options:
            return {}

        start_time = time.time()
        total = len(equity_options) + len(future_options or [])
        logger.debug("API call: /market-data/by-type options=%s", total)
        token = self._token_manager.ensure_valid_token()
        url = f"{self._credentials.api_base_url}/market-data/by-type"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        T = TypeVar("T")

        def chunked(items: list[T], size: int) -> list[list[T]]:
            return [items[i : i + size] for i in range(0, len(items), size)]

        equity_options = [str(s) for s in equity_options if s]
        future_options = [str(s) for s in (future_options or []) if s]

        results: dict[str, dict[str, Any]] = {}
        combined = [("equity-option", s) for s in equity_options] + [
            ("future-option", s) for s in future_options
        ]

        for batch in chunked(combined, 100):
            params: dict[str, list[str]] = {}
            for symbol_type, sym in batch:
                params.setdefault(symbol_type, []).append(sym)

            data = self._token_manager.fetch_api_data(url, headers, params)
            if not data:
                continue

            items = data.get("data", {}).get("items", []) if isinstance(data, dict) else []
            if not items and isinstance(data, list):
                items = data

            for item in items:
                symbol = str(item.get("symbol", "")).strip()
                if not symbol:
                    continue
                results[symbol] = {
                    "symbol": symbol,
                    "bid": _safe_float(item.get("bid")),
                    "ask": _safe_float(item.get("ask")),
                    "mid": _safe_float(item.get("mid")),
                    "mark": _safe_float(item.get("mark")),
                    "last": _safe_float(item.get("last")),
                    "updated_at": item.get("updatedAt") or item.get("updated-at"),
                }

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            "API /market-data/by-type options completed: %s symbols in %.0fms",
            total,
            elapsed_ms,
        )
        return results

    def _parse_metric_item(self, item: Any) -> Optional[TastytradeMetrics]:
        """
        Parse a single market metrics item from Tastytrade API response.

        Args:
            item: Raw metric item from API response

        Returns:
            TastytradeMetrics if symbol is valid, None otherwise
        """
        symbol = item.get("symbol", "").upper()
        if not symbol:
            return None
        metrics: TastytradeMetrics = {"symbol": symbol}

        hv30_val = _normalize_hv(_safe_float(item.get("historical-volatility-30-day")))
        if hv30_val is not None:
            metrics["hv30"] = hv30_val

        hv90_val = _normalize_hv(_safe_float(item.get("historical-volatility-90-day")))
        if hv90_val is not None:
            metrics["hv90"] = hv90_val

        iv_val = self._parse_iv(item.get("implied-volatility-index"), hv30_val, hv90_val)
        if iv_val is not None:
            metrics["iv"] = iv_val

        iv_rank = _safe_float(item.get("implied-volatility-index-rank"))
        if iv_rank is not None:
            metrics["iv_rank"] = iv_rank

        iv_percentile = self._parse_iv_percentile(item.get("implied-volatility-percentile"))
        if iv_percentile is not None:
            metrics["iv_percentile"] = iv_percentile

        liquidity_rating = _safe_int(item.get("liquidity-rating"))
        if liquidity_rating is not None:
            metrics["liquidity_rating"] = liquidity_rating

        liquidity_value = _safe_float(item.get("liquidity-value"))
        if liquidity_value is not None:
            metrics["liquidity_value"] = liquidity_value

        option_volume = _safe_float(item.get("option-volume"))
        if option_volume is not None:
            metrics["option_volume"] = option_volume

        corr_spy = _safe_float(item.get("corr-spy-3month"))
        if corr_spy is not None:
            metrics["corr_spy_3month"] = corr_spy

        beta = _safe_float(item.get("beta"))
        if beta is not None:
            metrics["beta"] = beta

        # Earnings
        earnings = item.get("earnings", {})
        if isinstance(earnings, dict):
            earnings_date = earnings.get("expected-report-date")
            if earnings_date:
                metrics["earnings_date"] = str(earnings_date)

        # Metadata
        updated_at = item.get("updated-at")
        if updated_at:
            metrics["updated_at"] = str(updated_at)

        return metrics

    @staticmethod
    def _parse_iv(
        raw_iv: Any, hv30_val: Optional[float], hv90_val: Optional[float]
    ) -> Optional[float]:
        """
        Parse and normalize implied volatility from API response.

        Uses HV values as anchor to determine if IV is in decimal or percent format.

        Args:
            raw_iv: Raw IV value from API
            hv30_val: 30-day HV (percent)
            hv90_val: 90-day HV (percent)

        Returns:
            IV normalized to percent (0-100 scale)
        """
        val = _safe_float(raw_iv)
        if val is None or val <= 0:
            return None

        anchor_vol = hv30_val if hv30_val else hv90_val
        if val < 1.0:
            return val * 100.0
        if anchor_vol and anchor_vol > 0:
            diff_unscaled = abs(val - anchor_vol)
            diff_scaled = abs((val * 100.0) - anchor_vol)
            return val * 100.0 if diff_scaled < diff_unscaled else val
        if val < 5.0:
            return val * 100.0
        return val

    @staticmethod
    def _parse_iv_percentile(raw_val: Any) -> Optional[float]:
        """
        Parse and normalize IV percentile from API response.

        Args:
            raw_val: Raw IV percentile value from API

        Returns:
            IV percentile normalized to 0-100 scale
        """
        val = _safe_float(raw_val)
        if val is None:
            return None
        return val * 100.0 if val <= 1.0 else val
