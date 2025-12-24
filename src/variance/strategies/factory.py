"""
Strategy Factory

Creates strategy instances based on strategy IDs.
"""

from typing import Any

from .base import BaseStrategy
from .default import DefaultStrategy


class StrategyFactory:
    """
    Registry and factory for all Variance strategies.
    Maps strategy_id (from detector) to specialized logic classes.
    """

    @staticmethod
    def get_strategy(
        strategy_id: str, strategies_config: dict[str, Any], rules: dict[str, Any]
    ) -> BaseStrategy:
        """
        Instantiates the correct strategy class using the Registry pattern.

        Args:
            strategy_id: The ID mapped by strategy_detector (e.g., 'short_strangle')
            strategies_config: The full dictionary from strategies.json
            rules: Trading rules from trading_rules.json
        """
        config = strategies_config.get(strategy_id, {})
        meta = config.get("metadata", {})
        strat_type = meta.get("type", "undefined")

        # 1. Look up class in registry by type
        strat_class = BaseStrategy.get_registered_class(strat_type)

        # 2. Fallback to ID-based lookup if type registry fails (legacy support)
        if not strat_class:
            strat_class = BaseStrategy.get_registered_class(strategy_id)

        # 3. Final fallback to DefaultStrategy (Safety Net)
        if not strat_class:
            strat_class = DefaultStrategy

        return strat_class(strategy_id, config, rules)
