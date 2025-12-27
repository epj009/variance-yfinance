"""
Unit tests for VerticalClassifier.
"""

from variance.classification.base import ClassificationContext
from variance.classification.classifiers.vertical import VerticalClassifier
from variance.models import Position


def test_identifies_vertical_spread():
    legs = [
        Position.from_row(
            {"Call/Put": "Call", "Quantity": "-1", "Strike Price": "100", "Type": "Option"}
        ),
        Position.from_row(
            {"Call/Put": "Call", "Quantity": "1", "Strike Price": "105", "Type": "Option"}
        ),
    ]
    ctx = ClassificationContext.from_legs(legs)
    classifier = VerticalClassifier()
    assert classifier.can_classify(legs, ctx) is True
    assert classifier.classify(legs, ctx) == "Vertical Spread (Call)"
