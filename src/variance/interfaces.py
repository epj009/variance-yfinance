from typing import Any, Optional, Protocol, TypedDict


class MarketData(TypedDict, total=False):
    """Standardized Market Data Model"""

    # Core Fields
    error: Optional[str]
    price: float
    iv: Optional[float]
    iv_rank: Optional[float]
    hv20: Optional[float]
    hv252: Optional[float]
    vrp_structural: Optional[float]
    vrp_tactical: Optional[float]
    earnings_date: Optional[str]
    sector: Optional[str]
    is_stale: bool
    proxy: Optional[str]
    returns: Optional[list[float]]
    beta: Optional[float]
    option_volume: Optional[float]
    call_bid: Optional[float]
    call_ask: Optional[float]
    put_bid: Optional[float]
    put_ask: Optional[float]
    atm_bid: Optional[float]
    atm_ask: Optional[float]

    # Tastytrade-native fields
    hv30: Optional[float]  # 30-day historical volatility (Tastytrade)
    hv90: Optional[float]  # 90-day historical volatility (Tastytrade)
    hv90_source: Optional[str]  # "tastytrade_rest" | "dxlink" | "proxy_dxlink"
    iv_percentile: Optional[float]  # IV percentile (0-100, Tastytrade)
    liquidity_rating: Optional[int]  # 1-5 rating (Tastytrade)
    liquidity_value: Optional[float]  # Numeric liquidity score (Tastytrade)
    data_source: Optional[str]  # "tastytrade"
    warning: Optional[str]  # Warning messages (e.g., "tastytrade_fallback")
    warning_detail: Optional[dict[str, Any]]  # Structured warning metadata
    warning_message: Optional[str]  # User-facing warning text


class IMarketDataProvider(Protocol):
    """
    Interface for Market Data Providers.
    Decouples the application from specific data sources (tastytrade, dxlink, etc).
    """

    def get_market_data(
        self,
        symbols: list[str],
        *,
        include_returns: bool = False,
        include_option_quotes: bool = False,
    ) -> dict[str, MarketData]:
        """
        Fetch market data for a list of symbols.

        Args:
            symbols: List of ticker symbols (e.g. ['AAPL', 'SPY'])

        Returns:
            Dictionary mapping symbols to their MarketData
        """
        ...
