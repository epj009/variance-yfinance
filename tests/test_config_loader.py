"""
Comprehensive test suite for scripts/config_loader.py and scripts/strategy_loader.py

Coverage target: 85%+
Runtime target: <2 seconds
Network: NO (all file I/O mocked via tmp_path)

Priority:
1. Config loading from config directory - CRITICAL
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
# TEST CLASS 1: load_trading_rules()
# ============================================================================

class TestLoadTradingRules:
    """Unit tests for load_trading_rules() function."""

    def test_load_valid_config(self, config_dir):
        """Load valid JSON file."""
        # Arrange
        config_file = config_dir / "trading_rules.json"
        config_file.write_text('{"vrp_structural_threshold": 0.95, "net_liquidity": 75000}')

        # Act
        result = config_loader.load_trading_rules(config_dir=str(config_dir))

        # Assert
        assert result["vrp_structural_threshold"] == 0.95  # Overridden
        assert result["net_liquidity"] == 75000       # Overridden
        assert set(result.keys()) == {"vrp_structural_threshold", "net_liquidity"}

    def test_missing_file_returns_empty_dict(self, config_dir):
        """Graceful fallback when file doesn't exist."""
        result = config_loader.load_trading_rules(config_dir=str(config_dir))

        assert result == {}

    def test_missing_file_warns_to_stderr(self, config_dir, capsys):
        """Verify warning message when config file missing."""
        result = config_loader.load_trading_rules(config_dir=str(config_dir))

        captured = capsys.readouterr()
        assert "trading_rules.json not found" in captured.err
        assert result == {}

    def test_malformed_json_returns_empty_dict(self, config_dir):
        """Graceful fallback on JSONDecodeError."""
        config_file = config_dir / "trading_rules.json"
        config_file.write_text('{ invalid json syntax')

        result = config_loader.load_trading_rules(config_dir=str(config_dir))

        assert result == {}

    def test_malformed_json_warns_to_stderr(self, config_dir, capsys):
        """Verify warning message for malformed JSON."""
        config_file = config_dir / "trading_rules.json"
        config_file.write_text('{ "incomplete": ')

        result = config_loader.load_trading_rules(config_dir=str(config_dir))

        captured = capsys.readouterr()
        assert "malformed" in captured.err
        assert result == {}

    def test_extra_keys_preserved(self, config_dir):
        """Unknown keys not stripped (future extensibility)."""
        config_file = config_dir / "trading_rules.json"
        config_file.write_text('{"custom_key": 123, "another_key": "test"}')

        result = config_loader.load_trading_rules(config_dir=str(config_dir))

        assert result["custom_key"] == 123
        assert result["another_key"] == "test"


# ============================================================================
# TEST CLASS 2: load_market_config()
# ============================================================================

class TestLoadMarketConfig:
    """Unit tests for load_market_config() function."""

    def test_load_valid_config(self, config_dir):
        """Load valid market config JSON."""
        config_file = config_dir / "runtime_config.json"
        config_data = {
            "market": {
                "FUTURES_MULTIPLIERS": {"/ES": 50, "/CL": 1000},
                "SECTOR_OVERRIDES": {"SPY": "Index"}
            }
        }
        config_file.write_text(json.dumps(config_data))

        result = config_loader.load_market_config(config_dir=str(config_dir))

        assert result == config_data["market"]

    def test_missing_file_returns_empty_dict(self, config_dir):
        """Missing file returns empty dict."""
        result = config_loader.load_market_config(config_dir=str(config_dir))

        assert result == {}

    def test_missing_file_warns_to_stderr(self, config_dir, capsys):
        """Warning printed for missing file."""
        result = config_loader.load_market_config(config_dir=str(config_dir))

        captured = capsys.readouterr()
        assert "runtime_config.json not found" in captured.err

    def test_malformed_json_returns_empty_dict(self, config_dir):
        """Graceful fallback on JSONDecodeError."""
        config_file = config_dir / "runtime_config.json"
        config_file.write_text('[invalid')

        result = config_loader.load_market_config(config_dir=str(config_dir))

        assert result == {}

    def test_malformed_json_warns_to_stderr(self, config_dir, capsys):
        """Warning printed for malformed JSON."""
        config_file = config_dir / "runtime_config.json"
        config_file.write_text('{"broken": ')

        result = config_loader.load_market_config(config_dir=str(config_dir))

        captured = capsys.readouterr()
        assert "malformed" in captured.err


# ============================================================================
# TEST CLASS 3: load_system_config()
# ============================================================================

class TestLoadSystemConfig:
    """Unit tests for load_system_config() function."""

    def test_load_valid_config(self, config_dir):
        """Load valid system config JSON."""
        config_file = config_dir / "runtime_config.json"
        config_data = {"system": {"cache_ttl": 3600, "watchlist_path": "watchlist.csv"}}
        config_file.write_text(json.dumps(config_data))

        result = config_loader.load_system_config(config_dir=str(config_dir))

        assert result == config_data["system"]

    def test_missing_file_returns_empty_dict(self, config_dir):
        """Missing file returns empty dict."""
        result = config_loader.load_system_config(config_dir=str(config_dir))

        assert result == {}

    def test_missing_file_warns_to_stderr(self, config_dir, capsys):
        """Warning printed for missing file."""
        result = config_loader.load_system_config(config_dir=str(config_dir))

        captured = capsys.readouterr()
        assert "runtime_config.json not found" in captured.err

    def test_malformed_json_returns_empty_dict(self, config_dir):
        """Graceful fallback on JSONDecodeError."""
        config_file = config_dir / "runtime_config.json"
        config_file.write_text('{')

        result = config_loader.load_system_config(config_dir=str(config_dir))

        assert result == {}

    def test_malformed_json_warns_to_stderr(self, config_dir, capsys):
        """Warning printed for malformed JSON."""
        config_file = config_dir / "runtime_config.json"
        config_file.write_text('{"incomplete"')

        result = config_loader.load_system_config(config_dir=str(config_dir))

        captured = capsys.readouterr()
        assert "malformed" in captured.err


# ============================================================================
# TEST CLASS 4: load_strategies()
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

        result = config_loader.load_strategies(config_dir=str(config_dir))

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

        result = config_loader.load_strategies(config_dir=str(config_dir))

        assert isinstance(result, dict)
        assert "strat1" in result
        assert "strat2" in result
        assert len(result) == 2


# ============================================================================
# TEST CLASS 5: load_config_bundle()
# ============================================================================

class TestLoadConfigBundle:
    """Unit tests for load_config_bundle() function."""

    def test_load_bundle_and_override(self, config_dir):
        (config_dir / "trading_rules.json").write_text('{"net_liquidity": 50000}')
        runtime_config = {
            "system": {"watchlist_path": "watchlists/default.csv"},
            "market": {},
            "screener_profiles": {}
        }
        (config_dir / "runtime_config.json").write_text(json.dumps(runtime_config))
        (config_dir / "strategies.json").write_text('[]')

        bundle = config_loader.load_config_bundle(config_dir=str(config_dir))
        assert "trading_rules" in bundle
        assert bundle["trading_rules"]["net_liquidity"] == 50000

        override = {"trading_rules": {"net_liquidity": 75000}}
        bundle_override = config_loader.load_config_bundle(config_dir=str(config_dir), overrides=override)
        assert bundle_override["trading_rules"]["net_liquidity"] == 75000


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
