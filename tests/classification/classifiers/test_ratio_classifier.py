"""
Unit tests for RatioClassifier.
"""

from variance.classification.base import ClassificationContext
from variance.classification.classifiers.ratio import RatioClassifier
from variance.models import Position


def test_identifies_ratio_spread():
    legs = [
        Position.from_row(
            {"Call/Put": "Call", "Quantity": "1", "Strike Price": "100", "Type": "Option"}
        ),
        Position.from_row(
            {"Call/Put": "Call", "Quantity": "-2", "Strike Price": "110", "Type": "Option"}
        ),
    ]
    ctx = ClassificationContext.from_legs(legs)
    classifier = RatioClassifier()
    assert classifier.can_classify(legs, ctx) is True
    assert classifier.classify(legs, ctx) == "Ratio Spread (Call)"


def test_identifies_zebra():
    legs = [
        Position.from_row(
            {"Call/Put": "Call", "Quantity": "2", "Strike Price": "100", "Type": "Option"}
        ),
        Position.from_row(
            {"Call/Put": "Call", "Quantity": "-1", "Strike Price": "110", "Type": "Option"}
        ),
    ]
    ctx = ClassificationContext.from_legs(legs)
    classifier = RatioClassifier()
    assert classifier.can_classify(legs, ctx) is True
    assert classifier.classify(legs, ctx) == "Call ZEBRA"
