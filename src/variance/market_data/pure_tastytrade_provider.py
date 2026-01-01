"""
Pure Tastytrade Provider - Complete replacement for yfinance.

Uses Tastytrade REST API + DXLink WebSocket streaming exclusively.
No yfinance dependency.

Data Sources:
- Tastytrade REST /market-metrics: IV, IVR, IVP, beta, correlation, liquidity
- Tastytrade REST /market-data/by-type: Current prices (fast batch)
- DXLink WebSocket: HV30/HV90, returns (when needed)
"""

import logging
from typing import Any, Optional, cast

from ..interfaces import IMarketDataProvider, MarketData
from ..market_data import settings as md_settings
from ..market_data.cache import MarketCache, cache
from ..market_data.clock import is_market_open
from ..market_data.helpers import (
    get_dynamic_ttl,
    make_cache_key,
)
from ..tastytrade_client import TastytradeAuthError, TastytradeClient, TastytradeMetrics

try:
    from tastytrade import Session

    from .dxlink_hv_provider import DXLinkHVProvider

    DXLINK_AVAILABLE = True
except ImportError:
    DXLinkHVProvider = None  # type: ignore[assignment]
    Session = None  # type: ignore[assignment]
    DXLINK_AVAILABLE = False

logger = logging.getLogger(__name__)


class PureTastytradeProvider(IMarketDataProvider):
    """
    Pure Tastytrade market data provider.

    Eliminates yfinance dependency entirely by using:
    - Tastytrade REST API for metrics and prices
    - DXLink WebSocket for HV calculation and returns

    This is faster, more reliable, and has no rate limits.
    """

    def __init__(
        self,
        cache_instance: Optional[MarketCache] = None,
        allow_after_hours_fetch: bool = False,
        market_open_fn: Optional[Any] = None,
    ):
        self.cache = cache_instance if cache_instance else cache
        self.market_open_fn = market_open_fn or is_market_open
        self.allow_after_hours_fetch = allow_after_hours_fetch

        # Initialize Tastytrade REST client
        self.tt_client: Optional[TastytradeClient]
        try:
            self.tt_client = TastytradeClient()
        except TastytradeAuthError as e:
            logger.error(f"Tastytrade authentication failed: {e}")
            self.tt_client = None

        # Initialize DXLink provider
        self.dxlink_provider: Optional[Any] = None
        if self.tt_client and DXLINK_AVAILABLE:
            try:
                session = Session(
                    provider_secret=self.tt_client.client_secret,
                    refresh_token=self.tt_client.refresh_token,
                )
                self.dxlink_provider = DXLinkHVProvider(session)
                logger.info("DXLink provider initialized")
            except Exception as e:
                logger.warning(f"Could not initialize DXLink provider: {e}")
                self.dxlink_provider = None

    def get_market_data(self, symbols: list[str]) -> dict[str, MarketData]:
        """
        Get complete market data using pure Tastytrade sources.

        Flow:
        1. Fetch REST API metrics (IV, IVR, IVP, HV30*, HV90*)
        2. Fetch REST API prices (bid, ask, last, mark)
        3. For symbols missing HV or returns: Use DXLink
        4. Merge and return complete MarketData

        Args:
            symbols: List of ticker symbols

        Returns:
            Dictionary mapping symbols to MarketData objects
        """
        if not self.tt_client:
            logger.error("Tastytrade client not available")
            return {sym: cast(MarketData, {"error": "tastytrade_unavailable"}) for sym in symbols}

        unique_symbols = list(set(symbols))
        results: dict[str, MarketData] = {}

        try:
            # Step 1: Fetch metrics (IV, IVR, IVP, HV30, HV90, etc.)
            logger.debug(f"Fetching metrics for {len(unique_symbols)} symbols")
            tt_metrics = self.tt_client.get_market_metrics(unique_symbols)

            # Step 2: Fetch prices (bid, ask, last, mark, etc.)
            logger.debug(f"Fetching prices for {len(unique_symbols)} symbols")
            tt_prices = self.tt_client.get_market_data(unique_symbols)  # type: ignore[attr-defined]

            # Step 3: Merge data for each symbol
            for symbol in unique_symbols:
                try:
                    merged = self._merge_tastytrade_data(
                        symbol, tt_metrics.get(symbol), tt_prices.get(symbol)
                    )
                    results[symbol] = merged

                    # Cache the result
                    if "error" not in merged:
                        cache_key = make_cache_key("market_data", symbol)
                        self.cache.set(cache_key, merged, get_dynamic_ttl("iv", 900))

                except Exception as e:
                    logger.error(f"Error processing {symbol}: {e}")
                    results[symbol] = cast(
                        MarketData, {"error": "processing_error", "symbol": symbol}
                    )

        except Exception as e:
            logger.error(f"Tastytrade API error: {e}")
            for symbol in unique_symbols:
                results[symbol] = cast(MarketData, {"error": "api_error", "symbol": symbol})

        return results

    def _merge_tastytrade_data(
        self,
        symbol: str,
        metrics: Optional[TastytradeMetrics],
        prices: Optional[dict[str, Any]],
    ) -> MarketData:
        """
        Merge Tastytrade metrics and price data, filling gaps with DXLink.

        Args:
            symbol: Ticker symbol
            metrics: Data from /market-metrics
            prices: Data from /market-data/by-type

        Returns:
            Complete MarketData object
        """
        # For futures, REST API may not provide prices - use DXLink fallback
        has_price = prices and prices.get("price") is not None
        is_futures = symbol.startswith("/")

        if not has_price and not is_futures:
            # Equities should always have REST API prices
            return cast(
                MarketData,
                {
                    "error": "price_unavailable",
                    "symbol": symbol,
                },
            )

        # Base data from prices (if available)
        merged: dict[str, Any] = {
            "symbol": symbol,
            "price": prices.get("price") if prices else None,
            "bid": prices.get("bid") if prices else None,
            "ask": prices.get("ask") if prices else None,
            "is_stale": False,
            "data_source": "tastytrade",
        }

        # Add metrics if available
        if metrics:
            merged["iv"] = metrics.get("iv")
            merged["iv_rank"] = metrics.get("iv_rank")
            merged["iv_percentile"] = metrics.get("iv_percentile")
            merged["liquidity_rating"] = metrics.get("liquidity_rating")
            merged["liquidity_value"] = metrics.get("liquidity_value")
            merged["option_volume"] = metrics.get("option_volume")
            merged["atm_volume"] = metrics.get("option_volume")  # Alias
            merged["corr_spy_3month"] = metrics.get("corr_spy_3month")
            merged["beta"] = (prices.get("beta") if prices else None) or metrics.get("beta")
            merged["earnings_date"] = metrics.get("earnings_date")

            # HV from REST API (if available)
            # NOTE: REST API returns HV as percentage (11.79), convert to decimal (0.1179)
            hv30_rest = metrics.get("hv30")
            hv90_rest = metrics.get("hv90")

            if hv30_rest is not None:
                merged["hv30"] = hv30_rest / 100.0  # Convert percentage to decimal
            if hv90_rest is not None:
                merged["hv90"] = hv90_rest / 100.0  # Convert percentage to decimal

        # Check if we need DXLink fallback
        needs_hv = merged.get("hv30") is None or merged.get("hv90") is None
        needs_returns = True  # Always need returns for VRP calculation
        needs_price = is_futures and not has_price  # Futures need DXLink for price

        if (needs_hv or needs_returns or needs_price) and self.dxlink_provider:
            try:
                logger.debug(
                    f"Using DXLink for {symbol} (needs_hv={needs_hv}, needs_returns={needs_returns}, needs_price={needs_price})"
                )

                # Fetch from DXLink
                dxlink_data = self.dxlink_provider.get_market_data_sync(symbol)

                # Fill HV30 if missing
                if merged.get("hv30") is None and dxlink_data.get("hv30") is not None:
                    merged["hv30"] = dxlink_data["hv30"]
                    logger.info(f"DXLink provided HV30 for {symbol}: {dxlink_data['hv30']:.4f}")

                # Fill HV90 if missing
                if merged.get("hv90") is None and dxlink_data.get("hv90") is not None:
                    merged["hv90"] = dxlink_data["hv90"]
                    logger.info(f"DXLink provided HV90 for {symbol}: {dxlink_data['hv90']:.4f}")

                # Add returns
                if dxlink_data.get("returns"):
                    merged["returns"] = list(dxlink_data["returns"][-60:])  # Last 60

                # Update price if REST API didn't have one
                if not merged.get("price") and dxlink_data.get("price"):
                    merged["price"] = dxlink_data["price"]
                    logger.info(f"DXLink provided price for {symbol}: ${dxlink_data['price']:.2f}")

            except Exception as e:
                logger.warning(f"DXLink fallback failed for {symbol}: {e}")
                # Continue without DXLink data

        # Calculate synthetic HV metrics if we have returns but no HV30/HV90
        # (This shouldn't happen with DXLink, but defensive coding)
        if not merged.get("hv30") and not merged.get("hv90"):
            merged["hv20"] = None
            merged["hv252"] = None
        else:
            # Use HV30 as proxy for HV20
            merged["hv20"] = merged.get("hv30")
            # Use HV90 as proxy for HV252 (annualized)
            merged["hv252"] = merged.get("hv90")

        # Calculate VRP (Variance Risk Premium)
        iv = merged.get("iv")
        hv30 = merged.get("hv30")
        hv90 = merged.get("hv90")

        if iv and hv30:
            merged["vrp_tactical"] = iv / max(hv30, md_settings.HV_FLOOR_PERCENT)

        if iv and hv90:
            merged["vrp_structural"] = iv / hv90

        # Sector/earnings placeholder (TODO: Add sector mapping if needed)
        merged["sector"] = None  # Can add manual sector mapping later
        merged["proxy"] = None

        return cast(MarketData, merged)
