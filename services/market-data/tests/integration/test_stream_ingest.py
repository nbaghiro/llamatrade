"""Integration test: stream write-through lands in the store AND the bus.

Real Timescale + real Redis EventBus; only the inbound bar payloads are
synthetic (as they would arrive from the Alpaca WS).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from llamatrade_events import BARS
from llamatrade_proto.generated import market_data_pb2

from src.ingest.stream import BarIngestor
from src.store.repository import BarStore

pytestmark = pytest.mark.integration


def _bar_payload(minute: int) -> dict[str, object]:
    t = datetime(2026, 1, 5, 14, 0, tzinfo=UTC) + timedelta(minutes=minute)
    return {
        "timestamp": t.isoformat(),
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.0 + minute,
        "volume": 1000 + minute,
    }


async def test_bars_land_in_store_and_bus(bar_store: BarStore, event_bus) -> None:
    ingestor = BarIngestor(bar_store, event_bus)

    for minute in range(5):
        await ingestor.handle_bar("AAPL", _bar_payload(minute))
    flushed = await ingestor.flush()
    assert flushed == 5

    # Store side.
    start = datetime(2026, 1, 5, 14, 0, tzinfo=UTC)
    end = datetime(2026, 1, 5, 14, 10, tzinfo=UTC)
    stored = await bar_store.select_bars("AAPL", "1Min", start, end)
    assert len(stored) == 5
    assert stored[-1].close == 104

    # Bus side: 5 raw Bar protos published to the BARS channel, parseable back.
    transport = event_bus.transport
    client = await transport._client()
    entries = await client.xrange(transport.key(BARS.key()))
    assert len(entries) == 5
    _id, raw = entries[0]
    value = raw[b"v"] if b"v" in raw else raw["v"]
    bar = market_data_pb2.Bar.FromString(value)
    assert bar.symbol == "AAPL"
    assert float(bar.close.value) == 100.0


async def test_empty_flush_is_noop(bar_store: BarStore, event_bus) -> None:
    ingestor = BarIngestor(bar_store, event_bus)
    assert await ingestor.flush() == 0


async def test_auto_flush_on_full_buffer(bar_store: BarStore, event_bus) -> None:
    ingestor = BarIngestor(bar_store, event_bus, max_buffer=3)
    for minute in range(3):
        await ingestor.handle_bar("MSFT", _bar_payload(minute))
    # Buffer hit capacity -> auto-flushed already.
    start = datetime(2026, 1, 5, 14, 0, tzinfo=UTC)
    end = datetime(2026, 1, 5, 14, 10, tzinfo=UTC)
    assert len(await bar_store.select_bars("MSFT", "1Min", start, end)) == 3
