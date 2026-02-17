"""
Tastytrade API Client Package.

Public API:
    TastytradeClient - Main client facade (backward compatible)
    TastytradeCredentials - OAuth credentials container
    TastytradeAuthError - Authentication exception
    TastytradeMetrics - Market metrics TypedDict
"""

import asyncio
from datetime import date
from typing import TYPE_CHECKING, Any, Optional

from ..market_data.cache import MarketCache
from .auth import (
    TastytradeAuthError,
    TastytradeCredentials,
    TastytradeMetrics,
    TokenManager,
)
from .market_data import MarketDataFetcher
from .options import OptionChainFetcher

if TYPE_CHECKING:
    from ..symbol_resolution.futures_resolver import FuturesSymbolResolver


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

        # Initialize sub-components
        self._cache = MarketCache()
        self._token_manager = TokenManager(self._credentials)
        self._market_data = MarketDataFetcher(self._token_manager, self._credentials, self._cache)
        self._options = OptionChainFetcher(self._token_manager, self._credentials, self._cache)

        # Lazy-initialize futures symbol resolver
        self._futures_resolver: Optional[FuturesSymbolResolver] = None

    @property
    def futures_resolver(self) -> "FuturesSymbolResolver":
        """Get or create the futures symbol resolver."""
        if self._futures_resolver is None:
            from ..symbol_resolution.futures_resolver import FuturesSymbolResolver

            self._futures_resolver = FuturesSymbolResolver(self._token_manager)
        return self._futures_resolver

    # Delegate all methods to sub-modules

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
        return self._market_data.get_market_metrics(symbols)

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
        return self._market_data.get_market_data(symbols)

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
        return self._market_data.get_option_quotes(equity_options, future_options)

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
        return self._options.get_option_chains_compact(symbols)

    def get_futures_option_chain(self, symbol: str) -> list[dict[str, Any]]:
        """
        Fetch full futures option chain data for a single symbol.

        Args:
            symbol: Futures root symbol (e.g., "/ES")

        Returns:
            List of option chain items.
        """
        return self._options.get_futures_option_chain(symbol)

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
        return self._options.find_atm_options(
            symbol, chain, underlying_price, target_dte, dte_min=dte_min, dte_max=dte_max
        )

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
        return self._options.find_futures_atm_options(
            chain_items, underlying_price, target_dte, dte_min=dte_min, dte_max=dte_max
        )

    @staticmethod
    def build_occ_symbol(symbol: str, expiration: date, strike: float, call_put: str) -> str:
        """
        Build OCC option symbol for equities.

        Format: SYMBOL(6) + YYMMDD + C/P + STRIKE(8, *1000)
        Example: AAPL  260220C00170000
        """
        return OptionChainFetcher.build_occ_symbol(symbol, expiration, strike, call_put)

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
        await self._token_manager.close_async()

    def close(self) -> None:
        """
        Close the async HTTP client and cleanup resources.

        Should be called when the client is no longer needed, especially
        when using the parallel async fetching features.
        """
        if self._token_manager._async_client is not None:
            asyncio.run(self.close_async())


__all__ = ["TastytradeClient", "TastytradeCredentials", "TastytradeAuthError", "TastytradeMetrics"]
