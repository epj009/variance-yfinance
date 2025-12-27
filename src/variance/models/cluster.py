"""
Strategy Cluster Domain Model

Groups individual positions into a logical strategy.
"""

from dataclasses import dataclass
from typing import Optional

from ..strategy_detector import identify_strategy, map_strategy_to_id
from .position import Position


@dataclass(frozen=True)
class StrategyCluster:
    """
    Represents a group of positions forming a single strategy (e.g., a Strangle).
    Calculates aggregate Greeks and handles strategy identification.
    """

    legs: list[Position]

    def __post_init__(self) -> None:
        for idx, leg in enumerate(self.legs):
            if not isinstance(leg, Position):
                raise TypeError(
                    f"StrategyCluster expects Position objects; got {type(leg).__name__} "
                    f"at index {idx}. Use PortfolioParser.parse_positions or Position.from_row."
                )

    @property
    def name(self) -> str:
        return identify_strategy(self.legs)

    @property
    def strategy_id(self) -> Optional[str]:
        return map_strategy_to_id(self.name, self.net_cost)

    @property
    def root_symbol(self) -> str:
        return self.legs[0].root_symbol if self.legs else "UNKNOWN"

    @property
    def net_pl(self) -> float:
        return sum(leg.pl_open for leg in self.legs)

    @property
    def net_cost(self) -> float:
        return sum(leg.cost for leg in self.legs)

    @property
    def total_delta(self) -> float:
        return sum(leg.beta_delta for leg in self.legs)

    @property
    def total_theta(self) -> float:
        return sum(leg.theta for leg in self.legs)

    @property
    def min_dte(self) -> int:
        option_dtes = [leg.dte for leg in self.legs if leg.is_option]
        return min(option_dtes) if option_dtes else 0
