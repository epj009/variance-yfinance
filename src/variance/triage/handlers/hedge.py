"""
Hedge Handler

Audits the utility of protective positions based on market environment and portfolio tilt.
"""

from variance.models.actions import ActionFactory
from variance.triage.handler import TriageHandler
from variance.triage.request import TriageRequest, TriageTag


class HedgeHandler(TriageHandler):
    """
    Handles verification of structural hedges.
    Flag positions that are 'Dead Money' (no P/L movement and low VRP).
    """

    def handle(self, request: TriageRequest) -> TriageRequest:
        # 1. Detect if this is a hedge
        # Qualifies if it's an Index and has negative delta
        is_index = request.sector == "Index"
        is_negative_delta = request.strategy_delta < -5

        if not (is_index and is_negative_delta):
            return self._pass_to_next(request)

        # 2. Check for 'Dead Money' state
        pl_low = self.rules.get("dead_money_pl_pct_low", -0.10)
        pl_high = self.rules.get("dead_money_pl_pct_high", 0.10)
        vrp_threshold = self.rules.get("dead_money_vrp_structural_threshold", 0.80)

        # If P/L is flat AND volatility is cheap, the hedge may be unnecessary
        is_flat_pl = request.pl_pct is not None and (pl_low <= request.pl_pct <= pl_high)
        is_cheap_vol = request.vrp_structural is not None and request.vrp_structural < vrp_threshold

        if is_flat_pl and is_cheap_vol:
            logic = f"Protective hedge on {request.root} is stagnant (Dead Money). Review utility."
            cmd = ActionFactory.create("Hedge_Check", request.root, logic)
            if cmd:
                tag = TriageTag(
                    tag_type="HEDGE_CHECK", priority=50, logic=cmd.logic, action_cmd=cmd
                )
                request = request.with_tag(tag)

        return self._pass_to_next(request)
