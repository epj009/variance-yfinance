"""
Concrete Market Specifications

Implementations of the Specification pattern for volatility filtering.
"""

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

        symbol = str(metrics.get("symbol", ""))
        if symbol.startswith("/"):
            return True  # Futures exemption

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
            "tastytrade_fallback",
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


class IVPercentileSpec(Specification[dict[str, Any]]):
    """Filters based on IV Percentile (IVP) from Tastytrade."""

    def __init__(self, min_percentile: float):
        self.min_percentile = min_percentile

    def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
        # If IV Percentile is missing, we assume it fails the filter (conservative)
        # unless min_percentile is 0, then we pass everything.
        if self.min_percentile <= 0:
            return True

        iv_pct = metrics.get("iv_percentile")
        if iv_pct is None:
            return False

        try:
            # Scale Tastytrade decimal (0.20) to 0-100 range (20.0)
            scaled_ivp = float(iv_pct) * 100.0
            return scaled_ivp >= self.min_percentile
        except (ValueError, TypeError):
            return False


class VolatilityTrapSpec(Specification[dict[str, Any]]):
    """
    Hard gate against Volatility Traps.
    Rejects symbols where realized volatility is either:
    1. Positional: Extreme low of its 1-year range (HV Rank < 15)
    2. Relative: Extremely compressed vs its own medium-term trend (HV30 / HV90 < 0.70)
    """

    def __init__(
        self, rank_threshold: float, compression_threshold: float, vrp_rich_threshold: float
    ):
        self.rank_threshold = rank_threshold
        self.compression_threshold = compression_threshold
        self.vrp_rich_threshold = vrp_rich_threshold

    def is_satisfied_by(self, metrics: dict[str, Any]) -> bool:
        hv_rank = metrics.get("hv_rank")
        hv30 = metrics.get("hv30")
        hv90 = metrics.get("hv90")
        vrp_s = metrics.get("vrp_structural")

        # Only apply trap logic if the symbol looks "Rich"
        if vrp_s is not None and float(vrp_s) > self.vrp_rich_threshold:
            # Trigger 1: Positional Rank (1-year context)
            if hv_rank is not None and float(hv_rank) < self.rank_threshold:
                return False

            # Trigger 2: Relative Compression (Quarterly context - Tastytrade Native)
            if hv30 and hv90 and float(hv90) > 0:
                if (float(hv30) / float(hv90)) < self.compression_threshold:
                    return False

        return True


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
