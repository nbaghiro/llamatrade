"""Bulk REST backfill: fills the store's history for the universe.

For each (symbol, timeframe) the controller computes the target window, asks the
store which sub-ranges are missing, and fetches only those from Alpaca — so it
is resumable and idempotent (a partial run just leaves smaller gaps next time).
Symbols are processed with bounded concurrency to respect Alpaca rate limits.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta

from src.ingest._types import AlpacaBars
from src.ingest.config import adjustment_for
from src.metrics import record_targeted_backfill
from src.models import Timeframe
from src.store.models import bar_row_from_alpaca
from src.store.repository import BarStore

logger = logging.getLogger(__name__)


def backfill_window(now: datetime, lookback_days: float) -> tuple[datetime, datetime]:
    """Target ``[now - lookback, now)`` window for a backfill pass (pure)."""
    return (now - timedelta(days=lookback_days), now)


class BackfillController:
    """Drives REST backfill of the configured universe into the store."""

    def __init__(
        self,
        store: BarStore,
        alpaca: AlpacaBars,
        *,
        timeframes: tuple[str, ...],
        lookback_for: dict[str, float],
        max_concurrency: int = 4,
        fetch_limit: int = 10_000,
    ) -> None:
        self._store = store
        self._alpaca = alpaca
        self._timeframes = timeframes
        self._lookback_for = lookback_for
        self._fetch_limit = fetch_limit
        self._semaphore = asyncio.Semaphore(max_concurrency)

    @property
    def store(self) -> BarStore:
        """The bar store this controller writes to (read access for collaborators)."""
        return self._store

    @property
    def alpaca(self) -> AlpacaBars:
        """The Alpaca bars source this controller fetches from."""
        return self._alpaca

    async def backfill_symbol_timeframe(self, symbol: str, timeframe: str, now: datetime) -> int:
        """Fill any gaps for one (symbol, timeframe). Returns rows written."""
        start, end = backfill_window(now, self._lookback_for[timeframe])
        gaps = await self._store.missing_ranges(symbol, timeframe, start, end)
        written = 0
        for gap_start, gap_end in gaps:
            bars = await self._alpaca.get_bars(
                symbol=symbol,
                timeframe=Timeframe(timeframe),
                start=gap_start,
                end=gap_end,
                limit=self._fetch_limit,
                adjustment=adjustment_for(timeframe),
            )
            if bars:
                rows = [bar_row_from_alpaca(symbol, b) for b in bars]
                written += await self._store.upsert_bars(rows, timeframe)
        if written:
            logger.info("Backfilled %s %s: %d bars", symbol, timeframe, written)
        return written

    async def run(self, symbols: list[str], now: datetime) -> dict[str, int]:
        """Backfill all (symbol, timeframe) pairs concurrently; rows-per-symbol."""

        async def _one(symbol: str) -> tuple[str, int]:
            async with self._semaphore:
                total = 0
                for timeframe in self._timeframes:
                    try:
                        total += await self.backfill_symbol_timeframe(symbol, timeframe, now)
                    except Exception:
                        logger.exception("Backfill failed for %s %s", symbol, timeframe)
                return symbol, total

        results = await asyncio.gather(*(_one(s) for s in symbols))
        return dict(results)


class TargetedBackfill:
    """Catch-up backfill for symbols that just entered the ingest universe.

    A symbol added by a universe refresh is streamed from the next bar on, but it
    has no history in the store until the next daily backfill pass (hourly gap
    repair only narrows the hole). The refresh that added it schedules a pass here
    instead.

    The pass runs on its own task, so the refresh loop never waits on Alpaca, and
    only one pass is in flight at a time: symbols added while a pass runs are
    folded into the next one. Failures are contained and counted — one unfetchable
    symbol must not stop universe refreshes.
    """

    def __init__(self, controller: BackfillController, now: Callable[[], datetime]) -> None:
        self._controller = controller
        self._now = now
        self._queued: set[str] = set()
        self._task: asyncio.Task[None] | None = None

    def schedule(self, symbols: Iterable[str]) -> None:
        """Queue ``symbols`` for a catch-up pass; a no-op when nothing was added."""
        added = set(symbols)
        if not added:
            return
        self._queued |= added
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._drain())

    async def _drain(self) -> None:
        while self._queued:
            symbols = sorted(self._queued)
            self._queued.clear()
            try:
                await self._controller.run(symbols, self._now())
            except Exception:
                record_targeted_backfill("error")
                logger.exception("Targeted backfill failed for %s", symbols)
            else:
                record_targeted_backfill("ok")
                logger.info("Targeted backfill completed for %s", symbols)

    async def aclose(self) -> None:
        """Cancel an in-flight pass (shutdown)."""
        task = self._task
        self._task = None
        self._queued.clear()
        if task is None or task.done():
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
