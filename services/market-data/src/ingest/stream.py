"""Real-time stream write-through: Alpaca minute bars -> store + internal bus.

Incoming bars are buffered and flushed in batches (the per-minute fan-out
arrives as a burst), upserted into the store, and republished on the internal
EventBus for the serving role's live fan-out. The flush is batched so the
minute-boundary burst is one DB round-trip, not thousands.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, cast

from llamatrade_common.events import EventBus

from src.store.models import BarRow
from src.store.repository import BarStore
from src.streaming.bar_events import BAR_STREAM, BAR_STREAM_MAXLEN, encode_bar_event

if TYPE_CHECKING:
    from llamatrade_alpaca.streaming import MarketDataStreamClient

logger = logging.getLogger(__name__)


def bar_row_from_stream(symbol: str, bar_data: Mapping[str, object]) -> BarRow:
    """Convert an Alpaca streaming ``BarData`` payload into a ``BarRow``."""
    return BarRow(
        symbol=symbol,
        time=datetime.fromisoformat(str(bar_data["timestamp"])),
        open=Decimal(str(bar_data["open"])),
        high=Decimal(str(bar_data["high"])),
        low=Decimal(str(bar_data["low"])),
        close=Decimal(str(bar_data["close"])),
        volume=int(cast(int, bar_data["volume"])),
        vwap=Decimal(str(bar_data["vwap"])) if "vwap" in bar_data else None,
        trade_count=int(cast(int, bar_data["trade_count"])) if "trade_count" in bar_data else None,
    )


class BarIngestor:
    """Buffers live minute bars and flushes them to the store + EventBus."""

    def __init__(self, store: BarStore, event_bus: EventBus, *, max_buffer: int = 1000) -> None:
        self._store = store
        self._bus = event_bus
        self._max_buffer = max_buffer
        self._buffer: list[BarRow] = []
        self._lock = asyncio.Lock()

    async def handle_bar(self, symbol: str, bar_data: Mapping[str, object]) -> None:
        """Stream callback: buffer one bar, auto-flushing when the buffer is full."""
        row = bar_row_from_stream(symbol, bar_data)
        async with self._lock:
            self._buffer.append(row)
            if len(self._buffer) >= self._max_buffer:
                await self._flush_locked()

    async def flush(self) -> int:
        """Persist + publish buffered bars; returns the count flushed."""
        async with self._lock:
            return await self._flush_locked()

    async def _flush_locked(self) -> int:
        if not self._buffer:
            return 0
        rows = self._buffer
        self._buffer = []
        await self._store.upsert_bars(rows, "1Min")
        for row in rows:
            await self._bus.publish(BAR_STREAM, encode_bar_event(row), maxlen=BAR_STREAM_MAXLEN)
        logger.debug("Flushed %d live bars to store + bus", len(rows))
        return len(rows)

    def attach(self, alpaca_stream: MarketDataStreamClient) -> None:
        """Wire this ingestor as the bar callback of an Alpaca stream client."""
        alpaca_stream.set_callbacks(on_bar=self.handle_bar)

    async def run_flush_loop(
        self, *, interval_s: float = 1.0, stop_event: asyncio.Event | None = None
    ) -> None:
        """Periodically flush the buffer until ``stop_event`` is set."""
        stop = stop_event or asyncio.Event()
        try:
            while not stop.is_set():
                await asyncio.sleep(interval_s)
                try:
                    await self.flush()
                except Exception:
                    logger.exception("Flush loop error")
        finally:
            await self.flush()  # drain on shutdown
