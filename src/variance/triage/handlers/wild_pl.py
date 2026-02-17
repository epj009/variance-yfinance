"""
Wild P/L Handler

Detects positions where IV-HV spread is very large (> 15 points),
indicating fast theta decay but wild daily P/L swings.
"""

from variance.models.actions import ActionFactory
from variance.triage.handler import TriageHandler
from variance.triage.request import TriageRequest, TriageTag


class WildPlHandler(TriageHandler[TriageRequest]):
    """Handles logic for volatile daily P/L warnings."""

    def handle(self, request: TriageRequest) -> TriageRequest:
        # Skip if no IV-HV spread data or daily swing data
        if not hasattr(request, "iv_hv_spread_points") or request.iv_hv_spread_points is None:
            return self._pass_to_next(request)

        # Check if spread is very large (> 15 points)
        if request.iv_hv_spread_points > 15.0:
            spread_val = round(request.iv_hv_spread_points, 1)
            daily_swing = getattr(request, "expected_daily_swing_pct", None)

            if daily_swing is not None:
                swing_pct = round(daily_swing * 100, 2)
                logic_msg = (
                    f"IV-HV Spread {spread_val} pts - Expect wild daily swings (~{swing_pct}%/day)"
                )
            else:
                logic_msg = f"IV-HV Spread {spread_val} pts - Expect wild daily P/L swings"

            cmd = ActionFactory.create("WILD_PL", request.root, logic_msg)
            if cmd:
                tag = TriageTag(
                    tag_type="WILD_PL",
                    priority=90,  # Low priority informational warning
                    logic=cmd.logic,
                    action_cmd=cmd,
                )
                request = request.with_tag(tag)

        return self._pass_to_next(request)
