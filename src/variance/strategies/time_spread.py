"""
Time Spread Strategy Class

Handles logic for Calendar and Diagonal spreads (Long Vega / Short Theta).
"""

from typing import Any, Optional

from ..portfolio_parser import is_stock_type, parse_currency
from .base import BaseStrategy


@BaseStrategy.register("time_spread")
class TimeSpreadStrategy(BaseStrategy):
    """
    Handles strategies that exploit horizontal or diagonal skew.
    Primary focus: Managing the front-month short strike.
    """

    def is_tested(self, legs: list[dict[str, Any]], underlying_price: float) -> bool:
        """
        Calendar/Diagonal is tested if the front-month short strike is breached.
        """
        # Find the short leg (usually the front month)
        for leg in legs:
            qty = float(parse_currency(leg.get("Quantity", "0")))
            if qty < 0:
                otype = leg.get("Call/Put")
                strike = float(parse_currency(leg.get("Strike Price", "0")))
                
                if otype == "Call" and underlying_price > strike:
                    return True
                if otype == "Put" and underlying_price < strike:
                    return True
        return False

    def check_harvest(self, symbol: str, pl_pct: float, days_held: int) -> Optional[Any]:
        """
        Calendars have a lower standard profit target (usually 25%).
        """
        target = self.config.get("management", {}).get("profit_target_pct", 0.25)
        
        if pl_pct >= target:
            from ..models.actions import ActionFactory
            return ActionFactory.create(
                "HARVEST", 
                symbol, 
                f"Time Spread Target: {pl_pct:.1%} (Target: {target:.0%})"
            )
        return super().check_harvest(symbol, pl_pct, days_held)
