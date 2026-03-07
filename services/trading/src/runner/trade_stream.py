"""Alpaca WebSocket trade stream for real-time order/fill updates.

This stream receives trade updates from Alpaca including:
- Order accepted/rejected
- Order fills (partial and complete)
- Order cancellations
- Order expirations

Position tracking is driven by fill events from this stream,
ensuring local state matches broker reality.
"""

import asyncio
import json
import logging
import os
import random
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

import websockets
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed
from websockets.protocol import State

from src.metrics import (
    record_trade_stream_event,
    record_trade_stream_reconnect,
    set_trade_stream_connected,
)

logger = logging.getLogger(__name__)


class TradeEventType(Enum):
    """Types of trade update events from Alpaca."""

    NEW = "new"
    FILL = "fill"
    PARTIAL_FILL = "partial_fill"
    CANCELED = "canceled"
    EXPIRED = "expired"
    DONE_FOR_DAY = "done_for_day"
    REPLACED = "replaced"
    REJECTED = "rejected"
    PENDING_NEW = "pending_new"
    STOPPED = "stopped"
    PENDING_CANCEL = "pending_cancel"
    PENDING_REPLACE = "pending_replace"
    CALCULATED = "calculated"
    SUSPENDED = "suspended"
    ORDER_REPLACE_REJECTED = "order_replace_rejected"
    ORDER_CANCEL_REJECTED = "order_cancel_rejected"


@dataclass
class FillData:
    """Data for a fill event."""

    order_id: str
    client_order_id: str
    symbol: str
    side: Literal["buy", "sell"]
    fill_qty: Decimal
    fill_price: Decimal
    total_filled_qty: Decimal
    remaining_qty: Decimal
    timestamp: datetime
    position_qty: Decimal | None = None  # Current position after fill


@dataclass
class TradeEvent:
    """Trade update event from Alpaca."""

    event_type: TradeEventType
    order_id: str
    client_order_id: str
    symbol: str
    side: Literal["buy", "sell"]
    order_type: str
    qty: Decimal
    filled_qty: Decimal
    filled_avg_price: Decimal | None
    timestamp: datetime
    # Fill-specific fields (only populated for fill events)
    fill: FillData | None = None


@dataclass
class TradeStreamConfig:
    """Configuration for trade stream."""

    api_key: str = field(default_factory=lambda: os.getenv("ALPACA_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("ALPACA_API_SECRET", ""))
    paper: bool = True
    reconnect_delay: float = 1.0
    max_reconnect_delay: float = 60.0
    max_reconnect_attempts: int = 10
    jitter_factor: float = 0.1


class AlpacaTradeStream:
    """WebSocket client for Alpaca real-time trade updates.

    Subscribes to the trade_updates stream to receive order lifecycle
    events including fills. This is the source of truth for position
    state - positions should only be updated based on fill events
    from this stream.
    """

    LIVE_URL = "wss://api.alpaca.markets/stream"
    PAPER_URL = "wss://paper-api.alpaca.markets/stream"

    def __init__(self, config: TradeStreamConfig | None = None):
        self.config = config or TradeStreamConfig()
        self.url = self.PAPER_URL if self.config.paper else self.LIVE_URL

        self._ws: ClientConnection | None = None
        self._running = False
        self._authenticated = False
        self._subscribed = False
        self._reconnect_attempts = 0

        # Queue for incoming trade events
        self._event_queue: asyncio.Queue[TradeEvent] = asyncio.Queue()

    @property
    def connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._ws is not None and self._ws.state == State.OPEN

    @property
    def authenticated(self) -> bool:
        """Check if stream is authenticated."""
        return self._authenticated

    @property
    def subscribed(self) -> bool:
        """Check if subscribed to trade updates."""
        return self._subscribed

    async def connect(self) -> bool:
        """Connect to Alpaca WebSocket and authenticate."""
        try:
            self._ws = await websockets.connect(self.url)
            assert self._ws is not None  # websockets.connect always returns a connection
            logger.info(f"Connected to Alpaca trade stream: {self.url}")

            # Authenticate
            auth_msg = {
                "action": "auth",
                "key": self.config.api_key,
                "secret": self.config.api_secret,
            }
            await self._ws.send(json.dumps(auth_msg))

            # Wait for auth response
            msg = await self._receive_message()
            if not msg:
                logger.error("No auth response received")
                return False

            # Check for authorized message
            if msg.get("stream") == "authorization":
                data = msg.get("data", {})
                if data.get("status") == "authorized":
                    self._authenticated = True
                    self._reconnect_attempts = 0
                    set_trade_stream_connected(True)
                    logger.info("Authenticated with Alpaca trade stream")
                    return True
                else:
                    logger.error(f"Auth failed: {data}")
                    return False

            logger.error(f"Unexpected auth response: {msg}")
            return False

        except Exception as e:
            logger.error(f"Failed to connect to Alpaca trade stream: {e}")
            set_trade_stream_connected(False)
            return False

    async def disconnect(self) -> None:
        """Disconnect from Alpaca WebSocket."""
        self._running = False
        self._authenticated = False
        self._subscribed = False

        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        set_trade_stream_connected(False)
        logger.info("Disconnected from Alpaca trade stream")

    async def subscribe(self) -> bool:
        """Subscribe to trade updates stream."""
        if not self.connected or not self._authenticated:
            logger.error("Cannot subscribe: not connected or authenticated")
            return False

        try:
            if not self._ws:
                return False

            sub_msg = {
                "action": "listen",
                "data": {
                    "streams": ["trade_updates"],
                },
            }
            await self._ws.send(json.dumps(sub_msg))

            # Wait for subscription confirmation
            msg = await self._receive_message()
            if msg and msg.get("stream") == "listening":
                streams = msg.get("data", {}).get("streams", [])
                if "trade_updates" in streams:
                    self._subscribed = True
                    logger.info("Subscribed to trade_updates stream")
                    return True

            logger.error(f"Subscription failed: {msg}")
            return False

        except Exception as e:
            logger.error(f"Failed to subscribe to trade updates: {e}")
            return False

    async def stream(self) -> AsyncGenerator[TradeEvent]:
        """Stream trade events as an async generator.

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

                # Check if it's a trade update
                if msg.get("stream") == "trade_updates":
                    event = self._parse_trade_event(msg.get("data", {}))
                    if event:
                        record_trade_stream_event(event.event_type.value)
                        yield event

            except ConnectionClosed:
                logger.warning("Trade stream connection closed, reconnecting...")
                self._ws = None
                self._authenticated = False
                self._subscribed = False

            except asyncio.CancelledError:
                break

            except Exception as e:
                logger.error(f"Trade stream error: {e}")
                await asyncio.sleep(1)

    async def _receive_message(self, timeout: float = 10.0) -> dict | None:
        """Receive and parse a WebSocket message."""
        if not self._ws:
            return None

        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
            result: dict = json.loads(raw)
            return result
        except TimeoutError:
            return None
        except Exception as e:
            logger.error(f"Error receiving trade message: {e}")
            return None

    async def _reconnect(self) -> bool:
        """Attempt to reconnect with exponential backoff and jitter."""
        if self._reconnect_attempts >= self.config.max_reconnect_attempts:
            logger.error("Max trade stream reconnection attempts reached")
            self._running = False
            return False

        self._reconnect_attempts += 1
        record_trade_stream_reconnect()

        # Calculate exponential backoff delay
        base_delay = self.config.reconnect_delay * (2 ** (self._reconnect_attempts - 1))
        jitter = random.uniform(0, self.config.jitter_factor * base_delay)
        delay = min(base_delay + jitter, self.config.max_reconnect_delay)

        logger.info(
            f"Reconnecting trade stream in {delay:.2f}s "
            f"(attempt {self._reconnect_attempts}/{self.config.max_reconnect_attempts})"
        )
        await asyncio.sleep(delay)

        if await self.connect():
            # Re-subscribe to trade updates
            if await self.subscribe():
                return True
            await self.disconnect()

        return False

    def _parse_trade_event(self, data: dict) -> TradeEvent | None:
        """Parse Alpaca trade update message to TradeEvent."""
        try:
            event_str = data.get("event", "")
            try:
                event_type = TradeEventType(event_str)
            except ValueError:
                logger.warning(f"Unknown trade event type: {event_str}")
                return None

            order = data.get("order", {})

            # Parse timestamp
            ts_str = data.get("timestamp") or order.get("updated_at", "")
            if ts_str:
                timestamp = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            else:
                timestamp = datetime.now(UTC)

            # Parse filled average price
            filled_avg_price = None
            if order.get("filled_avg_price"):
                filled_avg_price = Decimal(str(order["filled_avg_price"]))

            # Parse fill data for fill events
            fill = None
            if event_type in (TradeEventType.FILL, TradeEventType.PARTIAL_FILL):
                fill = FillData(
                    order_id=order.get("id", ""),
                    client_order_id=order.get("client_order_id", ""),
                    symbol=order.get("symbol", ""),
                    side=order.get("side", "buy"),
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

            return TradeEvent(
                event_type=event_type,
                order_id=order.get("id", ""),
                client_order_id=order.get("client_order_id", ""),
                symbol=order.get("symbol", ""),
                side=order.get("side", "buy"),
                order_type=order.get("type", "market"),
                qty=Decimal(str(order.get("qty", 0))),
                filled_qty=Decimal(str(order.get("filled_qty", 0))),
                filled_avg_price=filled_avg_price,
                timestamp=timestamp,
                fill=fill,
            )

        except Exception as e:
            logger.error(f"Failed to parse trade event: {e}")
            return None


class MockTradeStream:
    """Mock trade stream for testing without Alpaca connection."""

    def __init__(self, events: list[TradeEvent] | None = None):
        self._events = events or []
        self._event_index = 0
        self._running = False
        self._connected = False
        self._subscribed = False
        self._event_queue: asyncio.Queue[TradeEvent] = asyncio.Queue()

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def authenticated(self) -> bool:
        return self._connected

    @property
    def subscribed(self) -> bool:
        return self._subscribed

    async def connect(self) -> bool:
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False
        self._subscribed = False
        self._running = False

    async def subscribe(self) -> bool:
        if not self._connected:
            return False
        self._subscribed = True
        return True

    def add_event(self, event: TradeEvent) -> None:
        """Add an event to be emitted."""
        self._event_queue.put_nowait(event)

    def add_fill(
        self,
        order_id: str,
        symbol: str,
        side: Literal["buy", "sell"],
        fill_qty: Decimal,
        fill_price: Decimal,
        client_order_id: str = "",
    ) -> None:
        """Convenience method to add a fill event."""
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
        event = TradeEvent(
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
        self._event_queue.put_nowait(event)

    async def stream(self) -> AsyncGenerator[TradeEvent]:
        """Stream trade events from queue."""
        self._running = True

        # First yield pre-configured events
        for event in self._events:
            if not self._running:
                break
            yield event

        # Then wait for dynamically added events
        while self._running:
            try:
                event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=0.1,
                )
                yield event
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
