"""BusBridge supervision: a crashed tail loop restarts instead of silently dying."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import cast

import pytest

from llamatrade_events import BarEvents, EventBus
from llamatrade_events.testing import FakeTransport
from llamatrade_proto.generated import common_pb2, market_data_pb2
from tests.test_metrics import _exposition, _sample

from src.models import BarData
from src.streaming import bus_bridge as bus_bridge_module
from src.streaming.bus_bridge import BusBridge
from src.streaming.manager import StreamManager

_REAL_SLEEP = asyncio.sleep


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


async def test_bridge_records_fanout_lag_on_hand_off() -> None:
    manager = StreamManager()
    queue = await manager.connect(client_id=1)
    await manager.subscribe(1, trades=[], quotes=[], bars=["AAPL"])

    class _OneBar:
        stream = "market:bars:1m"

        async def tail(
            self, *, from_cursor: str = "$"
        ) -> AsyncIterator[tuple[str, market_data_pb2.Bar]]:
            yield "0:0", _bar("AAPL")

    bridge = BusBridge(EventBus(FakeTransport()), manager)
    bridge._bars = cast(BarEvents, _OneBar())

    name = "llamatrade_marketdata_bar_fanout_lag_seconds_count"
    before = _sample(_exposition(), name)
    await bridge.start()
    try:
        await asyncio.wait_for(queue.get(), timeout=3.0)
    finally:
        await bridge.stop()

    assert _sample(_exposition(), name) == (before or 0.0) + 1.0


async def test_bridge_clean_completion_ends_supervision() -> None:
    bridge = BusBridge(EventBus(FakeTransport()), StreamManager(), restart_base_delay=0.0)
    await bridge.start()
    task = bridge._task
    assert task is not None
    # FakeTransport's tail drains and completes; the supervisor must exit cleanly.
    await asyncio.wait_for(task, timeout=3.0)
    assert task.exception() is None
    await bridge.stop()


class _CrashNTimesBars:
    """Stub BarEvents: crashes ``crashes`` times, then blocks like a live tail."""

    def __init__(self, crashes: int, *, pre_crash_delay: float = 0.0) -> None:
        self.stream = "market:bars:1m"
        self.calls = 0
        self._crashes = crashes
        self._pre_crash_delay = pre_crash_delay

    async def tail(
        self, *, from_cursor: str = "$"
    ) -> AsyncIterator[tuple[str, market_data_pb2.Bar]]:
        self.calls += 1
        if self._pre_crash_delay:
            await _REAL_SLEEP(self._pre_crash_delay)
        if self.calls <= self._crashes:
            raise RuntimeError("transport blew up")
        await asyncio.Event().wait()
        yield "0:0", _bar("AAPL")


@pytest.fixture
def recorded_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace asyncio.sleep with an instant recording fake (restart delays only)."""
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)
        await _REAL_SLEEP(0)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return delays


class TestRestartBackoff:
    async def test_delay_doubles_and_caps(self, recorded_sleeps: list[float]) -> None:
        bars = _CrashNTimesBars(crashes=4)
        bridge = BusBridge(
            EventBus(FakeTransport()),
            StreamManager(),
            restart_base_delay=1.0,
            restart_max_delay=4.0,
        )
        bridge._bars = cast(BarEvents, bars)

        await bridge.start()
        try:

            async def settled() -> None:
                while bars.calls < 5:
                    await _REAL_SLEEP(0.005)

            await asyncio.wait_for(settled(), timeout=3.0)
        finally:
            await bridge.stop()

        assert recorded_sleeps == [1.0, 2.0, 4.0, 4.0]  # doubled, then capped

    async def test_steady_run_resets_the_delay(
        self, recorded_sleeps: list[float], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(bus_bridge_module, "_STEADY_RUN_SECONDS", 0.05)

        class _SteadyThenCrashBars(_CrashNTimesBars):
            """Two fast crashes, one steady run that crashes, then blocks."""

            async def tail(
                self, *, from_cursor: str = "$"
            ) -> AsyncIterator[tuple[str, market_data_pb2.Bar]]:
                self.calls += 1
                if self.calls <= 2:
                    raise RuntimeError("fast crash")
                if self.calls == 3:
                    await _REAL_SLEEP(0.06)  # outlives the steady-run threshold
                    raise RuntimeError("late crash")
                await asyncio.Event().wait()
                yield "0:0", _bar("AAPL")

        bars = _SteadyThenCrashBars(crashes=0)
        bridge = BusBridge(
            EventBus(FakeTransport()),
            StreamManager(),
            restart_base_delay=1.0,
            restart_max_delay=8.0,
        )
        bridge._bars = cast(BarEvents, bars)

        await bridge.start()
        try:

            async def settled() -> None:
                while bars.calls < 4:
                    await _REAL_SLEEP(0.005)

            await asyncio.wait_for(settled(), timeout=3.0)
        finally:
            await bridge.stop()

        # Two escalating delays, then the steady run resets to the base delay.
        assert recorded_sleeps == [1.0, 2.0, 1.0]


class TestPerBarRouteFailure:
    async def test_one_bad_bar_does_not_stop_the_tail(self) -> None:
        class _TwoBars:
            stream = "market:bars:1m"
            calls = 0

            async def tail(
                self, *, from_cursor: str = "$"
            ) -> AsyncIterator[tuple[str, market_data_pb2.Bar]]:
                type(self).calls += 1
                yield "0:0", _bar("AAPL")
                yield "0:1", _bar("MSFT")
                await asyncio.Event().wait()

        class _FlakyManager:
            def __init__(self) -> None:
                self.received: list[str] = []

            async def broadcast_bar(self, symbol: str, data: BarData) -> None:
                if symbol == "AAPL":
                    raise RuntimeError("broadcast blew up")
                self.received.append(symbol)

        manager = _FlakyManager()
        bars = _TwoBars()
        bridge = BusBridge(EventBus(FakeTransport()), cast(StreamManager, manager))
        bridge._bars = cast(BarEvents, bars)

        await bridge.start()
        try:

            async def settled() -> None:
                while not manager.received:
                    await _REAL_SLEEP(0.005)

            await asyncio.wait_for(settled(), timeout=3.0)
        finally:
            await bridge.stop()

        assert manager.received == ["MSFT"]  # the bad bar was swallowed, not fatal
        assert bars.calls == 1  # the tail loop never restarted


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
