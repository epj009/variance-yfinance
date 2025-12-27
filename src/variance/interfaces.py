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
    hv_rank: Optional[float]
    vrp_structural: Optional[float]
    vrp_tactical: Optional[float]
    earnings_date: Optional[str]
    sector: Optional[str]
    is_stale: bool
    proxy: Optional[str]
    returns: Optional[list[float]]

    # Tastytrade-native fields
    hv30: Optional[float]  # 30-day historical volatility (Tastytrade)
    hv90: Optional[float]  # 90-day historical volatility (Tastytrade)
    iv_percentile: Optional[float]  # IV percentile (0-100, Tastytrade)
    liquidity_rating: Optional[int]  # 1-5 rating (Tastytrade)
    liquidity_value: Optional[float]  # Numeric liquidity score (Tastytrade)
    data_source: Optional[str]  # "tastytrade" | "yfinance" | "composite"
    warning: Optional[str]  # Warning messages (e.g., "tastytrade_fallback")
    warning_detail: Optional[dict[str, Any]]  # Structured warning metadata
    warning_message: Optional[str]  # User-facing warning text


class IMarketDataProvider(Protocol):
    """
    Interface for Market Data Providers.
    Decouples the application from specific data sources (yfinance, tasty, etc).
    """

    def get_market_data(self, symbols: list[str]) -> dict[str, MarketData]:
        """
        Fetch market data for a list of symbols.

        Args:
            symbols: List of ticker symbols (e.g. ['AAPL', 'SPY'])

        Returns:
            Dictionary mapping symbols to their MarketData
        """
        ...
