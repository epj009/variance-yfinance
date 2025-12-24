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


class SizeThreatHandler(TriageHandler[TriageRequest]):
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

        max_loss = self._estimate_max_loss(request)

        if max_loss == 0:
            return None

        # Calculate percentage of net liquidity
        return abs(max_loss) / request.net_liquidity

    def _estimate_max_loss(self, request: TriageRequest) -> float:
        """
        Estimate maximum potential loss for the position.

        Uses a -2SD move against the beta-weighted index when available,
        otherwise falls back to current P/L as a simple tail proxy.
        """
        if request.beta_price is not None and request.beta_iv is not None:
            # 1-day expected move (1SD)
            em_1sd = request.beta_price * (request.beta_iv / 100.0 / 15.87)
            move_2sd = em_1sd * -2.0
            delta_pl = request.strategy_delta * move_2sd
            gamma_pl = 0.5 * request.strategy_gamma * (move_2sd**2)
            return delta_pl + gamma_pl

        if request.net_pl < 0:
            return abs(request.net_pl)

        return 0.0

    def _build_logic_message(self, tail_risk_pct: float, request: TriageRequest) -> str:
        """Build human-readable explanation of tail risk."""
        pct_display = f"{tail_risk_pct * 100:.1f}%"
        return f"Tail Risk: {pct_display} of Net Liq in -2SD move"
