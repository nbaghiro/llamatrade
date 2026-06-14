"""Corporate-action self-heal: re-pull a trailing window of adjusted daily bars.

Alpaca returns split/dividend-*adjusted* daily bars, so a stored series goes
stale the day a symbol splits. Re-fetching a recent window each night and
upserting overwrites the affected rows with fresh adjusted values — cheap
insurance for the daily tier that backtests depend on.
"""

from __future__ import annotations

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


class CorporateActionRefresher:
    """Re-pulls and overwrites a trailing window of adjusted daily bars."""

    def __init__(self, store: BarStore, alpaca: _AlpacaBars, *, window_days: int = 10) -> None:
        self._store = store
        self._alpaca = alpaca
        self._window_days = window_days

    async def refresh(self, symbols: list[str], now: datetime) -> int:
        """Overwrite the trailing-window daily bars for each symbol."""
        start = now - timedelta(days=self._window_days)
        written = 0
        for symbol in symbols:
            bars = await self._alpaca.get_bars(
                symbol=symbol, timeframe=Timeframe.DAY_1, start=start, end=now
            )
            if bars:
                written += await self._store.upsert_bars(
                    [bar_row_from_alpaca(symbol, b) for b in bars], "1Day"
                )
        if written:
            logger.info("Corporate-action refresh overwrote %d daily bars", written)
        return written
