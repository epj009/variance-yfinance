from typing import Optional, Protocol, TypedDict


class MarketData(TypedDict, total=False):
    """Standardized Market Data Model"""

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
