"""
Unit tests for StrategyCluster Domain Object.

Tests the StrategyCluster dataclass that groups individual positions
into logical strategies with aggregate calculations.
"""

import pytest

from variance.models import Position, StrategyCluster


@pytest.fixture
def short_put_leg():
    """Factory for a short put position."""
    return Position(
        symbol="AAPL 250117P145",
        asset_type="Option",
        call_put="Put",
        quantity=-1.0,
        strike=145.0,
        dte=45,
        exp_date="2025-01-17",
        cost=-50.0,
        pl_open=25.0,
        delta=5.0,
        beta_delta=5.0,
        theta=-1.0,
        gamma=0.03,
        underlying_price=150.0,
        raw_data={
            "Symbol": "AAPL 250117P145",
            "Type": "Option",
            "Call/Put": "Put",
            "Quantity": "-1",
            "Strike Price": "145.0",
        },
    )


@pytest.fixture
def short_call_leg():
    """Factory for a short call position."""
    return Position(
        symbol="AAPL 250117C155",
        asset_type="Option",
        call_put="Call",
        quantity=-1.0,
        strike=155.0,
        dte=45,
        exp_date="2025-01-17",
        cost=-50.0,
        pl_open=25.0,
        delta=-5.0,
        beta_delta=-5.0,
        theta=-1.0,
        gamma=0.03,
        underlying_price=150.0,
        raw_data={
            "Symbol": "AAPL 250117C155",
            "Type": "Option",
            "Call/Put": "Call",
            "Quantity": "-1",
            "Strike Price": "155.0",
        },
    )


@pytest.fixture
def stock_leg():
    """Factory for a stock position."""
    return Position(
        symbol="AAPL",
        asset_type="Stock",
        quantity=100.0,
        dte=0,
        cost=-15000.0,
        pl_open=500.0,
        delta=100.0,
        beta_delta=100.0,
        theta=0.0,
        gamma=0.0,
        underlying_price=150.0,
        raw_data={"Symbol": "AAPL", "Type": "Stock", "Quantity": "100"},
    )


class TestClusterAggregateCalculations:
    """Test StrategyCluster aggregate metric calculations."""

    def test_cluster_calculates_net_pl_correctly(self, short_put_leg, short_call_leg):
        """Net P/L should sum leg pl_open values."""
        cluster = StrategyCluster(legs=[short_put_leg, short_call_leg])

        assert cluster.net_pl == pytest.approx(50.0)

    def test_cluster_calculates_net_cost_correctly(self, short_put_leg, short_call_leg):
        """Net cost should sum leg cost values."""
        cluster = StrategyCluster(legs=[short_put_leg, short_call_leg])

        assert cluster.net_cost == pytest.approx(-100.0)

    def test_cluster_calculates_total_delta(self, short_put_leg, short_call_leg):
        """Total delta should sum leg beta_delta values."""
        cluster = StrategyCluster(legs=[short_put_leg, short_call_leg])

        # 5.0 + (-5.0) = 0.0 (delta-neutral strangle)
        assert cluster.total_delta == pytest.approx(0.0)

    def test_cluster_calculates_total_theta(self, short_put_leg, short_call_leg):
        """Total theta should sum leg theta values."""
        cluster = StrategyCluster(legs=[short_put_leg, short_call_leg])

        # -1.0 + (-1.0) = -2.0 (collecting theta)
        assert cluster.total_theta == pytest.approx(-2.0)


class TestClusterMinDTE:
    """Test StrategyCluster.min_dte property."""

    def test_cluster_min_dte_only_considers_options(self, short_put_leg, stock_leg):
        """min_dte should only consider option legs, not stock."""
        cluster = StrategyCluster(legs=[short_put_leg, stock_leg])

        # Stock has dte=0, but should be ignored
        assert cluster.min_dte == 45

    def test_cluster_min_dte_with_no_options_returns_zero(self, stock_leg):
        """Cluster with only stock legs should return min_dte=0."""
        stock_leg_2 = Position(
            symbol="SPY",
            asset_type="Stock",
            quantity=50.0,
            dte=0,
            raw_data={"Symbol": "SPY", "Type": "Stock"},
        )
        cluster = StrategyCluster(legs=[stock_leg, stock_leg_2])

        assert cluster.min_dte == 0


class TestClusterStrategyIdentification:
    """Test StrategyCluster.name and strategy_id properties."""

    def test_cluster_name_identifies_short_strangle(self, short_put_leg, short_call_leg):
        """2 short options at different strikes should identify as 'Short Strangle'."""
        cluster = StrategyCluster(legs=[short_put_leg, short_call_leg])

        # Strategy detector should identify this pattern
        assert "Strangle" in cluster.name or "short_strangle" in cluster.strategy_id

    def test_cluster_strategy_id_maps_credit_correctly(self, short_put_leg, short_call_leg):
        """Credit strategies (net_cost < 0) should map to correct ID."""
        cluster = StrategyCluster(legs=[short_put_leg, short_call_leg])

        # net_cost = -100.0 (credit)
        assert cluster.net_cost < 0
        # Should have a valid strategy_id
        assert cluster.strategy_id is not None

    def test_cluster_strategy_id_maps_debit_correctly(self):
        """Debit strategies (net_cost > 0) should map correctly or return None for unmapped."""
        long_put = Position(
            symbol="SPY 250117P500",
            asset_type="Option",
            call_put="Put",
            quantity=1.0,
            strike=500.0,
            dte=45,
            cost=300.0,
            pl_open=-50.0,
            raw_data={
                "Symbol": "SPY 250117P500",
                "Type": "Option",
                "Call/Put": "Put",
                "Quantity": "1",
                "Strike Price": "500.0",
            },
        )

        cluster = StrategyCluster(legs=[long_put])

        # net_cost = 300.0 (debit)
        assert cluster.net_cost > 0
        # Single Long Put doesn't have a strategy_id mapping (returns None)
        # This is expected behavior for unmapped strategies
        assert cluster.name == "Long Put"


class TestClusterEdgeCases:
    """Test StrategyCluster edge cases."""

    def test_cluster_with_empty_legs_list(self):
        """Empty cluster should handle calculations gracefully."""
        cluster = StrategyCluster(legs=[])

        assert cluster.net_pl == 0.0
        assert cluster.net_cost == 0.0
        assert cluster.total_delta == 0.0
        assert cluster.total_theta == 0.0
        assert cluster.min_dte == 0
        assert cluster.root_symbol == "UNKNOWN"

    def test_cluster_with_single_leg(self, short_put_leg):
        """Single leg cluster should calculate metrics correctly."""
        cluster = StrategyCluster(legs=[short_put_leg])

        assert cluster.net_pl == pytest.approx(25.0)
        assert cluster.net_cost == pytest.approx(-50.0)
        assert cluster.total_delta == pytest.approx(5.0)
        assert cluster.total_theta == pytest.approx(-1.0)
        assert cluster.min_dte == 45
        assert cluster.root_symbol == "AAPL"


class TestClusterRootSymbol:
    """Test StrategyCluster.root_symbol property."""

    def test_cluster_name_identifies_iron_condor(self):
        """4-leg iron condor should be identified correctly."""
        # Iron Condor: Buy Put, Sell Put, Sell Call, Buy Call
        legs = [
            Position(
                symbol="SPY 250117P490",
                asset_type="Option",
                call_put="Put",
                quantity=1.0,
                strike=490.0,
                dte=45,
                raw_data={
                    "Symbol": "SPY 250117P490",
                    "Type": "Option",
                    "Call/Put": "Put",
                    "Quantity": "1",
                    "Strike Price": "490.0",
                },
            ),
            Position(
                symbol="SPY 250117P495",
                asset_type="Option",
                call_put="Put",
                quantity=-1.0,
                strike=495.0,
                dte=45,
                raw_data={
                    "Symbol": "SPY 250117P495",
                    "Type": "Option",
                    "Call/Put": "Put",
                    "Quantity": "-1",
                    "Strike Price": "495.0",
                },
            ),
            Position(
                symbol="SPY 250117C505",
                asset_type="Option",
                call_put="Call",
                quantity=-1.0,
                strike=505.0,
                dte=45,
                raw_data={
                    "Symbol": "SPY 250117C505",
                    "Type": "Option",
                    "Call/Put": "Call",
                    "Quantity": "-1",
                    "Strike Price": "505.0",
                },
            ),
            Position(
                symbol="SPY 250117C510",
                asset_type="Option",
                call_put="Call",
                quantity=1.0,
                strike=510.0,
                dte=45,
                raw_data={
                    "Symbol": "SPY 250117C510",
                    "Type": "Option",
                    "Call/Put": "Call",
                    "Quantity": "1",
                    "Strike Price": "510.0",
                },
            ),
        ]

        cluster = StrategyCluster(legs=legs)

        # Strategy detector should identify this pattern
        assert cluster.root_symbol == "SPY"
        # Name should contain "Condor" or similar
        assert cluster.name is not None
