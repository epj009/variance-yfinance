"""
Unit tests for RatioClassifier.
"""

import pytest
from variance.classification.classifiers.ratio import RatioClassifier
from variance.classification.base import ClassificationContext


def test_identifies_ratio_spread():
    legs = [
        {"Call/Put": "Call", "Quantity": "1", "Strike Price": "100", "Type": "Option"},
        {"Call/Put": "Call", "Quantity": "-2", "Strike Price": "110", "Type": "Option"},
    ]
    ctx = ClassificationContext.from_legs(legs)
    classifier = RatioClassifier()
    assert classifier.can_classify(legs, ctx) is True
    assert classifier.classify(legs, ctx) == "Ratio Spread (Call)"

def test_identifies_zebra():
    legs = [
        {"Call/Put": "Call", "Quantity": "2", "Strike Price": "100", "Type": "Option"},
        {"Call/Put": "Call", "Quantity": "-1", "Strike Price": "110", "Type": "Option"},
    ]
    ctx = ClassificationContext.from_legs(legs)
    classifier = RatioClassifier()
    assert classifier.can_classify(legs, ctx) is True
    assert classifier.classify(legs, ctx) == "Call ZEBRA"
