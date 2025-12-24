"""
Unit tests for MultiExpClassifier.
"""

import pytest
from variance.classification.classifiers.multi_exp import MultiExpClassifier
from variance.classification.base import ClassificationContext


def test_identifies_calendar_spread():
    legs = [
        {"Call/Put": "Call", "Quantity": "-1", "Strike Price": "150", "Exp Date": "2026-01-23", "Type": "Option"},
        {"Call/Put": "Call", "Quantity": "1", "Strike Price": "150", "Exp Date": "2026-02-20", "Type": "Option"}
    ]
    ctx = ClassificationContext.from_legs(legs)
    classifier = MultiExpClassifier()
    assert classifier.can_classify(legs, ctx) is True
    assert classifier.classify(legs, ctx) == "Calendar Spread (Call)"
