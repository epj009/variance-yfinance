"""
Unit tests for EarningsHandler.
"""

from datetime import date, timedelta
from unittest.mock import Mock

from variance.triage.handlers.earnings import EarningsHandler
from variance.triage.request import TriageRequest


def test_adds_earnings_warning():
    rules = {"earnings_days_threshold": 10}
    handler = EarningsHandler(rules)

    # Set earnings to tomorrow
    earnings_date = (date.today() + timedelta(days=1)).isoformat()
    strat = Mock()
    strat.earnings_stance = "avoid"

    request = TriageRequest(
        root="AAPL",
        strategy_name="Strangle",
        strategy_id="ss",
        dte=30,
        net_pl=0,
        net_cost=-1000.0,
        strategy_delta=0,
        strategy_gamma=0,
        pl_pct=0,
        days_held=10,
        price=150.0,
        legs=(),
        vrp_structural=1.0,
        vrp_tactical=1.0,
        is_stale=False,
        sector="Tech",
        earnings_date=earnings_date,
        portfolio_beta_delta=0,
        net_liquidity=50000,
        strategy_obj=strat,
    )

    result = handler.handle(request)
    tags = [t for t in result.tags if t.tag_type == "EARNINGS_WARNING"]
    assert len(tags) == 1
    assert "Earnings 1d" in tags[0].logic
