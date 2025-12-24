"""
Defense Handler

Detects tested positions within the gamma trigger window that require rolling or adjustment.
"""

from ...models.actions import ActionFactory
from ..handler import TriageHandler
from ..request import TriageRequest, TriageTag


class DefenseHandler(TriageHandler):
    """Handles logic for defending tested/breached positions."""

    def handle(self, request: TriageRequest) -> TriageRequest:
        # Check if strategy is tested (delegate to strategy object)
        # Ensure legs is a list for backward compatibility with some strategy methods
        legs_list = list(request.legs)
        is_tested = request.strategy_obj.is_tested(legs_list, request.price)

        # Defense trigger: Tested AND within Gamma Window
        if is_tested and request.dte < request.strategy_obj.gamma_trigger_dte and request.dte > 0:
            logic = f"Tested & < {request.strategy_obj.gamma_trigger_dte} DTE"
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
