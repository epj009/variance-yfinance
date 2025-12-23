"""
Unit tests for BaseStrategy abstract class.

Tests the base strategy interface including profit harvest logic,
velocity harvest mechanics, and abstract method enforcement.
"""

import pytest

from variance.strategies.base import BaseStrategy
from variance.strategies.default import DefaultStrategy


@pytest.fixture
def mock_strategy_config():
    """Standard strategy configuration for testing."""
    return {
        "metadata": {
            "name": "Test Strategy",
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
def default_strategy(mock_strategy_config, mock_trading_rules):
    """DefaultStrategy instance for testing base class logic."""
    return DefaultStrategy(
        strategy_id="test_strategy",
        config=mock_strategy_config,
        rules=mock_trading_rules,
    )


class TestStrategyInitialization:
    """Test BaseStrategy initialization and config handling."""

    def test_strategy_initialization_uses_config(self, mock_trading_rules):
        """Strategy should use profit_target_pct from config.management."""
        config = {
            "metadata": {"name": "High Profit Strategy", "type": "short_vol"},
            "management": {"profit_target_pct": 0.75},
        }

        strategy = DefaultStrategy("test_id", config, mock_trading_rules)

        assert strategy.profit_target_pct == 0.75
        assert strategy.name == "High Profit Strategy"
        assert strategy.type == "short_vol"

    def test_strategy_initialization_uses_defaults(self, mock_trading_rules):
        """Strategy should fall back to rules when config is missing."""
        config = {"metadata": {}, "management": {}}

        strategy = DefaultStrategy("test_id", config, mock_trading_rules)

        # Falls back to profit_harvest_pct from rules
        assert strategy.profit_target_pct == 0.50
        assert strategy.gamma_trigger_dte == 21
        assert strategy.defense_mechanic == "roll_untested"


class TestCheckHarvestProfitTarget:
    """Test BaseStrategy.check_harvest() profit target logic."""

    def test_check_harvest_at_50pct_profit(self, default_strategy):
        """Exactly 50% profit should trigger harvest."""
        cmd = default_strategy.check_harvest(symbol="TEST", pl_pct=0.50, days_held=10)

        assert cmd is not None
        assert cmd.action_code == "HARVEST"
        assert "Profit 50.0%" in cmd.logic

    def test_check_harvest_above_50pct_profit(self, default_strategy):
        """Above 50% profit should trigger harvest."""
        cmd = default_strategy.check_harvest(symbol="TEST", pl_pct=0.65, days_held=10)

        assert cmd is not None
        assert cmd.action_code == "HARVEST"
        assert "Profit 65.0%" in cmd.logic

    def test_check_harvest_no_action_below_target(self, default_strategy):
        """Below 50% profit should not trigger harvest."""
        cmd = default_strategy.check_harvest(symbol="TEST", pl_pct=0.45, days_held=10)

        assert cmd is None


class TestCheckHarvestVelocity:
    """Test BaseStrategy.check_harvest() velocity logic."""

    def test_check_harvest_velocity_25pct_in_3days(self, default_strategy):
        """25% profit in 3 days should trigger velocity harvest."""
        cmd = default_strategy.check_harvest(symbol="TEST", pl_pct=0.25, days_held=3)

        assert cmd is not None
        assert cmd.action_code == "HARVEST"
        assert "Velocity" in cmd.logic
        assert "25.0%" in cmd.logic
        assert "3d" in cmd.logic
        assert "Early Win" in cmd.logic

    def test_check_harvest_velocity_25pct_in_5days(self, default_strategy):
        """25% profit in 5 days should NOT harvest (boundary: >=5 excluded)."""
        cmd = default_strategy.check_harvest(symbol="TEST", pl_pct=0.25, days_held=5)

        assert cmd is None

    def test_check_harvest_velocity_25pct_in_4days(self, default_strategy):
        """25% profit in 4 days should trigger velocity harvest (< 5)."""
        cmd = default_strategy.check_harvest(symbol="TEST", pl_pct=0.25, days_held=4)

        assert cmd is not None
        assert cmd.action_code == "HARVEST"
        assert "Velocity" in cmd.logic

    def test_check_harvest_no_action_velocity_too_slow(self, default_strategy):
        """25% profit in 10 days should NOT trigger velocity harvest."""
        cmd = default_strategy.check_harvest(symbol="TEST", pl_pct=0.25, days_held=10)

        assert cmd is None


class TestCheckHarvestEdgeCases:
    """Test BaseStrategy.check_harvest() edge cases."""

    def test_check_harvest_negative_pl(self, default_strategy):
        """Negative P/L should not trigger harvest."""
        cmd = default_strategy.check_harvest(symbol="TEST", pl_pct=-0.30, days_held=10)

        assert cmd is None

    def test_check_harvest_zero_days_held(self, default_strategy):
        """Zero days held should not trigger velocity harvest."""
        cmd = default_strategy.check_harvest(symbol="TEST", pl_pct=0.25, days_held=0)

        assert cmd is None

    def test_check_harvest_velocity_exactly_25pct_in_1day(self, default_strategy):
        """25% profit in 1 day should trigger velocity harvest."""
        cmd = default_strategy.check_harvest(symbol="TEST", pl_pct=0.25, days_held=1)

        assert cmd is not None
        assert cmd.action_code == "HARVEST"


class TestCheckToxicTheta:
    """Test BaseStrategy.check_toxic_theta() default behavior."""

    def test_check_toxic_theta_returns_none_for_base(self, default_strategy):
        """Base class should return None for toxic check (not defined)."""
        cmd = default_strategy.check_toxic_theta(
            symbol="TEST", metrics={}, market_data={}
        )

        assert cmd is None


class TestAbstractMethods:
    """Test BaseStrategy abstract method enforcement."""

    def test_is_tested_raises_not_implemented(self, default_strategy):
        """BaseStrategy.is_tested() is abstract but DefaultStrategy implements it."""
        legs = [
            {
                "Type": "Option",
                "Call/Put": "Put",
                "Quantity": "-1",
                "Strike Price": "150.0",
            }
        ]
        underlying_price = 155.0

        # DefaultStrategy implements is_tested() (returns False always)
        result = default_strategy.is_tested(legs, underlying_price)

        # DefaultStrategy returns False as fallback
        assert result is False

    def test_base_strategy_cannot_be_instantiated(self, mock_strategy_config, mock_trading_rules):
        """BaseStrategy is abstract and cannot be instantiated directly."""
        with pytest.raises(TypeError):
            # This should fail because BaseStrategy is abstract
            BaseStrategy("test_id", mock_strategy_config, mock_trading_rules)
