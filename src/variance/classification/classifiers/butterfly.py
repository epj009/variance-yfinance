"""
Butterfly Strategy Classifier
"""

from typing import Any, Dict, List

from ..base import ClassificationContext, StrategyClassifier


class ButterflyClassifier(StrategyClassifier):
    """Identifies Butterflies and Broken Wing variants."""

    def can_classify(self, legs: List[Dict[str, Any]], ctx: ClassificationContext) -> bool:
        return len(ctx.option_legs) == 4 and (len(ctx.call_legs) == 4 or len(ctx.put_legs) == 4)

    def classify(self, legs: List[Dict[str, Any]], ctx: ClassificationContext) -> str:
        side = "Call" if ctx.call_legs else "Put"

        # Simple butterfly has 1-2-1 ratio
        short_qty = ctx.short_call_qty if side == "Call" else ctx.short_put_qty
        long_qty = ctx.long_call_qty if side == "Call" else ctx.long_put_qty

        if abs(short_qty) == 2 and long_qty == 2:
            return f"Butterfly ({side})"

        return f"Custom {side} Butterfly"
