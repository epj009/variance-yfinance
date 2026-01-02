"""
DXLink Historical Volatility Provider using Tastytrade SDK.

Provides HV30/HV90 calculation via DXLink candle streaming as fallback
when Tastytrade REST API doesn't return these values.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from tastytrade import DXLinkStreamer, Session
from tastytrade.dxfeed import Candle

from ..market_data.cache import MarketCache, cache
from ..market_data.helpers import get_dynamic_ttl, make_cache_key
from .hv_calculator import CandleData, calculate_hv_metrics

logger = logging.getLogger(__name__)


class DXLinkHVProvider:
    """
    Provides HV30/HV90 calculation using DXLink candle streaming.

    Falls back to DXLink when Tastytrade REST API doesn't provide HV metrics.
    Uses tastytrade SDK for WebSocket management.
    """

    def __init__(
        self,
        session: Session,
        symbol_resolver: Optional[Callable[[str], Optional[str]]] = None,
        history_symbol_resolver: Optional[Callable[[str], list[str]]] = None,
        cache_instance: Optional[MarketCache] = None,
    ):
        """
        Initialize DXLink HV provider.

        Args:
            session: Authenticated Tastytrade session
        """
        self.session = session
        self.symbol_resolver = symbol_resolver
        self._resolved_symbol_cache: dict[str, str] = {}
        self.history_symbol_resolver = history_symbol_resolver
        self.cache = cache_instance if cache_instance else cache

    def _cache_key(self, symbol: str) -> str:
        return make_cache_key("dxlink_hv", symbol)

    def _get_cached(self, symbol: str) -> Optional[dict[str, Any]]:
        return self.cache.get(self._cache_key(symbol))

    def _set_cached(self, symbol: str, payload: dict[str, Any]) -> None:
        ttl = get_dynamic_ttl("hv", 86400)
        self.cache.set(self._cache_key(symbol), payload, ttl)

    def _resolve_dxlink_symbol(self, symbol: str) -> str:
        if not symbol:
            return symbol

        cached = self._resolved_symbol_cache.get(symbol)
        if cached:
            return cached

        resolved: Optional[str] = None
        if self.symbol_resolver:
            try:
                resolved = self.symbol_resolver(symbol)
            except Exception as exc:
                logger.debug("DXLink symbol resolver failed for %s: %s", symbol, exc)

        if not resolved:
            if symbol.startswith("/") and ":" not in symbol:
                resolved = symbol.lstrip("/")
            else:
                resolved = symbol

        self._resolved_symbol_cache[symbol] = resolved
        return resolved

    def _build_market_data_from_segments(
        self,
        symbol: str,
        candles_by_symbol: list[list[CandleData]],
        target_candles: int,
    ) -> dict[str, Any]:
        all_candles: list[CandleData] = []
        for segment in candles_by_symbol:
            all_candles.extend(segment)

        if not all_candles:
            return {
                "price": None,
                "hv30": None,
                "hv90": None,
                "returns": [],
            }

        if len(candles_by_symbol) > 1:
            combined: list[CandleData] = []
            for segment in candles_by_symbol:
                segment_sorted = sorted(segment, key=lambda c: c.time)
                if not combined:
                    combined = segment_sorted
                    continue
                # Adjust older segment to match the earliest price of the newer segment.
                boundary_new = combined[0].close if combined else None
                boundary_old = segment_sorted[-1].close if segment_sorted else None
                if boundary_new and boundary_old and boundary_new > 0 and boundary_old > 0:
                    factor = boundary_new / boundary_old
                    adjusted = []
                    for candle in segment_sorted:
                        adjusted.append(
                            CandleData(
                                symbol=candle.symbol,
                                time=candle.time,
                                open=candle.open * factor,
                                high=candle.high * factor,
                                low=candle.low * factor,
                                close=candle.close * factor,
                                volume=candle.volume,
                            )
                        )
                    combined = adjusted + combined
                else:
                    combined = segment_sorted + combined
            candles = combined
        else:
            candles = all_candles

        # Sort by time (oldest first) and dedupe by timestamp.
        deduped = {c.time: c for c in candles}
        candles = list(deduped.values())
        candles.sort(key=lambda c: c.time)
        if len(candles) > target_candles:
            candles = candles[-target_candles:]

        # Current price (latest close)
        current_price = candles[-1].close if candles else None

        # Calculate HV metrics
        hv_metrics = calculate_hv_metrics(candles)
        hv30 = hv_metrics.get("hv30")
        hv90 = hv_metrics.get("hv90")
        # DXLink HV is returned as a decimal; normalize to percent to match REST metrics.
        if hv30 is not None:
            hv30 *= 100.0
        if hv90 is not None:
            hv90 *= 100.0

        # Calculate returns (last 60 days for VRP calculation)
        import math

        returns = []
        if len(candles) >= 2:
            closes = [c.close for c in candles[-61:]]  # Last 61 to get 60 returns
            returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]

        logger.debug(
            f"DXLink data for {symbol}: price={current_price}, {len(candles)} candles, "
            f"HV30={hv30}, HV90={hv90}, "
            f"returns={len(returns)}"
        )

        return {
            "price": current_price,
            "hv30": hv30,
            "hv90": hv90,
            "returns": returns,
        }

    async def get_market_data(
        self,
        symbol: str,
        days: int = 150,
        timeout: float = 15.0,
    ) -> dict[str, Any]:
        """
        Get complete market data via DXLink candle streaming.

        Provides:
        - Current price (latest close)
        - HV30/HV90 (historical volatility)
        - Returns (log returns from candles)

        Args:
            symbol: Ticker symbol (e.g., "AAPL" or "/ES")
            days: Days of history to request (default 150 for ~100 trading days)
            timeout: Maximum wait time for data in seconds

        Returns:
            Dict with keys:
            - 'price': Latest close price
            - 'hv30': 30-day historical volatility
            - 'hv90': 90-day historical volatility
            - 'returns': List of log returns (last 60 days)
        """
        dxlink_symbol = self._resolve_dxlink_symbol(symbol)
        cached = self._get_cached(symbol)
        if cached:
            return cached
        is_futures = symbol.startswith("/")
        request_days = 220 if is_futures else days
        # HV90 needs 91 candles; returns need 61. 100 is a safe buffer.
        target_candles = 100
        history_symbols = []
        if is_futures and self.history_symbol_resolver:
            try:
                history_symbols = self.history_symbol_resolver(symbol)
            except Exception as exc:
                logger.debug("DXLink history symbol resolver failed for %s: %s", symbol, exc)
        if not history_symbols:
            history_symbols = [dxlink_symbol]

        try:
            async with DXLinkStreamer(self.session) as streamer:
                candles_by_symbol: list[list[CandleData]] = []

                async def fetch_candles_for_symbol(dxlink_symbol: str) -> list[CandleData]:
                    start_time = datetime.now() - timedelta(days=request_days)
                    await streamer.subscribe_candle(
                        symbols=[dxlink_symbol], interval="1d", start_time=start_time
                    )

                    candles: list[CandleData] = []

                    async def collect_candles() -> None:
                        async for candle in streamer.listen(Candle):
                            if candle.event_symbol.startswith(dxlink_symbol):
                                candles.append(
                                    CandleData(
                                        symbol=symbol,
                                        time=candle.time,
                                        open=float(candle.open),
                                        high=float(candle.high),
                                        low=float(candle.low),
                                        close=float(candle.close),
                                        volume=float(candle.volume) if candle.volume else 0.0,
                                    )
                                )
                                if len(candles) >= target_candles:
                                    break

                    try:
                        await asyncio.wait_for(collect_candles(), timeout=timeout)
                    except asyncio.TimeoutError:
                        logger.debug("DXLink timeout after %ss for %s", timeout, symbol)

                    await streamer.unsubscribe(Candle, [f"{dxlink_symbol}{{=1d}}"])
                    return candles

                for resolved_symbol in history_symbols:
                    if not resolved_symbol:
                        continue
                    candles_for_symbol = await fetch_candles_for_symbol(resolved_symbol)
                    if candles_for_symbol:
                        candles_by_symbol.append(candles_for_symbol)
                    if sum(len(seg) for seg in candles_by_symbol) >= target_candles:
                        break

                if not candles_by_symbol:
                    logger.warning("No candles received from DXLink for %s", symbol)
                    return {
                        "price": None,
                        "hv30": None,
                        "hv90": None,
                        "returns": [],
                    }

                payload = self._build_market_data_from_segments(
                    symbol, candles_by_symbol, target_candles
                )
                if payload.get("hv30") is not None or payload.get("hv90") is not None:
                    self._set_cached(symbol, payload)
                return payload

        except Exception as e:
            logger.error(f"DXLink error for {symbol}: {e}")
            return {
                "price": None,
                "hv30": None,
                "hv90": None,
                "returns": [],
            }

    def get_market_data_sync(self, symbol: str, **kwargs: Any) -> dict[str, Any]:
        """
        Synchronous wrapper for get_market_data.

        Args:
            symbol: Ticker symbol
            **kwargs: Passed to get_market_data

        Returns:
            Dict with keys 'price', 'hv30', 'hv90', 'returns'
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.get_market_data(symbol, **kwargs))

    async def get_market_data_batch(
        self,
        symbols: list[str],
        days: int = 150,
        timeout: float = 15.0,
    ) -> dict[str, dict[str, Any]]:
        if not symbols:
            return {}

        results: dict[str, dict[str, Any]] = {}
        pending_symbols: list[str] = []
        for symbol in symbols:
            cached = self._get_cached(symbol)
            if cached:
                results[symbol] = cached
            else:
                pending_symbols.append(symbol)

        if not pending_symbols:
            return results

        is_futures_any = any(sym.startswith("/") for sym in pending_symbols)
        request_days = 220 if is_futures_any else days
        target_candles = 100

        symbol_histories: dict[str, list[str]] = {}
        history_symbol_map: dict[str, tuple[str, int]] = {}

        for symbol in pending_symbols:
            dxlink_symbol = self._resolve_dxlink_symbol(symbol)
            history_symbols: list[str] = []
            if symbol.startswith("/") and self.history_symbol_resolver:
                try:
                    history_symbols = self.history_symbol_resolver(symbol)
                except Exception as exc:
                    logger.debug("DXLink history symbol resolver failed for %s: %s", symbol, exc)
            if not history_symbols:
                history_symbols = [dxlink_symbol]

            symbol_histories[symbol] = history_symbols
            for idx, hist_symbol in enumerate(history_symbols):
                if hist_symbol:
                    history_symbol_map[hist_symbol] = (symbol, idx)

        if not history_symbol_map:
            for symbol in pending_symbols:
                results[symbol] = {
                    "price": None,
                    "hv30": None,
                    "hv90": None,
                    "returns": [],
                }
            return results

        history_symbols = list(history_symbol_map.keys())
        history_symbols.sort(key=len, reverse=True)

        candles_by_symbol: dict[str, list[list[CandleData]]] = {
            symbol: [[] for _ in symbol_histories[symbol]] for symbol in pending_symbols
        }
        seen_times: dict[str, set[int]] = {symbol: set() for symbol in pending_symbols}
        finished: set[str] = set()

        try:
            async with DXLinkStreamer(self.session) as streamer:
                start_time = datetime.now() - timedelta(days=request_days)
                await streamer.subscribe_candle(
                    symbols=history_symbols, interval="1d", start_time=start_time
                )

                async def collect() -> None:
                    async for candle in streamer.listen(Candle):
                        event_symbol = candle.event_symbol
                        matched = None
                        for hist_symbol in history_symbols:
                            if event_symbol.startswith(hist_symbol):
                                matched = hist_symbol
                                break
                        if not matched:
                            continue
                        symbol, idx = history_symbol_map[matched]
                        candles_by_symbol[symbol][idx].append(
                            CandleData(
                                symbol=symbol,
                                time=candle.time,
                                open=float(candle.open),
                                high=float(candle.high),
                                low=float(candle.low),
                                close=float(candle.close),
                                volume=float(candle.volume) if candle.volume else 0.0,
                            )
                        )
                        seen_times[symbol].add(candle.time)
                        if len(seen_times[symbol]) >= target_candles:
                            finished.add(symbol)
                        if len(finished) == len(pending_symbols):
                            break

                try:
                    await asyncio.wait_for(collect(), timeout=timeout)
                except asyncio.TimeoutError:
                    logger.debug("DXLink timeout after %ss for batch", timeout)

                await streamer.unsubscribe(
                    Candle, [f"{hist_symbol}{{=1d}}" for hist_symbol in history_symbols]
                )

        except Exception as exc:
            logger.error("DXLink batch error: %s", exc)
            # Fill in errors for pending symbols only (keep cached results)
            for symbol in pending_symbols:
                if symbol not in results:
                    results[symbol] = {"price": None, "hv30": None, "hv90": None, "returns": []}
            return results

        for symbol in pending_symbols:
            payload = self._build_market_data_from_segments(
                symbol, candles_by_symbol.get(symbol, []), target_candles
            )
            if payload.get("hv30") is not None or payload.get("hv90") is not None:
                self._set_cached(symbol, payload)
            results[symbol] = payload

        return results

    def get_market_data_batch_sync(self, symbols: list[str], **kwargs: Any) -> dict[str, Any]:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.get_market_data_batch(symbols, **kwargs))

    def get_hv_metrics_sync(self, symbol: str, **kwargs: Any) -> dict[str, Optional[float]]:
        """
        Synchronous wrapper for HV metrics only (backwards compatibility).

        Args:
            symbol: Ticker symbol
            **kwargs: Passed to get_market_data

        Returns:
            Dict with keys 'hv30' and 'hv90'
        """
        data = self.get_market_data_sync(symbol, **kwargs)
        return {
            "hv30": data.get("hv30"),
            "hv90": data.get("hv90"),
        }
