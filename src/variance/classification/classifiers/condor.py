"""
Condor Strategy Classifier
"""

from typing import Any, Dict, List
from ..base import ClassificationContext, StrategyClassifier


class CondorClassifier(StrategyClassifier):
    """Identifies Iron Condors and Iron Flies."""

    def can_classify(self, legs: List[Dict[str, Any]], ctx: ClassificationContext) -> bool:
        if len(ctx.option_legs) != 4:
            return False
        return (
            len(ctx.short_calls) == 1 and len(ctx.long_calls) == 1 and
            len(ctx.short_puts) == 1 and len(ctx.long_puts) == 1
        )

    def classify(self, legs: List[Dict[str, Any]], ctx: ClassificationContext) -> str:
        # Iron Fly check
        if ctx.short_call_strikes and ctx.short_put_strikes:
            if ctx.short_call_strikes[0] == ctx.short_put_strikes[0]:
                return "Iron Fly"

        # Width check
        call_width = abs(ctx.long_call_strikes[0] - ctx.short_call_strikes[0])
        put_width = abs(ctx.short_put_strikes[0] - ctx.long_put_strikes[0])
        if call_width != put_width:
            return "Dynamic Width Iron Condor"

        return "Iron Condor"
