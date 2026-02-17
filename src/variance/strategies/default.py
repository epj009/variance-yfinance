"""
Default Strategy Implementation

Fallback for unmapped or generic strategies.
"""

from ..models.position import Position
from .base import BaseStrategy


@BaseStrategy.register("default")
class DefaultStrategy(BaseStrategy):
    """
    Fallback strategy for unrecognized position clusters.
    """

    def is_tested(self, legs: list[Position], underlying_price: float) -> bool:
        """Generic fallback cannot determine if tested accurately."""
        return False
