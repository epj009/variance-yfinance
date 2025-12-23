"""
Strategy Factory

Creates strategy instances based on strategy IDs.
"""

from typing import Any

from .base import BaseStrategy
from .default import DefaultStrategy
from .short_theta import ShortThetaStrategy


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
        Instantiates the correct strategy class.

        Args:
            strategy_id: The ID mapped by strategy_detector (e.g., 'short_strangle')
            strategies_config: The full dictionary from strategies.json
            rules: Trading rules from trading_rules.json
        """
        config = strategies_config.get(strategy_id, {})

        # Categorize by 'type' defined in metadata
        meta = config.get("metadata", {})
        strat_type = meta.get("type", "undefined")

        # PREMIUM SELLERS (Theta positive / Net credit)
        # Any 'undefined' strategy is assumed to be short theta for safety
        if strat_type in ["undefined", "short_vol", "neutral"]:
            return ShortThetaStrategy(strategy_id, config, rules)

        # Explicit mapping for single options and common complex setups
        short_theta_ids = [
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
        ]

        if strategy_id in short_theta_ids or strategy_id is None:
            return ShortThetaStrategy(strategy_id, config, rules)

        return DefaultStrategy(strategy_id, config, rules)
