"""
Vertical Strategy Classifier
"""

from typing import Any

from ..base import ClassificationContext, StrategyClassifier


class VerticalClassifier(StrategyClassifier):
    """Identifies simple vertical spreads."""

    def can_classify(self, legs: list[dict[str, Any]], ctx: ClassificationContext) -> bool:
        if len(ctx.option_legs) != 2:
            return False
        if ctx.is_multi_exp:
            return False
        if len(ctx.call_legs) == 2 and len(ctx.short_calls) == 1:
            return abs(ctx.short_call_qty) == ctx.long_call_qty
        if len(ctx.put_legs) == 2 and len(ctx.short_puts) == 1:
            return abs(ctx.short_put_qty) == ctx.long_put_qty
        return False

    def classify(self, legs: list[dict[str, Any]], ctx: ClassificationContext) -> str:
        side = "Call" if ctx.call_legs else "Put"
        return f"Vertical Spread ({side})"
