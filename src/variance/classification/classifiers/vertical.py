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
        return (len(ctx.call_legs) == 2 and len(ctx.short_calls) == 1) or (
            len(ctx.put_legs) == 2 and len(ctx.short_puts) == 1
        )

    def classify(self, legs: list[dict[str, Any]], ctx: ClassificationContext) -> str:
        side = "Call" if ctx.call_legs else "Put"
        return f"Vertical Spread ({side})"
