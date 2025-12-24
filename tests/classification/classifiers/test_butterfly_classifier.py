"""
Unit tests for ButterflyClassifier.
"""

from variance.classification.base import ClassificationContext
from variance.classification.classifiers.butterfly import ButterflyClassifier


def test_identifies_butterfly():
    legs = [
        {"Call/Put": "Call", "Quantity": "1", "Strike Price": "95", "Type": "Option"},
        {"Call/Put": "Call", "Quantity": "-2", "Strike Price": "100", "Type": "Option"},
        {"Call/Put": "Call", "Quantity": "1", "Strike Price": "105", "Type": "Option"},
        {"Call/Put": "Call", "Quantity": "0", "Strike Price": "0", "Type": "Option"}, # Dummy fourth leg for testing
    ]
    # Note: butterfly requires 4 legs in current implementation
    ctx = ClassificationContext.from_legs(legs)
    classifier = ButterflyClassifier()
    assert classifier.can_classify(legs, ctx) is True
    assert "Butterfly" in classifier.classify(legs, ctx)
