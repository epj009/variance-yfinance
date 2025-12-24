"""
Unit tests for StockClassifier.
"""

from variance.classification.base import ClassificationContext
from variance.classification.classifiers.stock import StockClassifier


def test_identifies_pure_stock():
    legs = [{"Symbol": "AAPL", "Type": "Stock", "Quantity": "100"}]
    ctx = ClassificationContext.from_legs(legs)
    classifier = StockClassifier()
    assert classifier.can_classify(legs, ctx) is True
    assert classifier.classify(legs, ctx) == "Stock"


def test_rejects_options():
    legs = [{"Symbol": "AAPL", "Type": "Option", "Call/Put": "Call", "Quantity": "1"}]
    ctx = ClassificationContext.from_legs(legs)
    classifier = StockClassifier()
    assert classifier.can_classify(legs, ctx) is False
