"""
Unit tests for HarvestHandler.
"""

from unittest.mock import Mock

import pytest

from variance.models.actions import HarvestCommand
from variance.triage.handlers.harvest import HarvestHandler
from variance.triage.request import TriageRequest


class TestHarvestHandler:
    @pytest.fixture
    def rules(self):
        return {"profit_harvest_pct": 0.50}

    @pytest.fixture
    def handler(self, rules):
        return HarvestHandler(rules)

    def test_adds_tag_on_profit_target(self, handler):
        # Arrange
        strategy_obj = Mock()
        strategy_obj.check_harvest.return_value = HarvestCommand(symbol="AAPL", logic="Profit 55%")

        request = TriageRequest(
            root="AAPL",
            strategy_name="Strangle",
            strategy_id="ss",
            dte=30,
            net_pl=550.0,
            net_cost=-1000.0,  # 55% profit
            strategy_delta=0,
            strategy_gamma=0,
            pl_pct=0.55,
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
            strategy_obj=strategy_obj,
        )

        # Act
        result = handler.handle(request)

        # Assert
        tags = [t for t in result.tags if t.tag_type == "HARVEST"]
        assert len(tags) == 1
        assert "Profit 55%" in tags[0].logic

    def test_skips_debit_positions(self, handler):
        request = TriageRequest(
            root="AAPL",
            strategy_name="Long Call",
            strategy_id="lc",
            dte=30,
            net_pl=100.0,
            net_cost=500.0,  # Debit
            strategy_delta=0,
            strategy_gamma=0,
            pl_pct=0.20,
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
            strategy_obj=Mock(),
        )
        result = handler.handle(request)
        assert len(result.tags) == 0
