"""Integration tests for the store-first read path (real Timescale, fake Alpaca).

Proves the serving layer reads from the store, hits Alpaca only for gaps, writes
closed bars back, and then serves subsequent reads locally.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from tests.fakes import FakeMarketDataClient

from llamatrade_alpaca import MarketDataClient

from src.models import Timeframe
from src.services.market_data_service import MarketDataService
from src.store.repository import BarStore

pytestmark = pytest.mark.integration

# A fully historical window so the "forming bar" guard and `now` don't intrude.
START = datetime(2026, 1, 5, 14, 0, tzinfo=UTC)
END = datetime(2026, 1, 5, 15, 0, tzinfo=UTC)  # 60 one-minute bars


async def _service(bar_store: BarStore, alpaca: FakeMarketDataClient) -> MarketDataService:
    # One typed seam: the fake mirrors the MarketDataClient surface the service uses.
    return MarketDataService(alpaca=cast(MarketDataClient, alpaca), cache=None, store=bar_store)


class TestStoreFirstReads:
    async def test_cold_store_fetches_all_then_serves_from_store(self, bar_store: BarStore) -> None:
        alpaca = FakeMarketDataClient()
        svc = await _service(bar_store, alpaca)

        # Cold: store empty -> one gap [START, END) -> fetched from Alpaca + stored.
        first = await svc.get_bars("AAPL", Timeframe.MINUTE_1, START, END)
        assert len(first) == 60
        assert len(alpaca.calls) == 1
        assert alpaca.adjustments == ["raw"]  # intraday gap fetches stay unadjusted

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
        assert alpaca.adjustments == ["raw", "raw"]

    async def test_daily_gap_fetch_requests_split_adjustment(self, bar_store: BarStore) -> None:
        alpaca = FakeMarketDataClient()
        svc = await _service(bar_store, alpaca)

        day_start = datetime(2026, 1, 5, tzinfo=UTC)
        day_end = datetime(2026, 1, 10, tzinfo=UTC)
        bars = await svc.get_bars("AAPL", Timeframe.DAY_1, day_start, day_end)

        assert len(bars) == 5
        # Daily bars are the split-adjusted base; the gap fetch must match.
        assert alpaca.adjustments == ["split"]

    async def test_refresh_bypasses_store(self, bar_store: BarStore) -> None:
        alpaca = FakeMarketDataClient()
        svc = await _service(bar_store, alpaca)

        await svc.get_bars("AAPL", Timeframe.MINUTE_1, START, END)  # warms store
        alpaca.calls.clear()

        # refresh=True must skip the store entirely and hit Alpaca for the full range.
        out = await svc.get_bars("AAPL", Timeframe.MINUTE_1, START, END, refresh=True)
        assert len(out) == 60
        assert alpaca.calls == [("AAPL", START, END)]

    async def test_multi_bars_per_symbol_read_through(self, bar_store: BarStore) -> None:
        alpaca = FakeMarketDataClient()
        svc = await _service(bar_store, alpaca)

        result = await svc.get_multi_bars(["AAPL", "MSFT"], Timeframe.MINUTE_1, START, END)
        assert set(result) == {"AAPL", "MSFT"}
        assert len(result["AAPL"]) == 60 and len(result["MSFT"]) == 60

        # Second call served from store -> no new single-symbol Alpaca fetches.
        before = len(alpaca.calls)
        await svc.get_multi_bars(["AAPL", "MSFT"], Timeframe.MINUTE_1, START, END)
        assert len(alpaca.calls) == before


class TestFormingBarGuard:
    async def test_forming_bar_served_but_not_persisted(
        self, bar_store: BarStore, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Pin "now" so the closed boundary (now - 1min) is exact: the gap fetch
        # returns bars both inside the boundary and the forming bar at now-1min.
        now = datetime(2026, 1, 5, 15, 0, tzinfo=UTC)
        monkeypatch.setattr("src.services.market_data_service._utcnow", lambda: now)

        alpaca = FakeMarketDataClient()
        svc = await _service(bar_store, alpaca)

        start = now - timedelta(minutes=10)
        out = await svc.get_bars("LIVE", Timeframe.MINUTE_1, start, None)

        # The read serves the whole window, forming bar (now-1min) included.
        forming_ts = now - timedelta(minutes=1)
        assert [b.timestamp for b in out] == [start + timedelta(minutes=k) for k in range(10)]
        assert out[-1].timestamp == forming_ts

        # The write-back persisted only bars strictly before the closed boundary.
        stored = await bar_store.select_bars("LIVE", "1Min", start, now + timedelta(minutes=1))
        assert [b.time for b in stored] == [start + timedelta(minutes=k) for k in range(9)]
        assert forming_ts not in {b.time for b in stored}
