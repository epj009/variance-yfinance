"""
Single Option Strategy Classifier
"""

from typing import Any

from ..base import ClassificationContext, StrategyClassifier


class SingleOptionClassifier(StrategyClassifier):
    """Identifies single-leg long or short options."""

    def can_classify(self, legs: list[dict[str, Any]], ctx: ClassificationContext) -> bool:
        return len(legs) == 1 and len(ctx.option_legs) == 1

    def classify(self, legs: list[dict[str, Any]], ctx: ClassificationContext) -> str:
        leg = ctx.option_legs[0]
        side = leg.get("Call/Put", "Option")
        qty = ctx.long_call_qty + ctx.short_call_qty + ctx.long_put_qty + ctx.short_put_qty

        prefix = "Long" if qty > 0 else "Short"
        return f"{prefix} {side}"
