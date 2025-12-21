"""
Comprehensive test suite for scripts/config_loader.py and scripts/strategy_loader.py

Coverage target: 85%+
Runtime target: <2 seconds
Network: NO (all file I/O mocked via tmp_path)

Priority:
1. Config loading with defaults - CRITICAL
2. Error handling (FileNotFoundError, JSONDecodeError) - CRITICAL
3. Strategy validation - HIGH
"""

import pytest
import sys
import os
import json

# Add scripts/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../scripts'))

import config_loader
import strategy_loader


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    """
    Creates isolated config directory and patches CWD.

    - Creates tmp_path/config/ directory
    - Monkeypatches working directory
    - Returns path to config directory for file creation
    """
    config_path = tmp_path / "config"
    config_path.mkdir()
    monkeypatch.chdir(tmp_path)
    return config_path


@pytest.fixture
def valid_strategy():
    """Returns minimal valid strategy dict for validation tests."""
    return {
        "id": "test_strategy",
        "name": "Test Strategy",
        "type": "defined_risk",
        "setup": {"legs_description": "Test"},
        "management": {"profit_target_pct": 0.50},
        "metadata": {"gamma_trigger_dte": 21}
    }


# ============================================================================
# TEST CLASS 1: DEFAULT_TRADING_RULES Validation
# ============================================================================

class TestDefaultTradingRules:
    """Unit tests for DEFAULT_TRADING_RULES constant."""

    def test_default_keys_exist(self):
        """All expected default keys present."""
        expected_keys = {
            "vrp_structural_threshold", "dead_money_vrp_structural_threshold",
            "dead_money_pl_pct_low", "dead_money_pl_pct_high",
            "low_ivr_threshold", "gamma_dte_threshold",
            "profit_harvest_pct", "earnings_days_threshold",
            "portfolio_delta_long_threshold", "portfolio_delta_short_threshold",
            "concentration_risk_pct", "net_liquidity",
            "theta_efficiency_low", "theta_efficiency_high",
            "beta_weighted_symbol", "global_staleness_threshold",
            "data_integrity_min_theta", "asset_mix_equity_threshold",
            "stress_scenarios", "min_atm_volume", "max_slippage_pct",
            "bats_efficiency_min_price", "bats_efficiency_max_price",
            "bats_efficiency_vrp_structural"
        }

        assert set(config_loader.DEFAULT_TRADING_RULES.keys()) == expected_keys

    def test_default_types_correct(self):
        """Type validation for complex defaults."""
        defaults = config_loader.DEFAULT_TRADING_RULES

        # Numeric types
        assert isinstance(defaults["vrp_structural_threshold"], float)
        assert isinstance(defaults["gamma_dte_threshold"], int)
        assert isinstance(defaults["net_liquidity"], int)

        # String types
        assert isinstance(defaults["beta_weighted_symbol"], str)

        # List of dicts
        assert isinstance(defaults["stress_scenarios"], list)
        assert len(defaults["stress_scenarios"]) == 5
        assert all("label" in s and "move_pct" in s for s in defaults["stress_scenarios"])


# ============================================================================
# TEST CLASS 2: load_trading_rules()
# ============================================================================

class TestLoadTradingRules:
    """Unit tests for load_trading_rules() function."""

    def test_load_valid_config(self, config_dir):
        """Load valid JSON file and verify merge with defaults."""
        # Arrange
        config_file = config_dir / "trading_rules.json"
        config_file.write_text('{"vrp_structural_threshold": 0.95, "net_liquidity": 75000}')

        # Act
        result = config_loader.load_trading_rules()

        # Assert
        assert result["vrp_structural_threshold"] == 0.95  # Overridden
        assert result["net_liquidity"] == 75000       # Overridden
        assert result["gamma_dte_threshold"] == 21    # Default preserved

    def test_merge_with_defaults(self, config_dir):
        """User config overrides defaults."""
        config_file = config_dir / "trading_rules.json"
        config_file.write_text('{"gamma_dte_threshold": 14, "profit_harvest_pct": 0.60}')

        result = config_loader.load_trading_rules()

        assert result["gamma_dte_threshold"] == 14
        assert result["profit_harvest_pct"] == 0.60
        assert result["vrp_structural_threshold"] == 0.85  # Default

    def test_missing_file_returns_defaults(self, config_dir):
        """Graceful fallback when file doesn't exist."""
        # config_dir exists but trading_rules.json does not

        result = config_loader.load_trading_rules()

        assert result == config_loader.DEFAULT_TRADING_RULES

    def test_missing_file_warns_to_stderr(self, config_dir, capsys):
        """Verify warning message when config file missing."""
        result = config_loader.load_trading_rules()

        captured = capsys.readouterr()
        assert "trading_rules.json not found" in captured.err
        assert result == config_loader.DEFAULT_TRADING_RULES

    def test_malformed_json_returns_defaults(self, config_dir):
        """Graceful fallback on JSONDecodeError."""
        config_file = config_dir / "trading_rules.json"
        config_file.write_text('{ invalid json syntax')

        result = config_loader.load_trading_rules()

        assert result == config_loader.DEFAULT_TRADING_RULES

    def test_malformed_json_warns_to_stderr(self, config_dir, capsys):
        """Verify warning message for malformed JSON."""
        config_file = config_dir / "trading_rules.json"
        config_file.write_text('{ "incomplete": ')

        result = config_loader.load_trading_rules()

        captured = capsys.readouterr()
        assert "malformed" in captured.err
        assert result == config_loader.DEFAULT_TRADING_RULES

    def test_partial_config_merged_with_defaults(self, config_dir):
        """Sparse config works - only one key overridden."""
        config_file = config_dir / "trading_rules.json"
        config_file.write_text('{"net_liquidity": 100000}')

        result = config_loader.load_trading_rules()

        assert result["net_liquidity"] == 100000
        # All other defaults preserved
        assert len(result) == len(config_loader.DEFAULT_TRADING_RULES)

    def test_extra_keys_preserved(self, config_dir):
        """Unknown keys not stripped (future extensibility)."""
        config_file = config_dir / "trading_rules.json"
        config_file.write_text('{"custom_key": 123, "another_key": "test"}')

        result = config_loader.load_trading_rules()

        assert result["custom_key"] == 123
        assert result["another_key"] == "test"


# ============================================================================
# TEST CLASS 3: load_market_config()
# ============================================================================

class TestLoadMarketConfig:
    """Unit tests for load_market_config() function."""

    def test_load_valid_config(self, config_dir):
        """Load valid market config JSON."""
        config_file = config_dir / "market_config.json"
        config_data = {
            "FUTURES_MULTIPLIERS": {"/ES": 50, "/CL": 1000},
            "SECTOR_OVERRIDES": {"SPY": "Index"}
        }
        config_file.write_text(json.dumps(config_data))

        result = config_loader.load_market_config()

        assert result == config_data

    def test_missing_file_returns_empty_dict(self, config_dir):
        """No defaults for market config - returns empty dict."""
        result = config_loader.load_market_config()

        assert result == {}

    def test_missing_file_warns_to_stderr(self, config_dir, capsys):
        """Warning printed for missing file."""
        result = config_loader.load_market_config()

        captured = capsys.readouterr()
        assert "market_config.json not found" in captured.err

    def test_malformed_json_returns_empty_dict(self, config_dir):
        """Graceful fallback on JSONDecodeError."""
        config_file = config_dir / "market_config.json"
        config_file.write_text('[invalid')

        result = config_loader.load_market_config()

        assert result == {}

    def test_malformed_json_warns_to_stderr(self, config_dir, capsys):
        """Warning printed for malformed JSON."""
        config_file = config_dir / "market_config.json"
        config_file.write_text('{"broken": ')

        result = config_loader.load_market_config()

        captured = capsys.readouterr()
        assert "malformed" in captured.err


# ============================================================================
# TEST CLASS 4: load_system_config()
# ============================================================================

class TestLoadSystemConfig:
    """Unit tests for load_system_config() function."""

    def test_load_valid_config(self, config_dir):
        """Load valid system config JSON."""
        config_file = config_dir / "system_config.json"
        config_data = {"cache_ttl": 3600, "watchlist_path": "watchlist.csv"}
        config_file.write_text(json.dumps(config_data))

        result = config_loader.load_system_config()

        assert result == config_data

    def test_missing_file_returns_empty_dict(self, config_dir):
        """No defaults for system config - returns empty dict."""
        result = config_loader.load_system_config()

        assert result == {}

    def test_missing_file_warns_to_stderr(self, config_dir, capsys):
        """Warning printed for missing file."""
        result = config_loader.load_system_config()

        captured = capsys.readouterr()
        assert "system_config.json not found" in captured.err

    def test_malformed_json_returns_empty_dict(self, config_dir):
        """Graceful fallback on JSONDecodeError."""
        config_file = config_dir / "system_config.json"
        config_file.write_text('{')

        result = config_loader.load_system_config()

        assert result == {}

    def test_malformed_json_warns_to_stderr(self, config_dir, capsys):
        """Warning printed for malformed JSON."""
        config_file = config_dir / "system_config.json"
        config_file.write_text('{"incomplete"')

        result = config_loader.load_system_config()

        captured = capsys.readouterr()
        assert "malformed" in captured.err


# ============================================================================
# TEST CLASS 5: load_strategies()
# ============================================================================

class TestLoadStrategies:
    """Unit tests for load_strategies() function."""

    def test_load_valid_strategies(self, config_dir):
        """Load valid strategies file."""
        config_file = config_dir / "strategies.json"
        strategies_data = [
            {
                "id": "short_strangle",
                "name": "Short Strangle",
                "type": "undefined_risk",
                "setup": {"legs": 2},
                "management": {"profit_target_pct": 0.50},
                "metadata": {"gamma_trigger_dte": 21}
            }
        ]
        config_file.write_text(json.dumps(strategies_data))

        result = config_loader.load_strategies()

        assert "short_strangle" in result
        assert result["short_strangle"]["name"] == "Short Strangle"

    def test_returns_dict_keyed_by_id(self, config_dir):
        """Output structure verification - dict keyed by strategy id."""
        config_file = config_dir / "strategies.json"
        strategies_data = [
            {
                "id": "strat1",
                "name": "Strategy 1",
                "type": "defined_risk",
                "setup": {},
                "management": {"profit_target_pct": 0.50},
                "metadata": {"gamma_trigger_dte": 21}
            },
            {
                "id": "strat2",
                "name": "Strategy 2",
                "type": "defined_risk",
                "setup": {},
                "management": {"profit_target_pct": 0.60},
                "metadata": {"gamma_trigger_dte": 14}
            }
        ]
        config_file.write_text(json.dumps(strategies_data))

        result = config_loader.load_strategies()

        assert isinstance(result, dict)
        assert "strat1" in result
        assert "strat2" in result
        assert len(result) == 2


# ============================================================================
# TEST CLASS 6: Strategy Validation (strategy_loader.py)
# ============================================================================

class TestStrategyValidation:
    """Unit tests for validate_strategy() function."""

    def test_valid_strategy_passes(self, valid_strategy):
        """Full valid strategy object validates successfully."""
        result = strategy_loader.validate_strategy(valid_strategy)

        assert result is True

    @pytest.mark.parametrize("missing_field", ["id", "name", "type", "setup", "management"])
    def test_missing_required_field_fails(self, valid_strategy, missing_field):
        """Each required field must be present."""
        invalid = valid_strategy.copy()
        del invalid[missing_field]

        result = strategy_loader.validate_strategy(invalid)

        assert result is False

    def test_invalid_type_field_fails(self, valid_strategy):
        """Type must be 'defined_risk' or 'undefined_risk'."""
        invalid = valid_strategy.copy()
        invalid["type"] = "risky_business"

        result = strategy_loader.validate_strategy(invalid)

        assert result is False

    def test_missing_profit_target_fails(self, valid_strategy):
        """management.profit_target_pct is required."""
        invalid = valid_strategy.copy()
        invalid["management"] = {}

        result = strategy_loader.validate_strategy(invalid)

        assert result is False

    @pytest.mark.parametrize("invalid_target", [0.05, 2.0, -0.5, 1.5])
    def test_profit_target_out_of_range_fails(self, valid_strategy, invalid_target):
        """Profit target must be between 0.1 and 1.0."""
        invalid = valid_strategy.copy()
        invalid["management"]["profit_target_pct"] = invalid_target

        result = strategy_loader.validate_strategy(invalid)

        assert result is False

    def test_missing_gamma_trigger_dte_fails(self, valid_strategy):
        """metadata.gamma_trigger_dte is required."""
        invalid = valid_strategy.copy()
        invalid["metadata"] = {}

        result = strategy_loader.validate_strategy(invalid)

        assert result is False

    @pytest.mark.parametrize("invalid_dte", [-5, 0, "21", 21.5])
    def test_gamma_trigger_dte_invalid_fails(self, valid_strategy, invalid_dte):
        """gamma_trigger_dte must be positive integer."""
        invalid = valid_strategy.copy()
        invalid["metadata"]["gamma_trigger_dte"] = invalid_dte

        result = strategy_loader.validate_strategy(invalid)

        assert result is False

    def test_load_strategies_skips_invalid(self, config_dir, capsys):
        """Invalid strategies logged and skipped, valid ones loaded."""
        config_file = config_dir / "strategies.json"
        strategies_data = [
            {
                "id": "valid_strat",
                "name": "Valid",
                "type": "defined_risk",
                "setup": {},
                "management": {"profit_target_pct": 0.50},
                "metadata": {"gamma_trigger_dte": 21}
            },
            {
                "id": "invalid_strat",
                "name": "Invalid - Missing type"
                # Missing required fields
            }
        ]
        config_file.write_text(json.dumps(strategies_data))

        result = strategy_loader.load_strategies()

        # Only valid strategy loaded
        assert "valid_strat" in result
        assert "invalid_strat" not in result

        # Warning printed
        captured = capsys.readouterr()
        assert "Skipping invalid strategy" in captured.err


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
