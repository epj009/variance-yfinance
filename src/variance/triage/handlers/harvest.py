"""
Harvest Handler

Detects profit-taking opportunities based on strategy targets.
"""

from variance.triage.handler import TriageHandler
from variance.triage.request import TriageRequest, TriageTag


class HarvestHandler(TriageHandler[TriageRequest]):
    """Handles profit harvesting logic."""

    def handle(self, request: TriageRequest) -> TriageRequest:
        # Only check credit positions (selling premium)
        if request.net_cost >= 0:
            return self._pass_to_next(request)

        if request.pl_pct is None:
            return self._pass_to_next(request)

        # Delegate to strategy object's profit check
        cmd = request.strategy_obj.check_harvest(request.root, request.pl_pct, request.days_held)

        if cmd:
            # Add HARVEST tag
            tag = TriageTag(
                tag_type="HARVEST",
                priority=10,
                logic=cmd.logic,
                action_cmd=cmd,
            )
            request = request.with_tag(tag)

        # ALWAYS pass to next (collector pattern)
        return self._pass_to_next(request)
