"""StreamFanout — one bus stream → many gRPC client streams.

Generalizes market-data's bespoke ``StreamManager``: a per-client bounded queue,
key-filtered routing (e.g. by symbol or session), and drop-on-full backpressure
so a slow client can't stall the producer or its peers. Both trading's
order/position streaming and market-data's bar streaming use this one fan-out.

Wire it as ``pump(bus.tail_…)`` in a background task; serve a gRPC stream with
``async for item in fanout.stream(client_id, keys): yield item``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterable
from typing import Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")
QUEUE_MAX = 1000


class StreamFanout(Generic[T]):
    """Routes keyed items to subscribed clients via per-client bounded queues."""

    def __init__(self, *, queue_max: int = QUEUE_MAX) -> None:
        self._queue_max = queue_max
        self._queues: dict[int, asyncio.Queue[T]] = {}
        self._subs: dict[int, set[str]] = {}  # client_id → keys ("" set = all)
        self._lock = asyncio.Lock()

    @property
    def client_count(self) -> int:
        return len(self._queues)

    async def connect(self, client_id: int, keys: Iterable[str] = ()) -> asyncio.Queue[T]:
        async with self._lock:
            queue: asyncio.Queue[T] = asyncio.Queue(maxsize=self._queue_max)
            self._queues[client_id] = queue
            self._subs[client_id] = {k.upper() for k in keys}
            return queue

    async def disconnect(self, client_id: int) -> None:
        async with self._lock:
            self._queues.pop(client_id, None)
            self._subs.pop(client_id, None)

    async def broadcast(self, key: str, item: T) -> None:
        """Deliver ``item`` to every client subscribed to ``key`` (or to all)."""
        key = key.upper()
        async with self._lock:
            targets = [
                (cid, q)
                for cid, q in self._queues.items()
                if not self._subs.get(cid) or key in self._subs[cid]
            ]
        for cid, queue in targets:
            try:
                queue.put_nowait(item)
            except asyncio.QueueFull:
                # Backpressure = drop; a slow client never stalls the producer.
                logger.warning("fanout queue full for client %s; dropping", cid)

    async def stream(self, client_id: int, keys: Iterable[str] = ()) -> AsyncIterator[T]:
        """Serve one gRPC client: subscribe, yield items, clean up on disconnect."""
        queue = await self.connect(client_id, keys)
        try:
            while True:
                yield await queue.get()
        finally:
            await self.disconnect(client_id)

    async def pump(
        self, source: AsyncIterator[tuple[str, T]], *, stop_event: asyncio.Event | None = None
    ) -> None:
        """Drive the fan-out from a ``(key, item)`` source (e.g. a bus tail)."""
        stop = stop_event or asyncio.Event()
        async for key, item in source:
            if stop.is_set():
                break
            await self.broadcast(key, item)
