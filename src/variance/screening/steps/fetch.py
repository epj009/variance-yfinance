"""
Market Data Fetching Step
"""

from typing import Any

from variance.diagnostics import MarketDataDiagnostics
from variance.market_data.service import MarketDataFactory


def fetch_market_data(symbols: list[str]) -> tuple[dict[str, Any], dict[str, int]]:
    """Fetches real-time volatility and price data in parallel."""
    provider = MarketDataFactory.get_provider()
    data = provider.get_market_data(symbols)
    diagnostics = MarketDataDiagnostics.from_payload(data)
    return data, diagnostics.to_dict()
