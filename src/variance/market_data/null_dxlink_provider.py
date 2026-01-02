"""
Null Object implementation for DXLink provider.

Eliminates conditional checks by providing a safe no-op implementation
when DXLink is unavailable.
"""

from typing import Any


class NullDXLinkProvider:
    """
    Null object for DXLink provider when unavailable.

    Returns empty/None values for all methods, allowing calling code
    to avoid null checks.
    """

    def get_market_data_sync(self, symbol: str, **kwargs: Any) -> dict[str, Any]:
        """
        Return empty market data.

        Args:
            symbol: Ticker symbol (ignored)
            **kwargs: Additional arguments (ignored)

        Returns:
            Empty market data dict with None values
        """
        return {
            "price": None,
            "hv30": None,
            "hv90": None,
            "returns": [],
        }

    def get_market_data_batch_sync(
        self, symbols: list[str], **kwargs: Any
    ) -> dict[str, dict[str, Any]]:
        """
        Return empty market data for multiple symbols.

        Args:
            symbols: List of ticker symbols
            **kwargs: Additional arguments (ignored)

        Returns:
            Dict mapping each symbol to empty market data
        """
        return {symbol: self.get_market_data_sync(symbol) for symbol in symbols}
