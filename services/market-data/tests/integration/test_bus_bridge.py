"""Integration test: a bar published to the bus reaches a subscribed client.

End-to-end of the consolidated fan-out: EventBus -> BusBridge -> StreamManager
-> per-client queue. Real Redis; real StreamManager (no mocks).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.store.models import BarRow
from src.streaming.bar_events import BAR_STREAM, encode_bar_event
from src.streaming.bus_bridge import BusBridge
from src.streaming.manager import StreamManager

pytestmark = pytest.mark.integration


def _row(symbol: str, close: float) -> BarRow:
    return BarRow(
        symbol=symbol,
        time=datetime(2026, 1, 5, 14, 30, tzinfo=UTC),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal(str(close)),
        volume=1000,
        vwap=None,
        trade_count=None,
    )


async def test_published_bar_reaches_subscribed_client(event_bus) -> None:
    manager = StreamManager()
    queue = await manager.connect(client_id=1)
    await manager.subscribe(1, trades=[], quotes=[], bars=["AAPL"])

    bridge = BusBridge(event_bus, manager)
    await bridge.start()
    try:
        await asyncio.sleep(0.3)  # let the tail loop begin (last_id="$")
        await event_bus.publish(BAR_STREAM, encode_bar_event(_row("AAPL", 150.0)))

        message = await asyncio.wait_for(queue.get(), timeout=3.0)
        assert message.symbol == "AAPL"
        assert float(message.data["close"]) == 150.0
    finally:
        await bridge.stop()


async def test_unsubscribed_symbol_not_delivered(event_bus) -> None:
    manager = StreamManager()
    queue = await manager.connect(client_id=2)
    await manager.subscribe(2, trades=[], quotes=[], bars=["AAPL"])

    bridge = BusBridge(event_bus, manager)
    await bridge.start()
    try:
        await asyncio.sleep(0.3)
        await event_bus.publish(BAR_STREAM, encode_bar_event(_row("TSLA", 200.0)))

        with pytest.raises(TimeoutError):
            await asyncio.wait_for(queue.get(), timeout=1.0)
    finally:
        await bridge.stop()
