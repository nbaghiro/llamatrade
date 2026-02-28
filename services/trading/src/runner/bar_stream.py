"""Alpaca WebSocket bar stream for real-time market data."""

import asyncio
import json
import logging
import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime

import websockets
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed
from websockets.protocol import State

from src.metrics import (
    record_bar_latency,
    record_bar_stream_reconnect,
    set_bar_stream_connected,
)

logger = logging.getLogger(__name__)


@dataclass
class BarData:
    """Real-time bar data from stream."""

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float | None = None
    trade_count: int | None = None


@dataclass
class StreamConfig:
    """Configuration for bar stream."""

    api_key: str = field(default_factory=lambda: os.getenv("ALPACA_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("ALPACA_API_SECRET", ""))
    paper: bool = True
    reconnect_delay: float = 5.0
    max_reconnect_attempts: int = 10


class AlpacaBarStream:
    """WebSocket client for Alpaca real-time bar data.

    Supports 1-minute bars aggregated by Alpaca. For longer timeframes,
    bars must be aggregated by the strategy runner.
    """

    LIVE_URL = "wss://stream.data.alpaca.markets/v2/iex"
    PAPER_URL = "wss://stream.data.sandbox.alpaca.markets/v2/iex"

    def __init__(self, config: StreamConfig | None = None):
        self.config = config or StreamConfig()
        self.url = self.PAPER_URL if self.config.paper else self.LIVE_URL

        self._ws: ClientConnection | None = None
        self._subscribed_symbols: set[str] = set()
        self._running = False
        self._authenticated = False
        self._reconnect_attempts = 0

        # Queue for incoming bars
        self._bar_queue: asyncio.Queue[BarData] = asyncio.Queue()

    @property
    def connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._ws is not None and self._ws.state == State.OPEN

    @property
    def authenticated(self) -> bool:
        """Check if stream is authenticated."""
        return self._authenticated

    @property
    def subscribed_symbols(self) -> set[str]:
        """Get currently subscribed symbols."""
        return self._subscribed_symbols.copy()

    async def connect(self) -> bool:
        """Connect to Alpaca WebSocket and authenticate."""
        try:
            self._ws = await websockets.connect(self.url)
            logger.info(f"Connected to Alpaca stream: {self.url}")

            # Wait for welcome message
            msg = await self._receive_message()
            if not msg or msg[0].get("T") != "success":
                logger.error(f"Unexpected welcome message: {msg}")
                return False

            # Authenticate
            auth_msg = {
                "action": "auth",
                "key": self.config.api_key,
                "secret": self.config.api_secret,
            }
            await self._ws.send(json.dumps(auth_msg))

            # Wait for auth response
            msg = await self._receive_message()
            if not msg or msg[0].get("T") != "success":
                logger.error(f"Authentication failed: {msg}")
                return False

            self._authenticated = True
            self._reconnect_attempts = 0
            set_bar_stream_connected(True)
            logger.info("Authenticated with Alpaca stream")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Alpaca stream: {e}")
            set_bar_stream_connected(False)
            return False

    async def disconnect(self) -> None:
        """Disconnect from Alpaca WebSocket."""
        self._running = False
        self._authenticated = False

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        self._subscribed_symbols.clear()
        set_bar_stream_connected(False)
        logger.info("Disconnected from Alpaca stream")

    async def subscribe(self, symbols: list[str]) -> bool:
        """Subscribe to bar updates for symbols."""
        if not self.connected or not self._authenticated:
            logger.error("Cannot subscribe: not connected or authenticated")
            return False

        symbols_upper = [s.upper() for s in symbols]
        new_symbols = [s for s in symbols_upper if s not in self._subscribed_symbols]

        if not new_symbols:
            return True

        try:
            if not self._ws:
                return False
            sub_msg = {
                "action": "subscribe",
                "bars": new_symbols,
            }
            await self._ws.send(json.dumps(sub_msg))

            # Wait for subscription confirmation
            msg = await self._receive_message()
            if msg and msg[0].get("T") == "subscription":
                bars_value: str | list[str] = msg[0].get("bars", [])
                subscribed: list[str] = bars_value if isinstance(bars_value, list) else []
                self._subscribed_symbols.update(subscribed)
                logger.info(f"Subscribed to bars: {subscribed}")
                return True

            logger.error(f"Subscription failed: {msg}")
            return False

        except Exception as e:
            logger.error(f"Failed to subscribe: {e}")
            return False

    async def unsubscribe(self, symbols: list[str] | None = None) -> bool:
        """Unsubscribe from bar updates.

        If symbols is None, unsubscribe from all.
        """
        if not self.connected:
            return True

        symbols_to_unsub = (
            [s.upper() for s in symbols] if symbols else list(self._subscribed_symbols)
        )

        if not symbols_to_unsub:
            return True

        try:
            if not self._ws:
                return False
            unsub_msg = {
                "action": "unsubscribe",
                "bars": symbols_to_unsub,
            }
            await self._ws.send(json.dumps(unsub_msg))

            # Wait for unsubscription confirmation
            msg = await self._receive_message()
            if msg and msg[0].get("T") == "subscription":
                for s in symbols_to_unsub:
                    self._subscribed_symbols.discard(s)
                logger.info(f"Unsubscribed from bars: {symbols_to_unsub}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to unsubscribe: {e}")
            return False

    async def stream(self) -> AsyncGenerator[BarData, None]:
        """Stream bar data as an async generator.

        This method handles reconnection automatically.
        """
        self._running = True

        while self._running:
            # Ensure connection
            if not self.connected:
                if not await self._reconnect():
                    break
                continue

            try:
                # Read messages from WebSocket
                msg = await self._receive_message(timeout=60.0)
                if not msg:
                    continue

                for item in msg:
                    msg_type = item.get("T")

                    if msg_type == "b":
                        # Bar message
                        bar = self._parse_bar(item)
                        if bar:
                            yield bar

                    elif msg_type == "error":
                        logger.error(f"Stream error: {item.get('msg')}")

            except ConnectionClosed:
                logger.warning("WebSocket connection closed, reconnecting...")
                self._ws = None
                self._authenticated = False

            except asyncio.CancelledError:
                break

            except Exception as e:
                logger.error(f"Stream error: {e}")
                await asyncio.sleep(1)

    async def _receive_message(self, timeout: float = 10.0) -> list[dict[str, str]] | None:
        """Receive and parse a WebSocket message."""
        if not self._ws:
            return None

        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
            result: list[dict[str, str]] = json.loads(raw)
            return result
        except TimeoutError:
            return None
        except Exception as e:
            logger.error(f"Error receiving message: {e}")
            return None

    async def _reconnect(self) -> bool:
        """Attempt to reconnect to the stream."""
        if self._reconnect_attempts >= self.config.max_reconnect_attempts:
            logger.error("Max reconnection attempts reached")
            self._running = False
            return False

        self._reconnect_attempts += 1
        delay = self.config.reconnect_delay * self._reconnect_attempts
        record_bar_stream_reconnect()

        logger.info(
            f"Reconnecting in {delay}s "
            f"(attempt {self._reconnect_attempts}/{self.config.max_reconnect_attempts})"
        )
        await asyncio.sleep(delay)

        if await self.connect():
            # Re-subscribe to symbols
            if self._subscribed_symbols:
                symbols = list(self._subscribed_symbols)
                self._subscribed_symbols.clear()
                await self.subscribe(symbols)
            return True

        return False

    def _parse_bar(self, data: dict) -> BarData | None:
        """Parse Alpaca bar message to BarData."""
        try:
            # Parse timestamp
            ts_str = data.get("t", "")
            if ts_str:
                timestamp = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            else:
                timestamp = datetime.now(UTC)

            # Record latency from bar timestamp to receipt
            now = datetime.now(UTC)
            latency = (now - timestamp).total_seconds()
            if latency > 0:
                record_bar_latency(latency)

            return BarData(
                symbol=data.get("S", ""),
                timestamp=timestamp,
                open=float(data.get("o", 0)),
                high=float(data.get("h", 0)),
                low=float(data.get("l", 0)),
                close=float(data.get("c", 0)),
                volume=int(data.get("v", 0)),
                vwap=float(data["vw"]) if data.get("vw") else None,
                trade_count=int(data["n"]) if data.get("n") else None,
            )
        except Exception as e:
            logger.error(f"Failed to parse bar: {e}")
            return None


class MockBarStream:
    """Mock bar stream for testing without Alpaca connection."""

    def __init__(self, bars: dict[str, list[BarData]] | None = None):
        self._bars = bars or {}
        self._subscribed_symbols: set[str] = set()
        self._running = False

    @property
    def connected(self) -> bool:
        return True

    @property
    def authenticated(self) -> bool:
        return True

    @property
    def subscribed_symbols(self) -> set[str]:
        return self._subscribed_symbols.copy()

    async def connect(self) -> bool:
        return True

    async def disconnect(self) -> None:
        self._running = False

    async def subscribe(self, symbols: list[str]) -> bool:
        self._subscribed_symbols.update(s.upper() for s in symbols)
        return True

    async def unsubscribe(self, symbols: list[str] | None = None) -> bool:
        if symbols:
            for s in symbols:
                self._subscribed_symbols.discard(s.upper())
        else:
            self._subscribed_symbols.clear()
        return True

    async def stream(self) -> AsyncGenerator[BarData, None]:
        """Stream mock bars."""
        self._running = True

        for symbol in self._subscribed_symbols:
            bars = self._bars.get(symbol, [])
            for bar in bars:
                if not self._running:
                    return
                yield bar
                await asyncio.sleep(0.01)  # Small delay between bars
