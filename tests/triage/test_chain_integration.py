"""
Integration tests for the Triage Chain.
"""

from unittest.mock import Mock

from variance.triage.chain import TriageChain
from variance.triage.request import TriageRequest


def test_full_chain_accumulation():
    rules = {"gamma_trigger_dte": 21, "profit_harvest_pct": 0.5}
    chain = TriageChain(rules)

    # Mock a position that is both a Harvest and in Gamma zone
    strat = Mock()
    strat.gamma_trigger_dte = 21
    strat.is_tested.return_value = False
    from variance.models.actions import HarvestCommand

    strat.check_harvest.return_value = HarvestCommand("AAPL", "Profit hit")

    request = TriageRequest(
        root="AAPL",
        strategy_name="Strangle",
        strategy_id="ss",
        dte=10,  # Gamma zone
        net_pl=600,
        net_cost=-1000,  # Harvest zone
        strategy_delta=0,
        strategy_gamma=0,
        pl_pct=0.60,
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

    result = chain.triage(request)
    tag_types = [t.tag_type for t in result.tags]

    # Should have accumulated BOTH tags
    assert "HARVEST" in tag_types
    assert "GAMMA" in tag_types

    # HARVEST (Priority 10) should be primary over GAMMA (Priority 40)
    assert result.primary_action.tag_type == "HARVEST"
