"""
Base Strategy Interface

Defines the contract for all specialized strategy logic in Variance.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional

from ..models.actions import ActionCommand, ActionFactory


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    Each strategy implementation handles its own profit targets,
    defense mechanics, and risk classification.
    """

    _registry: dict[str, type["BaseStrategy"]] = {}

    @classmethod
    def register(cls, strategy_type: str) -> Any:
        """Decorator to register a strategy subclass."""

        def decorator(subclass: type[BaseStrategy]) -> type[BaseStrategy]:
            cls._registry[strategy_type] = subclass
            return subclass

        return decorator

    @classmethod
    def get_registered_class(cls, strat_type: str) -> Optional[type["BaseStrategy"]]:
        """Returns the class registered for a given strategy type."""
        return cls._registry.get(strat_type)

    def __init__(self, strategy_id: str, config: dict[str, Any], rules: dict[str, Any]):
        self.strategy_id = strategy_id
        self.config = config
        self.rules = rules

        # Metadata
        meta = config.get("metadata", {})
        self.name = meta.get("name", strategy_id)
        self.type = meta.get("type", "undefined")
        self.gamma_trigger_dte = meta.get("gamma_trigger_dte", rules.get("gamma_dte_threshold", 21))
        self.earnings_stance = meta.get("earnings_stance", "avoid")

        # Management
        mgmt = config.get("management", {})
        self.profit_target_pct = mgmt.get(
            "profit_target_pct", rules.get("profit_harvest_pct", 0.50)
        )
        self.defense_mechanic = mgmt.get("defense_mechanic", "roll_untested")

    @abstractmethod
    def is_tested(self, legs: list[dict[str, Any]], underlying_price: float) -> bool:
        """Determines if the strategy is currently under pressure (ITM or breached)."""
        pass

    def check_harvest(self, symbol: str, pl_pct: float, days_held: int) -> Optional[ActionCommand]:
        """Generic profit harvesting logic using Command Pattern."""
        if pl_pct >= self.profit_target_pct:
            return ActionFactory.create(
                "HARVEST", symbol, f"Profit {pl_pct:.1%} (Target: {self.profit_target_pct:.0%})"
            )

        if 0 < days_held < 5 and pl_pct >= 0.25:
            return ActionFactory.create(
                "HARVEST", symbol, f"Velocity: {pl_pct:.1%} in {days_held}d (Early Win)"
            )

        return None

    def check_toxic_theta(
        self, symbol: str, metrics: dict[str, Any], market_data: dict[str, Any]
    ) -> Optional[ActionCommand]:
        """Re-implementation of the institutional 'Toxic Theta' check."""
        # Generic implementation suitable for most short-theta strategies
        if self.type != "undefined":
            return None  # Only check undefined/high-risk strategies for now

        return None
