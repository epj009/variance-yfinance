"""
DXLink Historical Volatility Provider using Tastytrade SDK.

Provides HV30/HV90 calculation via DXLink candle streaming as fallback
when Tastytrade REST API doesn't return these values.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from tastytrade import DXLinkStreamer, Session
from tastytrade.dxfeed import Candle

from .hv_calculator import CandleData, calculate_hv_metrics

logger = logging.getLogger(__name__)


class DXLinkHVProvider:
    """
    Provides HV30/HV90 calculation using DXLink candle streaming.

    Falls back to DXLink when Tastytrade REST API doesn't provide HV metrics.
    Uses tastytrade SDK for WebSocket management.
    """

    def __init__(self, session: Session):
        """
        Initialize DXLink HV provider.

        Args:
            session: Authenticated Tastytrade session
        """
        self.session = session

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
        # DXLink expects futures symbols without leading slash
        # Variance uses /ES, DXLink uses ES (auto-resolves to front-month)
        dxlink_symbol = symbol.lstrip("/") if symbol.startswith("/") else symbol

        try:
            async with DXLinkStreamer(self.session) as streamer:
                # Subscribe to daily candles with historical data
                start_time = datetime.now() - timedelta(days=days)

                await streamer.subscribe_candle(
                    symbols=[dxlink_symbol], interval="1d", start_time=start_time
                )

                # Collect candles
                candles: list[CandleData] = []

                async def collect_candles() -> None:
                    async for candle in streamer.listen(Candle):
                        # Check if candle is for our symbol
                        # eventSymbol format: "ES{=d,tho=true}" or "AAPL{=d,tho=true}"
                        if candle.event_symbol.startswith(dxlink_symbol):
                            candles.append(
                                CandleData(
                                    symbol=symbol,  # Use original symbol (with / for futures)
                                    time=candle.time,
                                    open=float(candle.open),
                                    high=float(candle.high),
                                    low=float(candle.low),
                                    close=float(candle.close),
                                    volume=float(candle.volume) if candle.volume else 0.0,
                                )
                            )

                            # Stop after getting enough candles
                            if len(candles) >= 100:
                                break

                try:
                    await asyncio.wait_for(collect_candles(), timeout=timeout)
                except asyncio.TimeoutError:
                    logger.debug(f"DXLink timeout after {timeout}s for {symbol}")

                # Unsubscribe (use DXLink symbol format)
                await streamer.unsubscribe(Candle, [f"{dxlink_symbol}{{=1d}}"])

                if not candles:
                    logger.warning(f"No candles received from DXLink for {symbol}")
                    return {
                        "price": None,
                        "hv30": None,
                        "hv90": None,
                        "returns": [],
                    }

                # Sort by time (oldest first)
                candles.sort(key=lambda c: c.time)

                # Current price (latest close)
                current_price = candles[-1].close if candles else None

                # Calculate HV metrics
                hv_metrics = calculate_hv_metrics(candles)

                # Calculate returns (last 60 days for VRP calculation)
                import math

                returns = []
                if len(candles) >= 2:
                    closes = [c.close for c in candles[-61:]]  # Last 61 to get 60 returns
                    returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]

                logger.info(
                    f"DXLink data for {symbol}: price={current_price}, {len(candles)} candles, "
                    f"HV30={hv_metrics['hv30']}, HV90={hv_metrics['hv90']}, "
                    f"returns={len(returns)}"
                )

                return {
                    "price": current_price,
                    "hv30": hv_metrics["hv30"],
                    "hv90": hv_metrics["hv90"],
                    "returns": returns,
                }

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
