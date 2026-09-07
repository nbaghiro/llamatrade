"""Trade-stream supervisor: give-up detection, backoff, rebuild, terminal exit.

Fills are the source of truth for positions, so ``_trade_stream_loop`` must
treat a stream that ends (the real client's reconnect give-up) as a fault:
alert, back off with doubling, rebuild the client, resume. These tests drive
the loop with ``MockTradeStream``'s give-up mode (which reproduces the real
generator's exhaustion semantics) and assert observable outcomes: processed
fills, alerts, exposition metrics, and recorded backoff delays.
"""

import asyncio
import contextlib
from decimal import Decimal
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from llamatrade_alpaca import MockBarStream, MockTradeStream
from tests.metrics_util import sample_metric
from tests.sessions import quiet_session

import src.runner.runner as runner_module
from src.runner.runner import RunnerConfig, StrategyRunner
from src.services.alert_service import AlertService


async def _shut_down(runner: StrategyRunner, task: asyncio.Task[None]) -> None:
    """End the supervisor loop; the mock stream may swallow the cancel and exit cleanly."""
    runner._running = False
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def _wait_for(predicate, timeout: float = 2.0) -> None:
    async def _poll() -> None:
        while not predicate():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(_poll(), timeout=timeout)


class _RecordingSleep:
    """Replacement for the runner module's ``asyncio.sleep`` that records delays."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    def __getattr__(self, name: str):
        return getattr(asyncio, name)

    async def sleep(self, delay: float) -> None:
        self.delays.append(delay)
        await asyncio.sleep(0)


class _RefusingTradeStream(MockTradeStream):
    """A trade stream whose reconnect attempts fail a configured number of times."""

    def __init__(self, connect_failures: int = 0, subscribe_failures: int = 0) -> None:
        super().__init__()
        self._connect_failures = connect_failures
        self._subscribe_failures = subscribe_failures

    async def connect(self) -> bool:
        if self._connect_failures > 0:
            self._connect_failures -= 1
            return False
        return await super().connect()

    async def subscribe(self) -> bool:
        if self._subscribe_failures > 0:
            self._subscribe_failures -= 1
            return False
        return await super().subscribe()


def _make_runner(
    trade_stream: MockTradeStream,
    alerts: AsyncMock | None = None,
    trade_stream_factory=None,
) -> StrategyRunner:
    config = RunnerConfig(
        tenant_id=uuid4(),
        execution_id=uuid4(),
        strategy_id=uuid4(),
        symbols=["AAPL"],
        timeframe="1Min",
        warmup_bars=5,
        enforce_trading_hours=False,
    )
    executor = AsyncMock()
    risk = AsyncMock()
    return StrategyRunner(
        config=config,
        session=quiet_session(),
        bar_stream=MockBarStream(bars={}),
        trade_stream=trade_stream,
        order_executor=executor,
        risk_manager=risk,
        alert_service=cast(AlertService, alerts) if alerts is not None else None,
        trade_stream_factory=trade_stream_factory,
    )


@pytest.fixture
def recorded_sleep(monkeypatch: pytest.MonkeyPatch) -> _RecordingSleep:
    shim = _RecordingSleep()
    monkeypatch.setattr(runner_module, "asyncio", shim)
    return shim


class TestTradeStreamSupervisor:
    async def test_give_up_alerts_backs_off_rebuilds_and_resumes_fills(
        self, recorded_sleep: _RecordingSleep
    ):
        """A mid-session give-up produces the connection-lost alert, a restart
        with backoff, and a reconnected stream that processes fresh fills."""
        stream = MockTradeStream()
        alerts = AsyncMock(spec=AlertService)
        runner = _make_runner(stream, alerts=alerts)
        runner._running = True
        await stream.connect()

        exhausted_before = sample_metric(
            "llamatrade_trading_strategy_errors_total", error_type="trade_stream_exhausted"
        )

        task = asyncio.create_task(runner._trade_stream_loop())
        try:
            stream.add_fill(
                "o-1", "AAPL", "buy", Decimal("10"), Decimal("150"), client_order_id="o-1"
            )
            await _wait_for(lambda: runner._fills_processed == 1)

            stream.give_up()
            await _wait_for(lambda: stream.connected)

            assert (
                sample_metric(
                    "llamatrade_trading_strategy_errors_total",
                    error_type="trade_stream_exhausted",
                )
                == exhausted_before + 1
            )
            alerts.on_connection_lost.assert_awaited_once_with(
                tenant_id=runner.config.tenant_id,
                session_id=runner.config.execution_id,
                service="trade_stream",
            )
            assert recorded_sleep.delays[0] == 1.0

            stream.add_fill(
                "o-2", "AAPL", "buy", Decimal("5"), Decimal("151"), client_order_id="o-2"
            )
            await _wait_for(lambda: runner._fills_processed == 2)
            assert runner.positions["AAPL"].quantity == Decimal("15")
        finally:
            await _shut_down(runner, task)

    async def test_backoff_doubles_across_consecutive_give_ups_and_caps(
        self, recorded_sleep: _RecordingSleep, monkeypatch: pytest.MonkeyPatch
    ):
        """Persistent reconnect failure doubles the restart delay up to the cap."""
        monkeypatch.setattr(runner_module, "_TRADE_STREAM_RESTART_MAX_DELAY_S", 4.0)
        stream = _RefusingTradeStream(connect_failures=10)
        runner = _make_runner(stream)
        runner._running = True
        stream.give_up()

        task = asyncio.create_task(runner._trade_stream_loop())
        try:
            await _wait_for(lambda: len(recorded_sleep.delays) >= 5)
        finally:
            await _shut_down(runner, task)

        assert recorded_sleep.delays[:5] == [1.0, 2.0, 4.0, 4.0, 4.0]

    async def test_healthy_event_resets_backoff(self, recorded_sleep: _RecordingSleep):
        """After a successful rebuild delivers an event, the next give-up backs
        off from the base delay again rather than continuing to double."""
        stream = MockTradeStream()
        runner = _make_runner(stream)
        runner._running = True
        await stream.connect()

        task = asyncio.create_task(runner._trade_stream_loop())
        try:
            stream.give_up()
            await _wait_for(lambda: stream.connected)
            stream.add_fill(
                "o-1", "AAPL", "buy", Decimal("1"), Decimal("100"), client_order_id="o-1"
            )
            await _wait_for(lambda: runner._fills_processed == 1)

            stream.give_up()
            await _wait_for(lambda: len(recorded_sleep.delays) >= 2)
        finally:
            await _shut_down(runner, task)

        assert recorded_sleep.delays[0] == 1.0
        assert recorded_sleep.delays[1] == 1.0

    async def test_factory_rebuild_replaces_the_client(self, recorded_sleep: _RecordingSleep):
        """With a factory, the rebuild swaps in a fresh client and disconnects
        the exhausted one; fills flow from the replacement."""
        original = MockTradeStream()
        replacement = MockTradeStream()
        factory_calls: list[int] = []

        def factory() -> MockTradeStream:
            factory_calls.append(1)
            return replacement

        runner = _make_runner(original, trade_stream_factory=factory)
        runner._running = True
        await original.connect()

        task = asyncio.create_task(runner._trade_stream_loop())
        try:
            original.give_up()
            await _wait_for(lambda: runner.trade_stream is replacement)
            assert factory_calls == [1]
            assert replacement.connected
            assert replacement.subscribed
            assert not original.connected

            replacement.add_fill(
                "o-9", "AAPL", "buy", Decimal("2"), Decimal("99"), client_order_id="o-9"
            )
            await _wait_for(lambda: runner._fills_processed == 1)
        finally:
            await _shut_down(runner, task)

    async def test_stop_after_give_up_is_terminal(self, recorded_sleep: _RecordingSleep):
        """A give-up on a stopping runner ends the loop without alert or restart."""
        stream = MockTradeStream()
        alerts = AsyncMock(spec=AlertService)
        runner = _make_runner(stream, alerts=alerts)
        runner._running = True
        await stream.connect()

        task = asyncio.create_task(runner._trade_stream_loop())
        try:
            stream.add_fill(
                "o-1", "AAPL", "buy", Decimal("1"), Decimal("100"), client_order_id="o-1"
            )
            await _wait_for(lambda: runner._fills_processed == 1)

            runner._running = False
            stream.give_up()
            await asyncio.wait_for(task, timeout=2.0)
        finally:
            if not task.done():
                task.cancel()

        alerts.on_connection_lost.assert_not_awaited()
        assert not stream.connected

    async def test_rebuild_retries_when_resubscribe_fails(self, recorded_sleep: _RecordingSleep):
        """A failed re-subscribe is retried on the next supervisor pass."""
        stream = _RefusingTradeStream(subscribe_failures=1)
        runner = _make_runner(stream)
        runner._running = True
        await stream.connect()

        task = asyncio.create_task(runner._trade_stream_loop())
        try:
            stream.give_up()
            await _wait_for(
                lambda: (
                    len(recorded_sleep.delays) >= 1 and stream.connected and not stream.subscribed
                )
            )

            stream.give_up()
            await _wait_for(lambda: stream.subscribed)
            assert len(recorded_sleep.delays) >= 2

            stream.add_fill(
                "o-1", "AAPL", "buy", Decimal("1"), Decimal("100"), client_order_id="o-1"
            )
            await _wait_for(lambda: runner._fills_processed == 1)
        finally:
            await _shut_down(runner, task)

    async def test_rebuild_survives_a_raising_factory(self, recorded_sleep: _RecordingSleep):
        """A factory that raises is contained; the supervisor keeps retrying."""
        stream = MockTradeStream()
        attempts: list[int] = []

        def flaky_factory() -> MockTradeStream:
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("factory down")
            return stream

        initial = MockTradeStream()
        runner = _make_runner(initial, trade_stream_factory=flaky_factory)
        runner._running = True
        await initial.connect()

        task = asyncio.create_task(runner._trade_stream_loop())
        try:
            initial.give_up()
            await _wait_for(lambda: len(attempts) >= 2 and runner.trade_stream is stream)
            stream.add_fill(
                "o-1", "AAPL", "buy", Decimal("1"), Decimal("100"), client_order_id="o-1"
            )
            await _wait_for(lambda: runner._fills_processed == 1)
        finally:
            await _shut_down(runner, task)

    async def test_fill_handler_error_does_not_end_the_loop(
        self, recorded_sleep: _RecordingSleep, monkeypatch: pytest.MonkeyPatch
    ):
        """An exception in per-event handling is contained; the stream keeps flowing."""
        stream = MockTradeStream()
        runner = _make_runner(stream)
        runner._running = True
        await stream.connect()

        original_handler = runner._handle_trade_event
        calls: list[str] = []

        async def flaky_handler(event) -> None:
            calls.append(event.order_id)
            if len(calls) == 1:
                raise RuntimeError("handler blew up")
            await original_handler(event)

        monkeypatch.setattr(runner, "_handle_trade_event", flaky_handler)

        task = asyncio.create_task(runner._trade_stream_loop())
        try:
            stream.add_fill(
                "o-1", "AAPL", "buy", Decimal("1"), Decimal("100"), client_order_id="o-1"
            )
            stream.add_fill(
                "o-2", "AAPL", "buy", Decimal("2"), Decimal("100"), client_order_id="o-2"
            )
            await _wait_for(lambda: runner._fills_processed == 1)
        finally:
            await _shut_down(runner, task)

        assert calls == ["o-1", "o-2"]
