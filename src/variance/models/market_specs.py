"""
Concrete Market Specifications

Implementations of the Specification pattern for volatility filtering.
"""

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from .specs import Specification


class LiquiditySpec(Specification[dict[str, Any]]):
    """
    Filters based on liquidity metrics.

    Prioritizes Tastytrade liquidity_rating (1-5 scale) when available.
    Falls back to bid/ask spread and volume analysis when Tastytrade data unavailable.

    Args:
        max_slippage: Maximum allowed bid/ask spread as percentage (fallback metric)
        min_vol: Minimum ATM volume required (fallback metric)
        allow_illiquid: If True, bypass all liquidity checks
        min_tt_liquidity_rating: Minimum Tastytrade liquidity rating (1-5, primary metric)
    """

    def __init__(
        self,
        max_slippage: float,
        min_vol: int,
        allow_illiquid: bool = False,
        min_tt_liquidity_rating: int = 4,
    ):
        self.max_slippage = max_slippage
        self.min_vol = min_vol
        self.allow_illiquid = allow_illiquid
        self.min_tt_liquidity_rating = min_tt_liquidity_rating

    def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
        if self.allow_illiquid:
            return True

        # --- Helper for spread calculation ---
        def calculate_slippage(metrics_dict: dict[str, Any]) -> tuple[bool, float]:
            """Returns (has_quote, max_slippage_found)."""
            call_bid = metrics_dict.get("call_bid")
            call_ask = metrics_dict.get("call_ask")
            put_bid = metrics_dict.get("put_bid")
            put_ask = metrics_dict.get("put_ask")

            max_val = 0.0
            quote_exists = False

            for bid, ask in [(call_bid, call_ask), (put_bid, put_ask)]:
                if bid is not None and ask is not None:
                    try:
                        f_bid, f_ask = float(bid), float(ask)
                        mid = (f_bid + f_ask) / 2
                        if mid > 0:
                            quote_exists = True
                            slippage = (f_ask - f_bid) / mid
                            if slippage > max_val:
                                max_val = slippage
                    except (ValueError, TypeError):
                        pass
            return quote_exists, max_val

        has_quote, max_slippage_found = calculate_slippage(metrics)

        # PRIMARY: Check Tastytrade liquidity_rating if present (1-5 scale)
        tt_rating = metrics.get("liquidity_rating")
        if tt_rating is not None:
            is_rated = int(tt_rating) >= self.min_tt_liquidity_rating
            if not is_rated:
                return False

            # SAFETY GUARD: Reject if spread is egregiously wide (> 25%), regardless of rating.
            # This protects against data anomalies or severe illiquidity that the static rating missed.
            if has_quote and max_slippage_found > 0.25:
                return False

            return True

        # FALLBACK: Use bid/ask spread logic when Tastytrade data unavailable
        # Implied Liquidity Check
        if has_quote and max_slippage_found <= self.max_slippage:
            return True

        vol_raw = metrics.get("option_volume", metrics.get("atm_volume"))
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
    """Requires tactical VRP to exceed minimum threshold (IV/HV30 or IV/HV20)."""

    def __init__(self, hv_floor: float, threshold: float = 1.0):
        self.hv_floor = hv_floor
        self.threshold = threshold

    def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
        vrp_tactical = metrics.get("vrp_tactical")
        if vrp_tactical is not None:
            return float(vrp_tactical) > self.threshold

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

        _vrp_tactical = iv_f / hv_floor
        return _vrp_tactical > self.threshold


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
            "tastytrade_fallback",
            "yfinance_unavailable_cached",
            None,
        ]
        return warning in soft_warnings


@dataclass(frozen=True)
class CorrelationResult:
    passed: bool
    correlation: Optional[float]
    used_proxy: bool


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

    def evaluate(self, metrics: dict[str, Any]) -> CorrelationResult:
        if self.portfolio_returns is None or len(self.portfolio_returns) == 0:
            return CorrelationResult(True, None, False)

        symbol = str(metrics.get("symbol", ""))
        candidate_returns = metrics.get("returns")

        # If no returns, try ETF proxy for futures (clock alignment)
        if not candidate_returns or len(candidate_returns) == 0:
            proxy_returns = self._get_etf_proxy_returns(symbol)
            if proxy_returns:
                candidate_returns = proxy_returns
                used_proxy = True
            else:
                # No returns and no proxy = cannot verify diversification
                # Must reject for safety (prevent blind correlation risk)
                return CorrelationResult(False, None, False)
        else:
            used_proxy = False

        from .correlation import CorrelationEngine

        corr = CorrelationEngine.calculate_correlation(
            self.portfolio_returns, np.array(candidate_returns)
        )

        return CorrelationResult(corr <= self.max_correlation, corr, used_proxy)

    def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
        return self.evaluate(metrics).passed


class IVPercentileSpec(Specification[dict[str, Any]]):
    """
    Filters based on IV Percentile (IVP) from Tastytrade.

    Note: Tastytrade does not provide IV Percentile for futures.
    Futures are automatically exempted from this filter.
    """

    def __init__(self, min_percentile: float):
        self.min_percentile = min_percentile

    def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
        # If IV Percentile is missing, we assume it fails the filter (conservative)
        # unless min_percentile is 0, then we pass everything.
        if self.min_percentile <= 0:
            return True

        # Futures exemption: Tastytrade doesn't provide IV Percentile for futures
        symbol = str(metrics.get("symbol", ""))
        if symbol.startswith("/"):
            return True

        iv_pct = metrics.get("iv_percentile")
        if iv_pct is None:
            return False

        try:
            # Tastytrade client already normalizes to 0-100 range
            # (e.g., 77.33 for 77th percentile)
            iv_pct_val = float(iv_pct)
            return iv_pct_val >= self.min_percentile
        except (ValueError, TypeError):
            return False


class VolatilityTrapSpec(Specification[dict[str, Any]]):
    """
    Hard gate against Volatility Traps (Positional).

    Rejects symbols where HV Rank < 15 (extreme low of 1-year range).
    Only applies when VRP > rich_threshold (1.30) to focus on "rich IV" setups.

    Rationale: If IV is rich (>1.30) but HV is at yearly lows (<15 percentile),
    you're likely catching a falling knife (vol compression mid-trade risk).

    Args:
        rank_threshold: Minimum HV Rank (default 15)
        vrp_rich_threshold: VRP level to trigger check (default 1.30)

    Note: This spec was refactored in ADR-0011 to remove compression logic.
    See VolatilityMomentumSpec for universal compression detection.
    """

    def __init__(self, rank_threshold: float, vrp_rich_threshold: float):
        self.rank_threshold = rank_threshold
        self.vrp_rich_threshold = vrp_rich_threshold

    def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
        hv_rank = metrics.get("hv_rank")
        vrp_s = metrics.get("vrp_structural")

        # Only apply if the symbol looks "Rich"
        if vrp_s is not None and float(vrp_s) > self.vrp_rich_threshold:
            if hv_rank is not None and float(hv_rank) < self.rank_threshold:
                return False

        return True


class VolatilityMomentumSpec(Specification[dict[str, Any]]):
    """
    Universal compression detection (not VRP-gated).

    Rejects symbols where HV30/HV90 < min_ratio (volatility contracting).
    Complements VolatilityTrapSpec by checking momentum across ALL VRP ranges.

    Use Cases:
    - Post-earnings calm (HV30 < HV90 as recent vol drops)
    - Market regime shift (vol trending down)
    - Prevents whipsaw from trading "rich" IV when HV is collapsing

    Args:
        min_momentum_ratio: Minimum HV30/HV90 ratio (default 0.85)
            - 1.0 = HV30 equals HV90 (neutral)
            - 0.85 = HV30 is 15% below HV90 (moderate contraction, OK)
            - 0.70 = HV30 is 30% below HV90 (severe contraction, reject)

    Example:
        Symbol: XYZ
        HV30: 15%
        HV90: 25%
        Momentum: 15/25 = 0.60 (40% contraction)

        With min_momentum_ratio = 0.85:
        Result: REJECT (0.60 < 0.85) - vol collapsing too fast

    Note: Added in ADR-0011 to fill VRP 1.10-1.30 blind spot.
    """

    def __init__(self, min_momentum_ratio: float = 0.85):
        self.min_momentum_ratio = min_momentum_ratio

    def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
        hv30 = metrics.get("hv30")
        hv90 = metrics.get("hv90")

        # Can't determine momentum - pass through
        if not hv30 or not hv90 or float(hv90) <= 0:
            return True

        try:
            momentum = float(hv30) / float(hv90)
            return momentum >= self.min_momentum_ratio
        except (ValueError, TypeError, ZeroDivisionError):
            return True  # Data error - don't reject


class RetailEfficiencySpec(Specification[dict[str, Any]]):
    """
    Ensures an underlying is 'Retail Efficient' for Tastylive mechanics.
    Criteria:
    1. Price Floor: Minimum underlying price ($25) to ensure manageable Gamma and strike density.
    2. Slippage Guard: Maximum Bid/Ask spread (5%) to prevent friction tax.
    """

    def __init__(self, min_price: float, max_slippage: float):
        self.min_price = min_price
        self.max_slippage = max_slippage

    def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
        symbol = str(metrics.get("symbol", ""))
        if symbol.startswith("/"):
            return True  # Futures exemption

        # Price Check
        price_raw = metrics.get("price")
        try:
            price = float(price_raw) if price_raw is not None else 0.0
        except (ValueError, TypeError):
            price = 0.0

        if price < self.min_price:
            return False

        # Slippage Check
        call_bid = metrics.get("call_bid")
        call_ask = metrics.get("call_ask")
        put_bid = metrics.get("put_bid")
        put_ask = metrics.get("put_ask")

        max_found = 0.0
        has_quote = False

        for bid, ask in [(call_bid, call_ask), (put_bid, put_ask)]:
            if bid is not None and ask is not None:
                try:
                    f_bid, f_ask = float(bid), float(ask)
                    mid = (f_bid + f_ask) / 2
                    if mid > 0:
                        has_quote = True
                        max_found = max(max_found, (f_ask - f_bid) / mid)
                except (ValueError, TypeError):
                    pass

        if has_quote and max_found > self.max_slippage:
            return False

        return True


class ScalableGateSpec(Specification[dict[str, Any]]):
    """
    Standalone gate to detect if an existing position is 'Scalable'.
    Permits re-entry/sizing if the volatility edge has surged significantly.
    """

    def __init__(self, markup_threshold: float, divergence_threshold: float):
        self.markup_threshold = markup_threshold
        self.divergence_threshold = divergence_threshold

    def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
        vtm_raw = metrics.get("vrp_tactical_markup")
        vtm = float(vtm_raw) if vtm_raw is not None else 0.0

        vsm_raw = metrics.get("vrp_structural")
        vsm = float(vsm_raw) if vsm_raw is not None else 1.0

        divergence = (vtm + 1.0) / vsm if vsm > 0 else 1.0

        # Trigger on either absolute markup surge or relative divergence momentum
        return vtm >= self.markup_threshold or divergence >= self.divergence_threshold
