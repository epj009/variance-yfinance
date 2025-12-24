"""
Action Command Pattern Implementation

Encapsulates portfolio management actions into executable objects.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class ActionCommand(ABC):
    """Abstract Base Command for Portfolio Actions."""
    symbol: str
    logic: str

    @property
    @abstractmethod
    def action_code(self) -> str:
        """The standard variance action code (e.g., HARVEST, DEFENSE)."""
        pass

    def to_dict(self) -> dict[str, Any]:
        """Serializes the command for the JSON report."""
        return {
            "action_code": self.action_code,
            "logic": self.logic
        }


class HarvestCommand(ActionCommand):
    """Command to close a position and realize profit."""
    @property
    def action_code(self) -> str:
        return "HARVEST"


class DefenseCommand(ActionCommand):
    """Command to roll or hedge a tested position."""
    @property
    def action_code(self) -> str:
        return "DEFENSE"


class GammaCommand(ActionCommand):
    """Command to manage high gamma risk (< 21 DTE)."""
    @property
    def action_code(self) -> str:
        return "GAMMA"


class ToxicCommand(ActionCommand):
    """Command to exit a position with negative expected yield."""
    @property
    def action_code(self) -> str:
        return "TOXIC"


class ScalableCommand(ActionCommand):
    """Command to increase size in a high-VRP environment."""
    @property
    def action_code(self) -> str:
        return "SCALABLE"


class HedgeCheckCommand(ActionCommand):
    """Command to audit the utility of a protective position."""
    @property
    def action_code(self) -> str:
        return "HEDGE_CHECK"


class ExpiringCommand(ActionCommand):
    """Command to manage positions expiring today."""
    @property
    def action_code(self) -> str:
        return "EXPIRING"


class ActionFactory:
    """Factory to create ActionCommands from codes and logic."""

    _MAP: dict[str, type[ActionCommand]] = {
        "HARVEST": HarvestCommand,
        "DEFENSE": DefenseCommand,
        "GAMMA": GammaCommand,
        "TOXIC": ToxicCommand,
        "SCALABLE": ScalableCommand,
        "HEDGE_CHECK": HedgeCheckCommand,
        "EXPIRING": ExpiringCommand,
    }

    @staticmethod
    def create(code: Optional[str], symbol: str, logic: str) -> Optional[ActionCommand]:
        if not code:
            return None

        cmd_class = ActionFactory._MAP.get(code.upper())
        if cmd_class:
            return cmd_class(symbol=symbol, logic=logic)
        return None
