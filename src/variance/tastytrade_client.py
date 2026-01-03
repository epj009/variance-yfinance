"""
Tastytrade OAuth API Client for Market Metrics.

This module provides a client for accessing Tastytrade's /market-metrics endpoint
using OAuth 2.0 authentication. It handles token refresh, IV scaling, and error handling.
"""

import asyncio
import logging
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Optional, TypedDict, TypeVar
from urllib.parse import quote

try:
    import requests
except ModuleNotFoundError:
    raise ImportError("Missing dependency 'requests'. Install with: pip install requests") from None

try:
    import httpx
except ModuleNotFoundError:
    raise ImportError("Missing dependency 'httpx'. Install with: pip install httpx") from None

if TYPE_CHECKING:
    from .symbol_resolution.futures_resolver import FuturesSymbolResolver

from .market_data.cache import MarketCache
from .market_data.helpers import get_dynamic_ttl, make_cache_key

logger = logging.getLogger(__name__)


class TastytradeAuthError(Exception):
    """Raised when OAuth authentication fails or credentials are missing."""

    pass


@dataclass(frozen=True)
class TastytradeCredentials:
    """OAuth credentials for Tastytrade API."""

    client_id: str
    client_secret: str
    refresh_token: str
    api_base_url: str = "https://api.tastytrade.com"

    @classmethod
    def from_environment(cls) -> "TastytradeCredentials":
        """
        Load credentials from environment variables.

        Environment Variables:
            TT_CLIENT_ID: OAuth client ID
            TT_CLIENT_SECRET: OAuth client secret
            TT_REFRESH_TOKEN: OAuth refresh token (long-lived)
            API_BASE_URL: Tastytrade API base URL (optional)

        Returns:
            TastytradeCredentials instance

        Raises:
            TastytradeAuthError: If required environment variables are missing
        """
        client_id = os.getenv("TT_CLIENT_ID")
        client_secret = os.getenv("TT_CLIENT_SECRET")
        refresh_token = os.getenv("TT_REFRESH_TOKEN")

        missing_vars = []
        if not client_id:
            missing_vars.append("TT_CLIENT_ID")
        if not client_secret:
            missing_vars.append("TT_CLIENT_SECRET")
        if not refresh_token:
            missing_vars.append("TT_REFRESH_TOKEN")

        if missing_vars:
            raise TastytradeAuthError(
                f"Missing required environment variables: {', '.join(missing_vars)}"
            )

        # mypy: After error check, these are guaranteed to be str
        assert client_id is not None
        assert client_secret is not None
        assert refresh_token is not None

        api_base_url = os.getenv("API_BASE_URL", "https://api.tastytrade.com")
        if not api_base_url.startswith("http"):
            api_base_url = f"https://{api_base_url}"

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
            api_base_url=api_base_url,
        )


class TastytradeMetrics(TypedDict, total=False):
    """
    Tastytrade market metrics response structure.

    Fields are mapped from Tastytrade API response to Variance internal format.
    """

    # Core volatility metrics
    iv: Optional[float]  # Implied volatility (converted to percent)
    iv_rank: Optional[float]  # IV rank (0-100)
    iv_percentile: Optional[float]  # IV percentile (0-100)
    hv30: Optional[float]  # 30-day historical volatility (percent)
    hv90: Optional[float]  # 90-day historical volatility (percent)

    # Liquidity metrics
    liquidity_rating: Optional[int]  # Liquidity rating (0-5)
    liquidity_value: Optional[float]  # Liquidity value score
    option_volume: Optional[float]  # 30-day average option volume

    # Correlation
    corr_spy_3month: Optional[float]  # 3-month correlation with SPY

    # Greeks (optional)
    beta: Optional[float]  # Beta vs market

    # Earnings
    earnings_date: Optional[str]  # Expected earnings report date (YYYY-MM-DD)

    # Metadata
    symbol: str  # Ticker symbol
    updated_at: Optional[str]  # Timestamp of last update


class TastytradeClient:
    """
    OAuth-authenticated client for Tastytrade market metrics API.

    This client handles:
    - OAuth token refresh using client credentials + refresh token
    - IV scaling from decimal (0.35) to percent (35.0)
    - Rate limiting and error handling
    - Batch symbol queries

    Environment Variables:
        TT_CLIENT_ID: OAuth client ID
        TT_CLIENT_SECRET: OAuth client secret
        TT_REFRESH_TOKEN: OAuth refresh token (long-lived)
        API_BASE_URL: Tastytrade API base URL (e.g., https://api.tastytrade.com)

    Raises:
        TastytradeAuthError: If credentials are missing or authentication fails
    """

    def __init__(self, credentials: Optional[TastytradeCredentials] = None) -> None:
        """
        Initialize the Tastytrade client.

        Args:
            credentials: OAuth credentials. If None, loads from environment variables.

        Raises:
            TastytradeAuthError: If credentials are missing or invalid
        """
        if credentials is None:
            credentials = TastytradeCredentials.from_environment()

        self._credentials = credentials

        # OAuth state
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0

        # Async client for parallel requests
        self._async_client: Optional[httpx.AsyncClient] = None
        self._async_token_lock = asyncio.Lock()

        # Lazy-initialize futures symbol resolver
        self._futures_resolver: Optional[FuturesSymbolResolver] = None

        # Market data cache
        self._cache = MarketCache()

    @property
    def futures_resolver(self) -> "FuturesSymbolResolver":
        """Get or create the futures symbol resolver."""
        if self._futures_resolver is None:
            from .symbol_resolution.futures_resolver import FuturesSymbolResolver

            self._futures_resolver = FuturesSymbolResolver(self)
        return self._futures_resolver

    def _refresh_access_token(self) -> None:
        """
        Refresh the OAuth access token using the refresh token.

        Uses the OAuth 2.0 refresh token grant to obtain a new access token.
        Updates internal state with new token and expiry time.

        Raises:
            TastytradeAuthError: If token refresh fails (invalid credentials, network error)
        """
        url = f"{self._credentials.api_base_url}/oauth/token"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self._credentials.refresh_token,
            "client_id": self._credentials.client_id,
            "client_secret": self._credentials.client_secret,
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise TastytradeAuthError(f"OAuth token refresh failed: {e}") from e

        try:
            data = response.json()
            self._access_token = data["access_token"]
            # expires_in is in seconds, add buffer of 60s
            expires_in = data.get("expires_in", 3600)
            self._token_expiry = time.time() + expires_in - 60
        except (KeyError, ValueError) as e:
            raise TastytradeAuthError(f"Invalid OAuth response format: {e}") from e

    def _ensure_valid_token(self) -> str:
        """
        Ensure a valid access token is available, refreshing if necessary.

        Returns:
            Valid access token

        Raises:
            TastytradeAuthError: If token refresh fails
        """
        if not self._access_token or time.time() >= self._token_expiry:
            self._refresh_access_token()

        # Type guard: _refresh_access_token ensures token is set
        assert self._access_token is not None
        return self._access_token

    def _get_async_client(self) -> httpx.AsyncClient:
        """
        Get or create the async HTTP client for parallel requests.

        Returns:
            Shared AsyncClient instance
        """
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(timeout=15.0)
        return self._async_client

    async def _ensure_valid_token_async(self) -> str:
        """
        Async version of _ensure_valid_token with lock protection.

        Returns:
            Valid access token

        Raises:
            TastytradeAuthError: If token refresh fails
        """
        async with self._async_token_lock:
            # Check again inside lock (double-check locking pattern)
            if not self._access_token or time.time() >= self._token_expiry:
                self._refresh_access_token()

            # Type guard: _refresh_access_token ensures token is set
            assert self._access_token is not None
            return self._access_token

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

        hv30_val = self._normalize_hv(self._safe_float(item.get("historical-volatility-30-day")))
        if hv30_val is not None:
            metrics["hv30"] = hv30_val

        hv90_val = self._normalize_hv(self._safe_float(item.get("historical-volatility-90-day")))
        if hv90_val is not None:
            metrics["hv90"] = hv90_val

        iv_val = self._parse_iv(item.get("implied-volatility-index"), hv30_val, hv90_val)
        if iv_val is not None:
            metrics["iv"] = iv_val

        iv_rank = self._safe_float(item.get("implied-volatility-index-rank"))
        if iv_rank is not None:
            metrics["iv_rank"] = iv_rank

        iv_percentile = self._parse_iv_percentile(item.get("implied-volatility-percentile"))
        if iv_percentile is not None:
            metrics["iv_percentile"] = iv_percentile

        liquidity_rating = self._safe_int(item.get("liquidity-rating"))
        if liquidity_rating is not None:
            metrics["liquidity_rating"] = liquidity_rating

        liquidity_value = self._safe_float(item.get("liquidity-value"))
        if liquidity_value is not None:
            metrics["liquidity_value"] = liquidity_value

        option_volume = self._safe_float(item.get("option-volume"))
        if option_volume is not None:
            metrics["option_volume"] = option_volume

        corr_spy = self._safe_float(item.get("corr-spy-3month"))
        if corr_spy is not None:
            metrics["corr_spy_3month"] = corr_spy

        beta = self._safe_float(item.get("beta"))
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
    def _safe_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_hv(value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        # REST HV values are returned as decimals (0.25 => 25%); normalize to percent.
        return value * 100.0 if value <= 2.0 else value

    @staticmethod
    def _parse_iv(
        raw_iv: Any, hv30_val: Optional[float], hv90_val: Optional[float]
    ) -> Optional[float]:
        val = TastytradeClient._safe_float(raw_iv)
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
        val = TastytradeClient._safe_float(raw_val)
        if val is None:
            return None
        return val * 100.0 if val <= 1.0 else val

    def _fetch_api_data(
        self, url: str, headers: dict[str, str], params: Mapping[str, str | list[str]]
    ) -> Optional[Any]:
        """
        Fetch data from Tastytrade API with error handling.

        Args:
            url: API endpoint URL
            headers: HTTP headers including auth token
            params: Query parameters (values can be strings or lists of strings)

        Returns:
            JSON response as dict, or None if error
        """
        try:
            response = requests.get(url, headers=headers, params=params, timeout=15)

            # Handle common HTTP errors
            if response.status_code == 401:
                # Token may have expired prematurely, try once more
                self._access_token = None
                token = self._ensure_valid_token()
                headers["Authorization"] = f"Bearer {token}"
                response = requests.get(url, headers=headers, params=params, timeout=15)

            if response.status_code == 404:
                return None

            if response.status_code == 429:
                # Rate limit hit - implement exponential backoff
                retry_after = int(response.headers.get("Retry-After", 5))
                retry_after = min(retry_after, 60)  # Cap at 60 seconds
                logger.warning(f"Rate limit hit (429), retrying after {retry_after}s")
                import time

                time.sleep(retry_after)

                # Retry once
                token = self._ensure_valid_token()
                headers["Authorization"] = f"Bearer {token}"
                response = requests.get(url, headers=headers, params=params, timeout=15)

                if response.status_code == 429:
                    raise requests.exceptions.RequestException(
                        f"Rate limit exceeded after retry. Waited {retry_after}s."
                    )

            if response.status_code >= 500:
                raise requests.exceptions.RequestException(
                    f"Tastytrade server error: {response.status_code}"
                )

            response.raise_for_status()
            return response.json()

        except (requests.exceptions.RequestException, ValueError) as e:
            logger.error("Tastytrade API error: %s", e)
            return None

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
            >>> client = TastytradeClient()
            >>> metrics = client.get_market_metrics(['AAPL', 'SPY'])
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
        token = self._ensure_valid_token()

        symbols_str = ",".join(uncached_symbols)
        url = f"{self._credentials.api_base_url}/market-metrics"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        params = {"symbols": symbols_str}

        # Fetch data from API
        data = self._fetch_api_data(url, headers, params)
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
            >>> client = TastytradeClient()
            >>> data = client.get_market_data(['AAPL'])
            >>> print(data['AAPL']['last'])  # Last traded price
            271.84
        """
        if not symbols:
            return {}

        start_time = time.time()
        logger.debug("API call: /market-data/by-type symbols=%s", len(symbols))

        token = self._ensure_valid_token()

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
            data = self._fetch_api_data(url, headers, params)
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
                    "price": self._safe_float(item.get("last"))
                    or self._safe_float(item.get("mark")),
                    "bid": self._safe_float(item.get("bid")),
                    "ask": self._safe_float(item.get("ask")),
                    "last": self._safe_float(item.get("last")),
                    "mark": self._safe_float(item.get("mark")),
                    "mid": self._safe_float(item.get("mid")),
                    "open": self._safe_float(item.get("open")),
                    "high": self._safe_float(item.get("dayHighPrice")),
                    "low": self._safe_float(item.get("dayLowPrice")),
                    "close": self._safe_float(item.get("close")),
                    "prev_close": self._safe_float(item.get("prevClose")),
                    "volume": self._safe_float(item.get("volume")),
                    "beta": self._safe_float(item.get("beta")),
                    "updated_at": item.get("updatedAt"),
                }

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            "API /market-data/by-type completed: %s symbols in %.0fms",
            len(unique_symbols),
            elapsed_ms,
        )
        return results

    async def _fetch_option_chain_async(
        self, symbol: str, semaphore: asyncio.Semaphore
    ) -> tuple[str, Optional[dict[str, Any]]]:
        """
        Fetch a single option chain asynchronously with rate limiting.

        Args:
            symbol: Underlying symbol (e.g., 'AAPL')
            semaphore: Semaphore for rate limiting

        Returns:
            Tuple of (symbol, normalized_chain_data)
        """
        async with semaphore:
            client = self._get_async_client()
            token = await self._ensure_valid_token_async()
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }

            symbol_path = quote(str(symbol), safe="")
            endpoint = f"/option-chains/{symbol_path}"  # FULL endpoint, not /compact
            url = f"{self._credentials.api_base_url}{endpoint}"

            try:
                response = await client.get(url, headers=headers)

                # Handle common HTTP errors
                if response.status_code == 401:
                    # Token may have expired, refresh and retry
                    token = await self._ensure_valid_token_async()
                    headers["Authorization"] = f"Bearer {token}"
                    response = await client.get(url, headers=headers)

                if response.status_code == 404:
                    logger.debug("No option chain available for %s (404 Not Found)", symbol)
                    return symbol, None

                if response.status_code == 429:
                    # Rate limit: exponential backoff
                    await asyncio.sleep(1.0)
                    response = await client.get(url, headers=headers)

                if response.status_code >= 500:
                    logger.error(
                        "Tastytrade server error %s for symbol %s",
                        response.status_code,
                        symbol,
                    )
                    return symbol, None

                response.raise_for_status()
                payload = response.json()
                normalized = self._normalize_option_chain_payload(symbol, payload)
                return symbol, normalized

            except (httpx.HTTPError, ValueError) as e:
                logger.error("Error fetching option chain for %s: %s", symbol, e)
                return symbol, None

    async def _get_option_chains_async(
        self, symbols: list[str], max_concurrent: int = 10
    ) -> dict[str, dict[str, Any]]:
        """
        Fetch option chains for multiple symbols in parallel.

        Args:
            symbols: List of underlying symbols (e.g., ['AAPL', 'SPY'])
            max_concurrent: Maximum concurrent requests (default: 10)

        Returns:
            Dictionary mapping symbol to chain data (filtered to Regular options).
        """
        if not symbols:
            return {}

        # Filter out futures symbols (not supported)
        equity_symbols = [s for s in symbols if s and not str(s).startswith("/")]
        if not equity_symbols:
            return {}

        start_time = time.time()
        logger.debug(
            "API call: /option-chains (parallel) symbols=%s, max_concurrent=%s",
            len(equity_symbols),
            max_concurrent,
        )

        # Create semaphore for rate limiting
        semaphore = asyncio.Semaphore(max_concurrent)

        # Fetch all chains in parallel
        tasks = [self._fetch_option_chain_async(symbol, semaphore) for symbol in equity_symbols]
        results_list = await asyncio.gather(*tasks)

        # Build results dictionary and track failures
        results: dict[str, dict[str, Any]] = {}
        failed_symbols = []
        for symbol, chain in results_list:
            if chain is not None:
                results[symbol] = chain
            else:
                failed_symbols.append(symbol)

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            "API /option-chains (parallel) completed: %s/%s symbols in %.0fms (%.0fms avg)",
            len(results),
            len(equity_symbols),
            elapsed_ms,
            elapsed_ms / len(equity_symbols) if equity_symbols else 0,
        )

        if failed_symbols:
            logger.info(
                "Option chains not available for %s symbols: %s",
                len(failed_symbols),
                ", ".join(failed_symbols),
            )

        return results

    def get_option_chains_compact(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        """
        Fetch equity option chains for multiple symbols.

        This method:
        1. Checks cache for each symbol first (24-hour TTL)
        2. Fetches only uncached symbols from API
        3. Uses parallel async fetching for multiple symbols
        4. Caches fresh results

        Note: Despite the name, this uses the FULL endpoint (not /compact) because
        the compact endpoint omits intermediate monthly expirations needed for
        Tastylive 30-45 DTE methodology.

        Args:
            symbols: List of underlying symbols (e.g., ['AAPL', 'SPY'])

        Returns:
            Dictionary mapping symbol to chain data (filtered to Regular options).
        """
        if not symbols:
            return {}

        # Filter equity symbols
        equity_symbols = [s for s in symbols if s and not str(s).startswith("/")]
        if not equity_symbols:
            return {}

        # Check cache and partition symbols
        cached_results: dict[str, dict[str, Any]] = {}
        uncached_symbols: list[str] = []

        for symbol in equity_symbols:
            cache_key = make_cache_key("option_chain", symbol)
            cached = self._cache.get(cache_key)
            if cached:
                cached_results[symbol] = cached
            else:
                uncached_symbols.append(symbol)

        # If all symbols are cached, return early
        if not uncached_symbols:
            logger.debug("Cache hit: all %s option chains cached", len(equity_symbols))
            return cached_results

        logger.debug(
            "Cache partial: %s cached, %s uncached of %s total option chains",
            len(cached_results),
            len(uncached_symbols),
            len(equity_symbols),
        )

        # Fetch uncached symbols
        fresh_results: dict[str, dict[str, Any]] = {}

        # Use parallel async fetching for multiple symbols
        if len(uncached_symbols) > 1:
            # Load max_concurrent from config or default to 10
            max_concurrent = 10
            try:
                import json
                from pathlib import Path

                config_path = Path(__file__).parent.parent.parent / "config" / "runtime_config.json"
                if config_path.exists():
                    with open(config_path) as f:
                        config = json.load(f)
                        max_concurrent = config.get("tastytrade", {}).get(
                            "max_concurrent_option_chains", 10
                        )
            except Exception:
                pass  # Use default if config loading fails

            # Run async version
            fresh_results = asyncio.run(
                self._get_option_chains_async(uncached_symbols, max_concurrent)
            )
        else:
            # Single symbol: use synchronous version (no async overhead)
            start_time = time.time()
            symbol = uncached_symbols[0]
            logger.debug("API call: /option-chains (full) symbol=%s", symbol)
            token = self._ensure_valid_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }

            symbol_path = quote(str(symbol), safe="")
            endpoint = f"/option-chains/{symbol_path}"  # FULL endpoint, not /compact
            url = f"{self._credentials.api_base_url}{endpoint}"
            payload = self._fetch_api_data(url, headers, params={})
            normalized = self._normalize_option_chain_payload(symbol, payload)

            if normalized:
                fresh_results[symbol] = normalized

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(
                "API /option-chains (full) completed: %s in %.0fms",
                symbol,
                elapsed_ms,
            )

        # Cache fresh results
        ttl = get_dynamic_ttl("option_chain", 86400)  # 24 hours (chain structure is stable)
        for symbol, chain in fresh_results.items():
            cache_key = make_cache_key("option_chain", symbol)
            self._cache.set(cache_key, chain, ttl_seconds=ttl)

        # Merge cached and fresh results
        all_results = {**cached_results, **fresh_results}

        logger.info(
            "Option chains completed: %s total (%s cached, %s fetched)",
            len(all_results),
            len(cached_results),
            len(fresh_results),
        )
        return all_results

    def get_futures_option_chain(self, symbol: str) -> list[dict[str, Any]]:
        """
        Fetch full futures option chain data for a single symbol.

        Args:
            symbol: Futures root symbol (e.g., "/ES")

        Returns:
            List of option chain items.
        """
        if not symbol:
            return []

        start_time = time.time()
        logger.debug("API call: /futures-option-chains symbol=%s", symbol)
        token = self._ensure_valid_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        symbol_path = quote(str(symbol), safe="")
        url = f"{self._credentials.api_base_url}/futures-option-chains/{symbol_path}"
        payload = self._fetch_api_data(url, headers, params={})
        items = self._normalize_futures_chain_payload(payload)
        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            "API /futures-option-chains completed: %s items in %.0fms",
            len(items),
            elapsed_ms,
        )
        return items

    def find_atm_options(
        self,
        symbol: str,
        chain: dict[str, Any],
        underlying_price: float,
        target_dte: int = 45,
        *,
        dte_min: Optional[int] = None,
        dte_max: Optional[int] = None,
    ) -> Optional[tuple[str, str]]:
        """
        Find ATM call and put OCC symbols from chain.

        Args:
            symbol: Underlying symbol
            chain: Compact chain data from get_option_chains_compact()
            underlying_price: Current underlying price
            target_dte: Target days to expiration (default: 45)
            dte_min: Optional minimum DTE bound
            dte_max: Optional maximum DTE bound

        Returns:
            (call_occ_symbol, put_occ_symbol) if found, otherwise None.
        """
        expirations = chain.get("expirations", [])
        if not expirations:
            return None

        selected = self._select_expiration(expirations, target_dte, dte_min, dte_max)
        if not selected:
            return None
        expiration, exp_date = selected

        strikes = self._extract_strikes(expiration)
        if not strikes:
            return None
        atm_strike = min(strikes, key=lambda s: abs(s - underlying_price))

        if str(symbol).startswith("/"):
            futures_symbols = self._find_futures_option_symbols(expiration, atm_strike)
            if futures_symbols:
                return futures_symbols
            return None

        root = (
            chain.get("option_root_symbol")
            or chain.get("root_symbol")
            or chain.get("underlying_symbol")
            or chain.get("symbol")
            or symbol
        )
        if not exp_date:
            return None

        call_symbol = self.build_occ_symbol(root, exp_date, atm_strike, "C")
        put_symbol = self.build_occ_symbol(root, exp_date, atm_strike, "P")
        return call_symbol, put_symbol

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
        token = self._ensure_valid_token()
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

            data = self._fetch_api_data(url, headers, params)
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
                    "bid": self._safe_float(item.get("bid")),
                    "ask": self._safe_float(item.get("ask")),
                    "mid": self._safe_float(item.get("mid")),
                    "mark": self._safe_float(item.get("mark")),
                    "last": self._safe_float(item.get("last")),
                    "updated_at": item.get("updatedAt") or item.get("updated-at"),
                }

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            "API /market-data/by-type options completed: %s symbols in %.0fms",
            total,
            elapsed_ms,
        )
        return results

    @staticmethod
    def build_occ_symbol(symbol: str, expiration: date, strike: float, call_put: str) -> str:
        """
        Build OCC option symbol for equities.

        Format: SYMBOL(6) + YYMMDD + C/P + STRIKE(8, *1000)
        Example: AAPL  260220C00170000
        """
        root = str(symbol).upper().replace("/", "")
        root = root.replace(".", "")
        root = root[:6].ljust(6)
        exp = expiration.strftime("%y%m%d")
        strike_int = int(round(strike * 1000))
        strike_str = f"{strike_int:08d}"
        return f"{root}{exp}{call_put.upper()}{strike_str}"

    def _normalize_option_chain_payload(
        self, symbol: str, payload: Any
    ) -> Optional[dict[str, Any]]:
        """
        Normalize raw option chain payloads into a compact, predictable structure.

        Handles both:
        - Full endpoint: individual option contracts that need grouping
        - Compact endpoint: pre-grouped expirations (legacy)
        """
        if payload is None:
            return None

        data = payload.get("data", payload) if isinstance(payload, dict) else payload
        if not isinstance(data, dict):
            return None

        items = data.get("items", [])
        if not isinstance(items, list) or not items:
            return None

        # Detect if these are individual options or grouped expirations
        first_item = items[0] if items else {}
        is_individual_options = "strike-price" in first_item

        if is_individual_options:
            # Full endpoint: Group individual options by expiration
            return self._group_options_by_expiration(symbol, items)
        else:
            # Compact endpoint (legacy): Already grouped
            return self._normalize_grouped_expirations(symbol, items, data)

    def _group_options_by_expiration(
        self, symbol: str, options: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Group individual option contracts by expiration date."""
        from collections import defaultdict

        # Filter to Regular/Quarterly (except major indexes)
        major_symbols = {"SPY", "QQQ", "SPX", "/ES", "/NQ", "DIA", "IWM"}
        if symbol not in major_symbols:
            options = [
                opt for opt in options if opt.get("expiration-type") in ("Regular", "Quarterly")
            ]

        # Group by expiration date
        by_expiration: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"symbols": [], "strikes": set()}
        )

        for opt in options:
            exp_date = opt.get("expiration-date")
            if not exp_date:
                continue

            exp_group = by_expiration[exp_date]
            exp_group["expiration-date"] = exp_date
            exp_group["days-to-expiration"] = opt.get("days-to-expiration")
            exp_group["expiration-type"] = opt.get("expiration-type")

            # Collect symbols and strikes
            opt_symbol = opt.get("symbol")
            if opt_symbol:
                exp_group["symbols"].append(opt_symbol)

            strike = opt.get("strike-price")
            if strike:
                try:
                    exp_group["strikes"].add(float(strike))
                except (TypeError, ValueError):
                    pass

        # Convert to final structure
        expirations = []
        for exp_date in sorted(by_expiration.keys()):
            exp = by_expiration[exp_date]
            exp["strikes"] = sorted(list(exp["strikes"]))
            expirations.append(exp)

        return {
            "symbol": symbol,
            "underlying_symbol": symbol,
            "root_symbol": symbol,
            "expirations": expirations,
        }

    def _normalize_grouped_expirations(
        self, symbol: str, items: list[dict[str, Any]], data: dict[str, Any]
    ) -> dict[str, Any]:
        """Normalize pre-grouped expirations from compact endpoint (legacy)."""
        underlying_symbol = (
            data.get("underlying-symbol")
            or data.get("underlying_symbol")
            or data.get("symbol")
            or symbol
        )
        root_symbol = (
            data.get("option-root-symbol")
            or data.get("option_root_symbol")
            or data.get("root-symbol")
            or data.get("root_symbol")
            or underlying_symbol
        )

        # Filter to Regular options only (exclude Weeklies)
        major_symbols = {"SPY", "QQQ", "SPX", "/ES", "/NQ", "DIA", "IWM"}
        if symbol not in major_symbols:
            items = [
                exp
                for exp in items
                if isinstance(exp, dict)
                and exp.get("expiration-type") in ("Regular", "Quarterly", None)
            ]

        # Parse OCC symbols if expiration data missing (legacy fallback)
        for exp_item in items:
            if not isinstance(exp_item, dict):
                continue
            if exp_item.get("expiration-date") and exp_item.get("days-to-expiration"):
                continue

            symbols_list = exp_item.get("symbols", [])
            if symbols_list and isinstance(symbols_list, list):
                first_symbol = str(symbols_list[0])
                if len(first_symbol) >= 12:
                    date_part = first_symbol[6:12]
                    try:
                        exp_date = datetime.strptime(f"20{date_part}", "%Y%m%d").date()
                        dte = (exp_date - date.today()).days
                        exp_item["expiration-date"] = exp_date.isoformat()
                        exp_item["days-to-expiration"] = dte
                    except (ValueError, AttributeError):
                        pass

        return {
            "symbol": symbol,
            "underlying_symbol": underlying_symbol,
            "root_symbol": root_symbol,
            "expirations": items,
        }

    @staticmethod
    def _normalize_futures_chain_payload(payload: Any) -> list[dict[str, Any]]:
        """Normalize futures option chain payload into a list of items."""
        if payload is None:
            return []
        data = payload.get("data", payload) if isinstance(payload, dict) else payload
        if isinstance(data, dict):
            items = data.get("items")
        elif isinstance(data, list):
            items = data
        else:
            items = None
        return items if isinstance(items, list) else []

    def _select_expiration(
        self,
        expirations: list[Any],
        target_dte: int,
        dte_min: Optional[int],
        dte_max: Optional[int],
    ) -> Optional[tuple[dict[str, Any], Optional[date]]]:
        """Select the expiration closest to target DTE within optional bounds."""
        candidates: list[tuple[dict[str, Any], int, Optional[date]]] = []
        for exp in expirations:
            if not isinstance(exp, dict):
                continue
            dte = exp.get("days-to-expiration") or exp.get("days_to_expiration")
            exp_date = self._parse_expiration_date(exp)
            if dte is None and exp_date:
                dte = (exp_date - date.today()).days
            if dte is None:
                continue
            try:
                dte_val = int(float(dte))
            except (TypeError, ValueError):
                continue
            if dte_min is not None and dte_val < dte_min:
                continue
            if dte_max is not None and dte_val > dte_max:
                continue
            candidates.append((exp, dte_val, exp_date))

        if not candidates:
            return None

        exp, _dte, exp_date = min(candidates, key=lambda item: abs(item[1] - target_dte))
        return exp, exp_date

    def _parse_expiration_date(self, expiration: dict[str, Any]) -> Optional[date]:
        """Parse an expiration date from chain metadata."""
        raw = expiration.get("expiration-date") or expiration.get("expiration_date")
        if not raw:
            return None
        if isinstance(raw, date):
            return raw
        if isinstance(raw, datetime):
            return raw.date()
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return datetime.strptime(str(raw), "%Y-%m-%d").date()
            except ValueError:
                return None

    def _extract_strikes(self, expiration: dict[str, Any]) -> list[float]:
        """Extract numeric strikes from chain expiration."""
        # Try explicit strikes field first (from full endpoint grouping)
        strikes_raw = expiration.get("strikes")
        if isinstance(strikes_raw, list) and strikes_raw:
            # Already sorted floats from _group_options_by_expiration
            return strikes_raw

        # Try other strike field names (legacy compact endpoint)
        strikes_raw = expiration.get("strike-prices") or expiration.get("strike_prices")
        if isinstance(strikes_raw, list):
            strikes: list[float] = []
            for strike in strikes_raw:
                try:
                    strikes.append(float(strike))
                except (TypeError, ValueError):
                    continue
            return sorted(strikes)

        # Final fallback: Parse from OCC symbols
        symbols_list = expiration.get("symbols", [])
        if isinstance(symbols_list, list) and symbols_list:
            strikes_set: set[float] = set()
            for occ_symbol in symbols_list:
                occ_str = str(occ_symbol)
                # OCC format: "SYMBOL  YYMMDDCTTTTTTKKKK"
                # Characters 13-20 = strike * 1000 (8 digits)
                if len(occ_str) >= 21:
                    try:
                        strike_str = occ_str[13:21]
                        strike_int = int(strike_str)
                        strike = strike_int / 1000.0
                        strikes_set.add(strike)
                    except (ValueError, IndexError):
                        continue
            return sorted(list(strikes_set))

        return []

    def _find_futures_option_symbols(
        self, expiration: dict[str, Any], strike: float
    ) -> Optional[tuple[str, str]]:
        """Locate futures option symbols for the selected strike when available."""
        options = (
            expiration.get("options")
            or expiration.get("option-symbols")
            or expiration.get("option_symbols")
        )
        if not isinstance(options, list):
            return None

        call_symbol = None
        put_symbol = None
        for option in options:
            if not isinstance(option, dict):
                continue
            strike_val = (
                option.get("strike") or option.get("strike-price") or option.get("strike_price")
            )
            if strike_val is None:
                continue
            try:
                strike_float = float(strike_val)
            except (TypeError, ValueError):
                continue
            if abs(strike_float - strike) > 1e-6:
                continue
            option_type = (
                option.get("option-type")
                or option.get("option_type")
                or option.get("type")
                or option.get("call-put")
            )
            symbol = (
                option.get("symbol") or option.get("option-symbol") or option.get("streamer-symbol")
            )
            if not symbol:
                continue
            if str(option_type).upper().startswith("C"):
                call_symbol = symbol
            elif str(option_type).upper().startswith("P"):
                put_symbol = symbol

        if call_symbol and put_symbol:
            return call_symbol, put_symbol
        return None

    def find_futures_atm_options(
        self,
        chain_items: list[dict[str, Any]],
        underlying_price: float,
        target_dte: int = 45,
        *,
        dte_min: Optional[int] = None,
        dte_max: Optional[int] = None,
    ) -> Optional[tuple[str, str]]:
        """
        Find ATM call/put symbols from a futures option chain.

        Args:
            chain_items: Futures option chain items
            underlying_price: Current underlying price
            target_dte: Target days to expiration (default: 45)
            dte_min: Optional minimum DTE bound
            dte_max: Optional maximum DTE bound

        Returns:
            (call_symbol, put_symbol) if found, otherwise None.
        """
        if not chain_items:
            return None

        candidates: list[tuple[dict[str, Any], int]] = []
        for item in chain_items:
            if not isinstance(item, dict):
                continue
            dte_val = self._extract_dte(item)
            if dte_val is None:
                continue
            if dte_min is not None and dte_val < dte_min:
                continue
            if dte_max is not None and dte_val > dte_max:
                continue
            candidates.append((item, dte_val))

        if not candidates:
            return None

        target_exp = min(candidates, key=lambda item: abs(item[1] - target_dte))[0]
        exp_date = (
            target_exp.get("expiration-date")
            or target_exp.get("expiration_date")
            or target_exp.get("expiration")
        )

        exp_items = []
        for item in chain_items:
            if not isinstance(item, dict):
                continue
            item_exp = (
                item.get("expiration-date") or item.get("expiration_date") or item.get("expiration")
            )
            if exp_date and item_exp != exp_date:
                continue
            exp_items.append(item)

        if not exp_items:
            return None

        strikes: list[float] = []
        for item in exp_items:
            strike = self._extract_strike(item)
            if strike is not None:
                strikes.append(strike)

        if not strikes:
            return None

        atm_strike = min(strikes, key=lambda s: abs(s - underlying_price))

        call_symbol = None
        put_symbol = None
        for item in exp_items:
            strike = self._extract_strike(item)
            if strike is None or abs(strike - atm_strike) > 1e-6:
                continue
            option_type = self._extract_option_type(item)
            symbol = item.get("symbol")
            if not symbol:
                continue
            if option_type == "C":
                call_symbol = symbol
            elif option_type == "P":
                put_symbol = symbol

        if call_symbol and put_symbol:
            return call_symbol, put_symbol
        return None

    def _extract_dte(self, item: dict[str, Any]) -> Optional[int]:
        dte = item.get("days-to-expiration") or item.get("days_to_expiration")
        if dte is not None:
            try:
                return int(float(dte))
            except (TypeError, ValueError):
                return None
        exp_date = self._parse_expiration_date(item)
        if not exp_date:
            return None
        return (exp_date - date.today()).days

    @staticmethod
    def _extract_strike(item: dict[str, Any]) -> Optional[float]:
        strike = item.get("strike-price") or item.get("strike_price") or item.get("strike")
        if strike is None:
            return None
        try:
            return float(strike)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_option_type(item: dict[str, Any]) -> Optional[str]:
        option_type = (
            item.get("option-type")
            or item.get("option_type")
            or item.get("type")
            or item.get("call-put")
        )
        if not option_type:
            return None
        option_type = str(option_type).upper()
        if option_type.startswith("C"):
            return "C"
        if option_type.startswith("P"):
            return "P"
        return None

    def resolve_dxlink_symbol(self, symbol: str) -> Optional[str]:
        """
        Resolve a symbol to DXLink-compatible symbology.

        Currently supports futures via Tastytrade instruments endpoints.

        Args:
            symbol: Futures symbol (e.g., /ES or /ESH25)

        Returns:
            DXLink streamer symbol (e.g., /ES:XCME:H25) or None
        """
        return self.futures_resolver.resolve_to_dxlink(symbol)

    def resolve_dxlink_history_symbols(self, symbol: str) -> list[str]:
        """
        Resolve a futures symbol to a list of DXLink streamer symbols for history stitching.

        Args:
            symbol: Futures root symbol (e.g., /ES)

        Returns:
            List of DXLink streamer symbols for active and previous contracts
        """
        return self.futures_resolver.resolve_history_chain(symbol)

    async def close_async(self) -> None:
        """Close the async HTTP client (async version)."""
        if self._async_client is not None:
            await self._async_client.aclose()
            self._async_client = None

    def close(self) -> None:
        """
        Close the async HTTP client and cleanup resources.

        Should be called when the client is no longer needed, especially
        when using the parallel async fetching features.
        """
        if self._async_client is not None:
            asyncio.run(self.close_async())
