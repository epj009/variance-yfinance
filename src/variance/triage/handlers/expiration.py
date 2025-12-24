"""
Expiration Handler

Detects positions expiring today that require manual intervention.
"""

from ...models.actions import ActionFactory
from ..handler import TriageHandler
from ..request import TriageRequest, TriageTag


class ExpirationHandler(TriageHandler):
    """Handles logic for day-of-expiration management."""

    def handle(self, request: TriageRequest) -> TriageRequest:
        if request.dte == 0:
            cmd = ActionFactory.create(
                "EXPIRING", request.root, "Expiration Day - Manual Management Required"
            )
            if cmd:
                tag = TriageTag(
                    tag_type="EXPIRING",
                    priority=0,
                    logic=cmd.logic,
                    action_cmd=cmd,
                )
                request = request.with_tag(tag)

        return self._pass_to_next(request)
