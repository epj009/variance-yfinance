"""
Unit tests for ToxicThetaHandler.
"""

from unittest.mock import Mock

from variance.models.actions import ToxicCommand
from variance.triage.handlers.toxic_theta import ToxicThetaHandler
from variance.triage.request import TriageRequest


def test_adds_toxic_tag_when_edge_lost():
    strat = Mock()
    strat.check_toxic_theta.return_value = ToxicCommand("AAPL", "Toxic Carry")

    handler = ToxicThetaHandler({})
    request = TriageRequest(
        root="AAPL", strategy_name="Strangle", strategy_id="ss",
        dte=30, net_pl=0, net_cost=-1000.0, strategy_delta=0, strategy_gamma=0,
        pl_pct=0, days_held=10, price=150.0, legs=(),
        vrp_structural=1.0, vrp_tactical=0.1, is_stale=False,
        sector="Tech", earnings_date=None, portfolio_beta_delta=0,
        net_liquidity=50000, strategy_obj=strat
    )

    result = handler.handle(request)
    tags = [t for t in result.tags if t.tag_type == "TOXIC"]
    assert len(tags) == 1
