"""Integration tests: gap repair fills interior holes; corporate-action refresh
overwrites stale adjusted daily bars. Real Timescale + fake Alpaca."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from tests.fakes import FakeMarketDataClient

from src.ingest.backfill import BackfillController
from src.ingest.corporate_actions import CorporateActionRefresher
from src.ingest.gaps import GapRepairer
from src.store.models import BarRow
from src.store.repository import BarStore

pytestmark = pytest.mark.integration


def _minute_row(minute: int, close: float = 100.0) -> BarRow:
    return BarRow(
        symbol="AAPL",
        time=datetime(2026, 1, 5, 14, 0, tzinfo=UTC) + timedelta(minutes=minute),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal(str(close)),
        volume=1000,
        vwap=None,
        trade_count=None,
    )


class TestGapRepair:
    async def test_fills_interior_hole(self, bar_store: BarStore) -> None:
        # Seed minutes 0,1,2,5,6,7,8,9 — a hole at minutes 3 and 4.
        present = [0, 1, 2, 5, 6, 7, 8, 9]
        await bar_store.upsert_bars([_minute_row(m) for m in present], "1Min")

        alpaca = FakeMarketDataClient()
        controller = BackfillController(
            bar_store, alpaca, timeframes=("1Min",), lookback_for={"1Min": 0.02}
        )
        repairer = GapRepairer(
            controller,
            step=timedelta(minutes=1),
            max_gap=timedelta(hours=4),
            recent_lookback_days=0.02,  # ~28 min window around the data
        )
        now = datetime(2026, 1, 5, 14, 10, tzinfo=UTC)
        await repairer.repair(["AAPL"], "1Min", now)

        start = datetime(2026, 1, 5, 14, 0, tzinfo=UTC)
        end = datetime(2026, 1, 5, 14, 10, tzinfo=UTC)
        stored = {b.time.minute for b in await bar_store.select_bars("AAPL", "1Min", start, end)}
        # The previously-missing minutes are now present.
        assert {3, 4}.issubset(stored)


class TestCorporateActionRefresh:
    async def test_overwrites_stale_adjusted_daily(self, bar_store: BarStore) -> None:
        # Seed a stale daily close that an adjustment would change.
        stale = BarRow(
            symbol="AAPL",
            time=datetime(2026, 1, 5, tzinfo=UTC),
            open=Decimal("100"),
            high=Decimal("100"),
            low=Decimal("100"),
            close=Decimal("999"),  # clearly wrong / pre-split
            volume=1,
            vwap=None,
            trade_count=None,
        )
        await bar_store.upsert_bars([stale], "1Day")

        alpaca = FakeMarketDataClient()  # returns close = 100 + idx for the window
        refresher = CorporateActionRefresher(bar_store, alpaca, window_days=10)
        now = datetime(2026, 1, 10, tzinfo=UTC)
        written = await refresher.refresh(["AAPL"], now)
        assert written > 0

        got = await bar_store.select_bars(
            "AAPL", "1Day", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 6, tzinfo=UTC)
        )
        jan5 = next(b for b in got if b.time.day == 5)
        assert jan5.close != Decimal("999")  # overwritten with fresh adjusted value
