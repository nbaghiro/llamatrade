"""Bus-sourced fan-out bridge for the serving role.

Replaces the serving role's own Alpaca WebSocket for bars: it tails the internal
bar channel (``llamatrade_events.BarEvents``, fed by the ingest role's single
platform-wide Alpaca stream) and broadcasts each bar to the StreamManager, which
routes it to subscribed clients.

This is the consolidation win — the serving role no longer holds an Alpaca
connection; the ingestor is the platform's sole Alpaca stream consumer. The tail
task is supervised: a crash restarts it with capped backoff instead of silently
stopping live bars until the pod is recycled.
"""

from __future__ import annotations

import asyncio
import logging
import time

from llamatrade_events import BarEvents, EventBus

from src.streaming.bar_events import proto_to_bar_data
from src.streaming.manager import StreamManager

logger = logging.getLogger(__name__)

_RESTART_BASE_DELAY_SECONDS = 1.0
_RESTART_MAX_DELAY_SECONDS = 30.0
# A run that survives this long is considered healthy; the next crash restarts
# from the base delay instead of the escalated one.
_STEADY_RUN_SECONDS = 60.0


class BusBridge:
    """Tails the internal bar stream and broadcasts bars to the StreamManager."""

    def __init__(
        self,
        event_bus: EventBus,
        stream_manager: StreamManager,
        *,
        restart_base_delay: float = _RESTART_BASE_DELAY_SECONDS,
        restart_max_delay: float = _RESTART_MAX_DELAY_SECONDS,
    ) -> None:
        self._bars = BarEvents(bus=event_bus)
        self._manager = stream_manager
        self._restart_base = restart_base_delay
        self._restart_max = restart_max_delay
        self._task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def running(self) -> bool:
        """Whether the supervised tail loop is active (the serving role's live
        connection to the bar stream)."""
        return self._running

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._supervise())
        logger.info("BusBridge started; sourcing live bars from %s", self._bars.stream)

    async def _supervise(self) -> None:
        """Run the tail loop, restarting it on crash with capped backoff."""
        delay = self._restart_base
        while self._running:
            started = time.monotonic()
            try:
                await self._run()
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                if not self._running:
                    return
                if time.monotonic() - started >= _STEADY_RUN_SECONDS:
                    delay = self._restart_base
                logger.exception("BusBridge tail loop crashed; restarting in %.1fs", delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, self._restart_max)

    async def _run(self) -> None:
        # "$" (CURSOR_NEW) = only new entries (live fan-out, not replay).
        async for _cursor, bar in self._bars.tail(from_cursor="$"):
            if not self._running:
                break
            try:
                await self._manager.broadcast_bar(bar.symbol, proto_to_bar_data(bar))
            except Exception:
                logger.exception("Failed to route bar event for %s", bar.symbol)

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
