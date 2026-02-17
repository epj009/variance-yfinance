"""
Butterfly Strategy Class

Handles logic for Butterflies and Iron Butterflies (Pin strategies).
"""

from typing import Any, Optional

from ..models.position import Position
from .base import BaseStrategy


@BaseStrategy.register("butterfly")
@BaseStrategy.register("pin_strategy")
class ButterflyStrategy(BaseStrategy):
    """
    Handles strategies with a narrow profit tent.
    Primary focus: Detecting breach of the inner short strikes.
    """

    def is_tested(self, legs: list[Position], underlying_price: float) -> bool:
        """
        Butterfly is tested if price moves outside the 'Tent' (the short strikes).
        """
        short_strikes = []
        for leg in legs:
            if leg.quantity < 0:
                short_strikes.append(float(leg.strike or 0.0))

        if not short_strikes:
            return False

        upper_short = max(short_strikes)
        lower_short = min(short_strikes)

        # Buffer: Butterflies are tested if they move beyond the short strikes
        return underlying_price > upper_short or underlying_price < lower_short

    def check_harvest(self, symbol: str, pl_pct: float, days_held: int) -> Optional[Any]:
        """
        Butterflies have low probability but high payoff; 25% is the standard target.
        """
        target = self.config.get("management", {}).get("profit_target_pct", 0.25)

        if pl_pct >= target:
            from ..models.actions import ActionFactory

            return ActionFactory.create(
                "HARVEST", symbol, f"Pin Target Hit: {pl_pct:.1%} (Target: {target:.0%})"
            )
        return super().check_harvest(symbol, pl_pct, days_held)
