"""Runner lifecycle: start/stop end to end, manager wiring, and signal/fill edges.

Covers ``start()`` including the stream-connect-failure alert branches and the
``finally`` teardown, ``stop()``, ``RunnerManager.start_runner``, averaging-up
arithmetic on fills, sub-notional signal skips, circuit-breaker signal
rejection, and the portfolio-cache invalidation after a terminal fill.
"""

import asyncio
import contextlib
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from llamatrade_alpaca import (
    FillData,
    MockBarStream,
    MockTradeStream,
    TradeEvent,
    TradeEventType,
    TradingClient,
)
from llamatrade_alpaca import StreamBar as BarData
from tests.metrics_util import sample_metric
from tests.sessions import quiet_session

from src.circuit_breaker import CircuitBreakerConfig
from src.clients.portfolio_client import PortfolioLedgerClient
from src.models import RiskCheckResult
from src.runner.runner import RunnerConfig, RunnerManager, RunnerPosition, Signal, StrategyRunner
from src.services.alert_service import AlertService
from src.streaming.publisher import TradingEventPublisher

SLEEVE_ID = UUID("88888888-8888-8888-8888-888888888888")
ACCOUNT_ID = UUID("99999999-9999-9999-9999-999999999999")


def _config(**overrides) -> RunnerConfig:
    defaults = {
        "tenant_id": uuid4(),
        "execution_id": uuid4(),
        "strategy_id": uuid4(),
        "symbols": ["AAPL"],
        "timeframe": "1Min",
        "warmup_bars": 100,
        "enforce_trading_hours": False,
    }
    defaults.update(overrides)
    return RunnerConfig(**defaults)


def _bars(count: int) -> list[BarData]:
    base = datetime(2024, 1, 15, 15, 0, tzinfo=UTC)
    return [
        BarData(
            symbol="AAPL",
            timestamp=base.replace(minute=i),
            open=150.0,
            high=151.0,
            low=149.0,
            close=150.5,
            volume=1000,
        )
        for i in range(count)
    ]


def _fill_event(
    order_id: str,
    side: Literal["buy", "sell"],
    qty: Decimal,
    price: Decimal,
    symbol: str = "AAPL",
    event_type: TradeEventType = TradeEventType.FILL,
) -> TradeEvent:
    now = datetime.now(UTC)
    fill = FillData(
        order_id=order_id,
        client_order_id=order_id,
        symbol=symbol,
        side=side,
        fill_qty=qty,
        fill_price=price,
        total_filled_qty=qty,
        remaining_qty=Decimal("0"),
        timestamp=now,
    )
    return TradeEvent(
        event_type=event_type,
        order_id=order_id,
        client_order_id=order_id,
        symbol=symbol,
        side=side,
        order_type="market",
        qty=qty,
        filled_qty=qty,
        filled_avg_price=price,
        timestamp=now,
        fill=fill if event_type in (TradeEventType.FILL, TradeEventType.PARTIAL_FILL) else None,
    )


class _DisconnectedBarStream(MockBarStream):
    """A bar stream that reports disconnected and refuses to connect."""

    def __init__(self, connect_result: bool = False, subscribe_result: bool = True) -> None:
        super().__init__()
        self._connect_result = connect_result
        self._subscribe_result = subscribe_result

    @property
    def connected(self) -> bool:
        return False

    async def connect(self) -> bool:
        return self._connect_result

    async def subscribe(self, symbols: list[str]) -> bool:
        return self._subscribe_result


class _RaisingBarStream(MockBarStream):
    """A bar stream whose live iteration blows up mid-session."""

    async def stream(self):
        yield _bars(1)[0]
        raise RuntimeError("feed exploded")


class _RefusingTradeStream(MockTradeStream):
    def __init__(self, connect_result: bool = False, subscribe_result: bool = True) -> None:
        super().__init__()
        self._connect_result = connect_result
        self._subscribe_result = subscribe_result

    async def connect(self) -> bool:
        if not self._connect_result:
            return False
        return await super().connect()

    async def subscribe(self) -> bool:
        if not self._subscribe_result:
            return False
        return await super().subscribe()


def _make_runner(
    config: RunnerConfig | None = None,
    *,
    bar_stream: MockBarStream | None = None,
    trade_stream: MockTradeStream | None = None,
    executor: AsyncMock | None = None,
    risk: AsyncMock | None = None,
    alerts: AsyncMock | None = None,
    alpaca_client: AsyncMock | None = None,
    ledger_publisher: AsyncMock | None = None,
    portfolio_client: AsyncMock | None = None,
    circuit_breaker_config: CircuitBreakerConfig | None = None,
) -> StrategyRunner:
    executor = executor or AsyncMock()
    if risk is None:
        risk = AsyncMock()
        risk.check_order = AsyncMock(return_value=RiskCheckResult(passed=True, violations=[]))
    return StrategyRunner(
        config=config or _config(),
        session=quiet_session(),
        bar_stream=bar_stream or MockBarStream(bars={"AAPL": _bars(3)}),
        trade_stream=trade_stream or MockTradeStream(),
        order_executor=executor,
        risk_manager=risk,
        alpaca_client=alpaca_client,
        alert_service=cast(AlertService, alerts) if alerts is not None else None,
        circuit_breaker_config=circuit_breaker_config,
        ledger_publisher=ledger_publisher,
        portfolio_client=portfolio_client,
    )


class TestStart:
    async def test_start_runs_recovery_alerts_and_tears_down(self):
        """A full start: stranded-order recovery, ledger re-publish (sleeve
        session), the started alert, and the finally-block task teardown."""
        config = _config(sleeve_id=SLEEVE_ID, account_id=ACCOUNT_ID)
        executor = AsyncMock()
        executor.recover_stranded_orders = AsyncMock(return_value=2)
        executor.republish_ledger_for_terminal_orders = AsyncMock(return_value=1)
        alerts = AsyncMock(spec=AlertService)
        runner = _make_runner(config, executor=executor, alerts=alerts)

        await asyncio.wait_for(runner.start(), timeout=5.0)

        executor.recover_stranded_orders.assert_awaited_once_with(
            config.tenant_id, config.execution_id
        )
        assert executor.republish_ledger_for_terminal_orders.await_count >= 1
        alerts.on_session_started.assert_awaited_once_with(
            tenant_id=config.tenant_id,
            session_id=config.execution_id,
            strategy_name="Unknown Strategy",
            mode="paper",
        )
        assert runner.running is False
        assert runner._trade_stream_task is not None and runner._trade_stream_task.done()
        assert runner._equity_sync_task is not None and runner._equity_sync_task.done()
        assert runner._ledger_republish_task is not None and runner._ledger_republish_task.done()

    async def test_start_is_a_noop_when_already_running(self):
        executor = AsyncMock()
        runner = _make_runner(executor=executor)
        runner._running = True

        await runner.start()

        executor.recover_stranded_orders.assert_not_awaited()

    async def test_start_survives_recovery_and_republish_failures(self):
        """Best-effort startup recovery: broker/ledger hiccups never block start."""
        config = _config(sleeve_id=SLEEVE_ID, account_id=ACCOUNT_ID)
        executor = AsyncMock()
        executor.recover_stranded_orders = AsyncMock(side_effect=RuntimeError("broker down"))
        executor.republish_ledger_for_terminal_orders = AsyncMock(
            side_effect=RuntimeError("kafka down")
        )
        alerts = AsyncMock(spec=AlertService)
        runner = _make_runner(config, executor=executor, alerts=alerts)

        await asyncio.wait_for(runner.start(), timeout=5.0)

        alerts.on_session_started.assert_awaited_once()
        alerts.on_connection_restored.assert_awaited_once_with(
            tenant_id=runner.config.tenant_id, session_id=runner.config.execution_id
        )

    async def test_bar_stream_connect_failure_alerts_and_raises(self):
        alerts = AsyncMock(spec=AlertService)
        runner = _make_runner(bar_stream=_DisconnectedBarStream(), alerts=alerts)

        with pytest.raises(RuntimeError, match="Failed to connect to bar stream"):
            await runner.start()

        alerts.on_connection_lost.assert_awaited_once_with(
            tenant_id=runner.config.tenant_id,
            session_id=runner.config.execution_id,
            service="bar_stream",
        )

    async def test_bar_stream_subscribe_failure_raises(self):
        stream = _DisconnectedBarStream(connect_result=True, subscribe_result=False)
        runner = _make_runner(bar_stream=stream)

        with pytest.raises(RuntimeError, match="Failed to subscribe to symbols"):
            await runner.start()

    async def test_trade_stream_connect_failure_alerts_and_raises(self):
        alerts = AsyncMock(spec=AlertService)
        runner = _make_runner(trade_stream=_RefusingTradeStream(), alerts=alerts)

        with pytest.raises(RuntimeError, match="Failed to connect to trade stream"):
            await runner.start()

        alerts.on_connection_lost.assert_awaited_once_with(
            tenant_id=runner.config.tenant_id,
            session_id=runner.config.execution_id,
            service="trade_stream",
        )

    async def test_trade_stream_subscribe_failure_raises(self):
        stream = _RefusingTradeStream(connect_result=True, subscribe_result=False)
        runner = _make_runner(trade_stream=stream)

        with pytest.raises(RuntimeError, match="Failed to subscribe to trade updates"):
            await runner.start()

    async def test_stream_crash_alerts_session_error_and_reraises(self):
        alerts = AsyncMock(spec=AlertService)
        runner = _make_runner(bar_stream=_RaisingBarStream(), alerts=alerts)

        with pytest.raises(RuntimeError, match="feed exploded"):
            await asyncio.wait_for(runner.start(), timeout=5.0)

        alerts.on_session_error.assert_awaited_once_with(
            tenant_id=runner.config.tenant_id,
            session_id=runner.config.execution_id,
            error="feed exploded",
        )
        assert runner.running is False
        assert runner._trade_stream_task is not None and runner._trade_stream_task.done()


class TestStop:
    async def test_stop_disconnects_cancels_and_alerts_with_reason(self):
        alerts = AsyncMock(spec=AlertService)
        trade_stream = MockTradeStream()
        runner = _make_runner(
            bar_stream=MockBarStream(bars={"AAPL": _bars(50)}),
            trade_stream=trade_stream,
            alerts=alerts,
        )
        task = asyncio.create_task(runner.start())
        try:
            await asyncio.wait_for(_wait_until(lambda: runner.running), timeout=2.0)

            await runner.stop(reason="user requested")

            assert runner.running is False
            assert trade_stream.connected is False
            alerts.on_session_stopped.assert_awaited_once_with(
                tenant_id=runner.config.tenant_id,
                session_id=runner.config.execution_id,
                reason="user requested",
            )
            await asyncio.wait_for(task, timeout=5.0)
        finally:
            if not task.done():
                task.cancel()

    async def test_stop_without_notify_skips_the_alert(self):
        """An internal teardown tears down without telling the user."""
        alerts = AsyncMock(spec=AlertService)
        trade_stream = MockTradeStream()
        runner = _make_runner(
            bar_stream=MockBarStream(bars={"AAPL": _bars(50)}),
            trade_stream=trade_stream,
            alerts=alerts,
        )
        task = asyncio.create_task(runner.start())
        try:
            await asyncio.wait_for(_wait_until(lambda: runner.running), timeout=2.0)

            await runner.stop(notify=False)

            assert runner.running is False
            assert trade_stream.connected is False
            alerts.on_session_stopped.assert_not_awaited()
            await asyncio.wait_for(task, timeout=5.0)
        finally:
            if not task.done():
                task.cancel()


async def _wait_until(predicate) -> None:
    while not predicate():
        await asyncio.sleep(0.005)


class TestRunnerManager:
    async def test_start_runner_registers_and_stop_runner_removes(self):
        manager = RunnerManager()
        config = _config()
        runner = await manager.start_runner(
            config=config,
            session=quiet_session(),
            bar_stream=MockBarStream(bars={"AAPL": _bars(2)}),
            trade_stream=MockTradeStream(),
            order_executor=AsyncMock(),
            risk_manager=AsyncMock(),
        )

        assert manager.get_runner(config.execution_id) is runner

        stopped = await manager.stop_runner(config.execution_id)
        assert stopped is True
        assert manager.get_runner(config.execution_id) is None

    async def test_stop_runner_deregisters_after_session_task_died(self, monkeypatch):
        """A dead session task must not leave the execution registered.

        Recovery evicts a runner that is present but no longer running, then
        re-claims the session; deregistration has to survive the task's own
        exception surfacing out of the await, or the re-claim fails forever.
        """
        died = asyncio.Event()

        async def _die(self) -> None:
            died.set()
            raise RuntimeError("session loop died")

        monkeypatch.setattr(StrategyRunner, "start", _die)

        manager = RunnerManager()
        config = _config()
        await manager.start_runner(
            config=config,
            session=quiet_session(),
            bar_stream=MockBarStream(bars={}),
            trade_stream=MockTradeStream(),
            order_executor=AsyncMock(),
            risk_manager=AsyncMock(),
        )
        await died.wait()
        await asyncio.sleep(0)

        assert await manager.stop_runner(config.execution_id) is True
        assert manager.get_runner(config.execution_id) is None

        monkeypatch.undo()
        try:
            reclaimed = await manager.start_runner(
                config=config,
                session=quiet_session(),
                bar_stream=MockBarStream(bars={}),
                trade_stream=MockTradeStream(),
                order_executor=AsyncMock(),
                risk_manager=AsyncMock(),
            )
            assert manager.get_runner(config.execution_id) is reclaimed
        finally:
            await manager.stop_all()

    async def test_stop_runner_deregisters_when_stop_raises(self, monkeypatch):
        """A failing ``stop()`` still frees the execution for a later re-claim."""
        manager = RunnerManager()
        config = _config()
        runner = await manager.start_runner(
            config=config,
            session=quiet_session(),
            bar_stream=MockBarStream(bars={}),
            trade_stream=MockTradeStream(),
            order_executor=AsyncMock(),
            risk_manager=AsyncMock(),
        )
        monkeypatch.setattr(runner, "stop", AsyncMock(side_effect=RuntimeError("teardown failed")))

        with pytest.raises(RuntimeError, match="teardown failed"):
            await manager.stop_runner(config.execution_id)

        assert manager.get_runner(config.execution_id) is None

    async def test_start_runner_rejects_duplicate_execution(self):
        manager = RunnerManager()
        config = _config()
        await manager.start_runner(
            config=config,
            session=quiet_session(),
            bar_stream=MockBarStream(bars={}),
            trade_stream=MockTradeStream(),
            order_executor=AsyncMock(),
            risk_manager=AsyncMock(),
        )
        try:
            with pytest.raises(ValueError, match="already exists"):
                await manager.start_runner(
                    config=config,
                    session=quiet_session(),
                    bar_stream=MockBarStream(bars={}),
                    trade_stream=MockTradeStream(),
                    order_executor=AsyncMock(),
                    risk_manager=AsyncMock(),
                )
        finally:
            await manager.stop_all()


class TestFillArithmetic:
    async def test_buy_fill_averages_into_existing_long(self):
        runner = _make_runner()
        runner._positions["AAPL"] = RunnerPosition(
            symbol="AAPL",
            side="long",
            quantity=Decimal("10"),
            entry_price=Decimal("100"),
            entry_date=datetime.now(UTC),
        )

        await runner._handle_fill_event(_fill_event("o-1", "buy", Decimal("10"), Decimal("120")))

        position = runner.positions["AAPL"]
        assert position.quantity == Decimal("20")
        assert position.entry_price == Decimal("110")

    async def test_sell_fill_averages_into_existing_short(self):
        runner = _make_runner()
        runner._positions["AAPL"] = RunnerPosition(
            symbol="AAPL",
            side="short",
            quantity=Decimal("10"),
            entry_price=Decimal("100"),
            entry_date=datetime.now(UTC),
        )

        await runner._handle_fill_event(_fill_event("o-1", "sell", Decimal("10"), Decimal("120")))

        position = runner.positions["AAPL"]
        assert position.side == "short"
        assert position.quantity == Decimal("20")
        assert position.entry_price == Decimal("110")

    async def test_buy_fill_fully_covers_short_with_pnl_and_alert(self):
        alerts = AsyncMock(spec=AlertService)
        runner = _make_runner(alerts=alerts)
        runner._positions["AAPL"] = RunnerPosition(
            symbol="AAPL",
            side="short",
            quantity=Decimal("10"),
            entry_price=Decimal("100"),
            entry_date=datetime.now(UTC),
        )

        await runner._handle_fill_event(_fill_event("o-1", "buy", Decimal("10"), Decimal("90")))

        assert "AAPL" not in runner.positions
        alerts.on_position_closed.assert_awaited_once_with(
            tenant_id=runner.config.tenant_id,
            session_id=runner.config.execution_id,
            symbol="AAPL",
            qty=10.0,
            pnl=100.0,
        )

    async def test_sell_fill_fully_closes_long_with_pnl_and_alert(self):
        alerts = AsyncMock(spec=AlertService)
        runner = _make_runner(alerts=alerts)
        runner._positions["AAPL"] = RunnerPosition(
            symbol="AAPL",
            side="long",
            quantity=Decimal("10"),
            entry_price=Decimal("100"),
            entry_date=datetime.now(UTC),
        )

        await runner._handle_fill_event(_fill_event("o-1", "sell", Decimal("10"), Decimal("110")))

        assert "AAPL" not in runner.positions
        alerts.on_position_closed.assert_awaited_once_with(
            tenant_id=runner.config.tenant_id,
            session_id=runner.config.execution_id,
            symbol="AAPL",
            qty=10.0,
            pnl=100.0,
        )

    async def test_sell_fill_opens_short_and_alerts(self):
        alerts = AsyncMock(spec=AlertService)
        runner = _make_runner(alerts=alerts)

        await runner._handle_fill_event(_fill_event("o-1", "sell", Decimal("5"), Decimal("100")))

        position = runner.positions["AAPL"]
        assert position.side == "short"
        assert position.quantity == Decimal("5")
        alerts.on_position_opened.assert_awaited_once_with(
            tenant_id=runner.config.tenant_id,
            session_id=runner.config.execution_id,
            symbol="AAPL",
            side="short",
            qty=5.0,
            price=100.0,
        )


class TestProcessSignalEdges:
    async def test_signal_rounding_to_zero_shares_is_skipped(self):
        executor = AsyncMock()
        runner = _make_runner(_config(fractional_shares=False), executor=executor)
        before = sample_metric("llamatrade_trading_strategy_sub_notional_skips_total")

        await runner._process_signal(
            Signal(type="buy", symbol="AAPL", quantity=Decimal("0.4"), price=Decimal("100"))
        )

        executor.submit_order.assert_not_awaited()
        assert sample_metric("llamatrade_trading_strategy_sub_notional_skips_total") == before + 1

    async def test_signal_below_notional_floor_is_skipped(self):
        executor = AsyncMock()
        runner = _make_runner(_config(min_order_notional=Decimal("5")), executor=executor)
        before = sample_metric("llamatrade_trading_strategy_sub_notional_skips_total")

        await runner._process_signal(
            Signal(type="buy", symbol="AAPL", quantity=Decimal("1"), price=Decimal("2"))
        )

        executor.submit_order.assert_not_awaited()
        assert sample_metric("llamatrade_trading_strategy_sub_notional_skips_total") == before + 1

    async def test_triggered_breaker_rejects_the_signal_before_risk(self):
        executor = AsyncMock()
        risk = AsyncMock()
        runner = _make_runner(executor=executor, risk=risk)
        await runner._circuit_breaker.manual_trigger("halt")

        await runner._process_signal(
            Signal(type="buy", symbol="AAPL", quantity=Decimal("10"), price=Decimal("100"))
        )

        risk.check_order.assert_not_awaited()
        executor.submit_order.assert_not_awaited()

    async def test_risk_rejection_counts_and_raises_the_breach_alert(self):
        executor = AsyncMock()
        risk = AsyncMock()
        risk.check_order = AsyncMock(
            return_value=RiskCheckResult(passed=False, violations=["Daily loss limit exceeded"])
        )
        alerts = AsyncMock(spec=AlertService)
        runner = _make_runner(executor=executor, alerts=alerts)
        runner.risk_manager = risk

        await runner._process_signal(
            Signal(type="buy", symbol="AAPL", quantity=Decimal("10"), price=Decimal("100"))
        )

        executor.submit_order.assert_not_awaited()
        assert runner._orders_rejected == 1
        alerts.on_risk_breach.assert_awaited_once()
        assert alerts.on_risk_breach.await_args.kwargs["breach_type"] == "signal_rejected"
        assert alerts.on_risk_breach.await_args.kwargs["details"]["violations"] == [
            "Daily loss limit exceeded"
        ]

    async def test_submit_failure_counts_rejection_and_feeds_the_breaker(self):
        executor = AsyncMock()
        executor.submit_order = AsyncMock(side_effect=RuntimeError("alpaca down"))
        runner = _make_runner(
            executor=executor,
            circuit_breaker_config=CircuitBreakerConfig(max_order_errors=1),
        )

        await runner._process_signal(
            Signal(type="buy", symbol="AAPL", quantity=Decimal("10"), price=Decimal("100"))
        )

        assert runner._orders_rejected == 1
        assert runner.circuit_breaker_triggered is True


class TestEquitySyncFailure:
    async def test_broker_equity_failure_feeds_the_breaker(self):
        alpaca = AsyncMock(spec=TradingClient)
        alpaca.get_account = AsyncMock(side_effect=RuntimeError("api down"))
        runner = _make_runner(
            alpaca_client=alpaca,
            circuit_breaker_config=CircuitBreakerConfig(max_api_errors=1),
        )

        await runner._sync_equity()

        assert runner.circuit_breaker_triggered is True


class TestLedgerFillPublication:
    def _sleeve_runner(self, publisher: AsyncMock, portfolio: AsyncMock) -> StrategyRunner:
        return _make_runner(
            _config(sleeve_id=SLEEVE_ID, account_id=ACCOUNT_ID),
            ledger_publisher=publisher,
            portfolio_client=portfolio,
        )

    async def test_terminal_fill_publishes_and_invalidates_the_sleeve_cache(self):
        publisher = AsyncMock(spec=TradingEventPublisher)
        portfolio = AsyncMock(spec=PortfolioLedgerClient)
        runner = self._sleeve_runner(publisher, portfolio)

        await runner._handle_trade_event(_fill_event("o-1", "buy", Decimal("10"), Decimal("150")))

        publisher.publish_ledger_fill.assert_awaited_once()
        payload = publisher.publish_ledger_fill.await_args.args[0]
        assert payload.client_order_id == "o-1"
        assert payload.qty == "10"
        assert payload.price == "150"
        portfolio.invalidate.assert_called_once_with(SLEEVE_ID)

    async def test_publish_failure_is_contained_and_cache_still_invalidated(self):
        publisher = AsyncMock(spec=TradingEventPublisher)
        publisher.publish_ledger_fill = AsyncMock(side_effect=RuntimeError("kafka down"))
        portfolio = AsyncMock(spec=PortfolioLedgerClient)
        runner = self._sleeve_runner(publisher, portfolio)

        await runner._handle_trade_event(_fill_event("o-1", "buy", Decimal("10"), Decimal("150")))

        portfolio.invalidate.assert_called_once_with(SLEEVE_ID)

    async def test_unfilled_cancel_publishes_only_the_reservation_release(self):
        publisher = AsyncMock(spec=TradingEventPublisher)
        portfolio = AsyncMock(spec=PortfolioLedgerClient)
        runner = self._sleeve_runner(publisher, portfolio)
        event = _fill_event(
            "o-1", "buy", Decimal("0"), Decimal("0"), event_type=TradeEventType.CANCELED
        )

        await runner._handle_trade_event(event)

        publisher.publish_ledger_fill.assert_awaited_once()
        release = publisher.publish_ledger_fill.await_args.args[0]
        assert release.event_type == "order_cancelled"
        portfolio.invalidate.assert_not_called()


class TestOpenOrderSync:
    """The REST catch-up that books fills the trade stream never delivered.

    The stream is the fast path, but it replays no gap on reconnect and delivers
    nothing while the pod is down, so an order that terminalized at the broker in
    that window stays non-terminal forever: the stranded sweep skips it (it has a
    broker id) and the republish drain skips it (it is not terminal). Only this
    pass books the fill, which is why it runs at start, on reconnect, and on the
    periodic drain.
    """

    async def test_start_syncs_open_orders(self):
        config = _config(sleeve_id=SLEEVE_ID, account_id=ACCOUNT_ID)
        executor = AsyncMock()
        executor.sync_all_pending_orders = AsyncMock(return_value=1)
        runner = _make_runner(config, executor=executor)

        await asyncio.wait_for(runner.start(), timeout=5.0)

        executor.sync_all_pending_orders.assert_any_await(config.tenant_id, config.execution_id)

    async def test_start_syncs_before_republishing(self):
        """The sync terminalizes what the stream missed, so it must run first for
        the republish to have anything to re-emit."""
        calls: list[str] = []
        config = _config(sleeve_id=SLEEVE_ID, account_id=ACCOUNT_ID)
        executor = AsyncMock()
        executor.sync_all_pending_orders = AsyncMock(
            side_effect=lambda *a, **k: calls.append("sync") or 0
        )
        executor.republish_ledger_for_terminal_orders = AsyncMock(
            side_effect=lambda *a, **k: calls.append("republish") or 0
        )
        runner = _make_runner(config, executor=executor)

        await asyncio.wait_for(runner.start(), timeout=5.0)

        assert calls[:2] == ["sync", "republish"]

    async def test_start_survives_sync_failure(self):
        """Best-effort: a broker hiccup during catch-up never blocks the session."""
        config = _config(sleeve_id=SLEEVE_ID, account_id=ACCOUNT_ID)
        executor = AsyncMock()
        executor.sync_all_pending_orders = AsyncMock(side_effect=RuntimeError("broker down"))
        alerts = AsyncMock(spec=AlertService)
        runner = _make_runner(config, executor=executor, alerts=alerts)

        await asyncio.wait_for(runner.start(), timeout=5.0)

        alerts.on_session_started.assert_awaited_once()

    async def test_periodic_drain_syncs_before_republishing(self):
        """Order matters: syncing terminalizes orders the stream missed, and the
        republish then covers those whose publish failed."""
        calls: list[str] = []
        executor = AsyncMock()
        executor.sync_all_pending_orders = AsyncMock(
            side_effect=lambda *a, **k: calls.append("sync") or 0
        )
        executor.republish_ledger_for_terminal_orders = AsyncMock(
            side_effect=lambda *a, **k: calls.append("republish") or 0
        )
        config = _config(
            sleeve_id=SLEEVE_ID, account_id=ACCOUNT_ID, ledger_republish_interval_seconds=0.01
        )
        runner = _make_runner(config, executor=executor)
        runner._running = True

        task = asyncio.create_task(runner._ledger_republish_loop())
        await asyncio.sleep(0.05)
        runner._running = False
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        assert calls[:2] == ["sync", "republish"]

    async def test_stream_reconnect_syncs_the_gap(self):
        executor = AsyncMock()
        executor.sync_all_pending_orders = AsyncMock(return_value=2)
        config = _config()
        runner = _make_runner(config, executor=executor)

        await runner._rebuild_trade_stream()

        executor.sync_all_pending_orders.assert_awaited_once_with(
            config.tenant_id, config.execution_id
        )

    async def test_failed_resubscribe_does_not_sync(self):
        """A reconnect that never re-subscribed has no restored feed to trust, so
        the next supervisor pass retries rather than claiming the gap is closed."""
        executor = AsyncMock()
        executor.sync_all_pending_orders = AsyncMock(return_value=0)
        trade_stream = MockTradeStream()
        trade_stream.subscribe = AsyncMock(return_value=False)
        runner = _make_runner(executor=executor, trade_stream=trade_stream)

        await runner._rebuild_trade_stream()

        executor.sync_all_pending_orders.assert_not_awaited()
