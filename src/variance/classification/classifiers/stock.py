"""
Stock Strategy Classifier
"""

from typing import Any

from ..base import ClassificationContext, StrategyClassifier


class StockClassifier(StrategyClassifier):
    """Identifies pure stock positions."""

    def can_classify(self, legs: list[dict[str, Any]], ctx: ClassificationContext) -> bool:
        return len(legs) == 1 and len(ctx.stock_legs) == 1

    def classify(self, legs: list[dict[str, Any]], ctx: ClassificationContext) -> str:
        return "Stock"
