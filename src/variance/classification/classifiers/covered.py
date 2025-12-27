"""
Covered Strategy Classifier
"""

from variance.models.position import Position

from ..base import ClassificationContext, StrategyClassifier


class CoveredClassifier(StrategyClassifier):
    """Identifies Covered Calls, Puts, and collars."""

    def can_classify(self, legs: list[Position], ctx: ClassificationContext) -> bool:
        return len(ctx.stock_legs) > 0 and len(ctx.option_legs) > 0

    def classify(self, legs: list[Position], ctx: ClassificationContext) -> str:
        _ = ctx.stock_legs[0].quantity

        if ctx.short_call_qty < 0 and ctx.short_put_qty < 0:
            return "Covered Strangle"
        if ctx.short_call_qty < 0:
            return "Covered Call"
        if ctx.short_put_qty < 0:
            return "Covered Put"
        if ctx.long_puts and ctx.short_calls:
            return "Collar"

        return "Custom/Combo"
