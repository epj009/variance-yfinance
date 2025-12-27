"""
Single Option Strategy Classifier
"""

from variance.models.position import Position

from ..base import ClassificationContext, StrategyClassifier


class SingleOptionClassifier(StrategyClassifier):
    """Identifies single-leg long or short options."""

    def can_classify(self, legs: list[Position], ctx: ClassificationContext) -> bool:
        return len(legs) == 1 and len(ctx.option_legs) == 1

    def classify(self, legs: list[Position], ctx: ClassificationContext) -> str:
        leg = ctx.option_legs[0]
        side = leg.call_put or "Option"
        qty = ctx.long_call_qty + ctx.short_call_qty + ctx.long_put_qty + ctx.short_put_qty

        prefix = "Long" if qty > 0 else "Short"
        return f"{prefix} {side}"
