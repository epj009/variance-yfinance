"""
Triage Chain Orchestrator

Explicitly builds and executes the sequence of triage handlers.
"""

from typing import Any, Optional

from variance.triage.handler import TriageHandler
from variance.triage.handlers.defense import DefenseHandler
from variance.triage.handlers.earnings import EarningsHandler
from variance.triage.handlers.expiration import ExpirationHandler
from variance.triage.handlers.gamma import GammaHandler
from variance.triage.handlers.harvest import HarvestHandler
from variance.triage.handlers.hedge import HedgeHandler
from variance.triage.handlers.scalable import ScalableHandler
from variance.triage.handlers.size_threat import SizeThreatHandler
from variance.triage.handlers.toxic_theta import ToxicThetaHandler
from variance.triage.request import TriageRequest


class TriageChain:
    """Builds and executes the triage handler chain using explicit orchestration."""

    def __init__(self, rules: dict[str, Any]):
        self.rules = rules
        self._head: Optional[TriageHandler[TriageRequest]] = None
        self._build_chain()

    def _build_chain(self) -> None:
        """Builds the chain in explicit priority order. No decorators required."""

        # 1. Define the sequence (Ordered by institutional priority)
        handlers = [
            ExpirationHandler(self.rules),
            HarvestHandler(self.rules),
            SizeThreatHandler(self.rules),
            DefenseHandler(self.rules),
            GammaHandler(self.rules),
            HedgeHandler(self.rules),
            ToxicThetaHandler(self.rules),
            EarningsHandler(self.rules),
            ScalableHandler(self.rules),
        ]

        if not handlers:
            return

        # 2. Link the chain
        self._head = handlers[0]
        current = self._head
        for handler in handlers[1:]:
            current = current.set_next(handler)

    def triage(self, request: TriageRequest) -> TriageRequest:
        """Execute the chain and return the final request with tags populated."""
        if self._head:
            return self._head.handle(request)
        return request
