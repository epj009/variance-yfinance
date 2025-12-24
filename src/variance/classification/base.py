"""
Classification Base and Context

Defines the shared state and contract for all strategy classifiers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from variance.portfolio_parser import is_stock_type, parse_currency


@dataclass(frozen=True)
class ClassificationContext:
    """Pre-computed data shared across classifiers."""

    legs: List[Dict[str, Any]]
    stock_legs: List[Dict[str, Any]]
    option_legs: List[Dict[str, Any]]

    call_legs: List[Dict[str, Any]]
    put_legs: List[Dict[str, Any]]

    long_calls: List[Dict[str, Any]]
    short_calls: List[Dict[str, Any]]
    long_puts: List[Dict[str, Any]]
    short_puts: List[Dict[str, Any]]

    long_call_qty: float
    short_call_qty: float
    long_put_qty: float
    short_put_qty: float

    long_call_strikes: List[float]
    short_call_strikes: List[float]
    long_put_strikes: List[float]
    short_put_strikes: List[float]

    is_multi_exp: bool
    underlying_price: float

    @classmethod
    def from_legs(cls, legs: List[Dict[str, Any]]) -> "ClassificationContext":
        """Factory method to build context from raw legs."""
        stock_legs = [l for l in legs if is_stock_type(l.get("Type", ""))]
        option_legs = [l for l in legs if not is_stock_type(l.get("Type", ""))]

        def _get_side(leg):
            s = str(leg.get("Call/Put", "")).strip().upper()
            if s in ["CALL", "C"]: return "Call"
            if s in ["PUT", "P"]: return "Put"
            return ""

        def _get_qty(leg):
            return float(parse_currency(leg.get("Quantity", "0")))

        def _get_strike(leg):
            return float(parse_currency(leg.get("Strike Price", "0")))

        call_legs = [l for l in option_legs if _get_side(l) == "Call"]
        put_legs = [l for l in option_legs if _get_side(l) == "Put"]

        long_calls = [l for l in call_legs if _get_qty(l) > 0]
        short_calls = [l for l in call_legs if _get_qty(l) < 0]
        long_puts = [l for l in put_legs if _get_qty(l) > 0]
        short_puts = [l for l in put_legs if _get_qty(l) < 0]

        expirations = set(str(l.get("Exp Date", "")).strip() for l in option_legs if l.get("Exp Date"))
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
            long_call_qty=sum(_get_qty(l) for l in long_calls),
            short_call_qty=sum(_get_qty(l) for l in short_calls),
            long_put_qty=sum(_get_qty(l) for l in long_puts),
            short_put_qty=sum(_get_qty(l) for l in short_puts),
            long_call_strikes=sorted([_get_strike(l) for l in long_calls]),
            short_call_strikes=sorted([_get_strike(l) for l in short_calls]),
            long_put_strikes=sorted([_get_strike(l) for l in long_puts]),
            short_put_strikes=sorted([_get_strike(l) for l in short_puts]),
            is_multi_exp=len(expirations) > 1,
            underlying_price=price,
        )


class StrategyClassifier(ABC):
    """Abstract base class for strategy classifiers."""

    @abstractmethod
    def can_classify(self, legs: List[Dict[str, Any]], ctx: ClassificationContext) -> bool:
        """Returns True if this classifier can handle the given legs."""
        pass

    @abstractmethod
    def classify(self, legs: List[Dict[str, Any]], ctx: ClassificationContext) -> str:
        """Returns the strategy name."""
        pass
