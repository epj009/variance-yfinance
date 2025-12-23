"""
Unit tests for StrategyFactory class.

Tests strategy selection logic, config propagation, and fallback behavior
for the factory pattern that instantiates strategy classes.
"""

import pytest

from variance.strategies.default import DefaultStrategy
from variance.strategies.factory import StrategyFactory
from variance.strategies.short_theta import ShortThetaStrategy


@pytest.fixture
def mock_strategies_config():
    """Mock strategies configuration matching strategies.json structure."""
    return {
        "short_strangle": {
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
        },
        "iron_condor": {
            "metadata": {
                "name": "Iron Condor",
                "type": "neutral",
                "gamma_trigger_dte": 21,
            },
            "management": {
                "profit_target_pct": 0.50,
            },
        },
        "jade_lizard": {
            "metadata": {
                "name": "Jade Lizard",
                "type": "undefined",
                "gamma_trigger_dte": 21,
            },
            "management": {
                "profit_target_pct": 0.50,
            },
        },
        "long_call": {
            "metadata": {
                "name": "Long Call",
                "type": "long_vol",
                "gamma_trigger_dte": 14,
            },
            "management": {
                "profit_target_pct": 0.75,
            },
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


class TestFactoryShortThetaMapping:
    """Test StrategyFactory returns ShortThetaStrategy for known IDs."""

    def test_factory_returns_short_theta_for_short_strangle(
        self, mock_strategies_config, mock_trading_rules
    ):
        """Short strangle ID should map to ShortThetaStrategy."""
        strategy = StrategyFactory.get_strategy(
            "short_strangle", mock_strategies_config, mock_trading_rules
        )

        assert isinstance(strategy, ShortThetaStrategy)
        assert strategy.strategy_id == "short_strangle"
        assert strategy.name == "Short Strangle"

    def test_factory_returns_short_theta_for_iron_condor(
        self, mock_strategies_config, mock_trading_rules
    ):
        """Iron condor ID should map to ShortThetaStrategy."""
        strategy = StrategyFactory.get_strategy(
            "iron_condor", mock_strategies_config, mock_trading_rules
        )

        assert isinstance(strategy, ShortThetaStrategy)
        assert strategy.strategy_id == "iron_condor"

    def test_factory_returns_short_theta_for_jade_lizard(
        self, mock_strategies_config, mock_trading_rules
    ):
        """Jade lizard ID should map to ShortThetaStrategy."""
        strategy = StrategyFactory.get_strategy(
            "jade_lizard", mock_strategies_config, mock_trading_rules
        )

        assert isinstance(strategy, ShortThetaStrategy)
        assert strategy.strategy_id == "jade_lizard"


class TestFactoryTypeMapping:
    """Test StrategyFactory maps strategies by type field."""

    def test_factory_returns_short_theta_for_undefined_type(self, mock_trading_rules):
        """Type='undefined' should map to ShortThetaStrategy (safe default)."""
        config = {
            "unknown_strategy": {
                "metadata": {"type": "undefined"},
                "management": {},
            }
        }

        strategy = StrategyFactory.get_strategy("unknown_strategy", config, mock_trading_rules)

        assert isinstance(strategy, ShortThetaStrategy)

    def test_factory_returns_short_theta_for_short_vol_type(self, mock_trading_rules):
        """Type='short_vol' should map to ShortThetaStrategy."""
        config = {
            "test_strategy": {
                "metadata": {"type": "short_vol"},
                "management": {},
            }
        }

        strategy = StrategyFactory.get_strategy("test_strategy", config, mock_trading_rules)

        assert isinstance(strategy, ShortThetaStrategy)

    def test_factory_returns_short_theta_for_neutral_type(self, mock_trading_rules):
        """Type='neutral' should map to ShortThetaStrategy."""
        config = {
            "test_strategy": {
                "metadata": {"type": "neutral"},
                "management": {},
            }
        }

        strategy = StrategyFactory.get_strategy("test_strategy", config, mock_trading_rules)

        assert isinstance(strategy, ShortThetaStrategy)


class TestFactoryDefaultMapping:
    """Test StrategyFactory returns DefaultStrategy for long/other strategies."""

    def test_factory_returns_default_for_long_strategies(
        self, mock_strategies_config, mock_trading_rules
    ):
        """Long strategies not in short_theta_ids should use DefaultStrategy."""
        strategy = StrategyFactory.get_strategy(
            "long_call", mock_strategies_config, mock_trading_rules
        )

        # Long call has type="long_vol" which is not in short_theta types
        assert isinstance(strategy, DefaultStrategy)
        assert strategy.strategy_id == "long_call"

    def test_factory_returns_short_theta_for_none_id(
        self, mock_strategies_config, mock_trading_rules
    ):
        """None strategy_id should default to ShortThetaStrategy (safety)."""
        strategy = StrategyFactory.get_strategy(None, mock_strategies_config, mock_trading_rules)

        assert isinstance(strategy, ShortThetaStrategy)


class TestFactoryConfigPropagation:
    """Test StrategyFactory correctly propagates config and rules."""

    def test_factory_passes_config_to_strategy(self, mock_strategies_config, mock_trading_rules):
        """Config should be passed to strategy instance."""
        strategy = StrategyFactory.get_strategy(
            "short_strangle", mock_strategies_config, mock_trading_rules
        )

        assert strategy.config == mock_strategies_config["short_strangle"]
        assert strategy.profit_target_pct == 0.50
        assert strategy.gamma_trigger_dte == 21

    def test_factory_passes_rules_to_strategy(self, mock_strategies_config, mock_trading_rules):
        """Rules should be passed to strategy instance."""
        strategy = StrategyFactory.get_strategy(
            "short_strangle", mock_strategies_config, mock_trading_rules
        )

        assert strategy.rules == mock_trading_rules

    def test_factory_with_missing_strategy_config(self, mock_trading_rules):
        """Missing strategy config should use empty dict."""
        empty_config = {}

        strategy = StrategyFactory.get_strategy("unknown_id", empty_config, mock_trading_rules)

        # Should still create a strategy with empty config
        assert isinstance(strategy, ShortThetaStrategy)
        assert strategy.config == {}
        # Should fall back to rules for profit_target_pct
        assert strategy.profit_target_pct == 0.50


class TestFactoryExplicitShortThetaIDs:
    """Test StrategyFactory maps all explicit short_theta_ids."""

    @pytest.mark.parametrize(
        "strategy_id",
        [
            "short_strangle",
            "short_straddle",
            "iron_condor",
            "iron_fly",
            "jade_lizard",
            "reverse_jade_lizard",
            "short_naked_put",
            "short_naked_call",
            "covered_call",
            "covered_put",
            "short_call_vertical_spread",
            "short_put_vertical_spread",
        ],
    )
    def test_factory_returns_short_theta_for_explicit_ids(self, strategy_id, mock_trading_rules):
        """All IDs in short_theta_ids list should map to ShortThetaStrategy."""
        config = {
            strategy_id: {
                "metadata": {"name": strategy_id.replace("_", " ").title()},
                "management": {},
            }
        }

        strategy = StrategyFactory.get_strategy(strategy_id, config, mock_trading_rules)

        assert isinstance(strategy, ShortThetaStrategy)
        assert strategy.strategy_id == strategy_id
