"""Alpaca WebSocket client for real-time market data.

Connects to Alpaca's streaming API to receive trades, quotes, and bars.
"""

import asyncio
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed
from websockets.protocol import State

from src.models import BarData, QuoteData, TradeData

logger = logging.getLogger(__name__)


class MessageType(StrEnum):
    """Alpaca stream message types."""

    SUCCESS = "success"
    ERROR = "error"
    SUBSCRIPTION = "subscription"
    TRADE = "t"
    QUOTE = "q"
    BAR = "b"


@dataclass
class StreamConfig:
    """Configuration for Alpaca stream."""

    api_key: str = field(default_factory=lambda: os.getenv("ALPACA_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("ALPACA_API_SECRET", ""))
    paper: bool = True
    reconnect_delay: float = 5.0
    max_reconnect_attempts: int = 10


# Callback types
TradeCallback = Callable[[str, TradeData], None]
QuoteCallback = Callable[[str, QuoteData], None]
BarCallback = Callable[[str, BarData], None]


class AlpacaStreamClient:
    """WebSocket client for Alpaca real-time market data.

    Supports trades, quotes, and bars streaming with automatic reconnection.
    """

    LIVE_URL = "wss://stream.data.alpaca.markets/v2/iex"
    PAPER_URL = "wss://stream.data.sandbox.alpaca.markets/v2/iex"

    def __init__(self, config: StreamConfig | None = None):
        self.config = config or StreamConfig()
        self.url = self.PAPER_URL if self.config.paper else self.LIVE_URL

        self._ws: ClientConnection | None = None
        self._running = False
        self._authenticated = False
        self._reconnect_attempts = 0
        self._lock = asyncio.Lock()

        # Track subscriptions
        self._subscribed_trades: set[str] = set()
        self._subscribed_quotes: set[str] = set()
        self._subscribed_bars: set[str] = set()

        # Callbacks for incoming data
        self._on_trade: TradeCallback | None = None
        self._on_quote: QuoteCallback | None = None
        self._on_bar: BarCallback | None = None

    @property
    def connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._ws is not None and self._ws.state == State.OPEN

    @property
    def authenticated(self) -> bool:
        """Check if stream is authenticated."""
        return self._authenticated

    @property
    def subscribed_symbols(self) -> dict[str, set[str]]:
        """Get currently subscribed symbols by type."""
        return {
            "trades": self._subscribed_trades.copy(),
            "quotes": self._subscribed_quotes.copy(),
            "bars": self._subscribed_bars.copy(),
        }

    def set_callbacks(
        self,
        on_trade: TradeCallback | None = None,
        on_quote: QuoteCallback | None = None,
        on_bar: BarCallback | None = None,
    ) -> None:
        """Set callbacks for incoming market data.

        Args:
            on_trade: Called when trade data is received
            on_quote: Called when quote data is received
            on_bar: Called when bar data is received
        """
        self._on_trade = on_trade
        self._on_quote = on_quote
        self._on_bar = on_bar

    async def connect(self) -> bool:
        """Connect to Alpaca WebSocket and authenticate.

        Returns:
            True if connection and authentication successful
        """
        try:
            self._ws = await websockets.connect(self.url)
            logger.info(f"Connected to Alpaca stream: {self.url}")

            # Wait for welcome message
            msg = await self._receive_message()
            if not msg or msg[0].get("T") != MessageType.SUCCESS:
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
            if not msg or msg[0].get("T") != MessageType.SUCCESS:
                logger.error(f"Authentication failed: {msg}")
                return False

            self._authenticated = True
            self._reconnect_attempts = 0
            logger.info("Authenticated with Alpaca stream")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Alpaca stream: {e}")
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

        self._subscribed_trades.clear()
        self._subscribed_quotes.clear()
        self._subscribed_bars.clear()
        logger.info("Disconnected from Alpaca stream")

    async def subscribe(
        self,
        trades: list[str] | None = None,
        quotes: list[str] | None = None,
        bars: list[str] | None = None,
    ) -> bool:
        """Subscribe to market data for symbols.

        Args:
            trades: Symbols to subscribe for trade updates
            quotes: Symbols to subscribe for quote updates
            bars: Symbols to subscribe for bar updates

        Returns:
            True if subscription successful
        """
        if not self.connected or not self._authenticated:
            logger.error("Cannot subscribe: not connected or authenticated")
            return False

        # Filter to only new subscriptions
        trades = [s.upper() for s in (trades or []) if s.upper() not in self._subscribed_trades]
        quotes = [s.upper() for s in (quotes or []) if s.upper() not in self._subscribed_quotes]
        bars = [s.upper() for s in (bars or []) if s.upper() not in self._subscribed_bars]

        if not trades and not quotes and not bars:
            return True  # Nothing new to subscribe

        try:
            sub_msg: dict[str, Any] = {"action": "subscribe"}
            if trades:
                sub_msg["trades"] = trades
            if quotes:
                sub_msg["quotes"] = quotes
            if bars:
                sub_msg["bars"] = bars

            if self._ws is None:
                logger.error("Cannot subscribe: WebSocket is None")
                return False
            await self._ws.send(json.dumps(sub_msg))

            # Wait for subscription confirmation
            msg = await self._receive_message()
            if msg and msg[0].get("T") == MessageType.SUBSCRIPTION:
                # Update tracked subscriptions
                self._subscribed_trades.update(msg[0].get("trades", []))
                self._subscribed_quotes.update(msg[0].get("quotes", []))
                self._subscribed_bars.update(msg[0].get("bars", []))
                logger.info(f"Subscribed: trades={trades}, quotes={quotes}, bars={bars}")
                return True

            logger.error(f"Subscription failed: {msg}")
            return False

        except Exception as e:
            logger.error(f"Failed to subscribe: {e}")
            return False

    async def unsubscribe(
        self,
        trades: list[str] | None = None,
        quotes: list[str] | None = None,
        bars: list[str] | None = None,
    ) -> bool:
        """Unsubscribe from market data for symbols.

        Args:
            trades: Symbols to unsubscribe from trade updates
            quotes: Symbols to unsubscribe from quote updates
            bars: Symbols to unsubscribe from bar updates

        Returns:
            True if unsubscription successful
        """
        if not self.connected:
            return True

        trades = [s.upper() for s in (trades or [])]
        quotes = [s.upper() for s in (quotes or [])]
        bars = [s.upper() for s in (bars or [])]

        if not trades and not quotes and not bars:
            return True

        try:
            unsub_msg: dict[str, Any] = {"action": "unsubscribe"}
            if trades:
                unsub_msg["trades"] = trades
            if quotes:
                unsub_msg["quotes"] = quotes
            if bars:
                unsub_msg["bars"] = bars

            if self._ws is None:
                return False
            await self._ws.send(json.dumps(unsub_msg))

            # Wait for confirmation
            msg = await self._receive_message()
            if msg and msg[0].get("T") == MessageType.SUBSCRIPTION:
                # Update tracked subscriptions
                for s in trades:
                    self._subscribed_trades.discard(s)
                for s in quotes:
                    self._subscribed_quotes.discard(s)
                for s in bars:
                    self._subscribed_bars.discard(s)
                logger.info(f"Unsubscribed: trades={trades}, quotes={quotes}, bars={bars}")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to unsubscribe: {e}")
            return False

    async def run(self) -> None:
        """Run the stream processing loop.

        This method handles receiving messages and dispatching to callbacks.
        It includes automatic reconnection on connection loss.
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
                    await self._dispatch_message(item)

            except ConnectionClosed:
                logger.warning("WebSocket connection closed, reconnecting...")
                self._ws = None
                self._authenticated = False

            except asyncio.CancelledError:
                break

            except Exception as e:
                logger.error(f"Stream error: {e}")
                await asyncio.sleep(1)

    async def _dispatch_message(self, item: dict) -> None:
        """Dispatch a message to the appropriate callback."""
        msg_type = item.get("T")

        if msg_type == MessageType.TRADE:
            if self._on_trade:
                trade_data = self._parse_trade(item)
                if trade_data:
                    symbol = item.get("S", "")
                    await asyncio.to_thread(self._on_trade, symbol, trade_data)

        elif msg_type == MessageType.QUOTE:
            if self._on_quote:
                quote_data = self._parse_quote(item)
                if quote_data:
                    symbol = item.get("S", "")
                    await asyncio.to_thread(self._on_quote, symbol, quote_data)

        elif msg_type == MessageType.BAR:
            if self._on_bar:
                bar_data = self._parse_bar(item)
                if bar_data:
                    symbol = item.get("S", "")
                    await asyncio.to_thread(self._on_bar, symbol, bar_data)

        elif msg_type == MessageType.ERROR:
            logger.error(f"Stream error message: {item.get('msg')}")

    async def _receive_message(self, timeout: float = 10.0) -> list[dict[Any, Any]] | None:
        """Receive and parse a WebSocket message."""
        if not self._ws:
            return None

        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
            parsed: list[dict[Any, Any]] = json.loads(raw)
            return parsed
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

        logger.info(
            f"Reconnecting in {delay}s "
            f"(attempt {self._reconnect_attempts}/{self.config.max_reconnect_attempts})"
        )
        await asyncio.sleep(delay)

        if await self.connect():
            # Re-subscribe to all previous subscriptions
            async with self._lock:
                trades = list(self._subscribed_trades)
                quotes = list(self._subscribed_quotes)
                bars = list(self._subscribed_bars)

                # Clear current subscriptions as they were lost
                self._subscribed_trades.clear()
                self._subscribed_quotes.clear()
                self._subscribed_bars.clear()

            # Re-subscribe
            if trades or quotes or bars:
                await self.subscribe(trades=trades, quotes=quotes, bars=bars)

            return True

        return False

    def _parse_trade(self, data: dict) -> TradeData | None:
        """Parse Alpaca trade message."""
        try:
            ts = data.get("t", "")
            return TradeData(
                price=float(data.get("p", 0)),
                size=int(data.get("s", 0)),
                exchange=data.get("x", ""),
                timestamp=ts,
            )
        except Exception as e:
            logger.error(f"Failed to parse trade: {e}")
            return None

    def _parse_quote(self, data: dict) -> QuoteData | None:
        """Parse Alpaca quote message."""
        try:
            ts = data.get("t", "")
            return QuoteData(
                bid_price=float(data.get("bp", 0)),
                bid_size=int(data.get("bs", 0)),
                ask_price=float(data.get("ap", 0)),
                ask_size=int(data.get("as", 0)),
                timestamp=ts,
            )
        except Exception as e:
            logger.error(f"Failed to parse quote: {e}")
            return None

    def _parse_bar(self, data: dict) -> BarData | None:
        """Parse Alpaca bar message."""
        try:
            ts = data.get("t", "")
            return BarData(
                open=float(data.get("o", 0)),
                high=float(data.get("h", 0)),
                low=float(data.get("l", 0)),
                close=float(data.get("c", 0)),
                volume=int(data.get("v", 0)),
                timestamp=ts,
            )
        except Exception as e:
            logger.error(f"Failed to parse bar: {e}")
            return None


# Global instance
_stream_client: AlpacaStreamClient | None = None


def get_alpaca_stream() -> AlpacaStreamClient:
    """Get the global Alpaca stream client."""
    global _stream_client
    if _stream_client is None:
        _stream_client = AlpacaStreamClient()
    return _stream_client


async def init_alpaca_stream() -> AlpacaStreamClient | None:
    """Initialize and connect the Alpaca stream client.

    Returns:
        Connected client or None if connection failed
    """
    global _stream_client
    _stream_client = AlpacaStreamClient()

    if await _stream_client.connect():
        return _stream_client

    logger.warning("Failed to connect to Alpaca stream")
    _stream_client = None
    return None


async def close_alpaca_stream() -> None:
    """Close the global Alpaca stream client."""
    global _stream_client
    if _stream_client:
        await _stream_client.disconnect()
        _stream_client = None
