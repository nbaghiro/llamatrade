"""Unit tests for the ingest write-through flush metrics (no DB / broker)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

from tests.test_metrics import _exposition, _sample

from llamatrade_events import EventBus
from llamatrade_events.testing import FakeTransport

from src.ingest.stream import BarIngestor
from src.store.models import BarRow
from src.store.repository import BarStore

_LAG_COUNT = "llamatrade_marketdata_bar_publish_lag_seconds_count"


class FakeStore:
    """Records upsert batch sizes; no database."""

    def __init__(self) -> None:
        self.upserts: list[int] = []

    async def upsert_bars(self, rows: list[BarRow], timeframe: str) -> None:
        self.upserts.append(len(rows))


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
