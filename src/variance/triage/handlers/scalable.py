"""
Scalable Handler

Detects VRP momentum surges that represent high-alpha entry or scaling opportunities.
"""

from variance.models.actions import ActionFactory
from variance.triage.handler import TriageHandler
from variance.triage.request import TriageRequest, TriageTag


class ScalableHandler(TriageHandler):
    """Handles detection of VRP momentum surges."""

    def handle(self, request: TriageRequest) -> TriageRequest:
        # Don't scale if we already have critical alerts
        if request.tags:
            # We allow scaling if only informational tags exist, but prioritize warnings
            if any(t.priority < 50 for t in request.tags):
                return self._pass_to_next(request)

        # Ported logic:
        # If pl_pct < target AND VRP Tactical > VRP Structural * 1.5
        if request.vrp_structural and request.vrp_tactical:
            markup = (request.vrp_tactical / request.vrp_structural) - 1
            if markup > self.rules.get("vrp_momentum_threshold", 0.50):
                logic = f"VRP Surge: Tactical markup ({request.vrp_tactical:.2f}) is significantly above trend. High Alpha Opportunity."
                cmd = ActionFactory.create("SCALABLE", request.root, logic)
                if cmd:
                    tag = TriageTag(
                        tag_type="SCALABLE",
                        priority=80,
                        logic=cmd.logic,
                        action_cmd=cmd,
                    )
                    request = request.with_tag(tag)

        return self._pass_to_next(request)
