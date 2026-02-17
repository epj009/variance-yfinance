"""
Triage Request and Tag Models

Defines the immutable data objects passed through the Triage Chain.
"""

from dataclasses import dataclass
from typing import Any, Optional

from variance.models.position import Position


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
    legs: tuple[Position, ...]

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

    # Strategy Metrics (for downstream checks)
    cluster_theta_raw: float = 0.0
    cluster_gamma_raw: float = 0.0
    hv20: Optional[float] = None
    hv252: Optional[float] = None
    beta_symbol: Optional[str] = None
    beta_price: Optional[float] = None
    beta_iv: Optional[float] = None

    # IV-HV Spread Metrics (for P/L expectations)
    iv_hv_spread_points: Optional[float] = None
    expected_daily_swing_pct: Optional[float] = None
    theta_decay_quality: Optional[str] = None

    # Multi-Tag System (collector pattern)
    tags: tuple[TriageTag, ...] = ()

    def __post_init__(self) -> None:
        for idx, leg in enumerate(self.legs):
            if not isinstance(leg, Position):
                raise TypeError(
                    f"TriageRequest expects Position legs; got {type(leg).__name__} "
                    f"at index {idx}. Use PortfolioParser.parse_positions or Position.from_row."
                )

    def with_tag(self, tag: TriageTag) -> "TriageRequest":
        """Returns a new request with an additional tag."""
        return TriageRequest(**{**self.__dict__, "tags": self.tags + (tag,)})

    @property
    def primary_action(self) -> Optional[TriageTag]:
        """Returns the highest-priority tag (lowest priority number)."""
        if not self.tags:
            return None
        return min(self.tags, key=lambda t: t.priority)
