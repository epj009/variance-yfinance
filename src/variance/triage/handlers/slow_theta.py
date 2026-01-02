"""
Slow Theta Handler

Detects positions where IV-HV spread is very small (< 5 points),
indicating slow theta decay and stable daily P/L.
"""

from variance.models.actions import ActionFactory
from variance.triage.handler import TriageHandler
from variance.triage.request import TriageRequest, TriageTag


class SlowThetaHandler(TriageHandler[TriageRequest]):
    """Handles logic for slow theta decay warnings."""

    def handle(self, request: TriageRequest) -> TriageRequest:
        # Skip if no IV-HV spread data
        if not hasattr(request, "iv_hv_spread_points") or request.iv_hv_spread_points is None:
            return self._pass_to_next(request)

        # Check if spread is very small (< 5 points)
        if request.iv_hv_spread_points < 5.0:
            spread_val = round(request.iv_hv_spread_points, 1)
            cmd = ActionFactory.create(
                "SLOW_THETA",
                request.root,
                f"IV-HV Spread only {spread_val} pts - Expect slow theta decay",
            )
            if cmd:
                tag = TriageTag(
                    tag_type="SLOW_THETA",
                    priority=90,  # Low priority informational warning
                    logic=cmd.logic,
                    action_cmd=cmd,
                )
                request = request.with_tag(tag)

        return self._pass_to_next(request)
