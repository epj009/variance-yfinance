"""
Unit tests for ShortThetaStrategy class.

Tests mechanical ITM detection (is_tested), institutional theta efficiency
filters (check_toxic_theta), and profit harvest inheritance from BaseStrategy.
"""

import pytest

from variance.strategies.short_theta import ShortThetaStrategy


@pytest.fixture
def mock_strategy_config():
    """Standard short theta strategy configuration."""
    return {
        "metadata": {
            "name": "Short Strangle",
            "type": "short_vol",
            "gamma_trigger_dte": 21,
            "earnings_stance": "avoid",
        },
        "management": {
            "profit_target_pct": 0.50,
            "defense_mechanic": "roll_untested",
        },
    }


@pytest.fixture
def mock_trading_rules():
    """Standard trading rules fixture."""
    return {
        "profit_harvest_pct": 0.50,
        "gamma_dte_threshold": 21,
        "theta_efficiency_low": 0.10,
        "hv_floor_percent": 5.0,
    }


@pytest.fixture
def short_theta_strategy(mock_strategy_config, mock_trading_rules):
    """ShortThetaStrategy instance for testing."""
    return ShortThetaStrategy(
        strategy_id="short_strangle",
        config=mock_strategy_config,
        rules=mock_trading_rules,
    )


class TestIsTestedShortPut:
    """Test ShortThetaStrategy.is_tested() for short put legs."""

    def test_is_tested_short_put_itm(self, short_theta_strategy):
        """Short put ITM when price < strike should return True."""
        legs = [
            {
                "Type": "Option",
                "Call/Put": "Put",
                "Quantity": "-1",
                "Strike Price": "150.0",
            }
        ]
        underlying_price = 145.0  # Price < Strike = ITM for put

        result = short_theta_strategy.is_tested(legs, underlying_price)

        assert result is True

    def test_is_tested_short_put_otm(self, short_theta_strategy):
        """Short put OTM when price > strike should return False."""
        legs = [
            {
                "Type": "Option",
                "Call/Put": "Put",
                "Quantity": "-1",
                "Strike Price": "150.0",
            }
        ]
        underlying_price = 155.0  # Price > Strike = OTM for put

        result = short_theta_strategy.is_tested(legs, underlying_price)

        assert result is False


class TestIsTestedShortCall:
    """Test ShortThetaStrategy.is_tested() for short call legs."""

    def test_is_tested_short_call_itm(self, short_theta_strategy):
        """Short call ITM when price > strike should return True."""
        legs = [
            {
                "Type": "Option",
                "Call/Put": "Call",
                "Quantity": "-1",
                "Strike Price": "150.0",
            }
        ]
        underlying_price = 155.0  # Price > Strike = ITM for call

        result = short_theta_strategy.is_tested(legs, underlying_price)

        assert result is True

    def test_is_tested_short_call_otm(self, short_theta_strategy):
        """Short call OTM when price < strike should return False."""
        legs = [
            {
                "Type": "Option",
                "Call/Put": "Call",
                "Quantity": "-1",
                "Strike Price": "150.0",
            }
        ]
        underlying_price = 145.0  # Price < Strike = OTM for call

        result = short_theta_strategy.is_tested(legs, underlying_price)

        assert result is False


class TestIsTestedLongLegs:
    """Test ShortThetaStrategy.is_tested() ignores long legs."""

    def test_is_tested_ignores_long_legs(self, short_theta_strategy):
        """Long legs (qty > 0) should never be considered tested."""
        legs = [
            {
                "Type": "Option",
                "Call/Put": "Put",
                "Quantity": "1",  # Long leg
                "Strike Price": "150.0",
            }
        ]
        underlying_price = 145.0  # Would be ITM if short, but is long

        result = short_theta_strategy.is_tested(legs, underlying_price)

        assert result is False


class TestIsTestedStockLegs:
    """Test ShortThetaStrategy.is_tested() ignores stock legs."""

    def test_is_tested_ignores_stock_legs(self, short_theta_strategy):
        """Stock legs should never be considered tested."""
        legs = [
            {
                "Type": "Stock",
                "Call/Put": "",
                "Quantity": "100",
                "Strike Price": None,
            }
        ]
        underlying_price = 150.0

        result = short_theta_strategy.is_tested(legs, underlying_price)

        assert result is False


class TestCheckToxicThetaEfficiency:
    """Test ShortThetaStrategy.check_toxic_theta() efficiency calculations."""

    def test_check_toxic_theta_low_efficiency(self, short_theta_strategy):
        """Efficiency < 0.10x should trigger TOXIC."""
        # Set up values to ensure low efficiency:
        # NOTE: cluster_theta_raw > 0 means we're net short theta (collecting premium)
        # em_1sd = 150.0 * (30.0 / 100.0 / 15.87) = 2.835
        # gamma_cost = 0.5 * 20.0 * (2.835^2) = 80.36
        # efficiency = 5.0 / 80.36 = 0.062x < 0.10 → TOXIC
        metrics = {
            "cluster_theta_raw": 5.0,  # Positive = collecting theta
            "cluster_gamma_raw": 20.0,  # High gamma for low efficiency
            "root": "AAPL",
            "price": 150.0,
        }
        market_data = {
            "AAPL": {"hv20": 30.0, "hv252": 25.0},
        }

        cmd = short_theta_strategy.check_toxic_theta(
            symbol="AAPL", metrics=metrics, market_data=market_data
        )

        assert cmd is not None
        assert cmd.action_code == "TOXIC"
        assert "Toxic Theta" in cmd.logic
        assert "0.06x" in cmd.logic or "0.07x" in cmd.logic  # Allow for rounding

    def test_check_toxic_theta_normal_efficiency(self, short_theta_strategy):
        """Efficiency >= 0.10x should return None (no action)."""
        metrics = {
            "cluster_theta_raw": 10.0,  # Positive = collecting theta
            "cluster_gamma_raw": 1.0,
            "root": "AAPL",
            "price": 150.0,
        }
        market_data = {
            "AAPL": {"hv20": 30.0, "hv252": 25.0},
        }

        cmd = short_theta_strategy.check_toxic_theta(
            symbol="AAPL", metrics=metrics, market_data=market_data
        )

        # em_1sd = 150.0 * 0.30 / 15.87 = 2.835
        # gamma_cost = 0.5 * 1.0 * (2.835^2) = 4.018
        # efficiency = 10.0 / 4.018 = 2.49x >= 0.10 → OK
        assert cmd is None


class TestCheckToxicThetaSkipCases:
    """Test ShortThetaStrategy.check_toxic_theta() skip conditions."""

    def test_check_toxic_theta_debit_trade_skipped(self, short_theta_strategy):
        """Debit trades (theta <= 0 or positive theta) should be skipped."""
        metrics = {
            "cluster_theta_raw": 0.0,  # Not collecting theta
            "cluster_gamma_raw": 1.0,
            "root": "AAPL",
            "price": 150.0,
        }
        market_data = {
            "AAPL": {"hv20": 30.0},
        }

        cmd = short_theta_strategy.check_toxic_theta(
            symbol="AAPL", metrics=metrics, market_data=market_data
        )

        assert cmd is None

    def test_check_toxic_theta_missing_hv_returns_none(self, short_theta_strategy):
        """Missing HV data should return None."""
        metrics = {
            "cluster_theta_raw": 5.0,  # Positive = collecting theta
            "cluster_gamma_raw": 1.0,
            "root": "AAPL",
            "price": 150.0,
        }
        market_data = {
            "AAPL": {}  # No HV data
        }

        cmd = short_theta_strategy.check_toxic_theta(
            symbol="AAPL", metrics=metrics, market_data=market_data
        )

        assert cmd is None

    def test_check_toxic_theta_missing_price_returns_none(self, short_theta_strategy):
        """Missing or invalid price should return None."""
        metrics = {
            "cluster_theta_raw": 5.0,  # Positive = collecting theta
            "cluster_gamma_raw": 1.0,
            "root": "AAPL",
            "price": 0.0,  # Invalid price
        }
        market_data = {
            "AAPL": {"hv20": 30.0},
        }

        cmd = short_theta_strategy.check_toxic_theta(
            symbol="AAPL", metrics=metrics, market_data=market_data
        )

        assert cmd is None

    def test_check_toxic_theta_zero_gamma_returns_none(self, short_theta_strategy):
        """Zero gamma (no risk) should return None."""
        metrics = {
            "cluster_theta_raw": 5.0,
            "cluster_gamma_raw": 0.0,
            "root": "AAPL",
            "price": 150.0,
        }
        market_data = {
            "AAPL": {"hv20": 30.0},
        }

        cmd = short_theta_strategy.check_toxic_theta(
            symbol="AAPL", metrics=metrics, market_data=market_data
        )

        assert cmd is None


class TestCheckToxicThetaHVFloor:
    """Test ShortThetaStrategy.check_toxic_theta() floor logic."""

    def test_check_toxic_theta_uses_hv_floor(self, short_theta_strategy):
        """Should use rules['hv_floor_percent'] if HV data is lower."""
        # em_1sd = 100.0 * (5.0 / 100.0 / 15.87) = 0.315
        # gamma_cost = 0.5 * 100.0 * (0.315^2) = 4.96
        # efficiency = 0.1 / 4.96 = 0.02x < 0.10 → TOXIC
        metrics = {
            "cluster_theta_raw": 0.1,
            "cluster_gamma_raw": 100.0,
            "root": "AAPL",
            "price": 100.0,
        }
        market_data = {
            "AAPL": {"hv20": 1.0},  # Lower than 5.0 floor
        }

        cmd = short_theta_strategy.check_toxic_theta(
            symbol="AAPL", metrics=metrics, market_data=market_data
        )

        assert cmd is not None
        assert cmd.action_code == "TOXIC"


class TestInheritedCheckHarvest:
    """Test ShortThetaStrategy inherits check_harvest() properly."""

    def test_inherits_check_harvest_from_base(self, short_theta_strategy):
        """ShortThetaStrategy should use the base harvest logic."""
        # 60% profit > 50% target
        cmd = short_theta_strategy.check_harvest(symbol="TEST", pl_pct=0.60, days_held=10)

        assert cmd is not None
        assert cmd.action_code == "HARVEST"
