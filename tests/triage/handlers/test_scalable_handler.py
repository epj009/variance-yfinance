"""
Unit tests for ScalableHandler.
"""

from variance.triage.handlers.scalable import ScalableHandler
from variance.triage.request import TriageRequest


def test_adds_scalable_tag_on_vrp_surge():
    rules = {"vrp_momentum_threshold": 0.50}
    handler = ScalableHandler(rules)

    request = TriageRequest(
        root="AAPL", strategy_name="Strangle", strategy_id="ss",
        dte=45, # Outside gamma zone
        net_pl=0, net_cost=-1000.0, strategy_delta=0, strategy_gamma=0,
        pl_pct=0.10, days_held=10, price=150.0, legs=(),
        vrp_structural=1.0,
        vrp_tactical=1.6, # 60% surge
        is_stale=False,
        sector="Tech", earnings_date=None, portfolio_beta_delta=0,
        net_liquidity=50000, strategy_obj=None
    )

    result = handler.handle(request)
    tags = [t for t in result.tags if t.tag_type == "SCALABLE"]
    assert len(tags) == 1
