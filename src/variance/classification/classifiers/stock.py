"""
Stock Strategy Classifier
"""

from variance.models.position import Position

from ..base import ClassificationContext, StrategyClassifier


class StockClassifier(StrategyClassifier):
    """Identifies pure stock positions."""

    def can_classify(self, legs: list[Position], ctx: ClassificationContext) -> bool:
        return len(legs) == 1 and len(ctx.stock_legs) == 1

    def classify(self, legs: list[Position], ctx: ClassificationContext) -> str:
        return "Stock"
