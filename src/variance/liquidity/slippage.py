"""
Slippage calculation utilities for options liquidity analysis.

This module provides a centralized implementation for calculating bid/ask slippage
from call and put option quotes.
"""

from typing import Any


class SlippageCalculator:
    """
    Calculates bid/ask slippage for options contracts.

    Slippage is defined as: (ask - bid) / mid, where mid = (bid + ask) / 2
    """

    @staticmethod
    def calculate_max_slippage(metrics: dict[str, Any]) -> tuple[bool, float]:
        """
        Calculate maximum slippage from call/put bid/ask quotes.

        This method examines both call and put option quotes and returns the
        maximum slippage percentage found. Used as a liquidity filter.

        Args:
            metrics: Dictionary containing option quote data with keys:
                - call_bid: Call option bid price
                - call_ask: Call option ask price
                - put_bid: Put option bid price
                - put_ask: Put option ask price

        Returns:
            Tuple of (has_valid_quote, max_slippage_percentage) where:
                - has_valid_quote: True if at least one valid bid/ask pair exists
                - max_slippage_percentage: Maximum slippage as decimal (0.05 = 5%)

        Example:
            >>> metrics = {"call_bid": 2.0, "call_ask": 2.2, "put_bid": 1.8, "put_ask": 2.0}
            >>> has_quote, slippage = SlippageCalculator.calculate_max_slippage(metrics)
            >>> has_quote
            True
            >>> round(slippage, 3)
            0.105  # 10.5% max slippage (from put: (2.0 - 1.8) / 1.9)
        """
        max_slippage = 0.0
        has_quote = False

        for bid_key, ask_key in [("call_bid", "call_ask"), ("put_bid", "put_ask")]:
            bid = metrics.get(bid_key)
            ask = metrics.get(ask_key)

            if bid is not None and ask is not None:
                try:
                    bid_float = float(bid)
                    ask_float = float(ask)
                    mid = (bid_float + ask_float) / 2

                    if mid > 0:
                        has_quote = True
                        slippage = (ask_float - bid_float) / mid
                        max_slippage = max(max_slippage, slippage)
                except (ValueError, TypeError):
                    # Skip invalid numeric values
                    pass

        return has_quote, max_slippage


# Function-based API for compatibility with vol_screener extraction
def calculate_max_leg_slippage(metrics: dict[str, Any]) -> tuple[bool, float]:
    """
    Calculate maximum slippage across call/put legs (function wrapper).

    Returns:
        tuple[bool, float]: (has_valid_quote, max_slippage_ratio)
    """
    return SlippageCalculator.calculate_max_slippage(metrics)
