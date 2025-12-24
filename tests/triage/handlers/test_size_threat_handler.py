"""
Unit tests for SizeThreatHandler.
"""

from variance.triage.handlers.size_threat import SizeThreatHandler
from variance.triage.request import TriageRequest


def test_adds_size_threat_on_tail_risk():
    rules = {"size_threat_pct": 0.05}
    handler = SizeThreatHandler(rules)

    # $600 loss on $5000 liquidity = 12% (> 5%)
    request = TriageRequest(
        root="AAPL",
        strategy_name="Strangle",
        strategy_id="ss",
        dte=30,
        net_pl=-600.0,
        net_cost=-1000.0,
        strategy_delta=0,
        strategy_gamma=0,
        pl_pct=-0.60,
        days_held=10,
        price=150.0,
        legs=(),
        vrp_structural=1.0,
        vrp_tactical=1.0,
        is_stale=False,
        sector="Tech",
        earnings_date=None,
        portfolio_beta_delta=0,
        net_liquidity=5000,
        strategy_obj=None,
    )

    result = handler.handle(request)
    tags = [t for t in result.tags if t.tag_type == "SIZE_THREAT"]
    assert len(tags) == 1
    assert "12.0%" in tags[0].logic
