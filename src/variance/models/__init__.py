"""
Variance Domain Models

Export core domain objects for external consumption.
"""

from typing import TYPE_CHECKING

__all__ = ["Position", "StrategyCluster", "Portfolio"]


if TYPE_CHECKING:
    from .cluster import StrategyCluster
    from .portfolio import Portfolio
    from .position import Position


def __getattr__(name: str) -> type:
    if name == "Position":
        from .position import Position

        return Position
    if name == "StrategyCluster":
        from .cluster import StrategyCluster

        return StrategyCluster
    if name == "Portfolio":
        from .portfolio import Portfolio

        return Portfolio
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
