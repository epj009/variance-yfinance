"""
Unit tests for SingleOptionClassifier.
"""

from variance.classification.base import ClassificationContext
from variance.classification.classifiers.single_option import SingleOptionClassifier


def test_identifies_long_call():
    legs = [{"Call/Put": "Call", "Quantity": "1", "Type": "Option"}]
    ctx = ClassificationContext.from_legs(legs)
    classifier = SingleOptionClassifier()
    assert classifier.can_classify(legs, ctx) is True
    assert classifier.classify(legs, ctx) == "Long Call"

def test_identifies_short_put():
    legs = [{"Call/Put": "Put", "Quantity": "-1", "Type": "Option"}]
    ctx = ClassificationContext.from_legs(legs)
    classifier = SingleOptionClassifier()
    assert classifier.classify(legs, ctx) == "Short Put"
