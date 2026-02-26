"""WebSocket stream manager for real-time data distribution."""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable

from fastapi import WebSocket

from src.models import BarData, QuoteData, StreamData, TradeData

logger = logging.getLogger(__name__)

# Callback type for subscription changes
SubscriptionCallback = Callable[
    [list[str], list[str], list[str]],  # trades, quotes, bars
    None,
]


class StreamManager:
    """Manages WebSocket connections and data subscriptions.

    Provides subscription tracking and data broadcasting to clients.
    """

    def __init__(self) -> None:
        # client_id -> WebSocket
        self._connections: dict[int, WebSocket] = {}

        # symbol -> set of client_ids
        self._trade_subs: dict[str, set[int]] = defaultdict(set)
        self._quote_subs: dict[str, set[int]] = defaultdict(set)
        self._bar_subs: dict[str, set[int]] = defaultdict(set)

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

        # Callbacks for subscription changes (for bridge integration)
        self._on_subscribe: SubscriptionCallback | None = None
        self._on_unsubscribe: SubscriptionCallback | None = None

    def set_subscription_callbacks(
        self,
        on_subscribe: SubscriptionCallback | None = None,
        on_unsubscribe: SubscriptionCallback | None = None,
    ) -> None:
        """Set callbacks for subscription changes.

        These are called when clients subscribe/unsubscribe to allow
        the bridge to sync with Alpaca.

        Args:
            on_subscribe: Called with (trades, quotes, bars) when subscribed
            on_unsubscribe: Called with (trades, quotes, bars) when unsubscribed
        """
        self._on_subscribe = on_subscribe
        self._on_unsubscribe = on_unsubscribe

    @property
    def connection_count(self) -> int:
        """Number of active connections."""
        return len(self._connections)

    @property
    def subscription_count(self) -> dict[str, int]:
        """Count of subscriptions by type."""
        return {
            "trades": sum(len(clients) for clients in self._trade_subs.values()),
            "quotes": sum(len(clients) for clients in self._quote_subs.values()),
            "bars": sum(len(clients) for clients in self._bar_subs.values()),
        }

    @property
    def subscribed_symbols(self) -> dict[str, set[str]]:
        """Get all symbols with at least one subscriber."""
        return {
            "trades": {s for s, clients in self._trade_subs.items() if clients},
            "quotes": {s for s, clients in self._quote_subs.items() if clients},
            "bars": {s for s, clients in self._bar_subs.items() if clients},
        }

    async def connect(self, client_id: int, websocket: WebSocket) -> None:
        """Register a new client connection."""
        async with self._lock:
            self._connections[client_id] = websocket
        logger.debug(f"Client {client_id} connected")

    async def disconnect(self, client_id: int) -> None:
        """Remove a client connection and all its subscriptions."""
        # Collect symbols to potentially unsubscribe from Alpaca
        removed_trades: list[str] = []
        removed_quotes: list[str] = []
        removed_bars: list[str] = []

        async with self._lock:
            # Remove from connections
            self._connections.pop(client_id, None)

            # Remove from all subscriptions and track what was removed
            for symbol, clients in list(self._trade_subs.items()):
                if client_id in clients:
                    clients.discard(client_id)
                    if not clients:
                        removed_trades.append(symbol)

            for symbol, clients in list(self._quote_subs.items()):
                if client_id in clients:
                    clients.discard(client_id)
                    if not clients:
                        removed_quotes.append(symbol)

            for symbol, clients in list(self._bar_subs.items()):
                if client_id in clients:
                    clients.discard(client_id)
                    if not clients:
                        removed_bars.append(symbol)

        # Notify bridge of removed subscriptions
        if self._on_unsubscribe and (removed_trades or removed_quotes or removed_bars):
            try:
                self._on_unsubscribe(removed_trades, removed_quotes, removed_bars)
            except Exception as e:
                logger.error(f"Error in unsubscribe callback: {e}")

        logger.debug(f"Client {client_id} disconnected")

    async def subscribe(
        self,
        client_id: int,
        trades: list[str],
        quotes: list[str],
        bars: list[str],
    ) -> None:
        """Subscribe a client to symbols.

        Args:
            client_id: Client identifier
            trades: Symbols for trade updates
            quotes: Symbols for quote updates
            bars: Symbols for bar updates
        """
        # Track which symbols are newly subscribed (first client)
        new_trades: list[str] = []
        new_quotes: list[str] = []
        new_bars: list[str] = []

        async with self._lock:
            for symbol in trades:
                symbol = symbol.upper()
                if not self._trade_subs[symbol]:
                    new_trades.append(symbol)
                self._trade_subs[symbol].add(client_id)

            for symbol in quotes:
                symbol = symbol.upper()
                if not self._quote_subs[symbol]:
                    new_quotes.append(symbol)
                self._quote_subs[symbol].add(client_id)

            for symbol in bars:
                symbol = symbol.upper()
                if not self._bar_subs[symbol]:
                    new_bars.append(symbol)
                self._bar_subs[symbol].add(client_id)

        # Notify bridge of new subscriptions
        if self._on_subscribe and (new_trades or new_quotes or new_bars):
            try:
                self._on_subscribe(new_trades, new_quotes, new_bars)
            except Exception as e:
                logger.error(f"Error in subscribe callback: {e}")

    async def unsubscribe(
        self,
        client_id: int,
        trades: list[str],
        quotes: list[str],
        bars: list[str],
    ) -> None:
        """Unsubscribe a client from symbols.

        Args:
            client_id: Client identifier
            trades: Symbols to unsubscribe from trade updates
            quotes: Symbols to unsubscribe from quote updates
            bars: Symbols to unsubscribe from bar updates
        """
        # Track which symbols have no more subscribers
        removed_trades: list[str] = []
        removed_quotes: list[str] = []
        removed_bars: list[str] = []

        async with self._lock:
            for symbol in trades:
                symbol = symbol.upper()
                self._trade_subs[symbol].discard(client_id)
                if not self._trade_subs[symbol]:
                    removed_trades.append(symbol)

            for symbol in quotes:
                symbol = symbol.upper()
                self._quote_subs[symbol].discard(client_id)
                if not self._quote_subs[symbol]:
                    removed_quotes.append(symbol)

            for symbol in bars:
                symbol = symbol.upper()
                self._bar_subs[symbol].discard(client_id)
                if not self._bar_subs[symbol]:
                    removed_bars.append(symbol)

        # Notify bridge of removed subscriptions
        if self._on_unsubscribe and (removed_trades or removed_quotes or removed_bars):
            try:
                self._on_unsubscribe(removed_trades, removed_quotes, removed_bars)
            except Exception as e:
                logger.error(f"Error in unsubscribe callback: {e}")

    async def broadcast_trade(self, symbol: str, data: TradeData) -> None:
        """Broadcast trade data to subscribed clients."""
        await self._broadcast(self._trade_subs, symbol, "trade", data)

    async def broadcast_quote(self, symbol: str, data: QuoteData) -> None:
        """Broadcast quote data to subscribed clients."""
        await self._broadcast(self._quote_subs, symbol, "quote", data)

    async def broadcast_bar(self, symbol: str, data: BarData) -> None:
        """Broadcast bar data to subscribed clients."""
        await self._broadcast(self._bar_subs, symbol, "bar", data)

    async def _broadcast(
        self,
        subs: dict[str, set[int]],
        symbol: str,
        msg_type: str,
        data: StreamData,
    ) -> None:
        """Broadcast data to subscribed clients."""
        symbol = symbol.upper()
        client_ids = subs.get(symbol, set())

        if not client_ids:
            return

        message = {
            "type": msg_type,
            "symbol": symbol,
            "data": data,
        }

        # Send to all subscribed clients
        disconnected = []
        for client_id in client_ids:
            websocket = self._connections.get(client_id)
            if websocket:
                try:
                    await websocket.send_json(message)
                except Exception:
                    disconnected.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected:
            await self.disconnect(client_id)


# Singleton instance
_manager: StreamManager | None = None


def get_stream_manager() -> StreamManager:
    """Dependency to get stream manager."""
    global _manager
    if _manager is None:
        _manager = StreamManager()
    return _manager


def reset_stream_manager() -> None:
    """Reset the stream manager (for testing)."""
    global _manager
    _manager = None
