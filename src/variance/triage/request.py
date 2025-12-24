"""
Triage Request and Tag Models

Defines the immutable data objects passed through the Triage Chain.
"""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class TriageTag:
    """A single triage tag applied to a position."""

    tag_type: str  # "HARVEST", "GAMMA", "EARNINGS_WARNING", etc.
    priority: int  # Lower = more urgent
    logic: str  # Human-readable reason
    action_cmd: Optional[Any] = None  # Optional actionable command


@dataclass(frozen=True)
class TriageRequest:
    """Immutable request object passed through the triage chain."""

    # Cluster Metrics
    root: str
    strategy_name: str
    strategy_id: Optional[str]
    dte: int
    net_pl: float
    net_cost: float
    strategy_delta: float
    strategy_gamma: float
    pl_pct: Optional[float]
    days_held: int
    price: float
    legs: tuple[dict[str, Any], ...]

    # Market Context
    vrp_structural: Optional[float]
    vrp_tactical: Optional[float]
    is_stale: bool
    sector: str
    earnings_date: Optional[str]

    # Portfolio Context
    portfolio_beta_delta: float
    net_liquidity: float

    # Strategy Object (for delegation)
    strategy_obj: Any  # BaseStrategy instance

    # Multi-Tag System (collector pattern)
    tags: tuple[TriageTag, ...] = ()

    def with_tag(self, tag: TriageTag) -> "TriageRequest":
        """Returns a new request with an additional tag."""
        return TriageRequest(**{**self.__dict__, "tags": self.tags + (tag,)})

    @property
    def primary_action(self) -> Optional[TriageTag]:
        """Returns the highest-priority tag (lowest priority number)."""
        if not self.tags:
            return None
        return min(self.tags, key=lambda t: t.priority)
