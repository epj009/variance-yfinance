"""
Unit tests for LizardClassifier.
"""

from variance.classification.base import ClassificationContext
from variance.classification.classifiers.lizard import LizardClassifier
from variance.models import Position


def test_identifies_jade_lizard():
    legs = [
        Position.from_row(
            {"Call/Put": "Put", "Quantity": "-1", "Strike Price": "90", "Type": "Option"}
        ),
        Position.from_row(
            {"Call/Put": "Call", "Quantity": "-1", "Strike Price": "110", "Type": "Option"}
        ),
        Position.from_row(
            {"Call/Put": "Call", "Quantity": "1", "Strike Price": "115", "Type": "Option"}
        ),
    ]
    ctx = ClassificationContext.from_legs(legs)
    classifier = LizardClassifier()
    assert classifier.can_classify(legs, ctx) is True
    assert classifier.classify(legs, ctx) == "Jade Lizard"
