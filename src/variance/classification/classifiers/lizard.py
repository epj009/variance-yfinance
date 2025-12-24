"""
Lizard Strategy Classifier
"""

from typing import Any, Dict, List

from ..base import ClassificationContext, StrategyClassifier


class LizardClassifier(StrategyClassifier):
    """Identifies Jade and Big Lizards."""

    def can_classify(self, legs: List[Dict[str, Any]], ctx: ClassificationContext) -> bool:
        return len(ctx.option_legs) == 3

    def classify(self, legs: List[Dict[str, Any]], ctx: ClassificationContext) -> str:
        # Jade Lizard: Short Put + Call Credit Spread
        if len(ctx.short_puts) == 1 and len(ctx.short_calls) == 1 and len(ctx.long_calls) == 1:
            return "Jade Lizard"
        # Reverse Jade Lizard: Short Call + Put Credit Spread
        if len(ctx.short_calls) == 1 and len(ctx.short_puts) == 1 and len(ctx.long_puts) == 1:
            return "Reverse Jade Lizard"

        return "Three-Leg Combo"
