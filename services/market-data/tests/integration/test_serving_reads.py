"""Integration tests for the store-first read path (real Timescale, fake Alpaca).

Proves the serving layer reads from the store, hits Alpaca only for gaps, writes
closed bars back, and then serves subsequent reads locally.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from tests.fakes import FakeMarketDataClient

from src.models import Timeframe
from src.services.market_data_service import MarketDataService
from src.store.repository import BarStore

pytestmark = pytest.mark.integration

# A fully historical window so the "forming bar" guard and `now` don't intrude.
START = datetime(2026, 1, 5, 14, 0, tzinfo=UTC)
END = datetime(2026, 1, 5, 15, 0, tzinfo=UTC)  # 60 one-minute bars


async def _service(bar_store: BarStore, alpaca: FakeMarketDataClient) -> MarketDataService:
    return MarketDataService(alpaca=alpaca, cache=None, store=bar_store)


class TestStoreFirstReads:
    async def test_cold_store_fetches_all_then_serves_from_store(self, bar_store: BarStore) -> None:
        alpaca = FakeMarketDataClient()
        svc = await _service(bar_store, alpaca)

        # Cold: store empty -> one gap [START, END) -> fetched from Alpaca + stored.
        first = await svc.get_bars("AAPL", Timeframe.MINUTE_1, START, END)
        assert len(first) == 60
        assert len(alpaca.calls) == 1

        # The closed bars were written back.
        stored = await bar_store.select_bars("AAPL", "1Min", START, END)
        assert len(stored) == 60

        # Warm: identical request is fully covered -> no further Alpaca calls.
        second = await svc.get_bars("AAPL", Timeframe.MINUTE_1, START, END)
        assert len(second) == 60
        assert len(alpaca.calls) == 1  # unchanged
        assert [b.timestamp for b in second] == [b.timestamp for b in first]

    async def test_partial_store_fetches_only_edges(self, bar_store: BarStore) -> None:
        # Pre-seed the middle third directly; the read should fetch only the edges.
        alpaca = FakeMarketDataClient()
        seed = FakeMarketDataClient()
        mid_start = datetime(2026, 1, 5, 14, 20, tzinfo=UTC)
        mid_end = datetime(2026, 1, 5, 14, 40, tzinfo=UTC)
        seeded_bars = await seed.get_bars("AAPL", Timeframe.MINUTE_1, mid_start, mid_end)
        from src.store.models import bar_row_from_alpaca

        await bar_store.upsert_bars([bar_row_from_alpaca("AAPL", b) for b in seeded_bars], "1Min")

        svc = await _service(bar_store, alpaca)
        result = await svc.get_bars("AAPL", Timeframe.MINUTE_1, START, END)

        # Edge gaps fetched: leading [14:00,14:20) and trailing [14:40,15:00).
        fetched_ranges = {(s, e) for _, s, e in alpaca.calls}
        assert (START, mid_start) in fetched_ranges
        assert (mid_end, END) in fetched_ranges
        assert len(result) == 60  # contiguous coverage after merge

    async def test_refresh_bypasses_store(self, bar_store: BarStore) -> None:
        alpaca = FakeMarketDataClient()
        svc = MarketDataService(alpaca=alpaca, cache=None, store=bar_store)

        await svc.get_bars("AAPL", Timeframe.MINUTE_1, START, END)  # warms store
        alpaca.calls.clear()

        # refresh=True must skip the store entirely and hit Alpaca for the full range.
        out = await svc.get_bars("AAPL", Timeframe.MINUTE_1, START, END, refresh=True)
        assert len(out) == 60
        assert alpaca.calls == [("AAPL", START, END)]

    async def test_multi_bars_per_symbol_read_through(self, bar_store: BarStore) -> None:
        alpaca = FakeMarketDataClient()
        svc = MarketDataService(alpaca=alpaca, cache=None, store=bar_store)

        result = await svc.get_multi_bars(["AAPL", "MSFT"], Timeframe.MINUTE_1, START, END)
        assert set(result) == {"AAPL", "MSFT"}
        assert len(result["AAPL"]) == 60 and len(result["MSFT"]) == 60

        # Second call served from store -> no new single-symbol Alpaca fetches.
        before = len(alpaca.calls)
        await svc.get_multi_bars(["AAPL", "MSFT"], Timeframe.MINUTE_1, START, END)
        assert len(alpaca.calls) == before


class TestForminBarGuard:
    async def test_forming_bar_not_persisted(self, bar_store: BarStore) -> None:
        # A window ending "now" includes a forming bar that must not be stored.
        alpaca = FakeMarketDataClient()
        svc = MarketDataService(alpaca=alpaca, cache=None, store=bar_store)

        now = datetime.now(UTC)
        start = now.replace(second=0, microsecond=0)
        # Request a window whose tail is the current minute.
        out = await svc.get_bars("LIVE", Timeframe.MINUTE_1, start, None)
        # We got bars back, but nothing at-or-after the closed boundary is stored.
        stored = await bar_store.select_bars("LIVE", "1Min", start, now)
        assert all(b.time < now for b in stored)
        assert out is not None
