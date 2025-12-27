"""
Classification Base

Defines the context and base classes for strategy identification.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from variance.models.position import Position
from variance.portfolio_parser import is_stock_type


@dataclass(frozen=True)
class ClassificationContext:
    """Pre-computed data shared across classifiers."""

    legs: list[Position]
    stock_legs: list[Position]
    option_legs: list[Position]

    call_legs: list[Position]
    put_legs: list[Position]

    long_calls: list[Position]
    short_calls: list[Position]
    long_puts: list[Position]
    short_puts: list[Position]

    long_call_qty: float
    short_call_qty: float
    long_put_qty: float
    short_put_qty: float

    long_call_strikes: list[float]
    short_call_strikes: list[float]
    long_put_strikes: list[float]
    short_put_strikes: list[float]

    is_multi_exp: bool
    underlying_price: float

    @classmethod
    def _ensure_positions(cls, legs: list[Position]) -> list[Position]:
        for idx, leg in enumerate(legs):
            if not isinstance(leg, Position):
                raise TypeError(
                    f"Classification expects Position objects; got {type(leg).__name__} "
                    f"at index {idx}. Use PortfolioParser.parse_positions or Position.from_row."
                )
        return list(legs)

    @classmethod
    def from_legs(cls, legs: list[Position]) -> "ClassificationContext":
        """Factory method to build context from raw legs."""
        positions = cls._ensure_positions(legs)
        stock_legs = [leg for leg in positions if is_stock_type(leg.asset_type)]
        option_legs = [leg for leg in positions if not is_stock_type(leg.asset_type)]

        def _get_side(leg: Position) -> str:
            s = str(leg.call_put or "").strip().upper()
            if s in ["CALL", "C"]:
                return "Call"
            if s in ["PUT", "P"]:
                return "Put"
            return ""

        def _get_qty(leg: Position) -> float:
            return float(leg.quantity)

        def _get_strike(leg: Position) -> float:
            return float(leg.strike or 0.0)

        call_legs = [leg for leg in option_legs if _get_side(leg) == "Call"]
        put_legs = [leg for leg in option_legs if _get_side(leg) == "Put"]

        long_calls = [leg for leg in call_legs if _get_qty(leg) > 0]
        short_calls = [leg for leg in call_legs if _get_qty(leg) < 0]
        long_puts = [leg for leg in put_legs if _get_qty(leg) > 0]
        short_puts = [leg for leg in put_legs if _get_qty(leg) < 0]

        expirations = set(str(leg.exp_date or "").strip() for leg in option_legs if leg.exp_date)
        price = float(positions[0].underlying_price) if positions else 0.0

        return cls(
            legs=positions,
            stock_legs=stock_legs,
            option_legs=option_legs,
            call_legs=call_legs,
            put_legs=put_legs,
            long_calls=long_calls,
            short_calls=short_calls,
            long_puts=long_puts,
            short_puts=short_puts,
            long_call_qty=sum(_get_qty(leg) for leg in long_calls),
            short_call_qty=sum(_get_qty(leg) for leg in short_calls),
            long_put_qty=sum(_get_qty(leg) for leg in long_puts),
            short_put_qty=sum(_get_qty(leg) for leg in short_puts),
            long_call_strikes=sorted([_get_strike(leg) for leg in long_calls]),
            short_call_strikes=sorted([_get_strike(leg) for leg in short_calls]),
            long_put_strikes=sorted([_get_strike(leg) for leg in long_puts]),
            short_put_strikes=sorted([_get_strike(leg) for leg in short_puts]),
            is_multi_exp=len(expirations) > 1,
            underlying_price=price,
        )


class StrategyClassifier(ABC):
    """Abstract base class for all strategy identifiers."""

    @abstractmethod
    def can_classify(self, legs: list[Position], ctx: ClassificationContext) -> bool:
        """Returns True if this classifier can handle the given legs."""
        pass

    @abstractmethod
    def classify(self, legs: list[Position], ctx: ClassificationContext) -> str:
        """Returns the strategy name."""
        pass
