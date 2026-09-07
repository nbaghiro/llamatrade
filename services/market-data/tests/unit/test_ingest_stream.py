"""Unit tests for the ingest write-through flush (no DB / broker)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

import pytest
from tests.test_metrics import _exposition, _sample

from llamatrade_events import EventBus
from llamatrade_events.testing import FakeTransport

from src.ingest.stream import BarIngestor
from src.store.models import BarRow
from src.store.repository import BarStore

if TYPE_CHECKING:
    from llamatrade_alpaca.streaming import MarketDataStreamClient

_LAG_COUNT = "llamatrade_marketdata_bar_publish_lag_seconds_count"


class FakeStore:
    """Records upsert batch sizes; no database."""

    def __init__(self) -> None:
        self.upserts: list[int] = []

    async def upsert_bars(self, rows: list[BarRow], timeframe: str) -> None:
        self.upserts.append(len(rows))


class FlakyStore:
    """Fails the first ``fail_times`` upserts, then records batches like the DB."""

    def __init__(self, fail_times: int = 0) -> None:
        self.upserts: list[list[BarRow]] = []
        self.fail_times = fail_times

    async def upsert_bars(self, rows: list[BarRow], timeframe: str) -> int:
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("db down")
        self.upserts.append(list(rows))
        return len(rows)


def _payload(ts: datetime) -> dict[str, object]:
    return {
        "timestamp": ts.isoformat(),
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 1000,
    }


async def test_flush_records_publish_lag_per_bar() -> None:
    store = FakeStore()
    ingestor = BarIngestor(cast(BarStore, store), EventBus(FakeTransport()))
    now = datetime.now(UTC)
    await ingestor.handle_bar("AAPL", _payload(now - timedelta(seconds=70)))
    await ingestor.handle_bar("MSFT", _payload(now - timedelta(seconds=65)))

    before = _sample(_exposition(), _LAG_COUNT)
    assert await ingestor.flush() == 2
    after = _sample(_exposition(), _LAG_COUNT)

    assert after == (before or 0.0) + 2.0
    assert store.upserts == [2]


async def test_empty_flush_records_no_lag() -> None:
    ingestor = BarIngestor(cast(BarStore, FakeStore()), EventBus(FakeTransport()))
    before = _sample(_exposition(), _LAG_COUNT)
    assert await ingestor.flush() == 0
    assert _sample(_exposition(), _LAG_COUNT) == before


class TestFlushFailureRestoresBuffer:
    async def test_failed_store_write_requeues_and_retry_writes_once(self) -> None:
        store = FlakyStore(fail_times=1)
        transport = FakeTransport()
        ingestor = BarIngestor(cast(BarStore, store), EventBus(transport))
        now = datetime.now(UTC)
        await ingestor.handle_bar("AAPL", _payload(now - timedelta(seconds=70)))
        await ingestor.handle_bar("MSFT", _payload(now - timedelta(seconds=65)))

        with pytest.raises(RuntimeError):
            await ingestor.flush()
        # Nothing was written or published; both bars are back in the buffer.
        assert store.upserts == []
        assert transport.records == []

        assert await ingestor.flush() == 2
        assert len(store.upserts) == 1
        assert [r.symbol for r in store.upserts[0]] == ["AAPL", "MSFT"]
        assert len(transport.records) == 2  # each bar published exactly once

    async def test_failed_flush_publishes_nothing_and_records_no_lag(self) -> None:
        transport = FakeTransport()
        ingestor = BarIngestor(cast(BarStore, FlakyStore(fail_times=1)), EventBus(transport))
        await ingestor.handle_bar("AAPL", _payload(datetime.now(UTC)))

        before = _sample(_exposition(), _LAG_COUNT)
        with pytest.raises(RuntimeError):
            await ingestor.flush()

        assert _sample(_exposition(), _LAG_COUNT) == before
        assert transport.records == []

    async def test_bars_arriving_after_a_failure_join_the_retry_in_order(self) -> None:
        store = FlakyStore(fail_times=1)
        ingestor = BarIngestor(cast(BarStore, store), EventBus(FakeTransport()))
        now = datetime.now(UTC)
        await ingestor.handle_bar("AAPL", _payload(now - timedelta(seconds=70)))
        with pytest.raises(RuntimeError):
            await ingestor.flush()
        await ingestor.handle_bar("MSFT", _payload(now - timedelta(seconds=65)))

        assert await ingestor.flush() == 2
        assert [r.symbol for r in store.upserts[0]] == ["AAPL", "MSFT"]

    async def test_prolonged_outage_caps_retained_buffer_dropping_oldest(self) -> None:
        store = FlakyStore(fail_times=10_000)
        ingestor = BarIngestor(cast(BarStore, store), EventBus(FakeTransport()), max_buffer=2)
        now = datetime.now(UTC)
        # max_buffer=2 -> retained cap 20; feed 30 bars while the store is down.
        for i in range(30):
            try:
                await ingestor.handle_bar("AAPL", _payload(now + timedelta(minutes=i)))
            except RuntimeError:
                pass

        store.fail_times = 0
        flushed = await ingestor.flush()
        assert flushed == 20
        # The newest bars survive; the oldest were dropped for gap repair to heal.
        times = [r.time for r in store.upserts[0]]
        assert times == sorted(times)
        assert times[-1] == now + timedelta(minutes=29)

    async def test_auto_flush_failure_propagates_but_keeps_the_bars(self) -> None:
        store = FlakyStore(fail_times=1)
        ingestor = BarIngestor(cast(BarStore, store), EventBus(FakeTransport()), max_buffer=2)
        now = datetime.now(UTC)
        await ingestor.handle_bar("AAPL", _payload(now))
        with pytest.raises(RuntimeError):
            await ingestor.handle_bar("MSFT", _payload(now))

        assert await ingestor.flush() == 2
        assert [r.symbol for r in store.upserts[0]] == ["AAPL", "MSFT"]


class TestRunFlushLoop:
    async def test_loop_survives_flush_errors_and_retries(self) -> None:
        """The periodic loop swallows a failed flush; the requeued bars land next tick."""
        store = FlakyStore(fail_times=1)
        ingestor = BarIngestor(cast(BarStore, store), EventBus(FakeTransport()))
        await ingestor.handle_bar("AAPL", _payload(datetime.now(UTC)))

        stop = asyncio.Event()
        task = asyncio.create_task(ingestor.run_flush_loop(interval_s=0.01, stop_event=stop))
        try:

            async def landed() -> None:
                while not store.upserts:
                    await asyncio.sleep(0.005)

            await asyncio.wait_for(landed(), timeout=2.0)
        finally:
            stop.set()
            await asyncio.wait_for(task, timeout=2.0)

        assert store.fail_times == 0  # the first flush did fail inside the loop
        assert [r.symbol for r in store.upserts[0]] == ["AAPL"]

    async def test_cancellation_drains_the_buffer(self) -> None:
        """Shutdown cancels the loop (as the supervisor does); the drain still runs."""
        store = FlakyStore()
        ingestor = BarIngestor(cast(BarStore, store), EventBus(FakeTransport()))
        task = asyncio.create_task(ingestor.run_flush_loop(interval_s=60.0))
        await asyncio.sleep(0)  # let the loop enter its interval sleep
        await ingestor.handle_bar("AAPL", _payload(datetime.now(UTC)))

        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        assert len(store.upserts) == 1  # drained on shutdown despite the long interval
        assert [r.symbol for r in store.upserts[0]] == ["AAPL"]


def test_attach_wires_the_bar_callback() -> None:
    class RecordingStream:
        def __init__(self) -> None:
            self.on_bar: object = None

        def set_callbacks(
            self,
            on_trade: object = None,
            on_quote: object = None,
            on_bar: object = None,
        ) -> None:
            self.on_bar = on_bar

    ingestor = BarIngestor(cast(BarStore, FakeStore()), EventBus(FakeTransport()))
    stream = RecordingStream()
    ingestor.attach(cast("MarketDataStreamClient", stream))
    assert stream.on_bar == ingestor.handle_bar
