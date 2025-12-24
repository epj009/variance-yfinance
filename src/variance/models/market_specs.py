"""
Concrete Market Specifications

Implementations of the Specification pattern for volatility filtering.
"""

from typing import Any, Optional

import numpy as np

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
            return True  # Futures exemption

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

        vol_raw = metrics.get("atm_volume")
        oi_raw = metrics.get("atm_open_interest")
        if not has_quote and vol_raw is None and oi_raw is None:
            return True

        # Volume Check
        vol = int(vol_raw or 0)
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


class VrpTacticalSpec(Specification[dict[str, Any]]):
    """Requires tactical VRP to be computable (IV and HV20)."""

    def __init__(self, hv_floor: float):
        self.hv_floor = hv_floor

    def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
        vrp_tactical = metrics.get("vrp_tactical")
        if vrp_tactical is not None:
            return True

        iv = metrics.get("iv")
        hv20 = metrics.get("hv20")
        if iv is None or hv20 is None:
            return False

        try:
            iv_f = float(iv)
            hv20_f = float(hv20)
        except (TypeError, ValueError):
            return False

        if hv20_f <= 0:
            return False

        hv_floor = max(hv20_f, self.hv_floor)
        if hv_floor <= 0:
            return False

        metrics["vrp_tactical"] = iv_f / hv_floor
        return True


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
        # Allow soft warnings and after-hours rescued data
        soft_warnings = [
            "iv_scale_corrected",
            "iv_scale_assumed_decimal",
            "after_hours_stale",
            None,
        ]
        return warning in soft_warnings


class CorrelationSpec(Specification[dict[str, Any]]):
    """Filters based on correlation with the current portfolio."""

    def __init__(
        self,
        portfolio_returns: Optional[np.ndarray],
        max_correlation: float,
        raw_data: Optional[dict[str, Any]] = None,
    ):
        self.portfolio_returns = portfolio_returns
        self.max_correlation = max_correlation
        self.raw_data = raw_data or {}

    def _get_etf_proxy_returns(self, symbol: str) -> Optional[list[Any]]:
        """
        Get ETF proxy returns for futures correlation (clock-aligned).

        Uses FAMILY_MAP to find ETF equivalent for futures symbols.
        Example: /ES -> SPY, /CL -> USO, /GC -> GLD

        Args:
            symbol: Futures symbol (e.g., "/ES")

        Returns:
            Returns from ETF proxy, or None if unavailable
        """
        # Only apply to futures symbols
        if not symbol.startswith("/"):
            return None

        from variance.config_loader import load_market_config

        market_config = load_market_config()
        family_map = market_config.get("FAMILY_MAP", {})

        # Find which family this futures belongs to
        for _family_name, members in family_map.items():
            if symbol in members:
                # Find first non-futures member (ETF) with returns data
                for member in members:
                    if not member.startswith("/") and member in self.raw_data:
                        proxy_data = self.raw_data[member]
                        proxy_returns = proxy_data.get("returns")
                        if proxy_returns and len(proxy_returns) > 0:
                            return list(proxy_returns)
                break

        return None

    def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
        if self.portfolio_returns is None or len(self.portfolio_returns) == 0:
            return True

        symbol = str(metrics.get("symbol", ""))
        candidate_returns = metrics.get("returns")

        # If no returns, try ETF proxy for futures (clock alignment)
        if not candidate_returns or len(candidate_returns) == 0:
            proxy_returns = self._get_etf_proxy_returns(symbol)
            if proxy_returns:
                candidate_returns = proxy_returns
                metrics["correlation_via_proxy"] = True  # Transparency flag
            else:
                # No returns and no proxy = cannot verify diversification
                # Must reject for safety (prevent blind correlation risk)
                return False

        from .correlation import CorrelationEngine

        corr = CorrelationEngine.calculate_correlation(
            self.portfolio_returns, np.array(candidate_returns)
        )

        # Attach the rho for downstream TUI rendering
        metrics["portfolio_rho"] = corr

        return corr <= self.max_correlation
