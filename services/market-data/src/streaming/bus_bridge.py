"""Bus-sourced fan-out bridge for the serving role.

Replaces the serving role's own Alpaca WebSocket for bars: it tails the internal
bar channel (``llamatrade_events.BarEvents``, fed by the ingest role's single
platform-wide Alpaca stream) and broadcasts each bar to the StreamManager, which
routes it to subscribed clients.

This is the consolidation win — the serving role no longer holds an Alpaca
connection; the ingestor is the platform's sole Alpaca stream consumer.
"""

from __future__ import annotations

import asyncio
import logging

from llamatrade_events import BarEvents, EventBus

from src.streaming.bar_events import proto_to_bar_data
from src.streaming.manager import StreamManager

logger = logging.getLogger(__name__)


class BusBridge:
    """Tails the internal bar stream and broadcasts bars to the StreamManager."""

    def __init__(
        self,
        event_bus: EventBus,
        stream_manager: StreamManager,
    ) -> None:
        self._bars = BarEvents(bus=event_bus)
        self._manager = stream_manager
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("BusBridge started; sourcing live bars from %s", self._bars.stream)

    async def _run(self) -> None:
        # "$" (CURSOR_NEW) = only new entries (live fan-out, not replay).
        try:
            async for _cursor, bar in self._bars.tail(from_cursor="$"):
                if not self._running:
                    break
                try:
                    await self._manager.broadcast_bar(bar.symbol, proto_to_bar_data(bar))
                except Exception:
                    logger.exception("Failed to route bar event for %s", bar.symbol)
        except asyncio.CancelledError:
            raise

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
