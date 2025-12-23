"""
Portfolio Domain Model

Root object representing the entire trading account state.
"""

from dataclasses import dataclass, field
from typing import Any

from .cluster import StrategyCluster


@dataclass
class Portfolio:
    """
    Represents the complete state of a trading account.
    """

    clusters: list[StrategyCluster] = field(default_factory=list)
    net_liquidity: float = 0.0
    rules: dict[str, Any] = field(default_factory=dict)

    @property
    def total_theta(self) -> float:
        return sum(c.total_theta for c in self.clusters)

    @property
    def total_delta(self) -> float:
        return sum(c.total_delta for c in self.clusters)

    @property
    def cluster_count(self) -> int:
        return len(self.clusters)
