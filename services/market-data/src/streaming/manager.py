"""WebSocket stream manager for real-time data distribution."""

import asyncio
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class StreamManager:
    """Manages WebSocket connections and data subscriptions."""

    def __init__(self):
        # client_id -> WebSocket
        self._connections: dict[int, WebSocket] = {}

        # symbol -> set of client_ids
        self._trade_subs: dict[str, set[int]] = defaultdict(set)
        self._quote_subs: dict[str, set[int]] = defaultdict(set)
        self._bar_subs: dict[str, set[int]] = defaultdict(set)

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

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

    async def connect(self, client_id: int, websocket: WebSocket):
        """Register a new client connection."""
        async with self._lock:
            self._connections[client_id] = websocket

    async def disconnect(self, client_id: int):
        """Remove a client connection and all its subscriptions."""
        async with self._lock:
            # Remove from connections
            self._connections.pop(client_id, None)

            # Remove from all subscriptions
            for subs in [self._trade_subs, self._quote_subs, self._bar_subs]:
                for symbol_clients in subs.values():
                    symbol_clients.discard(client_id)

    async def subscribe(
        self,
        client_id: int,
        trades: list[str],
        quotes: list[str],
        bars: list[str],
    ):
        """Subscribe a client to symbols."""
        async with self._lock:
            for symbol in trades:
                self._trade_subs[symbol.upper()].add(client_id)
            for symbol in quotes:
                self._quote_subs[symbol.upper()].add(client_id)
            for symbol in bars:
                self._bar_subs[symbol.upper()].add(client_id)

    async def unsubscribe(
        self,
        client_id: int,
        trades: list[str],
        quotes: list[str],
        bars: list[str],
    ):
        """Unsubscribe a client from symbols."""
        async with self._lock:
            for symbol in trades:
                self._trade_subs[symbol.upper()].discard(client_id)
            for symbol in quotes:
                self._quote_subs[symbol.upper()].discard(client_id)
            for symbol in bars:
                self._bar_subs[symbol.upper()].discard(client_id)

    async def broadcast_trade(self, symbol: str, data: dict[str, Any]):
        """Broadcast trade data to subscribed clients."""
        await self._broadcast(self._trade_subs, symbol, "trade", data)

    async def broadcast_quote(self, symbol: str, data: dict[str, Any]):
        """Broadcast quote data to subscribed clients."""
        await self._broadcast(self._quote_subs, symbol, "quote", data)

    async def broadcast_bar(self, symbol: str, data: dict[str, Any]):
        """Broadcast bar data to subscribed clients."""
        await self._broadcast(self._bar_subs, symbol, "bar", data)

    async def _broadcast(
        self,
        subs: dict[str, set[int]],
        symbol: str,
        msg_type: str,
        data: dict[str, Any],
    ):
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
