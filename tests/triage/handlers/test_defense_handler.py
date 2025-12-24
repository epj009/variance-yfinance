"""
Unit tests for DefenseHandler.
"""

from unittest.mock import Mock

from variance.triage.handlers.defense import DefenseHandler
from variance.triage.request import TriageRequest


def test_adds_defense_tag_when_tested_and_low_dte():
    strat = Mock()
    strat.gamma_trigger_dte = 21
    strat.is_tested.return_value = True

    handler = DefenseHandler({})
    request = TriageRequest(
        root="AAPL",
        strategy_name="Strangle",
        strategy_id="ss",
        dte=10,  # Within window
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
        strategy_obj=strat,
    )

    result = handler.handle(request)
    tags = [t for t in result.tags if t.tag_type == "DEFENSE"]
    assert len(tags) == 1
