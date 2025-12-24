"""
Ratio Strategy Classifier
"""

from typing import Any, Dict, List

from ..base import ClassificationContext, StrategyClassifier


class RatioClassifier(StrategyClassifier):
    """Identifies Ratio Spreads and ZEBRAs."""

    def can_classify(self, legs: List[Dict[str, Any]], ctx: ClassificationContext) -> bool:
        return len(ctx.option_legs) == 2 or len(ctx.option_legs) == 3

    def classify(self, legs: List[Dict[str, Any]], ctx: ClassificationContext) -> str:
        # ZEBRA (3-leg) - Check higher complexity first
        if len(ctx.option_legs) == 3:
            if len(ctx.call_legs) == 3 and ctx.long_call_qty == 2 and abs(ctx.short_call_qty) == 1:
                return "Call ZEBRA"
            if len(ctx.put_legs) == 3 and ctx.long_put_qty == 2 and abs(ctx.short_put_qty) == 1:
                return "Put ZEBRA"

        # 2-Leg Ratio
        if len(ctx.option_legs) == 2:
            if len(ctx.call_legs) == 2 and abs(ctx.short_call_qty) != ctx.long_call_qty:
                return "Ratio Spread (Call)"
            if len(ctx.put_legs) == 2 and abs(ctx.short_put_qty) != ctx.long_put_qty:
                return "Ratio Spread (Put)"

        return "Custom Combo"
