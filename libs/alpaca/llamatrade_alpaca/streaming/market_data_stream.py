"""Alpaca market-data WebSocket client (real-time trades, quotes, bars).

Connects to ``wss://stream.data.alpaca.markets`` (IEX feed), authenticates,
subscribes per-symbol, and dispatches parsed payloads to async callbacks.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from websockets.exceptions import ConnectionClosed

from ..config import AlpacaCredentials, AlpacaUrls
from ..models import BarData, QuoteData, StreamBar, TradeData
from .base import AlpacaWebSocketBase

logger = logging.getLogger(__name__)


class MessageType(StrEnum):
    """Alpaca market-data stream message discriminators (``T`` field)."""

    SUCCESS = "success"
    ERROR = "error"
    SUBSCRIPTION = "subscription"
    TRADE = "t"
    QUOTE = "q"
    BAR = "b"


# Async callbacks invoked per parsed payload.
TradeCallback = Callable[[str, TradeData], Awaitable[None]]
QuoteCallback = Callable[[str, QuoteData], Awaitable[None]]
BarCallback = Callable[[str, BarData], Awaitable[None]]


class _DataStreamClient(AlpacaWebSocketBase):
    """Shared base for Alpaca market-data stream clients.

    Implements the welcome + auth handshake: Alpaca sends a welcome
    ``[{"T": "success"}]`` on connect, then expects an auth message and replies
    with another ``success``.
    """

    async def _authenticate(self) -> bool:
        welcome = await self._recv()
        if not welcome or welcome[0].get("T") != MessageType.SUCCESS:
            logger.error(f"Unexpected welcome message: {welcome}")
            return False
        await self._send(self._auth_payload())
        auth = await self._recv()
        if not auth or auth[0].get("T") != MessageType.SUCCESS:
            logger.error(f"Authentication failed: {auth}")
            return False
        return True


class MarketDataStreamClient(_DataStreamClient):
    """WebSocket client for Alpaca real-time market data.

    Supports trades, quotes, and bars with automatic reconnection and
    re-subscription. Delivery is via async callbacks set with ``set_callbacks``.
    """

    def __init__(
        self,
        credentials: AlpacaCredentials | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        paper: bool = True,
        reconnect_delay: float = 1.0,
        max_reconnect_delay: float = 60.0,
        max_reconnect_attempts: int = 10,
    ) -> None:
        super().__init__(
            url=AlpacaUrls.stream_url(paper=paper),
            credentials=credentials,
            api_key=api_key,
            api_secret=api_secret,
            reconnect_delay=reconnect_delay,
            max_reconnect_delay=max_reconnect_delay,
            max_reconnect_attempts=max_reconnect_attempts,
        )
        self.paper = paper
        self._lock = asyncio.Lock()

        self._subscribed_trades: set[str] = set()
        self._subscribed_quotes: set[str] = set()
        self._subscribed_bars: set[str] = set()

        self._on_trade: TradeCallback | None = None
        self._on_quote: QuoteCallback | None = None
        self._on_bar: BarCallback | None = None

    @property
    def subscribed_symbols(self) -> dict[str, set[str]]:
        """Currently subscribed symbols by stream type."""
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
        """Register async callbacks for incoming market data."""
        self._on_trade = on_trade
        self._on_quote = on_quote
        self._on_bar = on_bar

    # ------------------------------------------------------------ handshake

    def _on_disconnect(self) -> None:
        self._subscribed_trades.clear()
        self._subscribed_quotes.clear()
        self._subscribed_bars.clear()

    async def _resubscribe(self) -> None:
        async with self._lock:
            trades = list(self._subscribed_trades)
            quotes = list(self._subscribed_quotes)
            bars = list(self._subscribed_bars)
            self._subscribed_trades.clear()
            self._subscribed_quotes.clear()
            self._subscribed_bars.clear()
        if trades or quotes or bars:
            await self.subscribe(trades=trades, quotes=quotes, bars=bars)

    # --------------------------------------------------------- subscriptions

    async def subscribe(
        self,
        trades: list[str] | None = None,
        quotes: list[str] | None = None,
        bars: list[str] | None = None,
    ) -> bool:
        """Subscribe to market data for the given symbols (idempotent)."""
        if not self.connected or not self._authenticated:
            logger.error("Cannot subscribe: not connected or authenticated")
            return False

        trades = [s.upper() for s in (trades or []) if s.upper() not in self._subscribed_trades]
        quotes = [s.upper() for s in (quotes or []) if s.upper() not in self._subscribed_quotes]
        bars = [s.upper() for s in (bars or []) if s.upper() not in self._subscribed_bars]

        if not trades and not quotes and not bars:
            return True

        try:
            sub_msg: dict[str, Any] = {"action": "subscribe"}
            if trades:
                sub_msg["trades"] = trades
            if quotes:
                sub_msg["quotes"] = quotes
            if bars:
                sub_msg["bars"] = bars
            await self._send(sub_msg)

            msg = await self._recv()
            if msg and msg[0].get("T") == MessageType.SUBSCRIPTION:
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
        """Unsubscribe from market data for the given symbols."""
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
            await self._send(unsub_msg)

            msg = await self._recv()
            if msg and msg[0].get("T") == MessageType.SUBSCRIPTION:
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

    # -------------------------------------------------------------- run loop

    async def run(self) -> None:
        """Receive and dispatch messages, reconnecting on connection loss."""
        self._running = True

        while self._running:
            if not self.connected:
                if not await self._reconnect():
                    break
                continue

            try:
                msg = await self._recv(timeout=60.0)
                if not msg:
                    continue
                for item in msg:
                    await self._dispatch_message(item)
            except ConnectionClosed:
                logger.warning("Market data stream closed, reconnecting...")
                self._ws = None
                self._authenticated = False
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Market data stream error: {e}")
                await asyncio.sleep(1)

    async def _dispatch_message(self, item: dict[str, Any]) -> None:
        msg_type: str | None = item.get("T")

        if msg_type == MessageType.TRADE:
            if self._on_trade and (trade := self._parse_trade(item)) is not None:
                await self._on_trade(item.get("S", ""), trade)
        elif msg_type == MessageType.QUOTE:
            if self._on_quote and (quote := self._parse_quote(item)) is not None:
                await self._on_quote(item.get("S", ""), quote)
        elif msg_type == MessageType.BAR:
            if self._on_bar and (bar := self._parse_bar(item)) is not None:
                await self._on_bar(item.get("S", ""), bar)
        elif msg_type == MessageType.ERROR:
            logger.error(f"Stream error message: {item.get('msg')}")

    # --------------------------------------------------------------- parsers

    def _parse_trade(self, data: dict[str, Any]) -> TradeData | None:
        try:
            return TradeData(
                price=float(data.get("p", 0)),
                size=int(data.get("s", 0)),
                exchange=str(data.get("x", "")),
                timestamp=str(data.get("t", "")),
            )
        except Exception as e:
            logger.error(f"Failed to parse trade: {e}")
            return None

    def _parse_quote(self, data: dict[str, Any]) -> QuoteData | None:
        try:
            return QuoteData(
                bid_price=float(data.get("bp", 0)),
                bid_size=int(data.get("bs", 0)),
                ask_price=float(data.get("ap", 0)),
                ask_size=int(data.get("as", 0)),
                timestamp=str(data.get("t", "")),
            )
        except Exception as e:
            logger.error(f"Failed to parse quote: {e}")
            return None

    def _parse_bar(self, data: dict[str, Any]) -> BarData | None:
        try:
            return BarData(
                open=float(data.get("o", 0)),
                high=float(data.get("h", 0)),
                low=float(data.get("l", 0)),
                close=float(data.get("c", 0)),
                volume=int(data.get("v", 0)),
                timestamp=str(data.get("t", "")),
            )
        except Exception as e:
            logger.error(f"Failed to parse bar: {e}")
            return None


# =============================================================================
# Singleton lifecycle helpers
# =============================================================================

_stream_client: MarketDataStreamClient | None = None
_stream_lock: asyncio.Lock | None = None


def _get_stream_lock() -> asyncio.Lock:
    global _stream_lock
    if _stream_lock is None:
        _stream_lock = asyncio.Lock()
    return _stream_lock


def get_market_data_stream() -> MarketDataStreamClient:
    """Get the singleton market-data stream client (creates if absent)."""
    global _stream_client
    if _stream_client is None:
        _stream_client = MarketDataStreamClient()
    return _stream_client


async def init_market_data_stream() -> MarketDataStreamClient | None:
    """Create and connect the singleton market-data stream client.

    Thread-safe. Returns the connected client, or ``None`` on failure.
    """
    global _stream_client
    async with _get_stream_lock():
        if _stream_client is not None and _stream_client.connected:
            return _stream_client
        _stream_client = MarketDataStreamClient()
        if await _stream_client.connect():
            return _stream_client
        logger.warning("Failed to connect to Alpaca market data stream")
        _stream_client = None
        return None


async def close_market_data_stream() -> None:
    """Disconnect and clear the singleton market-data stream client."""
    global _stream_client
    async with _get_stream_lock():
        if _stream_client:
            await _stream_client.disconnect()
            _stream_client = None


# =============================================================================
# Shared data-stream auth + generator-based bar client
# =============================================================================


class BarStreamClient(_DataStreamClient):
    """Generator-based Alpaca market-data stream for real-time bars.

    Subscribes to bars only and yields self-contained :class:`StreamBar` objects
    (symbol + OHLCV + vwap/trade_count), suited to a live strategy runner that
    consumes ``async for bar in client.stream()``. Connection/reconnection metrics
    are surfaced via the ``on_reconnect`` / ``on_connection_change`` hooks; per-bar
    latency is left to the consumer (which holds the bar timestamp).
    """

    def __init__(
        self,
        credentials: AlpacaCredentials | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        paper: bool = True,
        reconnect_delay: float = 1.0,
        max_reconnect_delay: float = 60.0,
        max_reconnect_attempts: int = 10,
        jitter_factor: float = 0.1,
        on_reconnect: Callable[[], None] | None = None,
        on_connection_change: Callable[[bool], None] | None = None,
    ) -> None:
        super().__init__(
            url=AlpacaUrls.stream_url(paper=paper),
            credentials=credentials,
            api_key=api_key,
            api_secret=api_secret,
            reconnect_delay=reconnect_delay,
            max_reconnect_delay=max_reconnect_delay,
            max_reconnect_attempts=max_reconnect_attempts,
            jitter_factor=jitter_factor,
            on_reconnect=on_reconnect,
            on_connection_change=on_connection_change,
        )
        self.paper = paper
        self._subscribed_symbols: set[str] = set()

    @property
    def subscribed_symbols(self) -> set[str]:
        """Symbols currently subscribed for bars."""
        return self._subscribed_symbols.copy()

    def _on_disconnect(self) -> None:
        self._subscribed_symbols.clear()

    async def _resubscribe(self) -> None:
        symbols = list(self._subscribed_symbols)
        self._subscribed_symbols.clear()
        if symbols:
            await self.subscribe(symbols)

    async def subscribe(self, symbols: list[str]) -> bool:
        """Subscribe to bar updates for the given symbols (idempotent)."""
        if not self.connected or not self._authenticated:
            logger.error("Cannot subscribe: not connected or authenticated")
            return False

        new = [s.upper() for s in symbols if s.upper() not in self._subscribed_symbols]
        if not new:
            return True

        try:
            await self._send({"action": "subscribe", "bars": new})
            msg = await self._recv()
            if msg and msg[0].get("T") == MessageType.SUBSCRIPTION:
                self._subscribed_symbols.update(msg[0].get("bars", []))
                logger.info(f"Subscribed to bars: {new}")
                return True
            logger.error(f"Bar subscription failed: {msg}")
            return False
        except Exception as e:
            logger.error(f"Failed to subscribe to bars: {e}")
            return False

    async def unsubscribe(self, symbols: list[str] | None = None) -> bool:
        """Unsubscribe from bar updates (all symbols if ``symbols`` is None)."""
        if not self.connected:
            return True

        targets = [s.upper() for s in symbols] if symbols else list(self._subscribed_symbols)
        if not targets:
            return True

        try:
            await self._send({"action": "unsubscribe", "bars": targets})
            msg = await self._recv()
            if msg and msg[0].get("T") == MessageType.SUBSCRIPTION:
                for s in targets:
                    self._subscribed_symbols.discard(s)
                logger.info(f"Unsubscribed from bars: {targets}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to unsubscribe from bars: {e}")
            return False

    async def stream(self) -> AsyncGenerator[StreamBar]:
        """Yield real-time bars, reconnecting and re-subscribing automatically."""
        self._running = True

        while self._running:
            if not self.connected:
                if not await self._reconnect():
                    break
                continue

            try:
                msg = await self._recv(timeout=60.0)
                if not msg:
                    continue
                for item in msg:
                    msg_type = item.get("T")
                    if msg_type == MessageType.BAR:
                        bar = self._parse_bar(item)
                        if bar:
                            yield bar
                    elif msg_type == MessageType.ERROR:
                        logger.error(f"Stream error message: {item.get('msg')}")
            except ConnectionClosed:
                logger.warning("Bar stream closed, reconnecting...")
                self._ws = None
                self._authenticated = False
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Bar stream error: {e}")
                await asyncio.sleep(1)

    def _parse_bar(self, data: dict[str, Any]) -> StreamBar | None:
        try:
            ts_str = data.get("t", "")
            timestamp = (
                datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts_str
                else datetime.now(UTC)
            )
            return StreamBar(
                symbol=str(data.get("S", "")),
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
    """In-memory bar stream for tests (no network)."""

    def __init__(self, bars: dict[str, list[StreamBar]] | None = None) -> None:
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

    async def stream(self) -> AsyncGenerator[StreamBar]:
        self._running = True
        for symbol in self._subscribed_symbols:
            for bar in self._bars.get(symbol, []):
                if not self._running:
                    return
                yield bar
                await asyncio.sleep(0.01)
