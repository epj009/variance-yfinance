"""
Unit tests for ExpirationHandler.
"""

from variance.triage.handlers.expiration import ExpirationHandler
from variance.triage.request import TriageRequest


def test_adds_expiring_tag():
    handler = ExpirationHandler({})
    request = TriageRequest(
        root="AAPL",
        strategy_name="Strangle",
        strategy_id="ss",
        dte=0,  # Expiring today
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
        earnings_date=None,
        portfolio_beta_delta=0,
        net_liquidity=50000,
        strategy_obj=None,
    )
    result = handler.handle(request)
    tags = [t for t in result.tags if t.tag_type == "EXPIRING"]
    assert len(tags) == 1
