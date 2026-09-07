"""Alpaca trading (account) WebSocket client for ``trade_updates`` events.

Connects to ``wss://api.alpaca.markets/stream``, authenticates, subscribes to
the ``trade_updates`` stream, and yields parsed order-lifecycle events. Fill
events from this stream are the source of truth for position state.

Metrics are intentionally NOT recorded here: pass ``on_reconnect`` /
``on_connection_change`` hooks for connection metrics, and record per-event
metrics in the consumer of ``stream()``.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, cast

from websockets.exceptions import ConnectionClosed

from ..config import AlpacaCredentials, AlpacaUrls
from ..models import FillData, TradeEvent, TradeEventType
from .base import AlpacaWebSocketBase

logger = logging.getLogger(__name__)

# Typed empty collections for strict typing.
_EMPTY_OBJECT_DICT: dict[str, object] = {}
_EMPTY_OBJECT_LIST: list[object] = []


class TradingStreamClient(AlpacaWebSocketBase):
    """WebSocket client for Alpaca real-time ``trade_updates`` events."""

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
            url=AlpacaUrls.trade_stream_url(paper=paper),
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
        self._subscribed = False

    @property
    def subscribed(self) -> bool:
        """Whether subscribed to the ``trade_updates`` stream."""
        return self._subscribed

    # ------------------------------------------------------------ handshake

    async def _authenticate(self) -> bool:
        await self._send(self._auth_payload())

        msg = await self._recv()
        if not msg:
            logger.error("No auth response received")
            return False

        if msg.get("stream") == "authorization":
            data_raw = msg.get("data", _EMPTY_OBJECT_DICT)
            auth_data = cast(
                dict[str, object],
                data_raw if isinstance(data_raw, dict) else _EMPTY_OBJECT_DICT,
            )
            if auth_data.get("status") == "authorized":
                return True
            logger.error("Auth failed: %s", auth_data)
            return False

        logger.error("Unexpected auth response: %s", msg)
        return False

    def _on_disconnect(self) -> None:
        self._subscribed = False

    async def _resubscribe(self) -> None:
        if not await self.subscribe():
            await self.disconnect()

    async def subscribe(self) -> bool:
        """Subscribe to the ``trade_updates`` stream."""
        if not self.connected or not self._authenticated:
            logger.error("Cannot subscribe: not connected or authenticated")
            return False

        try:
            await self._send({"action": "listen", "data": {"streams": ["trade_updates"]}})
            msg = await self._recv()
            if msg and msg.get("stream") == "listening":
                data_raw = msg.get("data", _EMPTY_OBJECT_DICT)
                sub_data = cast(
                    dict[str, object],
                    data_raw if isinstance(data_raw, dict) else _EMPTY_OBJECT_DICT,
                )
                streams_raw = sub_data.get("streams", _EMPTY_OBJECT_LIST)
                streams = cast(
                    list[object],
                    streams_raw if isinstance(streams_raw, list) else _EMPTY_OBJECT_LIST,
                )
                if "trade_updates" in streams:
                    self._subscribed = True
                    logger.info("Subscribed to trade_updates stream")
                    return True
            logger.error("Subscription failed: %s", msg)
            return False
        except Exception as e:
            logger.error("Failed to subscribe to trade updates: %s", e)
            return False

    # -------------------------------------------------------------- run loop

    async def stream(self) -> AsyncGenerator[TradeEvent]:
        """Yield ``trade_updates`` events, reconnecting automatically."""
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
                if msg.get("stream") == "trade_updates":
                    event_data = msg.get("data", _EMPTY_OBJECT_DICT)
                    trade_data = cast(
                        dict[str, object],
                        event_data if isinstance(event_data, dict) else _EMPTY_OBJECT_DICT,
                    )
                    event = self._parse_trade_event(trade_data)
                    if event:
                        yield event
            except ConnectionClosed:
                logger.warning("Trade stream connection closed, reconnecting...")
                self._ws = None
                self._authenticated = False
                self._subscribed = False
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Trade stream error: %s", e)
                # A persistently malformed feed loops here; the pacing sleep bounds it to 1/s.
                await self._sleep(1.0)

    # --------------------------------------------------------------- parser

    def _parse_trade_event(self, data: dict[str, object]) -> TradeEvent | None:
        try:
            event_str = str(data.get("event", ""))
            try:
                event_type = TradeEventType(event_str)
            except ValueError:
                logger.warning("Unknown trade event type: %s", event_str)
                return None

            order_data = data.get("order")
            order = cast(
                dict[str, object],
                order_data if isinstance(order_data, dict) else _EMPTY_OBJECT_DICT,
            )

            ts_raw = data.get("timestamp") or order.get("updated_at", "")
            ts_str = str(ts_raw) if ts_raw else ""
            timestamp = (
                datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts_str
                else datetime.now(UTC)
            )

            filled_avg_price = None
            if order.get("filled_avg_price"):
                filled_avg_price = Decimal(str(order["filled_avg_price"]))

            fill = None
            if event_type in (TradeEventType.FILL, TradeEventType.PARTIAL_FILL):
                side_raw = order.get("side", "buy")
                side_str: Literal["buy", "sell"] = "sell" if side_raw == "sell" else "buy"
                fill = FillData(
                    order_id=str(order.get("id", "")),
                    client_order_id=str(order.get("client_order_id", "")),
                    symbol=str(order.get("symbol", "")),
                    side=side_str,
                    fill_qty=Decimal(str(data.get("qty", 0))),
                    fill_price=Decimal(str(data.get("price", 0))),
                    total_filled_qty=Decimal(str(order.get("filled_qty", 0))),
                    remaining_qty=Decimal(str(order.get("qty", 0)))
                    - Decimal(str(order.get("filled_qty", 0))),
                    timestamp=timestamp,
                    position_qty=(
                        Decimal(str(data["position_qty"])) if data.get("position_qty") else None
                    ),
                )

            event_side_raw = order.get("side", "buy")
            event_side: Literal["buy", "sell"] = "sell" if event_side_raw == "sell" else "buy"

            return TradeEvent(
                event_type=event_type,
                order_id=str(order.get("id", "")),
                client_order_id=str(order.get("client_order_id", "")),
                symbol=str(order.get("symbol", "")),
                side=event_side,
                order_type=str(order.get("type", "market")),
                qty=Decimal(str(order.get("qty", 0))),
                filled_qty=Decimal(str(order.get("filled_qty", 0))),
                filled_avg_price=filled_avg_price,
                timestamp=timestamp,
                fill=fill,
            )
        except Exception as e:
            logger.error("Failed to parse trade event: %s", e)
            return None


class _StreamEnd:
    """Queue sentinel: promptly ends the active ``MockTradeStream.stream()`` generator."""


_STREAM_END = _StreamEnd()


class MockTradeStream:
    """In-memory trade stream for tests (no network).

    ``give_up()`` reproduces the real client's reconnect give-up: the active
    ``stream()`` generator exhausts (the ``async for`` ends) with ``_running``
    false and the connection state cleared, exactly as ``TradingStreamClient``
    behaves once ``_reconnect`` fails or runs out of attempts. A subsequent
    ``connect()`` clears the given-up state so a supervisor's rebuild path can
    stream again.
    """

    def __init__(self, events: list[TradeEvent] | None = None) -> None:
        self._events = events or []
        self._running = False
        self._connected = False
        self._authenticated = False
        self._subscribed = False
        self._gave_up = False
        self._event_queue: asyncio.Queue[TradeEvent | _StreamEnd] = asyncio.Queue()

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def authenticated(self) -> bool:
        """Distinct from ``connected``: tests can model connected-but-unauthenticated."""
        return self._authenticated

    @property
    def subscribed(self) -> bool:
        return self._subscribed

    @property
    def gave_up(self) -> bool:
        """Whether the stream ended via a simulated reconnect give-up."""
        return self._gave_up

    def give_up(self) -> None:
        """Simulate the real client exhausting its reconnect attempts."""
        self._gave_up = True
        self._running = False
        self._connected = False
        self._authenticated = False
        self._subscribed = False
        self._event_queue.put_nowait(_STREAM_END)

    async def connect(self) -> bool:
        self._gave_up = False
        self._connected = True
        self._authenticated = True
        return True

    async def disconnect(self) -> None:
        self._connected = False
        self._authenticated = False
        self._subscribed = False
        self._running = False

    async def subscribe(self) -> bool:
        if not self._connected:
            return False
        self._subscribed = True
        return True

    def add_fill(
        self,
        order_id: str,
        symbol: str,
        side: Literal["buy", "sell"],
        fill_qty: Decimal,
        fill_price: Decimal,
        client_order_id: str = "",
    ) -> None:
        """Convenience helper to queue a complete fill event."""
        now = datetime.now(UTC)
        fill = FillData(
            order_id=order_id,
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            fill_qty=fill_qty,
            fill_price=fill_price,
            total_filled_qty=fill_qty,
            remaining_qty=Decimal("0"),
            timestamp=now,
        )
        self._event_queue.put_nowait(
            TradeEvent(
                event_type=TradeEventType.FILL,
                order_id=order_id,
                client_order_id=client_order_id,
                symbol=symbol,
                side=side,
                order_type="market",
                qty=fill_qty,
                filled_qty=fill_qty,
                filled_avg_price=fill_price,
                timestamp=now,
                fill=fill,
            )
        )

    async def stream(self) -> AsyncGenerator[TradeEvent]:
        self._running = not self._gave_up
        for event in self._events:
            if not self._running or self._gave_up:
                break
            yield event
        while self._running and not self._gave_up:
            try:
                item = await asyncio.wait_for(self._event_queue.get(), timeout=0.1)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            if isinstance(item, _StreamEnd):
                if self._gave_up:
                    break
                continue  # stale sentinel from a give-up before this stream started
            yield item
        self._running = False
