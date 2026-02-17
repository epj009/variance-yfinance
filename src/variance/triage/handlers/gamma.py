"""
Gamma Handler

Detects positions approaching expiration that are not yet tested but carry high gamma risk.
"""

from variance.models.actions import ActionFactory
from variance.triage.handler import TriageHandler
from variance.triage.request import TriageRequest, TriageTag


class GammaHandler(TriageHandler[TriageRequest]):
    """Handles alerts for low-DTE positions not currently under pressure."""

    def handle(self, request: TriageRequest) -> TriageRequest:
        # Check if already tested (that's Defense territory)
        is_tested = request.strategy_obj.is_tested(request.legs, request.price)

        # Gamma trigger: Not tested AND within window AND not expiring today
        if not is_tested and 0 < request.dte <= request.strategy_obj.gamma_trigger_dte:
            logic = f"<= {request.strategy_obj.gamma_trigger_dte} DTE Risk"
            cmd = ActionFactory.create("GAMMA", request.root, logic)
            if cmd:
                tag = TriageTag(
                    tag_type="GAMMA",
                    priority=40,
                    logic=cmd.logic,
                    action_cmd=cmd,
                )
                request = request.with_tag(tag)

        return self._pass_to_next(request)
