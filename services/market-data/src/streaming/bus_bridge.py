"""Bus-sourced fan-out bridge for the serving role.

Replaces the serving role's own Alpaca WebSocket for bars: it tails the internal
EventBus (fed by the ingest role's single platform-wide Alpaca stream) and
broadcasts each bar to the StreamManager, which routes it to subscribed clients.

This is the consolidation win — the serving role no longer holds an Alpaca
connection; the ingestor is the platform's sole Alpaca stream consumer.
"""

from __future__ import annotations

import asyncio
import logging

from llamatrade_common.events import EventBus

from src.models import BarData
from src.store.models import BarRow
from src.streaming.bar_events import BAR_STREAM, decode_bar_event
from src.streaming.manager import StreamManager

logger = logging.getLogger(__name__)


def _bar_row_to_bardata(row: BarRow) -> BarData:
    """Adapt a decoded store BarRow to the streaming BarData the manager expects."""
    return BarData(
        open=float(row.open),
        high=float(row.high),
        low=float(row.low),
        close=float(row.close),
        volume=int(row.volume),
        timestamp=row.time.isoformat(),
    )


class BusBridge:
    """Tails the internal bar stream and broadcasts bars to the StreamManager."""

    def __init__(
        self,
        event_bus: EventBus,
        stream_manager: StreamManager,
        *,
        stream: str = BAR_STREAM,
    ) -> None:
        self._bus = event_bus
        self._manager = stream_manager
        self._stream = stream
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("BusBridge started; sourcing live bars from %s", self._stream)

    async def _run(self) -> None:
        # "$" = only new entries (live fan-out, not replay).
        try:
            async for _entry_id, fields in self._bus.tail(self._stream, last_id="$"):
                if not self._running:
                    break
                try:
                    row = decode_bar_event(fields)
                    await self._manager.broadcast_bar(row.symbol, _bar_row_to_bardata(row))
                except Exception:
                    logger.exception("Failed to route bar event %s", fields)
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
