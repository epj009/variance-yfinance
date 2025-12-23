"""
Unit tests for Portfolio Domain Object.

Tests the Portfolio dataclass representing the complete trading account state.
"""

import pytest

from variance.models import Portfolio, Position, StrategyCluster


@pytest.fixture
def sample_cluster_1():
    """Factory for first sample cluster."""
    legs = [
        Position(
            symbol="AAPL 250117P145",
            asset_type="Option",
            quantity=-1.0,
            theta=-1.5,
            beta_delta=5.0,
            cost=-50.0,
            pl_open=25.0,
            raw_data={"Symbol": "AAPL 250117P145"},
        ),
        Position(
            symbol="AAPL 250117C155",
            asset_type="Option",
            quantity=-1.0,
            theta=-1.5,
            beta_delta=-5.0,
            cost=-50.0,
            pl_open=25.0,
            raw_data={"Symbol": "AAPL 250117C155"},
        ),
    ]
    return StrategyCluster(legs=legs)


@pytest.fixture
def sample_cluster_2():
    """Factory for second sample cluster."""
    legs = [
        Position(
            symbol="SPY 250117P500",
            asset_type="Option",
            quantity=-2.0,
            theta=-2.0,
            beta_delta=10.0,
            cost=-100.0,
            pl_open=50.0,
            raw_data={"Symbol": "SPY 250117P500"},
        ),
    ]
    return StrategyCluster(legs=legs)


class TestPortfolioAggregations:
    """Test Portfolio-level aggregate calculations."""

    def test_portfolio_total_theta_aggregates_clusters(self, sample_cluster_1, sample_cluster_2):
        """Portfolio total_theta should sum cluster theta values."""
        portfolio = Portfolio(
            clusters=[sample_cluster_1, sample_cluster_2],
            net_liquidity=50000.0,
        )

        # cluster_1: -1.5 + -1.5 = -3.0
        # cluster_2: -2.0
        # Total: -5.0
        assert portfolio.total_theta == pytest.approx(-5.0)

    def test_portfolio_total_delta_aggregates_clusters(self, sample_cluster_1, sample_cluster_2):
        """Portfolio total_delta should sum cluster beta_delta values."""
        portfolio = Portfolio(
            clusters=[sample_cluster_1, sample_cluster_2],
            net_liquidity=50000.0,
        )

        # cluster_1: 5.0 + (-5.0) = 0.0
        # cluster_2: 10.0
        # Total: 10.0
        assert portfolio.total_delta == pytest.approx(10.0)

    def test_portfolio_cluster_count(self, sample_cluster_1, sample_cluster_2):
        """Portfolio cluster_count should return number of clusters."""
        portfolio = Portfolio(
            clusters=[sample_cluster_1, sample_cluster_2],
            net_liquidity=50000.0,
        )

        assert portfolio.cluster_count == 2


class TestPortfolioEdgeCases:
    """Test Portfolio edge cases."""

    def test_portfolio_with_empty_clusters(self):
        """Empty portfolio should handle aggregations gracefully."""
        portfolio = Portfolio(clusters=[], net_liquidity=25000.0)

        assert portfolio.total_theta == 0.0
        assert portfolio.total_delta == 0.0
        assert portfolio.cluster_count == 0

    def test_portfolio_with_negative_net_liquidity(self, sample_cluster_1):
        """Portfolio can have negative net_liquidity (margin call scenario)."""
        portfolio = Portfolio(
            clusters=[sample_cluster_1],
            net_liquidity=-5000.0,
        )

        assert portfolio.net_liquidity == -5000.0
        assert portfolio.cluster_count == 1


class TestPortfolioInitialization:
    """Test Portfolio initialization and defaults."""

    def test_portfolio_initialization_defaults(self):
        """Portfolio should initialize with empty defaults."""
        portfolio = Portfolio()

        assert portfolio.clusters == []
        assert portfolio.net_liquidity == 0.0
        assert portfolio.rules == {}
        assert portfolio.total_theta == 0.0
        assert portfolio.total_delta == 0.0
        assert portfolio.cluster_count == 0

    def test_portfolio_with_single_cluster(self, sample_cluster_1):
        """Portfolio with single cluster should calculate correctly."""
        portfolio = Portfolio(
            clusters=[sample_cluster_1],
            net_liquidity=50000.0,
        )

        assert portfolio.cluster_count == 1
        assert portfolio.total_theta == pytest.approx(-3.0)
        assert portfolio.total_delta == pytest.approx(0.0)

    def test_portfolio_with_multiple_clusters(self, sample_cluster_1, sample_cluster_2):
        """Portfolio with 3+ clusters should aggregate correctly."""
        cluster_3 = StrategyCluster(
            legs=[
                Position(
                    symbol="QQQ 250117C400",
                    asset_type="Option",
                    quantity=-1.0,
                    theta=-0.5,
                    beta_delta=-3.0,
                    raw_data={"Symbol": "QQQ 250117C400"},
                ),
            ]
        )

        portfolio = Portfolio(
            clusters=[sample_cluster_1, sample_cluster_2, cluster_3],
            net_liquidity=100000.0,
            rules={"max_position_size": 0.05},
        )

        assert portfolio.cluster_count == 3
        assert portfolio.total_theta == pytest.approx(-5.5)
        assert portfolio.total_delta == pytest.approx(7.0)
        assert portfolio.rules == {"max_position_size": 0.05}
