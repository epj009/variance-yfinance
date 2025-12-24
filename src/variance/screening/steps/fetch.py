"""
Market Data Fetching Step
"""

from typing import Any

from variance.get_market_data import MarketDataFactory


def fetch_market_data(symbols: list[str]) -> dict[str, Any]:
    """Fetches real-time volatility and price data in parallel."""
    provider = MarketDataFactory.get_provider()
    return provider.get_market_data(symbols)
