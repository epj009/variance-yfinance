"""
Unit tests for CondorClassifier.
"""

import pytest

from variance.classification.base import ClassificationContext
from variance.classification.classifiers.condor import CondorClassifier


class TestCondorClassifier:
    @pytest.fixture
    def classifier(self):
        return CondorClassifier()

    def test_identifies_iron_condor(self, classifier):
        legs = [
            {"Call/Put": "Call", "Quantity": "-1", "Strike Price": "100", "Exp Date": "2026-01-23", "Type": "Option"},
            {"Call/Put": "Call", "Quantity": "1", "Strike Price": "105", "Exp Date": "2026-01-23", "Type": "Option"},
            {"Call/Put": "Put", "Quantity": "-1", "Strike Price": "95", "Exp Date": "2026-01-23", "Type": "Option"},
            {"Call/Put": "Put", "Quantity": "1", "Strike Price": "90", "Exp Date": "2026-01-23", "Type": "Option"},
        ]
        ctx = ClassificationContext.from_legs(legs)
        assert classifier.can_classify(legs, ctx) is True
        assert classifier.classify(legs, ctx) == "Iron Condor"

    def test_identifies_iron_fly(self, classifier):
        legs = [
            {"Call/Put": "Call", "Quantity": "-1", "Strike Price": "100", "Exp Date": "2026-01-23", "Type": "Option"},
            {"Call/Put": "Call", "Quantity": "1", "Strike Price": "105", "Exp Date": "2026-01-23", "Type": "Option"},
            {"Call/Put": "Put", "Quantity": "-1", "Strike Price": "100", "Exp Date": "2026-01-23", "Type": "Option"},
            {"Call/Put": "Put", "Quantity": "1", "Strike Price": "95", "Exp Date": "2026-01-23", "Type": "Option"},
        ]
        ctx = ClassificationContext.from_legs(legs)
        assert classifier.classify(legs, ctx) == "Iron Fly"
