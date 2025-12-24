"""
Earnings Handler

Detects upcoming binary risk events (earnings) within the threshold window.
"""

from datetime import datetime

from variance.models.actions import ActionFactory
from variance.triage.handler import TriageHandler
from variance.triage.request import TriageRequest, TriageTag


class EarningsHandler(TriageHandler[TriageRequest]):
    """Handles logic for upcoming earnings events."""

    def handle(self, request: TriageRequest) -> TriageRequest:
        if not request.earnings_date or request.earnings_date == "Unavailable":
            return self._pass_to_next(request)

        try:
            edate = datetime.fromisoformat(request.earnings_date).date()
            days_to_earn = (edate - datetime.now().date()).days

            threshold = self.rules.get("earnings_days_threshold", 5)

            if 0 <= days_to_earn <= threshold:
                logic = f"Earnings {days_to_earn}d"
                code = "EARNINGS_WARNING"

                # Check for stance (avoid vs play)
                if request.strategy_obj.earnings_stance == "avoid":
                    code = "EARNINGS_WARNING"
                    logic = f"Binary Event Risk (Avoid) | {logic}"

                cmd = ActionFactory.create(code, request.root, logic)
                if cmd:
                    tag = TriageTag(
                        tag_type=code,
                        priority=70,
                        logic=cmd.logic,
                        action_cmd=cmd,
                    )
                    request = request.with_tag(tag)
        except (ValueError, TypeError):
            pass

        return self._pass_to_next(request)
