"""BarStore — the read/write interface over the Timescale bar tables.

Used by both roles: the ingest role writes (``upsert_bars``) and the serving
role reads (``select_bars`` / ``missing_ranges``). Derived timeframes resolve to
continuous-aggregate relations (read-only); only the two base tables accept
writes.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import (
    CursorResult,
    RowMapping,
    bindparam,
    column,
    delete,
    func,
    select,
)
from sqlalchemy import (
    table as sa_table,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.store.config import get_sessionmaker
from src.store.intervals import Interval, subtract
from src.store.models import (
    AGGREGATE_RELATION_BY_TIMEFRAME,
    BASE_TABLE_BY_TIMEFRAME,
    BarRow,
)

_READ_COLUMNS = ("time", "symbol", "open", "high", "low", "close", "volume", "vwap", "trade_count")


class UnsupportedTimeframeError(ValueError):
    """Raised for a timeframe with no backing table or aggregate."""


class ReadOnlyTimeframeError(ValueError):
    """Raised when writing a timeframe that is a continuous aggregate."""


def _relation_name(timeframe: str) -> str:
    """Whitelisted physical/view name for a timeframe (no user input reaches SQL)."""
    base = BASE_TABLE_BY_TIMEFRAME.get(timeframe)
    if base is not None:
        return base.name
    agg = AGGREGATE_RELATION_BY_TIMEFRAME.get(timeframe)
    if agg is not None:
        return agg
    raise UnsupportedTimeframeError(timeframe)


def _readable(timeframe: str):
    """A lightweight, injection-safe selectable for any readable timeframe."""
    return sa_table(_relation_name(timeframe), *(column(c) for c in _READ_COLUMNS))


class BarStore:
    """Persistence for OHLCV bars in the dedicated Timescale database."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        # Injectable so tests bind it to a throwaway (testcontainer) engine.
        self._session_factory = session_factory or get_sessionmaker()

    # ---------------------------------------------------------------- writes

    async def upsert_bars(self, rows: Sequence[BarRow], timeframe: str) -> int:
        """Idempotently insert/update bars, keyed on ``(symbol, time)``.

        Safe to call with overlapping ranges (backfill vs stream vs repair):
        a re-seen bar overwrites in place. Returns the number of rows applied.
        """
        table = BASE_TABLE_BY_TIMEFRAME.get(timeframe)
        if table is None:
            if timeframe in AGGREGATE_RELATION_BY_TIMEFRAME:
                raise ReadOnlyTimeframeError(timeframe)
            raise UnsupportedTimeframeError(timeframe)
        if not rows:
            return 0

        is_daily = timeframe == "1Day"
        values = [self._row_values(r, is_daily) for r in rows]

        stmt = pg_insert(table).values(values)
        update_cols = {
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
            "vwap": stmt.excluded.vwap,
            "trade_count": stmt.excluded.trade_count,
        }
        if is_daily:
            update_cols["adjustment"] = stmt.excluded.adjustment
            update_cols["fetched_at"] = stmt.excluded.fetched_at
        stmt = stmt.on_conflict_do_update(index_elements=["symbol", "time"], set_=update_cols)

        async with self._session_factory() as session:
            result = await session.execute(stmt)
            await session.commit()
            return cast(CursorResult[Any], result).rowcount or 0

    @staticmethod
    def _row_values(row: BarRow, is_daily: bool) -> dict[str, object]:
        values: dict[str, object] = {
            "time": row.time,
            "symbol": row.symbol,
            "open": row.open,
            "high": row.high,
            "low": row.low,
            "close": row.close,
            "volume": row.volume,
            "vwap": row.vwap,
            "trade_count": row.trade_count,
        }
        if is_daily:
            values["adjustment"] = "split"  # Alpaca's default adjusted daily
            values["fetched_at"] = func.now()
        return values

    async def delete_older_than(self, timeframe: str, cutoff: datetime) -> int:
        """Drop bars older than ``cutoff`` (manual retention; policies automate it)."""
        table = BASE_TABLE_BY_TIMEFRAME.get(timeframe)
        if table is None:
            raise UnsupportedTimeframeError(timeframe)
        async with self._session_factory() as session:
            result = await session.execute(delete(table).where(table.c.time < cutoff))
            await session.commit()
            return cast(CursorResult[Any], result).rowcount or 0

    # ----------------------------------------------------------------- reads

    async def select_bars(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[BarRow]:
        """Bars for ``symbol`` in ``[start, end)``, ordered by time ascending."""
        rel = _readable(timeframe)
        stmt = (
            select(*(rel.c[c] for c in _READ_COLUMNS))
            .where(rel.c.symbol == bindparam("symbol"))
            .where(rel.c.time >= bindparam("start"))
            .where(rel.c.time < bindparam("end"))
            .order_by(rel.c.time)
        )
        async with self._session_factory() as session:
            result = await session.execute(stmt, {"symbol": symbol, "start": start, "end": end})
            return [self._to_bar_row(m) for m in result.mappings()]

    async def covered_interval(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> Interval | None:
        """Span ``[min_time, max_time]`` of stored bars within ``[start, end)``.

        Used to compute edge gaps for the read path. Interior holes are the
        ingest gap-repair loop's responsibility, not the read path's.
        """
        rel = _readable(timeframe)
        stmt = (
            select(func.min(rel.c.time), func.max(rel.c.time))
            .where(rel.c.symbol == bindparam("symbol"))
            .where(rel.c.time >= bindparam("start"))
            .where(rel.c.time < bindparam("end"))
        )
        async with self._session_factory() as session:
            lo, hi = (
                await session.execute(stmt, {"symbol": symbol, "start": start, "end": end})
            ).one()
        if lo is None or hi is None:
            return None
        return (lo, hi)

    async def missing_ranges(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> list[Interval]:
        """Sub-ranges of ``[start, end)`` not covered by stored data (edge gaps)."""
        covered = await self.covered_interval(symbol, timeframe, start, end)
        return subtract((start, end), [covered] if covered else [])

    async def latest_ts(self, symbol: str, timeframe: str) -> datetime | None:
        """Newest stored bar time for ``symbol`` — ingestion-lag / append cursor."""
        rel = _readable(timeframe)
        stmt = select(func.max(rel.c.time)).where(rel.c.symbol == bindparam("symbol"))
        async with self._session_factory() as session:
            return (await session.execute(stmt, {"symbol": symbol})).scalar_one_or_none()

    @staticmethod
    def _to_bar_row(m: RowMapping) -> BarRow:
        return BarRow(
            symbol=m["symbol"],
            time=m["time"],
            open=m["open"],
            high=m["high"],
            low=m["low"],
            close=m["close"],
            volume=m["volume"],
            vwap=m["vwap"],
            trade_count=m["trade_count"],
        )


_store_singleton: BarStore | None = None


def get_bar_store() -> BarStore | None:
    """Process-wide BarStore, or None when persistence is disabled.

    Gated on ``MARKET_DATA_DB_URL`` being set, so a deployment without the
    dedicated Timescale instance transparently falls back to the legacy
    Alpaca pass-through (serving) path.
    """
    global _store_singleton
    if os.getenv("MARKET_DATA_DB_URL") is None:
        return None
    if _store_singleton is None:
        _store_singleton = BarStore()
    return _store_singleton
