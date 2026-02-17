"""
Unit tests for SingleOptionClassifier.
"""

from variance.classification.base import ClassificationContext
from variance.classification.classifiers.single_option import SingleOptionClassifier
from variance.models import Position


def test_identifies_long_call():
    legs = [Position.from_row({"Call/Put": "Call", "Quantity": "1", "Type": "Option"})]
    ctx = ClassificationContext.from_legs(legs)
    classifier = SingleOptionClassifier()
    assert classifier.can_classify(legs, ctx) is True
    assert classifier.classify(legs, ctx) == "Long Call"


def test_identifies_short_put():
    legs = [Position.from_row({"Call/Put": "Put", "Quantity": "-1", "Type": "Option"})]
    ctx = ClassificationContext.from_legs(legs)
    classifier = SingleOptionClassifier()
    assert classifier.classify(legs, ctx) == "Short Put"
