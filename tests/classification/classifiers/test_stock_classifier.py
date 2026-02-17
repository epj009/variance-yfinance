"""
Unit tests for StockClassifier.
"""

from variance.classification.base import ClassificationContext
from variance.classification.classifiers.stock import StockClassifier
from variance.models import Position


def test_identifies_pure_stock():
    legs = [Position.from_row({"Symbol": "AAPL", "Type": "Stock", "Quantity": "100"})]
    ctx = ClassificationContext.from_legs(legs)
    classifier = StockClassifier()
    assert classifier.can_classify(legs, ctx) is True
    assert classifier.classify(legs, ctx) == "Stock"


def test_rejects_options():
    legs = [
        Position.from_row({"Symbol": "AAPL", "Type": "Option", "Call/Put": "Call", "Quantity": "1"})
    ]
    ctx = ClassificationContext.from_legs(legs)
    classifier = StockClassifier()
    assert classifier.can_classify(legs, ctx) is False
