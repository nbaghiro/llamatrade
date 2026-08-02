"""BusBridge supervision: a crashed tail loop restarts instead of silently dying."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import cast

from llamatrade_events import BarEvents, EventBus
from llamatrade_events.testing import FakeTransport
from llamatrade_proto.generated import common_pb2, market_data_pb2

from src.streaming.bus_bridge import BusBridge
from src.streaming.manager import StreamManager


def _bar(symbol: str) -> market_data_pb2.Bar:
    return market_data_pb2.Bar(
        symbol=symbol,
        timestamp=common_pb2.Timestamp(
            seconds=int(datetime(2026, 1, 5, 14, 30, tzinfo=UTC).timestamp())
        ),
        open=common_pb2.Decimal(value="100"),
        high=common_pb2.Decimal(value="101"),
        low=common_pb2.Decimal(value="99"),
        close=common_pb2.Decimal(value="150"),
        volume=1000,
    )


class _CrashingBars:
    """Stub BarEvents whose first tail attempt crashes; the second delivers a bar."""

    def __init__(self, bar: market_data_pb2.Bar) -> None:
        self.stream = "market:bars:1m"
        self.calls = 0
        self._bar = bar

    async def tail(
        self, *, from_cursor: str = "$"
    ) -> AsyncIterator[tuple[str, market_data_pb2.Bar]]:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transport blew up")
        yield "0:0", self._bar


async def test_bridge_restarts_tail_after_crash() -> None:
    manager = StreamManager()
    queue = await manager.connect(client_id=1)
    await manager.subscribe(1, trades=[], quotes=[], bars=["AAPL"])

    bridge = BusBridge(EventBus(FakeTransport()), manager, restart_base_delay=0.0)
    bars = _CrashingBars(_bar("AAPL"))
    bridge._bars = cast(BarEvents, bars)

    await bridge.start()
    try:
        message = await asyncio.wait_for(queue.get(), timeout=3.0)
    finally:
        await bridge.stop()

    assert message.symbol == "AAPL"
    assert bars.calls == 2  # crashed once; the supervised restart delivered the bar


async def test_bridge_clean_completion_ends_supervision() -> None:
    bridge = BusBridge(EventBus(FakeTransport()), StreamManager(), restart_base_delay=0.0)
    await bridge.start()
    task = bridge._task
    assert task is not None
    # FakeTransport's tail drains and completes; the supervisor must exit cleanly.
    await asyncio.wait_for(task, timeout=3.0)
    assert task.exception() is None
    await bridge.stop()


async def test_bridge_stop_cancels_running_supervision() -> None:
    class _BlockingBars:
        stream = "market:bars:1m"

        async def tail(
            self, *, from_cursor: str = "$"
        ) -> AsyncIterator[tuple[str, market_data_pb2.Bar]]:
            await asyncio.Event().wait()  # never yields — a live broker tail
            yield "0:0", _bar("AAPL")

    bridge = BusBridge(EventBus(FakeTransport()), StreamManager())
    bridge._bars = cast(BarEvents, _BlockingBars())
    await bridge.start()
    await asyncio.wait_for(bridge.stop(), timeout=3.0)  # cancel must not hang
    assert bridge._task is None
