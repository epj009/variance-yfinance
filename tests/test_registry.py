"""
Unit tests for the Strategy Registry pattern.
"""

import pytest
from variance.strategies.base import BaseStrategy
from variance.strategies.factory import StrategyFactory


class NewAlphaStrategy(BaseStrategy):
    """A fake new strategy for testing registration."""
    def is_tested(self, legs, price):
        return False

def test_manual_registration():
    # 1. Register a new type manually
    BaseStrategy.register("new_alpha")(NewAlphaStrategy)
    
    # 2. Verify registry lookup
    assert BaseStrategy.get_registered_class("new_alpha") == NewAlphaStrategy
    
    # 3. Verify Factory retrieval
    config = {
        "alpha_trade": {
            "metadata": {"type": "new_alpha"},
            "management": {}
        }
    }
    rules = {"profit_harvest_pct": 0.5}
    
    strategy = StrategyFactory.get_strategy("alpha_trade", config, rules)
    assert isinstance(strategy, NewAlphaStrategy)

def test_registry_fallback():
    # Verify that an unregistered type falls back to DefaultStrategy (the Safety Net)
    from variance.strategies.default import DefaultStrategy
    
    config = {
        "ghost_trade": {
            "metadata": {"type": "unregistered_type"},
            "management": {}
        }
    }
    rules = {"profit_harvest_pct": 0.5}
    
    strategy = StrategyFactory.get_strategy("ghost_trade", config, rules)
    assert isinstance(strategy, DefaultStrategy)
