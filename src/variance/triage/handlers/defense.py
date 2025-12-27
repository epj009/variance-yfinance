"""
Defense Handler

Detects tested positions within the gamma trigger window that require rolling or adjustment.
"""

from variance.models.actions import ActionFactory
from variance.triage.handler import TriageHandler
from variance.triage.request import TriageRequest, TriageTag


class DefenseHandler(TriageHandler[TriageRequest]):
    """Handles logic for defending tested/breached positions."""

    def handle(self, request: TriageRequest) -> TriageRequest:
        # Check if strategy is tested (delegate to strategy object)
        is_tested = request.strategy_obj.is_tested(list(request.legs), request.price)

        # Defense trigger: Tested AND within Gamma Window
        if is_tested and request.dte <= request.strategy_obj.gamma_trigger_dte and request.dte > 0:
            logic = f"Tested & <= {request.strategy_obj.gamma_trigger_dte} DTE"
            cmd = ActionFactory.create("DEFENSE", request.root, logic)
            if cmd:
                tag = TriageTag(
                    tag_type="DEFENSE",
                    priority=30,
                    logic=cmd.logic,
                    action_cmd=cmd,
                )
                request = request.with_tag(tag)

        return self._pass_to_next(request)
