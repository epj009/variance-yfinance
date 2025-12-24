"""
Covered Strategy Classifier
"""

from typing import Any, Dict, List

from ..base import ClassificationContext, StrategyClassifier


class CoveredClassifier(StrategyClassifier):
    """Identifies Covered Calls, Puts, and collars."""

    def can_classify(self, legs: List[Dict[str, Any]], ctx: ClassificationContext) -> bool:
        return len(ctx.stock_legs) > 0 and len(ctx.option_legs) > 0

    def classify(self, legs: List[Dict[str, Any]], ctx: ClassificationContext) -> str:
        s_qty = ctx.stock_legs[0].get("Quantity", "0")

        if ctx.short_call_qty < 0 and ctx.short_put_qty < 0:
            return "Covered Strangle"
        if ctx.short_call_qty < 0:
            return "Covered Call"
        if ctx.short_put_qty < 0:
            return "Covered Put"
        if ctx.long_puts and ctx.short_calls:
            return "Collar"

        return "Custom/Combo"
