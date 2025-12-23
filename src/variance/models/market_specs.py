"""
Concrete Market Specifications

Implementations of the Specification pattern for volatility filtering.
"""
from typing import Any

from .specs import Specification


class LiquiditySpec(Specification[dict[str, Any]]):

    """Filters based on bid/ask spread and volume."""
    def __init__(self, max_slippage: float, min_vol: int, allow_illiquid: bool = False):
        self.max_slippage = max_slippage
        self.min_vol = min_vol
        self.allow_illiquid = allow_illiquid

    def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
        if self.allow_illiquid:
            return True

        symbol = str(metrics.get("symbol", ""))
        if symbol.startswith("/"):
            return True # Futures exemption

        # Implied Liquidity Check
        call_bid = metrics.get("call_bid")
        call_ask = metrics.get("call_ask")
        put_bid = metrics.get("put_bid")
        put_ask = metrics.get("put_ask")

        max_found = 0.0
        has_quote = False

        for bid, ask in [(call_bid, call_ask), (put_bid, put_ask)]:
            if bid is not None and ask is not None:
                mid = (float(bid) + float(ask)) / 2
                if mid > 0:
                    has_quote = True
                    max_found = max(max_found, (float(ask) - float(bid)) / mid)

        if has_quote and max_found <= self.max_slippage:
            return True

        # Volume Check
        vol = int(metrics.get("atm_volume", 0) or 0)
        return vol >= self.min_vol


class VrpStructuralSpec(Specification[dict[str, Any]]):
    """Filters based on Structural VRP (IV/HV252)."""
    def __init__(self, threshold: float):
        self.threshold = threshold

    def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
        vrp = metrics.get("vrp_structural")
        return vrp is not None and float(vrp) > self.threshold


class LowVolTrapSpec(Specification[dict[str, Any]]):
    """Prevents symbols with extremely low realized vol (noise) from passing."""
    def __init__(self, hv_floor: float):
        self.hv_floor = hv_floor

    def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
        hv252 = metrics.get("hv252")
        if hv252 is None:
            return True
        return float(hv252) >= self.hv_floor


class SectorExclusionSpec(Specification[dict[str, Any]]):
    """Excludes specific sectors."""
    def __init__(self, excluded_sectors: list[str]):
        self.excluded = [s.lower() for s in excluded_sectors]

    def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
        sector = str(metrics.get("sector", "Unknown")).lower()
        return sector not in self.excluded


class DataIntegritySpec(Specification[dict[str, Any]]):
    """Rejects candidates with critical data warnings."""
    def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
        warning = metrics.get("warning")
        soft_warnings = ["iv_scale_corrected", "iv_scale_assumed_decimal", None]
        return warning in soft_warnings
