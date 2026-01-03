"""
Pure Tastytrade Provider - Complete replacement for legacy provider.

Uses Tastytrade REST API + DXLink WebSocket streaming exclusively.
No legacy provider dependency.

Data Sources:
- Tastytrade REST /market-metrics: IV, IVR, IVP, beta, correlation, liquidity
- Tastytrade REST /market-data/by-type: Current prices (fast batch)
- DXLink WebSocket: HV30/HV90, returns (when needed)
"""

import logging
import os
import time
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
from .null_dxlink_provider import NullDXLinkProvider

try:
    from tastytrade import Session

    from .dxlink_hv_provider import DXLinkHVProvider

    DXLINK_AVAILABLE = True
except ImportError:
    Session: Any = None  # type: ignore[no-redef]
    DXLinkHVProvider: Any = None  # type: ignore[no-redef]
    DXLINK_AVAILABLE = False

logger = logging.getLogger(__name__)


def _safe_float(value: Any) -> float:
    """Coerce value to float with a safe fallback."""
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _get_price_from_sources(
    symbol: str,
    tt_prices: dict[str, dict[str, Any]],
    dxlink_prefetch: dict[str, dict[str, Any]],
) -> Optional[float]:
    """Return the best available underlying price from REST or DXLink."""
    prices = tt_prices.get(symbol, {})
    price = prices.get("price")
    if price is not None:
        try:
            return float(price)
        except (TypeError, ValueError):
            return None

    dxlink = dxlink_prefetch.get(symbol, {})
    dx_price = dxlink.get("price")
    if dx_price is not None:
        try:
            return float(dx_price)
        except (TypeError, ValueError):
            return None

    return None


class PureTastytradeProvider(IMarketDataProvider):
    """
    Pure Tastytrade market data provider.

    Eliminates legacy provider dependency entirely by using:
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

        # Initialize DXLink provider (Null Object pattern - never None)
        self.dxlink_provider: Any
        if self.tt_client and DXLINK_AVAILABLE:
            try:
                session = Session(
                    provider_secret=self.tt_client._credentials.client_secret,
                    refresh_token=self.tt_client._credentials.refresh_token,
                )
                self.dxlink_provider = DXLinkHVProvider(
                    session,
                    symbol_resolver=self._resolve_dxlink_symbol,
                    history_symbol_resolver=self._resolve_dxlink_history_symbols,
                    cache_instance=self.cache,
                )
                logger.info("DXLink provider initialized")
            except Exception as e:
                logger.warning(f"Could not initialize DXLink provider: {e}")
                self.dxlink_provider = NullDXLinkProvider()
        else:
            self.dxlink_provider = NullDXLinkProvider()

    def _resolve_dxlink_symbol(self, symbol: str) -> Optional[str]:
        if not self.tt_client:
            return None
        try:
            return self.tt_client.resolve_dxlink_symbol(symbol)
        except Exception as exc:
            logger.debug("DXLink symbol resolution failed for %s: %s", symbol, exc)
            return None

    def _resolve_dxlink_history_symbols(self, symbol: str) -> list[str]:
        if not self.tt_client:
            return []
        try:
            return self.tt_client.resolve_dxlink_history_symbols(symbol)
        except Exception as exc:
            logger.debug("DXLink history resolution failed for %s: %s", symbol, exc)
            return []

    def _get_futures_proxy_hv_symbol(self, symbol: str) -> Optional[str]:
        if not symbol.startswith("/"):
            return None
        proxy_config = md_settings.FUTURES_PROXY.get(symbol)
        if not proxy_config:
            return None
        hv_symbol = proxy_config.get("hv_symbol")
        if (
            isinstance(hv_symbol, str)
            and hv_symbol
            and not hv_symbol.endswith("=F")
            and not hv_symbol.startswith("/")
        ):
            return hv_symbol

        iv_symbol = proxy_config.get("iv_symbol")
        if (
            isinstance(iv_symbol, str)
            and iv_symbol
            and not iv_symbol.endswith("=F")
            and not iv_symbol.startswith("/")
        ):
            return iv_symbol

        for _family_name, members in md_settings.FAMILY_MAP.items():
            if symbol in members:
                for member in members:
                    if not member.startswith("/"):
                        return str(member)

        return None

    def get_market_data(
        self,
        symbols: list[str],
        *,
        include_returns: bool = False,
        include_option_quotes: bool = False,
    ) -> dict[str, MarketData]:
        """
        Get complete market data using pure Tastytrade sources.

        Flow:
        1. Fetch REST API metrics (IV, IVR, IVP, HV30*, HV90*)
        2. Fetch REST API prices (bid, ask, last, mark)
        3. For symbols missing HV or returns: Use DXLink
        4. Merge and return complete MarketData
        5. Optionally fetch ATM option quotes for yield calculations

        Args:
            symbols: List of ticker symbols
            include_option_quotes: If True, include ATM call/put bid/ask data

        Returns:
            Dictionary mapping symbols to MarketData objects
        """
        if not self.tt_client:
            logger.error("Tastytrade client not available")
            return {sym: cast(MarketData, {"error": "tastytrade_unavailable"}) for sym in symbols}

        unique_symbols = list(set(symbols))
        results: dict[str, MarketData] = {}

        # Benchmarking setup
        enable_benchmark = os.getenv("VARIANCE_BENCHMARK", "").lower() in ("1", "true", "yes")
        timings: dict[str, float] = {}

        try:
            # Step 1: Fetch metrics (IV, IVR, IVP, HV30, HV90, etc.)
            logger.debug(f"Fetching metrics for {len(unique_symbols)} symbols")
            t0 = time.time()
            tt_metrics = self.tt_client.get_market_metrics(unique_symbols)
            timings["TT Metrics API"] = (time.time() - t0) * 1000

            # Step 2: Fetch prices (bid, ask, last, mark, etc.)
            logger.debug(f"Fetching prices for {len(unique_symbols)} symbols")
            t0 = time.time()
            tt_prices = self.tt_client.get_market_data(unique_symbols)
            timings["TT Prices API"] = (time.time() - t0) * 1000

            dxlink_prefetch: dict[str, dict[str, Any]] = {}
            dxlink_needed = []
            for symbol in unique_symbols:
                metrics = tt_metrics.get(symbol)
                prices = tt_prices.get(symbol)
                hv30_rest = metrics.get("hv30") if metrics else None
                hv90_rest = metrics.get("hv90") if metrics else None
                is_futures = symbol.startswith("/")
                has_price = prices and prices.get("price") is not None
                needs_hv = hv30_rest is None or hv90_rest is None
                needs_returns = include_returns
                needs_price = is_futures and not has_price
                if needs_hv or needs_returns or needs_price:
                    dxlink_needed.append(symbol)

            if dxlink_needed and hasattr(self.dxlink_provider, "get_market_data_batch_sync"):
                try:
                    t0 = time.time()
                    dxlink_prefetch = self.dxlink_provider.get_market_data_batch_sync(dxlink_needed)
                    timings[f"DXLink Batch ({len(dxlink_needed)} symbols)"] = (
                        time.time() - t0
                    ) * 1000
                except Exception as e:
                    logger.warning(f"DXLink batch prefetch failed: {e}")

            option_quotes: dict[str, dict[str, Any]] = {}
            atm_option_map: dict[str, tuple[str, str]] = {}
            if include_option_quotes:
                t0 = time.time()
                option_quotes, atm_option_map = self._fetch_atm_option_quotes(
                    unique_symbols, tt_prices, dxlink_prefetch
                )
                timings["Option Quotes"] = (time.time() - t0) * 1000

            # Step 3: Merge data for each symbol
            t0 = time.time()
            for symbol in unique_symbols:
                try:
                    merged = self._merge_tastytrade_data(
                        symbol,
                        tt_metrics.get(symbol),
                        tt_prices.get(symbol),
                        include_returns=include_returns,
                        dxlink_data=dxlink_prefetch.get(symbol),
                        option_quotes=option_quotes,
                        atm_option_map=atm_option_map,
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
            timings["Merge & Cache"] = (time.time() - t0) * 1000

        except Exception as e:
            logger.error(f"Tastytrade API error: {e}")
            for symbol in unique_symbols:
                results[symbol] = cast(MarketData, {"error": "api_error", "symbol": symbol})

        # Data quality validation - fail fast if too many errors
        failed_symbols = [sym for sym, data in results.items() if "error" in data]
        error_rate = len(failed_symbols) / len(unique_symbols) if unique_symbols else 0

        if error_rate > 0.20:  # >20% failure threshold
            error_msg = f"Market data quality too low: {error_rate:.1%} failures ({len(failed_symbols)}/{len(unique_symbols)} symbols)"
            logger.error(error_msg)
            logger.error(f"Failed symbols: {failed_symbols[:10]}...")  # Show first 10
            raise RuntimeError(error_msg)

        # Add data quality metadata to results (for diagnostics)
        if failed_symbols:
            logger.warning(
                f"Partial market data failures: {len(failed_symbols)}/{len(unique_symbols)} symbols ({error_rate:.1%})"
            )

        # Print benchmark if enabled
        if enable_benchmark and timings:
            self._print_market_data_benchmark(timings, len(unique_symbols))

        return results

    def _print_market_data_benchmark(self, timings: dict[str, float], symbol_count: int) -> None:
        """Print detailed market data fetch benchmark."""
        total_ms = sum(timings.values())
        print("\n" + "=" * 80, file=__import__("sys").stderr)
        print("MARKET DATA FETCH BREAKDOWN", file=__import__("sys").stderr)
        print("=" * 80, file=__import__("sys").stderr)
        print(
            f"Total: {total_ms:.0f}ms for {symbol_count} symbols ({total_ms / symbol_count:.1f}ms/symbol)",
            file=__import__("sys").stderr,
        )
        print("-" * 80, file=__import__("sys").stderr)

        for name in sorted(timings.keys(), key=lambda k: timings[k], reverse=True):
            ms = timings[name]
            pct = (ms / total_ms * 100) if total_ms else 0
            print(f"  {name:<40} {ms:>8.0f}ms  ({pct:>5.1f}%)", file=__import__("sys").stderr)

        print("=" * 80, file=__import__("sys").stderr)

    def _build_base_data(self, symbol: str, prices: Optional[dict[str, Any]]) -> dict[str, Any]:
        """Build base data dictionary from price information."""
        return {
            "symbol": symbol,
            "price": prices.get("price") if prices else None,
            "bid": prices.get("bid") if prices else None,
            "ask": prices.get("ask") if prices else None,
            "is_stale": False,
            "data_source": "tastytrade",
        }

    def _add_tastytrade_metrics(
        self,
        merged: dict[str, Any],
        metrics: TastytradeMetrics,
        prices: Optional[dict[str, Any]],
    ) -> None:
        """Add Tastytrade metrics to merged data dictionary."""
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
        # NOTE: HV values are already normalized to PERCENT format (25.0 = 25%)
        # by tastytrade_client._normalize_hv() - no conversion needed here
        hv30_rest = metrics.get("hv30")
        hv90_rest = metrics.get("hv90")

        if hv30_rest is not None:
            merged["hv30"] = hv30_rest  # Already in percent: 25.0 = 25%
        if hv90_rest is not None:
            merged["hv90"] = hv90_rest  # Already in percent: 25.0 = 25%
            merged["hv90_source"] = "tastytrade_rest"

    def _needs_dxlink_fallback(
        self, merged: dict[str, Any], symbol: str, include_returns: bool
    ) -> bool:
        """Check if DXLink fallback is needed for missing data."""
        has_price = merged.get("price") is not None
        is_futures = symbol.startswith("/")

        needs_hv = merged.get("hv30") is None or merged.get("hv90") is None
        needs_returns = include_returns
        needs_price = is_futures and not has_price

        return needs_hv or needs_returns or needs_price

    def _apply_dxlink_fallback(
        self,
        merged: dict[str, Any],
        symbol: str,
        dxlink_data: Optional[dict[str, Any]],
        include_returns: bool,
    ) -> None:
        """Apply DXLink fallback for missing HV, returns, or price data."""
        has_price = merged.get("price") is not None
        is_futures = symbol.startswith("/")

        needs_hv = merged.get("hv30") is None or merged.get("hv90") is None
        needs_returns = include_returns
        needs_price = is_futures and not has_price

        try:
            logger.debug(
                f"Using DXLink for {symbol} (needs_hv={needs_hv}, needs_returns={needs_returns}, needs_price={needs_price})"
            )

            # Fetch from DXLink if not prefetched
            if dxlink_data is None:
                dxlink_data = self.dxlink_provider.get_market_data_sync(symbol)

            # Fill HV30 if missing
            if merged.get("hv30") is None and dxlink_data.get("hv30") is not None:
                merged["hv30"] = dxlink_data["hv30"]
                logger.debug(f"DXLink provided HV30 for {symbol}: {dxlink_data['hv30']:.4f}")

            # Fill HV90 if missing
            if merged.get("hv90") is None and dxlink_data.get("hv90") is not None:
                merged["hv90"] = dxlink_data["hv90"]
                merged["hv90_source"] = "dxlink"
                logger.debug(f"DXLink provided HV90 for {symbol}: {dxlink_data['hv90']:.4f}")

            # Add returns
            if dxlink_data.get("returns"):
                merged["returns"] = list(dxlink_data["returns"][-60:])  # Last 60

            # Update price if REST API didn't have one
            if not merged.get("price") and dxlink_data.get("price"):
                merged["price"] = dxlink_data["price"]
                logger.debug(f"DXLink provided price for {symbol}: ${dxlink_data['price']:.2f}")

        except Exception as e:
            logger.warning(f"DXLink fallback failed for {symbol}: {e}")

        # Try proxy for futures HV90 if still missing
        if is_futures and merged.get("hv90") is None:
            self._try_proxy_hv90(merged, symbol)

    def _try_proxy_hv90(self, merged: dict[str, Any], symbol: str) -> None:
        """Attempt to fill HV90 using a proxy symbol for futures."""
        proxy_symbol = self._get_futures_proxy_hv_symbol(symbol)
        if proxy_symbol and proxy_symbol != symbol:
            try:
                proxy_data = self.dxlink_provider.get_market_data_sync(proxy_symbol)
                proxy_hv90 = proxy_data.get("hv90")
                if proxy_hv90 is not None:
                    merged["hv90"] = proxy_hv90
                    merged["hv90_source"] = "proxy_dxlink"
                    merged["proxy"] = proxy_symbol
                    logger.debug(
                        "DXLink proxy HV90 for %s via %s: %.4f",
                        symbol,
                        proxy_symbol,
                        proxy_hv90,
                    )
            except Exception as e:
                logger.warning(f"DXLink proxy HV90 failed for {symbol} via {proxy_symbol}: {e}")

    def _calculate_vrp(self, merged: dict[str, Any]) -> None:
        """Calculate VRP (Variance Risk Premium) metrics."""
        iv = merged.get("iv")
        hv30 = merged.get("hv30")
        hv90 = merged.get("hv90")

        if iv and hv30:
            merged["vrp_tactical"] = iv / max(hv30, md_settings.HV_FLOOR_PERCENT)

        if iv and hv90:
            merged["vrp_structural"] = iv / max(hv90, md_settings.HV_FLOOR_PERCENT)

            # Warn about cross-asset VRP when using proxy HV90
            if merged.get("hv90_source") == "proxy_dxlink":
                proxy = merged.get("proxy", "unknown")
                symbol = merged.get("symbol", "unknown")
                merged["cross_asset_vrp"] = True
                merged["warning"] = f"cross_asset_vrp: {symbol} IV vs {proxy} HV90"
                logger.info(
                    f"Cross-asset VRP for {symbol}: IV/{proxy} HV90 = {merged['vrp_structural']:.2f} "
                    f"(tracking error risk during futures rolls)"
                )

    def _add_default_fields(self, merged: dict[str, Any]) -> None:
        """Add default fields to complete the MarketData structure."""
        # Calculate synthetic HV metrics
        if not merged.get("hv30") and not merged.get("hv90"):
            merged["hv20"] = None
            merged["hv252"] = None
        else:
            # Use HV30 as proxy for HV20
            merged["hv20"] = merged.get("hv30")
            # Use HV90 as proxy for HV252 (annualized)
            merged["hv252"] = merged.get("hv90")

        # Sector/earnings placeholder
        merged["sector"] = None
        if merged.get("proxy") is None:
            merged["proxy"] = None

    def _merge_tastytrade_data(
        self,
        symbol: str,
        metrics: Optional[TastytradeMetrics],
        prices: Optional[dict[str, Any]],
        *,
        include_returns: bool = False,
        dxlink_data: Optional[dict[str, Any]] = None,
        option_quotes: Optional[dict[str, dict[str, Any]]] = None,
        atm_option_map: Optional[dict[str, tuple[str, str]]] = None,
    ) -> MarketData:
        """
        Merge Tastytrade metrics and price data, filling gaps with DXLink.

        Args:
            symbol: Ticker symbol
            metrics: Data from /market-metrics
            prices: Data from /market-data/by-type
            include_returns: Whether to fetch return data
            dxlink_data: Pre-fetched DXLink data (optional)

        Returns:
            Complete MarketData object
        """
        # Validate that equities have price data
        has_price = prices and prices.get("price") is not None
        is_futures = symbol.startswith("/")

        if not has_price and not is_futures:
            return cast(
                MarketData,
                {
                    "error": "price_unavailable",
                    "symbol": symbol,
                },
            )

        # Build base data structure
        merged = self._build_base_data(symbol, prices)

        # Add Tastytrade metrics
        if metrics:
            self._add_tastytrade_metrics(merged, metrics, prices)

        # Apply DXLink fallback if needed
        if self._needs_dxlink_fallback(merged, symbol, include_returns):
            self._apply_dxlink_fallback(merged, symbol, dxlink_data, include_returns)

        # Add ATM option quotes if available
        if option_quotes and atm_option_map and symbol in atm_option_map:
            call_occ, put_occ = atm_option_map[symbol]
            call_quote = option_quotes.get(call_occ)
            put_quote = option_quotes.get(put_occ)
            if call_quote and put_quote:
                call_bid = call_quote.get("bid")
                call_ask = call_quote.get("ask")
                put_bid = put_quote.get("bid")
                put_ask = put_quote.get("ask")
                merged["call_bid"] = call_bid
                merged["call_ask"] = call_ask
                merged["put_bid"] = put_bid
                merged["put_ask"] = put_ask
                merged["atm_bid"] = _safe_float(call_bid) + _safe_float(put_bid)
                merged["atm_ask"] = _safe_float(call_ask) + _safe_float(put_ask)

        # Calculate VRP metrics
        self._calculate_vrp(merged)

        # Add default fields
        self._add_default_fields(merged)

        return cast(MarketData, merged)

    def _fetch_atm_option_quotes(
        self,
        symbols: list[str],
        tt_prices: dict[str, dict[str, Any]],
        dxlink_prefetch: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, dict[str, Any]], dict[str, tuple[str, str]]]:
        """Fetch ATM call/put quotes for each symbol when available."""
        if not self.tt_client:
            return {}, {}

        equity_symbols = [s for s in symbols if not str(s).startswith("/")]
        futures_symbols = [s for s in symbols if str(s).startswith("/")]

        chains = self.tt_client.get_option_chains_compact(equity_symbols)
        equity_options: list[str] = []
        future_options: list[str] = []
        atm_map: dict[str, tuple[str, str]] = {}

        for symbol in equity_symbols:
            chain = chains.get(symbol)
            if not chain:
                continue

            price = _get_price_from_sources(symbol, tt_prices, dxlink_prefetch)
            if price is None:
                continue

            selection = self.tt_client.find_atm_options(
                symbol,
                chain,
                price,
                target_dte=md_settings.TARGET_DTE,
                dte_min=md_settings.DTE_MIN,
                dte_max=md_settings.DTE_MAX,
            )
            if not selection:
                continue

            call_occ, put_occ = selection
            atm_map[symbol] = (call_occ, put_occ)
            equity_options.extend([call_occ, put_occ])

        for symbol in futures_symbols:
            price = _get_price_from_sources(symbol, tt_prices, dxlink_prefetch)
            if price is None:
                continue

            cache_key = make_cache_key("futures_option_chain", symbol)
            chain_items = self.cache.get(cache_key)
            if not isinstance(chain_items, list):
                chain_items = self.tt_client.get_futures_option_chain(symbol)
                ttl = get_dynamic_ttl("option_chain", 900)
                self.cache.set(cache_key, chain_items, ttl)

            selection = self.tt_client.find_futures_atm_options(
                chain_items,
                price,
                target_dte=md_settings.TARGET_DTE,
                dte_min=md_settings.DTE_MIN,
                dte_max=md_settings.DTE_MAX,
            )
            if not selection:
                continue

            call_occ, put_occ = selection
            atm_map[symbol] = (call_occ, put_occ)
            future_options.extend([call_occ, put_occ])

        equity_options = list(dict.fromkeys(equity_options))
        future_options = list(dict.fromkeys(future_options))

        if not equity_options and not future_options:
            return {}, atm_map

        option_quotes = self.tt_client.get_option_quotes(equity_options, future_options)
        return option_quotes, atm_map
