"""
Unit tests for LizardClassifier.
"""

from variance.classification.base import ClassificationContext
from variance.classification.classifiers.lizard import LizardClassifier


def test_identifies_jade_lizard():
    legs = [
        {"Call/Put": "Put", "Quantity": "-1", "Strike Price": "90", "Type": "Option"},
        {"Call/Put": "Call", "Quantity": "-1", "Strike Price": "110", "Type": "Option"},
        {"Call/Put": "Call", "Quantity": "1", "Strike Price": "115", "Type": "Option"},
    ]
    ctx = ClassificationContext.from_legs(legs)
    classifier = LizardClassifier()
    assert classifier.can_classify(legs, ctx) is True
    assert classifier.classify(legs, ctx) == "Jade Lizard"
