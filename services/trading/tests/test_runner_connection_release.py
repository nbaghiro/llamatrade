"""A runner never keeps its order executor's DB connection checked out.

The runner owns one long-lived executor session for the life of a trading
session. Each executor call must hand the connection back to the pool when it
finishes, fails, or is cancelled, and the executor must be closed as soon as the
session task ends, or crashed and evicted runners drain the pool.
"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_alpaca import MockBarStream, MockTradeStream
from tests.sessions import quiet_session

from src.executor.order_executor import OrderExecutor, create_order_executor
from src.models import RiskCheckResult
from src.risk.risk_manager import RiskManager
from src.runner.runner import RunnerConfig, RunnerManager, Signal, StrategyRunner
from src.services.live_session_service import create_live_session_service


class _PooledExecutor:
    """Executor double that tracks whether its session holds a pooled connection.

    Every call checks a connection out (as an AsyncSession's autobegin does) and
    only ``release_connection``/``aclose`` return it.
    """

    def __init__(self) -> None:
        self.checked_out = False
        self.in_flight = 0
        self.max_in_flight = 0
        self.close_calls = 0
        self.fail_with: BaseException | None = None
        self.block: asyncio.Event | None = None
        self.entered = asyncio.Event()

    async def _work(self) -> None:
        self.checked_out = True
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        self.entered.set()
        try:
            if self.block is not None:
                await self.block.wait()
            else:
                await asyncio.sleep(0)
            if self.fail_with is not None:
                raise self.fail_with
        finally:
            self.in_flight -= 1

    async def submit_order(self, **_: object) -> object:
        await self._work()
        return AsyncMock(id=uuid4(), status=1, client_order_id=None)

    async def sync_all_pending_orders(self, tenant_id: UUID, session_id: UUID) -> int:
        await self._work()
        return 0

    async def recover_stranded_orders(self, tenant_id: UUID, session_id: UUID) -> int:
        await self._work()
        return 0

    async def republish_ledger_for_terminal_orders(
        self, tenant_id: UUID, session_id: UUID, since: datetime
    ) -> int:
        await self._work()
        return 0

    async def release_connection(self) -> None:
        self.checked_out = False

    async def aclose(self) -> None:
        self.close_calls += 1
        self.checked_out = False


def _config() -> RunnerConfig:
    return RunnerConfig(
        tenant_id=uuid4(),
        execution_id=uuid4(),
        strategy_id=uuid4(),
        symbols=["AAPL"],
        timeframe="1Min",
        warmup_bars=100,
        enforce_trading_hours=False,
    )


def _risk() -> RiskManager:
    risk = AsyncMock()
    risk.check_order = AsyncMock(return_value=RiskCheckResult(passed=True, violations=[]))
    return cast(RiskManager, risk)


def _runner(executor: _PooledExecutor) -> StrategyRunner:
    return StrategyRunner(
        config=_config(),
        session=quiet_session(),
        bar_stream=MockBarStream(bars={}),
        trade_stream=MockTradeStream(),
        order_executor=cast(OrderExecutor, executor),
        risk_manager=_risk(),
    )


def _buy() -> Signal:
    return Signal(
        type="buy",
        symbol="AAPL",
        quantity=Decimal("10"),
        price=Decimal("100"),
        timestamp=datetime(2024, 1, 15, 15, 0, tzinfo=UTC),
    )


class TestExecutorCallsReturnTheConnection:
    async def test_successful_submit(self):
        executor = _PooledExecutor()
        runner = _runner(executor)

        await runner._process_signal(_buy())

        assert runner._orders_submitted == 1
        assert executor.checked_out is False

    async def test_broker_failure_during_submit(self):
        executor = _PooledExecutor()
        executor.fail_with = RuntimeError("alpaca down")
        runner = _runner(executor)

        await runner._process_signal(_buy())

        assert runner._orders_rejected == 1
        assert executor.checked_out is False

    async def test_failed_open_order_sync(self):
        executor = _PooledExecutor()
        executor.fail_with = TimeoutError("broker hung")
        runner = _runner(executor)

        assert await runner._sync_open_orders(context="periodic drain") == 0
        assert executor.checked_out is False

    async def test_cancelled_broker_call(self):
        executor = _PooledExecutor()
        executor.block = asyncio.Event()
        runner = _runner(executor)

        task = asyncio.create_task(runner._process_signal(_buy()))
        await executor.entered.wait()
        assert executor.checked_out is True
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert executor.checked_out is False

    async def test_concurrent_loops_never_share_the_session(self):
        executor = _PooledExecutor()
        runner = _runner(executor)

        await asyncio.gather(
            runner._process_signal(_buy()),
            runner._sync_open_orders(context="periodic drain"),
            runner._sync_open_orders(context="startup"),
        )

        assert executor.max_in_flight == 1
        assert executor.checked_out is False


async def _start(manager: RunnerManager, executor: _PooledExecutor) -> RunnerConfig:
    config = _config()
    await manager.start_runner(
        config=config,
        session=quiet_session(),
        bar_stream=MockBarStream(bars={}),
        trade_stream=MockTradeStream(),
        order_executor=cast(OrderExecutor, executor),
        risk_manager=_risk(),
    )
    return config


class TestRunnerReleasesTheExecutor:
    async def test_dead_session_task_closes_the_executor_before_eviction(self, monkeypatch):
        async def _die(self: StrategyRunner) -> None:
            async with self._executor_op() as op:
                await op.recover_stranded_orders(self.config.tenant_id, self.config.execution_id)
            raise RuntimeError("Failed to connect to bar stream")

        monkeypatch.setattr(StrategyRunner, "start", _die)
        manager = RunnerManager()
        executor = _PooledExecutor()
        config = await _start(manager, executor)

        task = manager._tasks[config.execution_id]
        with pytest.raises(RuntimeError):
            await task

        assert executor.close_calls == 1
        assert executor.checked_out is False

        assert await manager.stop_runner(config.execution_id) is True
        assert executor.close_calls == 1

    async def test_stop_runner_closes_the_executor_once(self):
        manager = RunnerManager()
        executor = _PooledExecutor()
        config = await _start(manager, executor)
        await executor.entered.wait()

        assert await manager.stop_runner(config.execution_id) is True

        assert executor.close_calls == 1
        assert executor.checked_out is False

    async def test_stop_runner_closes_a_runner_whose_task_never_ran(self):
        manager = RunnerManager()
        executor = _PooledExecutor()
        config = await _start(manager, executor)

        # Stopped before the session task gets its first step, so its own cleanup never runs.
        assert await manager.stop_runner(config.execution_id) is True

        assert executor.close_calls == 1

    async def test_close_failure_is_contained(self):
        executor = _PooledExecutor()
        executor.aclose = AsyncMock(side_effect=OSError("connection reset"))  # type: ignore[method-assign]
        runner = _runner(executor)

        await runner.aclose()
        await runner.aclose()

        executor.aclose.assert_awaited_once()


class TestFactoriesCloseTheSessionOnFailure:
    async def test_order_executor_closes_db_when_credential_lookup_raises(
        self, monkeypatch, tenant_id, session_id
    ):
        db = AsyncMock(spec=AsyncSession)
        monkeypatch.setattr("llamatrade_db.session.get_session_maker", lambda: lambda: db)
        monkeypatch.setattr("llamatrade_db.session.bind_tenant_guc", lambda *_: None)
        monkeypatch.setattr(
            "src.credentials.resolve_session_credentials",
            AsyncMock(side_effect=TimeoutError("QueuePool limit reached")),
        )

        with pytest.raises(TimeoutError):
            await create_order_executor(session_id=session_id, tenant_id=tenant_id)

        db.close.assert_awaited_once()

    async def test_live_session_service_closes_db_when_executor_factory_raises(
        self, monkeypatch, tenant_id
    ):
        db = AsyncMock(spec=AsyncSession)
        monkeypatch.setattr("llamatrade_db.session.get_session_maker", lambda: lambda: db)
        monkeypatch.setattr("llamatrade_db.session.bind_tenant_guc", lambda *_: None)
        monkeypatch.setattr(
            "src.executor.order_executor.create_order_executor",
            AsyncMock(side_effect=TimeoutError("QueuePool limit reached")),
        )

        with pytest.raises(TimeoutError):
            await create_live_session_service(tenant_id)

        db.close.assert_awaited_once()


async def test_release_connection_closes_the_session_but_keeps_it_usable():
    db = AsyncMock(spec=AsyncSession)
    executor = OrderExecutor(db=db, alpaca_client=AsyncMock(), risk_manager=_risk())

    await executor.release_connection()

    db.close.assert_awaited_once()
