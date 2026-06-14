"""Integration tests for the backfill controller (real Timescale + fake Alpaca)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from tests.fakes import FakeMarketDataClient

from src.ingest.backfill import BackfillController
from src.models import Timeframe
from src.store.models import bar_row_from_alpaca
from src.store.repository import BarStore

pytestmark = pytest.mark.integration

# Fixed historical "now" so windows are deterministic; 6-hour minute lookback to
# keep the generated bar count small and the test fast.
NOW = datetime(2026, 1, 5, 20, 0, tzinfo=UTC)
_SIX_HOURS_MIN = 6 * 60


def _controller(store: BarStore, alpaca: FakeMarketDataClient) -> BackfillController:
    return BackfillController(
        store,
        alpaca,
        timeframes=("1Min",),
        lookback_for={"1Min": 0.25},  # 6 hours
        max_concurrency=2,
    )


def _window_bounds() -> tuple[datetime, datetime]:
    return (NOW - timedelta(hours=6), NOW)


class TestBackfill:
    async def test_fills_empty_store_for_window(self, bar_store: BarStore) -> None:
        alpaca = FakeMarketDataClient()
        controller = _controller(bar_store, alpaca)

        result = await controller.run(["AAPL"], NOW)
        assert result["AAPL"] > 0

        start, end = _window_bounds()
        stored = await bar_store.select_bars("AAPL", "1Min", start, end)
        assert len(stored) == _SIX_HOURS_MIN  # one bar per minute over 6h

    async def test_is_idempotent_no_duplicates(self, bar_store: BarStore) -> None:
        alpaca = FakeMarketDataClient()
        controller = _controller(bar_store, alpaca)

        await controller.run(["AAPL"], NOW)
        start, end = _window_bounds()
        count_after_first = len(await bar_store.select_bars("AAPL", "1Min", start, end))

        await controller.run(["AAPL"], NOW)
        count_after_second = len(await bar_store.select_bars("AAPL", "1Min", start, end))

        assert count_after_second == count_after_first  # upsert, no dupes

    async def test_fetches_only_missing_ranges(self, bar_store: BarStore) -> None:
        # Pre-seed the first 2 hours; backfill should fetch only the remaining 4h.
        seed = FakeMarketDataClient()
        start, end = _window_bounds()
        seeded = await seed.get_bars("AAPL", Timeframe.MINUTE_1, start, start + timedelta(hours=2))
        await bar_store.upsert_bars([bar_row_from_alpaca("AAPL", b) for b in seeded], "1Min")

        alpaca = FakeMarketDataClient()
        controller = _controller(bar_store, alpaca)
        await controller.run(["AAPL"], NOW)

        # Alpaca was asked only for the trailing gap, not the seeded prefix.
        assert len(alpaca.calls) == 1
        _, fetch_start, _ = alpaca.calls[0]
        assert fetch_start >= start + timedelta(hours=2) - timedelta(minutes=1)

        stored = await bar_store.select_bars("AAPL", "1Min", start, end)
        assert len(stored) == _SIX_HOURS_MIN

    async def test_multi_symbol(self, bar_store: BarStore) -> None:
        alpaca = FakeMarketDataClient()
        controller = _controller(bar_store, alpaca)
        result = await controller.run(["AAPL", "MSFT", "TSLA"], NOW)
        assert set(result) == {"AAPL", "MSFT", "TSLA"}
        for sym in ("AAPL", "MSFT", "TSLA"):
            start, end = _window_bounds()
            assert len(await bar_store.select_bars(sym, "1Min", start, end)) == _SIX_HOURS_MIN
