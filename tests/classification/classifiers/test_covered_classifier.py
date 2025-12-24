"""
Unit tests for CoveredClassifier.
"""

from variance.classification.base import ClassificationContext
from variance.classification.classifiers.covered import CoveredClassifier


def test_identifies_covered_call():
    legs = [
        {"Symbol": "AAPL", "Type": "Stock", "Quantity": "100"},
        {
            "Symbol": "AAPL",
            "Type": "Option",
            "Call/Put": "Call",
            "Quantity": "-1",
            "Strike Price": "160",
        },
    ]
    ctx = ClassificationContext.from_legs(legs)
    classifier = CoveredClassifier()
    assert classifier.can_classify(legs, ctx) is True
    assert classifier.classify(legs, ctx) == "Covered Call"
