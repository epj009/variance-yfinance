"""
Strangle Strategy Classifier
"""

from variance.models.position import Position

from ..base import ClassificationContext, StrategyClassifier


class StrangleClassifier(StrategyClassifier):
    """Identifies Strangles and Straddles."""

    def can_classify(self, legs: list[Position], ctx: ClassificationContext) -> bool:
        return len(ctx.option_legs) == 2 and len(ctx.short_calls) == 1 and len(ctx.short_puts) == 1

    def classify(self, legs: list[Position], ctx: ClassificationContext) -> str:
        if ctx.short_call_strikes == ctx.short_put_strikes:
            return "Short Straddle"
        return "Short Strangle"
