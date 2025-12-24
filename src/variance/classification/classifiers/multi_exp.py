"""
Multi-Expiry Strategy Classifier
"""

from typing import Any, Dict, List
from ..base import ClassificationContext, StrategyClassifier


class MultiExpClassifier(StrategyClassifier):
    """Identifies Calendars and Diagonals."""

    def can_classify(self, legs: List[Dict[str, Any]], ctx: ClassificationContext) -> bool:
        return ctx.is_multi_exp and len(ctx.option_legs) == 2

    def classify(self, legs: List[Dict[str, Any]], ctx: ClassificationContext) -> str:
        if len(ctx.call_legs) == 2:
            if ctx.long_call_strikes == ctx.short_call_strikes:
                return "Calendar Spread (Call)"
            return "Diagonal Spread (Call)"
        if len(ctx.put_legs) == 2:
            if ctx.long_put_strikes == ctx.short_put_strikes:
                return "Calendar Spread (Put)"
            return "Diagonal Spread (Put)"
            
        return "Multi-Exp Combo"
