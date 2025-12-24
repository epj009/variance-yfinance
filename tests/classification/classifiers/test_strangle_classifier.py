"""
Unit tests for StrangleClassifier.
"""

import pytest

from variance.classification.base import ClassificationContext
from variance.classification.classifiers.strangle import StrangleClassifier


class TestStrangleClassifier:
    @pytest.fixture
    def classifier(self):
        return StrangleClassifier()

    def test_identifies_short_strangle(self, classifier):
        legs = [
            {
                "Call/Put": "Call",
                "Quantity": "-1",
                "Strike Price": "110",
                "Exp Date": "2026-01-23",
                "Type": "Option",
            },
            {
                "Call/Put": "Put",
                "Quantity": "-1",
                "Strike Price": "90",
                "Exp Date": "2026-01-23",
                "Type": "Option",
            },
        ]
        ctx = ClassificationContext.from_legs(legs)
        assert classifier.can_classify(legs, ctx) is True
        assert classifier.classify(legs, ctx) == "Short Strangle"

    def test_identifies_short_straddle(self, classifier):
        legs = [
            {
                "Call/Put": "Call",
                "Quantity": "-1",
                "Strike Price": "100",
                "Exp Date": "2026-01-23",
                "Type": "Option",
            },
            {
                "Call/Put": "Put",
                "Quantity": "-1",
                "Strike Price": "100",
                "Exp Date": "2026-01-23",
                "Type": "Option",
            },
        ]
        ctx = ClassificationContext.from_legs(legs)
        assert classifier.classify(legs, ctx) == "Short Straddle"
