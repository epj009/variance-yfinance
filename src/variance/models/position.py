"""
Position Domain Model

Encapsulates a single position leg with validated data access.
"""

from dataclasses import dataclass
from typing import Any, Optional

from ..portfolio_parser import get_root_symbol, is_stock_type, parse_currency, parse_dte


@dataclass(frozen=True)
class Position:
    """
    Represents a single position leg (Option or Stock).
    Encapsulates raw broker data and provides clean properties.
    """

    symbol: str
    asset_type: str
    quantity: float
    strike: Optional[float] = None
    dte: int = 0
    exp_date: Optional[str] = None
    call_put: Optional[str] = None
    underlying_price: float = 0.0
    pl_open: float = 0.0
    cost: float = 0.0
    delta: float = 0.0
    beta_delta: float = 0.0
    beta_gamma: Optional[float] = None
    theta: float = 0.0
    gamma: float = 0.0
    vega: float = 0.0
    bid: float = 0.0
    ask: float = 0.1
    mark: float = 0.05
    open_date: Optional[str] = None
    raw_data: Optional[dict[str, Any]] = None

    @property
    def root_symbol(self) -> str:
        return get_root_symbol(self.symbol)

    @property
    def is_option(self) -> bool:
        return not is_stock_type(self.asset_type)

    @property
    def is_stock(self) -> bool:
        return is_stock_type(self.asset_type)

    @property
    def is_short(self) -> bool:
        return self.quantity < 0

    @property
    def is_long(self) -> bool:
        return self.quantity > 0

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "Position":
        """Factory method to create a Position from a normalized CSV row."""
        return cls(
            symbol=row.get("Symbol", "UNKNOWN"),
            asset_type=row.get("Type", "Option"),
            quantity=parse_currency(row.get("Quantity", "0")),
            strike=parse_currency(row.get("Strike Price")) or None,
            dte=parse_dte(row.get("DTE")),
            exp_date=row.get("Exp Date") or None,
            call_put=row.get("Call/Put") or None,
            underlying_price=parse_currency(row.get("Underlying Last Price", "0")),
            pl_open=parse_currency(row.get("P/L Open", "0")),
            cost=parse_currency(row.get("Cost", "0")),
            delta=parse_currency(row.get("Delta", "0")),
            beta_delta=parse_currency(row.get("beta_delta") or row.get("Delta", "0")),
            beta_gamma=(
                parse_currency(row.get("beta_gamma"))
                if row.get("beta_gamma") is not None and str(row.get("beta_gamma")).strip() != ""
                else None
            ),
            theta=parse_currency(row.get("Theta", "0")),
            gamma=parse_currency(row.get("Gamma", "0")),
            vega=parse_currency(row.get("Vega", "0")),
            bid=parse_currency(row.get("Bid", "0")),
            ask=parse_currency(row.get("Ask", "0")),
            mark=parse_currency(row.get("Mark") or row.get("Mid", "0")),
            open_date=row.get("Open Date"),
            raw_data=row,
        )
