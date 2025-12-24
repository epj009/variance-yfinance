"""
Classifier Registry

Manages the explicit chain of strategy classifiers.
"""

from typing import Any, Dict, List, Optional

from .base import ClassificationContext, StrategyClassifier
from .classifiers.stock import StockClassifier
from .classifiers.single_option import SingleOptionClassifier
from .classifiers.covered import CoveredClassifier
from .classifiers.multi_exp import MultiExpClassifier
from .classifiers.condor import CondorClassifier
from .classifiers.butterfly import ButterflyClassifier
from .classifiers.lizard import LizardClassifier
from .classifiers.ratio import RatioClassifier
from .classifiers.vertical import VerticalClassifier
from .classifiers.strangle import StrangleClassifier


class ClassifierChain:
    """Executes classifiers in explicit priority order."""

    def __init__(self):
        # Explicit priority order (Clinical Order: Simple -> Complex)
        self._chain: List[StrategyClassifier] = [
            StockClassifier(),
            SingleOptionClassifier(),
            StrangleClassifier(),
            VerticalClassifier(),
            CoveredClassifier(),
            MultiExpClassifier(),
            CondorClassifier(),
            ButterflyClassifier(),
            LizardClassifier(),
            RatioClassifier(),
        ]

    def classify(self, legs: List[Dict[str, Any]]) -> str:
        """
        Classifies legs using the chain. First match wins.
        """
        if not legs:
            return "Empty"

        ctx = ClassificationContext.from_legs(legs)

        for classifier in self._chain:
            if classifier.can_classify(legs, ctx):
                return classifier.classify(legs, ctx)

        return "Custom/Combo"
