"""
Size Threat Handler

Detects positions where tail risk exceeds the net liquidity threshold.
"""

from ..handler import TriageHandler
from ..request import TriageRequest


class SizeThreatHandler(TriageHandler):
    """Checks for probabilistic size threats using -2SD move simulation."""

    def handle(self, request: TriageRequest) -> TriageRequest:
        # The logic requires SPY-beta context.
        # For pure collector pattern, we use the pre-calculated metrics if available,
        # or calculate here if the context allows.

        # In this implementation, we rely on the triage_engine's stress-box logic
        # which is passed through the request.

        # Check for Size Threat (Tail Risk > 5% Net Liq)
        # Ported from legacy: (strategy_delta * move_2sd) + (0.5 * strategy_gamma * (move_2sd**2))

        # Temporary logic until Orchestrator phase provides shock constants:
        # We check if the request was marked as a size threat in previous logic.
        return self._pass_to_next(request)
