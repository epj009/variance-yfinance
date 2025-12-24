"""
Size Threat Handler for Triage Engine.

Detects positions with tail risk (max potential loss) exceeding a configurable
percentage of net liquidity. Default threshold: 5% of NLV.

This prevents portfolio blow-up scenarios from oversized positions.
"""

from typing import Any

from variance.models.actions import ActionFactory
from variance.triage.handler import TriageHandler
from variance.triage.request import TriageRequest, TriageTag


class SizeThreatHandler(TriageHandler):
    """
    Detects positions with tail risk exceeding NLV threshold.

    Priority: 20 (High priority - above defense/gamma)
    Actionable: Yes (reduce position size)
    """

    def __init__(self, rules: dict[str, Any]) -> None:
        """
        Initialize handler with trading rules.

        Args:
            rules: Dictionary containing 'size_threat_pct' (default: 0.05)
        """
        super().__init__(rules)
        self.threshold = rules.get("size_threat_pct", 0.05)

    def handle(self, request: TriageRequest) -> TriageRequest:
        """
        Check for tail risk exceeding threshold and add tag if triggered.

        Args:
            request: Immutable triage request with position metrics

        Returns:
            New TriageRequest with SIZE_THREAT tag added if condition met
        """
        # Only check losing positions (tail risk only applies to losses)
        if request.net_pl >= 0:
            return self._pass_to_next(request)

        # Calculate tail risk percentage
        tail_risk_pct = self._calculate_tail_risk_pct(request)

        if tail_risk_pct is None:
            return self._pass_to_next(request)

        # Check if tail risk exceeds threshold
        if tail_risk_pct > self.threshold:
            logic = self._build_logic_message(tail_risk_pct, request)
            cmd = ActionFactory.create("SIZE_THREAT", request.root, logic)
            if cmd:
                tag = TriageTag(
                    tag_type="SIZE_THREAT", priority=20, logic=cmd.logic, action_cmd=cmd
                )
                request = request.with_tag(tag)

        return self._pass_to_next(request)

    def _calculate_tail_risk_pct(self, request: TriageRequest) -> float | None:
        """
        Calculate tail risk as percentage of net liquidity.
        Uses the same formula as the stress-box scenario in analyze_portfolio.py.
        """
        if request.net_liquidity <= 0:
            return None

        # Determine max potential loss based on position type
        max_loss = self._estimate_max_loss(request)

        if max_loss <= 0:
            return None

        # Calculate percentage of net liquidity
        return abs(max_loss) / request.net_liquidity

    def _estimate_max_loss(self, request: TriageRequest) -> float:
        """
        Estimate maximum potential loss for the position.

        For credit positions (net_cost < 0): We use the actual credit collected
        as a proxy for the 'at-risk' capital in standard triage.
        """
        # Credit position: Max loss is often tied to credit collected or spread width
        if request.net_cost < 0:
            return abs(request.net_cost)

        # Debit position: Max loss is the debit paid
        if request.net_cost > 0:
            return abs(request.net_cost)

        return 0.0

    def _build_logic_message(self, tail_risk_pct: float, request: TriageRequest) -> str:
        """Build human-readable explanation of tail risk."""
        pct_display = f"{tail_risk_pct * 100:.1f}%"
        nlv_display = f"${request.net_liquidity:,.0f}"
        max_loss_display = f"${self._estimate_max_loss(request):,.0f}"

        return (
            f"Tail risk {pct_display} of NLV ({max_loss_display} / {nlv_display}) "
            f"exceeds {self.threshold * 100:.0f}% threshold"
        )
