"""
Default Strategy Implementation

Fallback for unmapped or generic strategies.
"""

from typing import Any
from .base import BaseStrategy


class DefaultStrategy(BaseStrategy):
    """Fallback strategy that uses generic logic."""

    def is_tested(self, legs: list[dict[str, Any]], underlying_price: float) -> bool:
        """Generic fallback cannot determine if tested accurately."""
        return False
