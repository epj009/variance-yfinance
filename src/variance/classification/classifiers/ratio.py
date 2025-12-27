"""
Ratio Strategy Classifier
"""

from variance.models.position import Position

from ..base import ClassificationContext, StrategyClassifier


class RatioClassifier(StrategyClassifier):
    """Identifies Ratio Spreads and ZEBRAs."""

    def can_classify(self, legs: list[Position], ctx: ClassificationContext) -> bool:
        if len(ctx.option_legs) != 2:
            return False
        return len(ctx.call_legs) == 2 or len(ctx.put_legs) == 2

    def classify(self, legs: list[Position], ctx: ClassificationContext) -> str:
        if len(ctx.call_legs) == 2 and ctx.short_calls:
            if ctx.long_call_qty == 2 and abs(ctx.short_call_qty) == 1:
                return "Call ZEBRA"
            if abs(ctx.short_call_qty) != ctx.long_call_qty:
                return "Ratio Spread (Call)"

        if len(ctx.put_legs) == 2 and ctx.short_puts:
            if ctx.long_put_qty == 2 and abs(ctx.short_put_qty) == 1:
                return "Put ZEBRA"
            if abs(ctx.short_put_qty) != ctx.long_put_qty:
                return "Ratio Spread (Put)"

        return "Custom/Combo"
