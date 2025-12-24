"""
Classification Base

Defines the context and base classes for strategy identification.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from variance.portfolio_parser import is_stock_type, parse_currency


@dataclass(frozen=True)
class ClassificationContext:
    """Pre-computed data shared across classifiers."""

    legs: list[dict[str, Any]]
    stock_legs: list[dict[str, Any]]
    option_legs: list[dict[str, Any]]

    call_legs: list[dict[str, Any]]
    put_legs: list[dict[str, Any]]

    long_calls: list[dict[str, Any]]
    short_calls: list[dict[str, Any]]
    long_puts: list[dict[str, Any]]
    short_puts: list[dict[str, Any]]

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
    def from_legs(cls, legs: list[dict[str, Any]]) -> "ClassificationContext":
        """Factory method to build context from raw legs."""
        stock_legs = [leg for leg in legs if is_stock_type(leg.get("Type", ""))]
        option_legs = [leg for leg in legs if not is_stock_type(leg.get("Type", ""))]

        def _get_side(leg):
            s = str(leg.get("Call/Put", "")).strip().upper()
            if s in ["CALL", "C"]:
                return "Call"
            if s in ["PUT", "P"]:
                return "Put"
            return ""

        def _get_qty(leg):
            return float(parse_currency(leg.get("Quantity", "0")))

        def _get_strike(leg):
            return float(parse_currency(leg.get("Strike Price", "0")))

        call_legs = [leg for leg in option_legs if _get_side(leg) == "Call"]
        put_legs = [leg for leg in option_legs if _get_side(leg) == "Put"]

        long_calls = [leg for leg in call_legs if _get_qty(leg) > 0]
        short_calls = [leg for leg in call_legs if _get_qty(leg) < 0]
        long_puts = [leg for leg in put_legs if _get_qty(leg) > 0]
        short_puts = [leg for leg in put_legs if _get_qty(leg) < 0]

        expirations = set(
            str(leg.get("Exp Date", "")).strip() for leg in option_legs if leg.get("Exp Date")
        )
        price = float(parse_currency(legs[0].get("Underlying Last Price", "0"))) if legs else 0.0

        return cls(
            legs=legs,
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
    def can_classify(self, legs: list[dict[str, Any]], ctx: ClassificationContext) -> bool:
        """Returns True if this classifier can handle the given legs."""
        pass

    @abstractmethod
    def classify(self, legs: list[dict[str, Any]], ctx: ClassificationContext) -> str:
        """Returns the strategy name."""
        pass
