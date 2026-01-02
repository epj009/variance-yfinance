"""
DXLink WebSocket client for real-time and historical market data.

Provides access to DXFeed/DXLink streaming market data via Tastytrade's
WebSocket API, including:
- Historical OHLC candles for HV calculation
- Real-time Greeks for options
- Real-time quotes and trades

Authentication via OAuth 2.0 tokens.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

import websockets
from websockets.client import WebSocketClientProtocol

logger = logging.getLogger(__name__)


@dataclass
class CandleData:
    """OHLC candle data point."""

    symbol: str
    time: int  # Unix epoch milliseconds
    open: float
    high: float
    low: float
    close: float
    volume: float

    @classmethod
    def from_event(cls, event: dict[str, Any]) -> "CandleData":
        """Create from DXLink Candle event."""
        # Extract base symbol (remove {=1d} suffix if present)
        event_symbol = event.get("eventSymbol", "")
        base_symbol = event_symbol.split("{")[0] if "{" in event_symbol else event_symbol

        return cls(
            symbol=base_symbol,
            time=event.get("time", 0),
            open=event.get("open", 0.0),
            high=event.get("high", 0.0),
            low=event.get("low", 0.0),
            close=event.get("close", 0.0),
            volume=event.get("volume", 0.0),
        )


class DXLinkClient:
    """
    DXLink WebSocket client for market data streaming.

    Connects to Tastytrade's DXLink WebSocket API using OAuth authentication.
    Supports historical and real-time OHLC candles, Greeks, quotes, and trades.
    """

    def __init__(
        self,
        dxlink_url: str,
        auth_token: str,
        timeout: float = 30.0,
    ):
        """
        Initialize DXLink client.

        Args:
            dxlink_url: DXLink WebSocket URL (from /api-quote-tokens)
            auth_token: DXLink authentication token (from /api-quote-tokens)
            timeout: WebSocket operation timeout in seconds
        """
        self.dxlink_url = dxlink_url
        self.auth_token = auth_token
        self.timeout = timeout
        self.websocket: Optional[WebSocketClientProtocol] = None
        self.message_id = 0

    async def connect(self) -> None:
        """
        Connect to DXLink WebSocket.

        Establishes WebSocket connection and performs authentication handshake.

        Raises:
            ConnectionError: If connection or authentication fails
        """
        try:
            logger.info(f"Connecting to DXLink: {self.dxlink_url}")
            self.websocket = await asyncio.wait_for(
                websockets.connect(self.dxlink_url),
                timeout=self.timeout,
            )
            logger.info("✅ Connected to DXLink WebSocket")

            # Perform DXLink authentication
            await self._authenticate()

        except asyncio.TimeoutError as e:
            raise ConnectionError(f"DXLink connection timeout: {e}") from e
        except Exception as e:
            raise ConnectionError(f"DXLink connection failed: {e}") from e

    async def _authenticate(self) -> None:
        """
        Authenticate with DXLink service.

        DXLink authentication flow:
        1. Send SETUP message
        2. Receive SETUP response
        3. Receive AUTH_STATE with "UNAUTHORIZED" (expected initial state)
        4. Send AUTH message with token
        5. Receive AUTH_STATE with "AUTHORIZED"

        Raises:
            ConnectionError: If authentication fails
        """
        if not self.websocket:
            raise ConnectionError("WebSocket not connected")

        # DXLink SETUP message
        setup_message = {
            "type": "SETUP",
            "channel": 0,
            "version": "0.1-DXF-JS/0.3.0",
            "keepaliveTimeout": 60,
            "acceptKeepaliveTimeout": 60,
        }

        try:
            await self.websocket.send(json.dumps(setup_message))
            logger.debug("Sent SETUP message")

            # Wait for SETUP response
            response = await asyncio.wait_for(self.websocket.recv(), timeout=self.timeout)
            response_data = json.loads(response)

            if response_data.get("type") != "SETUP":
                raise ConnectionError(f"Unexpected response: {response_data}")

            logger.debug("Received SETUP response")

            # Wait for initial AUTH_STATE (UNAUTHORIZED)
            auth_state_response = await asyncio.wait_for(
                self.websocket.recv(), timeout=self.timeout
            )
            auth_state_data = json.loads(auth_state_response)

            if auth_state_data.get("type") == "AUTH_STATE":
                initial_state = auth_state_data.get("state")
                logger.debug(f"Initial AUTH_STATE: {initial_state}")

                # UNAUTHORIZED is expected at this point
                if initial_state not in ["UNAUTHORIZED", "AUTHORIZED"]:
                    raise ConnectionError(f"Unexpected auth state: {initial_state}")
            else:
                logger.warning(f"Expected AUTH_STATE, got: {auth_state_data}")

            # Send AUTH message with token
            auth_message = {"type": "AUTH", "channel": 0, "token": self.auth_token}

            await self.websocket.send(json.dumps(auth_message))
            logger.debug("Sent AUTH message with token")

            # Wait for AUTH_STATE response (should be AUTHORIZED)
            final_auth_response = await asyncio.wait_for(
                self.websocket.recv(), timeout=self.timeout
            )
            final_auth_data = json.loads(final_auth_response)

            if final_auth_data.get("type") == "AUTH_STATE":
                final_state = final_auth_data.get("state")
                if final_state == "AUTHORIZED":
                    logger.info("✅ DXLink authorization successful")
                else:
                    raise ConnectionError(
                        f"Authorization failed: {final_state}. "
                        f"Check token validity and account permissions."
                    )
            else:
                raise ConnectionError(f"Unexpected response: {final_auth_data}")

        except asyncio.TimeoutError as e:
            raise ConnectionError(f"DXLink authentication timeout: {e}") from e
        except json.JSONDecodeError as e:
            raise ConnectionError(f"Invalid JSON response: {e}") from e

    async def disconnect(self) -> None:
        """Close WebSocket connection."""
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            logger.info("Disconnected from DXLink")

    async def get_historical_candles(
        self,
        symbol: str,
        days: int = 120,
        interval: str = "1d",
        max_candles: int = 200,
    ) -> list[CandleData]:
        """
        Fetch historical daily candles for HV calculation.

        DXLink protocol requires:
        1. Create feed channel (CHANNEL_REQUEST)
        2. Setup feed with event types (FEED_SETUP)
        3. Subscribe to symbols (FEED_SUBSCRIPTION)

        Args:
            symbol: Ticker symbol (e.g., "AAPL", "/ES")
            days: Days of history to fetch (default 120 for HV90)
            interval: Candle interval (default "1d" for daily)
            max_candles: Maximum candles to collect

        Returns:
            List of CandleData objects sorted by time (oldest first)

        Raises:
            ConnectionError: If not connected or subscription fails
        """
        if not self.websocket:
            raise ConnectionError("Not connected to DXLink")

        # Format symbol with interval
        candle_symbol = f"{symbol}{{={interval}}}"

        # Calculate fromTime (Unix epoch milliseconds for DXLink)
        from_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)

        logger.info(
            f"Requesting {days} days of {interval} candles for {symbol} (fromTime: {from_time})"
        )

        # Step 1: Create feed channel
        channel_id = 1  # Use channel 1 for feed
        channel_request = {
            "type": "CHANNEL_REQUEST",
            "channel": channel_id,
            "service": "FEED",
            "parameters": {"contract": "AUTO"},
        }

        try:
            await self.websocket.send(json.dumps(channel_request))
            logger.debug(f"Sent CHANNEL_REQUEST for channel {channel_id}")

            # Wait for channel response
            channel_response = await asyncio.wait_for(self.websocket.recv(), timeout=self.timeout)
            channel_data = json.loads(channel_response)
            logger.debug(f"Channel response: {channel_data}")

        except Exception as e:
            raise ConnectionError(f"Failed to create feed channel: {e}") from e

        # Step 2: Setup feed with event types
        feed_setup = {
            "type": "FEED_SETUP",
            "channel": channel_id,
            "acceptAggregationPeriod": 10.0,
            "acceptDataFormat": "COMPACT",
            "acceptEventFields": {
                "Candle": [
                    "eventSymbol",
                    "eventTime",
                    "time",
                    "sequence",
                    "count",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                ]
            },
        }

        try:
            await self.websocket.send(json.dumps(feed_setup))
            logger.debug("Sent FEED_SETUP")

            # Wait for setup response
            setup_response = await asyncio.wait_for(self.websocket.recv(), timeout=self.timeout)
            setup_data = json.loads(setup_response)
            logger.debug(f"Feed setup response: {setup_data}")

        except Exception as e:
            raise ConnectionError(f"Failed to setup feed: {e}") from e

        # Step 3: Subscribe to Candle events with fromTime
        subscribe_message = {
            "type": "FEED_SUBSCRIPTION",
            "channel": channel_id,
            "add": [
                {
                    "type": "Candle",
                    "symbol": candle_symbol,
                    "fromTime": from_time,
                }
            ],
        }

        try:
            await self.websocket.send(json.dumps(subscribe_message))
            logger.debug(f"Sent subscription for {candle_symbol}")

            # Collect candles
            candles: list[CandleData] = []
            timeout_start = datetime.now()
            max_wait = timedelta(seconds=self.timeout)

            while True:
                # Check timeout
                if datetime.now() - timeout_start > max_wait:
                    logger.warning(f"Timeout waiting for candles after {self.timeout}s")
                    break

                # Check max candles limit
                if len(candles) >= max_candles:
                    logger.info(f"Reached max candles limit: {max_candles}")
                    break

                try:
                    # Wait for message with short timeout for checking conditions
                    message = await asyncio.wait_for(self.websocket.recv(), timeout=1.0)
                    data = json.loads(message)

                    # DEBUG: Log all received messages
                    logger.debug(f"Received message type: {data.get('type')}")
                    if data.get("type") not in ["KEEPALIVE"]:
                        logger.debug(f"Message content: {data}")

                    # Process different message types
                    if data.get("type") == "FEED_DATA":
                        # COMPACT format: ["EventType", [field1, field2, ...], [field1, field2, ...], ...]
                        # Extract candle events
                        data_lists = data.get("data", [])
                        logger.info(f"📊 FEED_DATA received with {len(data_lists)} event lists")

                        # DEBUG: Print first event list structure
                        if data_lists and len(data_lists) > 0:
                            first_list = data_lists[0]
                            if isinstance(first_list, list) and len(first_list) > 0:
                                logger.info(
                                    f"First event type: {first_list[0]}, items: {len(first_list) - 1}"
                                )
                                if len(first_list) > 1:
                                    logger.info(
                                        f"First item sample: {first_list[1][:5] if isinstance(first_list[1], list) else first_list[1]}"
                                    )

                        for event_list in data_lists:
                            if not isinstance(event_list, list) or len(event_list) < 2:
                                logger.debug(f"Skipping invalid event_list: {event_list}")
                                continue

                            event_type = event_list[0]  # Event type string
                            logger.debug(
                                f"Event type: {event_type}, elements: {len(event_list) - 1}"
                            )

                            if event_type == "Candle":
                                # Parse candle events in COMPACT format
                                # Each element after [0] is an array of field values
                                # Fields order from FEED_SETUP:
                                # [eventSymbol, eventTime, time, sequence, count, open, high, low, close, volume]
                                for event_data in event_list[1:]:
                                    if isinstance(event_data, list) and len(event_data) >= 10:
                                        # Parse compact format
                                        event_obj = {
                                            "eventSymbol": event_data[0],
                                            "eventTime": event_data[1],
                                            "time": event_data[2],
                                            "sequence": event_data[3],
                                            "count": event_data[4],
                                            "open": event_data[5],
                                            "high": event_data[6],
                                            "low": event_data[7],
                                            "close": event_data[8],
                                            "volume": event_data[9],
                                        }

                                        # Skip NaN values
                                        if (
                                            event_obj["open"] == "NaN"
                                            or event_obj["close"] == "NaN"
                                        ):
                                            continue

                                        # Convert string numbers to floats
                                        try:
                                            event_obj["open"] = float(event_obj["open"])
                                            event_obj["high"] = float(event_obj["high"])
                                            event_obj["low"] = float(event_obj["low"])
                                            event_obj["close"] = float(event_obj["close"])
                                            event_obj["volume"] = float(event_obj["volume"])
                                        except (ValueError, TypeError):
                                            continue

                                        candle = CandleData.from_event(event_obj)
                                        candles.append(candle)

                                        if len(candles) <= 5:  # Log first few
                                            logger.debug(
                                                f"Candle: {candle.symbol} "
                                                f"time={candle.time} "
                                                f"close={candle.close}"
                                            )

                    elif data.get("type") == "FEED_CONFIG":
                        logger.debug("Received FEED_CONFIG")

                    elif data.get("type") == "KEEPALIVE":
                        # Respond to keepalive
                        await self.websocket.send(json.dumps({"type": "KEEPALIVE", "channel": 0}))

                except asyncio.TimeoutError:
                    # Short timeout expired, check if we have enough data
                    if candles:
                        # If we've received candles and there's a pause, assume complete
                        logger.debug(f"No more candles received, collected {len(candles)}")
                        break
                    continue

                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in message: {e}")
                    continue

            # Unsubscribe from candles
            unsubscribe_message = {
                "type": "FEED_SUBSCRIPTION",
                "channel": channel_id,
                "remove": [{"type": "Candle", "symbol": candle_symbol}],
            }
            await self.websocket.send(json.dumps(unsubscribe_message))
            logger.debug(f"Unsubscribed from {candle_symbol}")

            # Sort by time (oldest first)
            candles.sort(key=lambda c: c.time)

            logger.info(f"✅ Collected {len(candles)} candles for {symbol}")
            return candles

        except Exception as e:
            logger.error(f"Error fetching candles: {e}")
            raise

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
