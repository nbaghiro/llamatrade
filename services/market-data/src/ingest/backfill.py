"""Bulk REST backfill: fills the store's history for the universe.

For each (symbol, timeframe) the controller computes the target window, asks the
store which sub-ranges are missing, and fetches only those from Alpaca — so it
is resumable and idempotent (a partial run just leaves smaller gaps next time).
Symbols are processed with bounded concurrency to respect Alpaca rate limits.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from datetime import datetime, timedelta
from typing import Protocol

from src.models import Bar, Timeframe
from src.store.models import bar_row_from_alpaca
from src.store.repository import BarStore

logger = logging.getLogger(__name__)


class _AlpacaBars(Protocol):
    def get_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime | None = ...,
        limit: int = ...,
        adjustment: str = ...,
    ) -> Awaitable[list[Bar]]: ...


def backfill_window(now: datetime, lookback_days: float) -> tuple[datetime, datetime]:
    """Target ``[now - lookback, now)`` window for a backfill pass (pure)."""
    return (now - timedelta(days=lookback_days), now)


class BackfillController:
    """Drives REST backfill of the configured universe into the store."""

    def __init__(
        self,
        store: BarStore,
        alpaca: _AlpacaBars,
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
    def alpaca(self) -> _AlpacaBars:
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
