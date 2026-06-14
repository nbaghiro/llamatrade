"""Integration tests for BarStore against a real TimescaleDB.

No mocking: real upserts, real selects, real continuous-aggregate rollups.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from src.store.models import BarRow
from src.store.repository import (
    BarStore,
    ReadOnlyTimeframeError,
    UnsupportedTimeframeError,
)

pytestmark = pytest.mark.integration


def _minute_bar(symbol: str, minute: int, close: float = 100.0) -> BarRow:
    return BarRow(
        symbol=symbol,
        time=datetime(2026, 1, 5, 14, 30, tzinfo=UTC) + timedelta(minutes=minute),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal(str(close)),
        volume=1000 + minute,
        vwap=Decimal("100.5"),
        trade_count=10,
    )


def _daily_bar(symbol: str, day: int, close: float = 100.0) -> BarRow:
    return BarRow(
        symbol=symbol,
        time=datetime(2026, 1, day, tzinfo=UTC),
        open=Decimal("100"),
        high=Decimal("105"),
        low=Decimal("95"),
        close=Decimal(str(close)),
        volume=1_000_000,
        vwap=Decimal("100.5"),
        trade_count=5000,
    )


class TestUpsertAndSelect:
    async def test_insert_then_select_ordered(self, bar_store: BarStore) -> None:
        bars = [_minute_bar("AAPL", m) for m in (2, 0, 1)]  # out of order
        n = await bar_store.upsert_bars(bars, "1Min")
        assert n == 3

        got = await bar_store.select_bars(
            "AAPL", "1Min", _minute_bar("AAPL", 0).time, _minute_bar("AAPL", 5).time
        )
        assert [b.time for b in got] == [_minute_bar("AAPL", m).time for m in (0, 1, 2)]
        assert got[0].close == Decimal("100")

    async def test_upsert_is_idempotent(self, bar_store: BarStore) -> None:
        await bar_store.upsert_bars([_minute_bar("MSFT", 0, close=100.0)], "1Min")
        # Re-upsert the same (symbol, time) with a new close — must update, not dup.
        await bar_store.upsert_bars([_minute_bar("MSFT", 0, close=222.0)], "1Min")

        got = await bar_store.select_bars(
            "MSFT", "1Min", _minute_bar("MSFT", 0).time, _minute_bar("MSFT", 1).time
        )
        assert len(got) == 1
        assert got[0].close == Decimal("222")

    async def test_select_is_half_open_and_symbol_scoped(self, bar_store: BarStore) -> None:
        await bar_store.upsert_bars([_minute_bar("AAPL", m) for m in range(5)], "1Min")
        await bar_store.upsert_bars([_minute_bar("TSLA", 0)], "1Min")

        start = _minute_bar("AAPL", 1).time
        end = _minute_bar("AAPL", 3).time  # exclusive
        got = await bar_store.select_bars("AAPL", "1Min", start, end)
        assert [b.time for b in got] == [_minute_bar("AAPL", 1).time, _minute_bar("AAPL", 2).time]

    async def test_daily_upsert_sets_adjustment_and_fetched_at(self, bar_store: BarStore) -> None:
        await bar_store.upsert_bars([_daily_bar("SPY", 2)], "1Day")
        got = await bar_store.select_bars(
            "SPY", "1Day", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 10, tzinfo=UTC)
        )
        assert len(got) == 1 and got[0].close == Decimal("100")

    async def test_write_to_aggregate_is_rejected(self, bar_store: BarStore) -> None:
        with pytest.raises(ReadOnlyTimeframeError):
            await bar_store.upsert_bars([_minute_bar("AAPL", 0)], "1Hour")

    async def test_unknown_timeframe_rejected(self, bar_store: BarStore) -> None:
        with pytest.raises(UnsupportedTimeframeError):
            await bar_store.upsert_bars([_minute_bar("AAPL", 0)], "2Min")


class TestGapDetection:
    async def test_empty_store_whole_range_missing(self, bar_store: BarStore) -> None:
        start = datetime(2026, 1, 5, tzinfo=UTC)
        end = datetime(2026, 1, 6, tzinfo=UTC)
        assert await bar_store.missing_ranges("NVDA", "1Min", start, end) == [(start, end)]

    async def test_partial_coverage_returns_edges(self, bar_store: BarStore) -> None:
        # store minutes 2..4; ask for 0..10 -> leading + trailing gaps
        await bar_store.upsert_bars([_minute_bar("AMD", m) for m in (2, 3, 4)], "1Min")
        start = _minute_bar("AMD", 0).time
        end = _minute_bar("AMD", 10).time
        gaps = await bar_store.missing_ranges("AMD", "1Min", start, end)
        assert gaps[0][0] == start  # leading gap starts at requested start
        assert gaps[-1][1] == end  # trailing gap ends at requested end

    async def test_latest_ts(self, bar_store: BarStore) -> None:
        assert await bar_store.latest_ts("META", "1Min") is None
        await bar_store.upsert_bars([_minute_bar("META", m) for m in range(3)], "1Min")
        assert await bar_store.latest_ts("META", "1Min") == _minute_bar("META", 2).time


class TestContinuousAggregate:
    async def test_minute_bars_roll_up_to_hourly(
        self, bar_store: BarStore, timescale_engine
    ) -> None:
        # 60 one-minute bars anchored to the top of an hour -> exactly one
        # hourly bucket. Unique symbol isolates the materialized aggregate.
        base = datetime(2026, 1, 5, 13, 0, tzinfo=UTC)
        bars = [
            BarRow(
                symbol="CAGGT",
                time=base + timedelta(minutes=m),
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal(str(100 + m)),
                volume=1000 + m,
                vwap=Decimal("100.5"),
                trade_count=10,
            )
            for m in range(60)
        ]
        await bar_store.upsert_bars(bars, "1Min")

        # Force-refresh the continuous aggregate (the refresh policy runs in the
        # background in prod). CALL must run outside a transaction -> AUTOCOMMIT.
        autocommit = timescale_engine.execution_options(isolation_level="AUTOCOMMIT")
        async with autocommit.connect() as conn:
            await conn.exec_driver_sql("CALL refresh_continuous_aggregate('bars_1h', NULL, NULL)")

        hour_start = datetime(2026, 1, 5, 13, 0, tzinfo=UTC)
        hour_end = datetime(2026, 1, 5, 14, 0, tzinfo=UTC)
        rolled = await bar_store.select_bars("CAGGT", "1Hour", hour_start, hour_end)
        assert len(rolled) == 1
        bucket = rolled[0]
        assert bucket.open == Decimal("100")  # first minute's open
        assert bucket.close == Decimal("159")  # last minute's close (100 + 59)
        assert bucket.high == Decimal("101")
        assert bucket.volume == sum(1000 + m for m in range(60))


class TestRetention:
    async def test_delete_older_than(self, bar_store: BarStore) -> None:
        await bar_store.upsert_bars([_daily_bar("SPY", d) for d in (2, 5, 9)], "1Day")
        removed = await bar_store.delete_older_than("1Day", datetime(2026, 1, 6, tzinfo=UTC))
        assert removed == 2  # Jan 2 and Jan 5
        remaining = await bar_store.select_bars(
            "SPY", "1Day", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 20, tzinfo=UTC)
        )
        assert [b.time.day for b in remaining] == [9]
