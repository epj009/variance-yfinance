"""
Unit tests for GammaHandler.
"""

import pytest
from unittest.mock import Mock
from variance.triage.handlers.gamma import GammaHandler
from variance.triage.request import TriageRequest


class TestGammaHandler:
    @pytest.fixture
    def rules(self):
        return {"gamma_trigger_dte": 21}

    @pytest.fixture
    def handler(self, rules):
        return GammaHandler(rules)

    def test_adds_tag_in_gamma_zone(self, handler):
        # Arrange
        strat = Mock()
        strat.gamma_trigger_dte = 21
        strat.is_tested.return_value = False
        
        request = TriageRequest(
            root="AAPL", strategy_name="Strangle", strategy_id="ss",
            dte=15,  # Within 21 DTE
            net_pl=0, net_cost=-1000.0,
            strategy_delta=0, strategy_gamma=0, pl_pct=0,
            days_held=10, price=150.0, legs=(),
            vrp_structural=1.0, vrp_tactical=1.0, is_stale=False,
            sector="Tech", earnings_date=None, portfolio_beta_delta=0,
            net_liquidity=50000, strategy_obj=strat
        )

        # Act
        result = handler.handle(request)

        # Assert
        tags = [t for t in result.tags if t.tag_type == "GAMMA"]
        assert len(tags) == 1
        assert "21 DTE Risk" in tags[0].logic

    def test_skips_if_not_in_gamma_zone(self, handler):
        strat = Mock()
        strat.gamma_trigger_dte = 21
        strat.is_tested.return_value = False
        request = TriageRequest(
            # ...
            dte=45,  # Outside window
            # ...
            root="AAPL", strategy_name="Strangle", strategy_id="ss",
            net_pl=0, net_cost=-1000.0,
            strategy_delta=0, strategy_gamma=0, pl_pct=0,
            days_held=10, price=150.0, legs=(),
            vrp_structural=1.0, vrp_tactical=1.0, is_stale=False,
            sector="Tech", earnings_date=None, portfolio_beta_delta=0,
            net_liquidity=50000, strategy_obj=strat
        )
        result = handler.handle(request)
        assert len(result.tags) == 0
