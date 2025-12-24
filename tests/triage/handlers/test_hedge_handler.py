"""
Unit tests for HedgeHandler.
"""

from unittest.mock import Mock

import pytest

from variance.triage.handlers.hedge import HedgeHandler
from variance.triage.request import TriageRequest


class TestHedgeHandler:
    @pytest.fixture
    def rules(self):
        return {
            "dead_money_pl_pct_low": -0.10,
            "dead_money_pl_pct_high": 0.10,
            "dead_money_vrp_structural_threshold": 0.80,
        }

    @pytest.fixture
    def handler(self, rules):
        return HedgeHandler(rules)

    def test_adds_hedge_check_on_dead_money(self, handler):
        request = TriageRequest(
            root="SPY",
            strategy_name="Long Put",
            strategy_id="lp",
            dte=45,
            net_pl=0,
            net_cost=1000.0,
            strategy_delta=-10.0,  # Negative delta
            strategy_gamma=0,
            pl_pct=0.05,  # Within dead money
            days_held=10,
            price=450.0,
            legs=(),
            vrp_structural=0.5,  # Low VRP
            vrp_tactical=0.5,
            is_stale=False,
            sector="Index",  # Required
            earnings_date=None,
            portfolio_beta_delta=0,
            net_liquidity=50000,
            strategy_obj=Mock(),
        )
        result = handler.handle(request)
        tags = [t for t in result.tags if t.tag_type == "HEDGE_CHECK"]
        assert len(tags) == 1

    def test_skips_if_profitable(self, handler):
        request = TriageRequest(
            root="SPY",
            strategy_name="Long Put",
            strategy_id="lp",
            dte=45,
            net_pl=500,
            net_cost=1000.0,
            strategy_delta=-10.0,
            strategy_gamma=0,
            pl_pct=0.50,  # Outside dead money
            days_held=10,
            price=450.0,
            legs=(),
            vrp_structural=0.5,
            vrp_tactical=0.5,
            is_stale=False,
            sector="Index",
            earnings_date=None,
            portfolio_beta_delta=0,
            net_liquidity=50000,
            strategy_obj=Mock(),
        )
        result = handler.handle(request)
        assert len(result.tags) == 0
