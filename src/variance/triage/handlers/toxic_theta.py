"""
Toxic Theta Handler

Detects positions where the statistical cost of movement risk exceeds the time decay collected.
"""

from ..handler import TriageHandler
from ..request import TriageRequest, TriageTag


class ToxicThetaHandler(TriageHandler):
    """Handles detection of mathematically invalid premium selling."""

    def handle(self, request: TriageRequest) -> TriageRequest:
        # Only check positions not already marked as winners
        if any(t.tag_type == "HARVEST" for t in request.tags):
            return self._pass_to_next(request)

        # Delegate to strategy object's toxic check
        # We need to construct metrics dict for backward compat with strategy methods
        metrics = {
            "cluster_theta_raw": request.strategy_gamma,  # (Simplified for now)
            "price": request.price,
            "root": request.root,
        }

        # Note: Strategy objects are being refactored to accept Request objects.
        # For now, we mock the market_data context.
        market_data = {request.root: {"hv20": request.vrp_tactical}}

        cmd = request.strategy_obj.check_toxic_theta(request.root, metrics, market_data)

        if cmd:
            tag = TriageTag(
                tag_type="TOXIC",
                priority=60,
                logic=cmd.logic,
                action_cmd=cmd,
            )
            request = request.with_tag(tag)

        return self._pass_to_next(request)
