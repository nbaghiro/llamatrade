"""End-to-end lifecycle tests: RunBacktest RPC → execution → results via GetBacktest.

These are the tests that would have caught the original wiring gaps:
- RunBacktest created a PENDING row that nothing ever executed
- GetBacktest never populated BacktestRun.results, so the UI had nothing to render

Celery runs in eager mode (task executes synchronously inside .delay()), the
market data client is a deterministic fake, and the DB layer is a stateful
in-memory fake shared across the servicer and worker sessions — no external
services required.
"""

import datetime as dt
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import grpc.aio
import pytest

from llamatrade_proto.generated import backtest_pb2, common_pb2
from llamatrade_proto.generated.backtest_pb2 import (
    BACKTEST_STATUS_COMPLETED,
    BACKTEST_STATUS_FAILED,
)
from llamatrade_proto.generated.strategy_pb2 import STRATEGY_STATUS_ACTIVE

from src.services.backtest_service import MarketDataError

TEST_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
TEST_USER_ID = UUID("22222222-2222-2222-2222-222222222222")
TEST_STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")

pytestmark = pytest.mark.asyncio


class MockServicerContext:
    """Mock gRPC servicer context that raises on abort."""

    def __init__(self) -> None:
        self.code = None
        self.details = None

    async def abort(self, code, details: str) -> None:
        self.code = code
        self.details = details
        raise grpc.aio.AioRpcError(
            code=code,
            initial_metadata=None,
            trailing_metadata=None,
            details=details,
            debug_error_string=None,
        )

    def cancelled(self) -> bool:
        return False


class FakeStore:
    """In-memory backtest store shared by all fake DB sessions."""

    def __init__(self, cancel_on_finalize: bool = False) -> None:
        # When True, the conditional terminal UPDATE reports 0 rows (3A): a
        # concurrent CancelBacktest committed CANCELLED first, so the run must
        # discard its result rather than overwrite the cancel.
        self.cancel_on_finalize = cancel_on_finalize
        self.strategy = MagicMock()
        self.strategy.id = TEST_STRATEGY_ID
        self.strategy.tenant_id = TEST_TENANT_ID
        self.strategy.current_version = 1
        self.strategy.status = STRATEGY_STATUS_ACTIVE

        self.strategy_version = MagicMock()
        self.strategy_version.strategy_id = TEST_STRATEGY_ID
        self.strategy_version.version = 1
        self.strategy_version.config_sexpr = (
            '(strategy "Test" :benchmark SPY :rebalance daily (asset AAPL :weight 100))'
        )
        self.strategy_version.timeframe = "1D"
        self.strategy_version.symbols = ["AAPL"]

        self.backtest = None
        self.result = None

    def make_session(self) -> AsyncMock:
        """Create a fake AsyncSession backed by this store.

        Routes `execute()` by inspecting the selected entity, so the same
        fake works for every service query pattern.
        """
        store = self

        session = AsyncMock()
        session.add = MagicMock()
        # Staged rows are promoted to the shared store only on commit, and
        # dropped on rollback — so a discarded result (3A cancel race) truly
        # disappears rather than lingering from the add().
        pending: dict[str, object] = {}

        def handle_add(obj) -> None:
            from llamatrade_db.models.backtest import Backtest, BacktestResult

            if isinstance(obj, Backtest):
                obj.id = uuid4()
                obj.created_at = datetime.now(UTC)
                pending["backtest"] = obj
            elif isinstance(obj, BacktestResult):
                obj.id = uuid4()
                obj.created_at = datetime.now(UTC)
                pending["result"] = obj

        session.add.side_effect = handle_add

        async def handle_commit() -> None:
            if "backtest" in pending:
                store.backtest = pending["backtest"]
            if "result" in pending:
                store.result = pending["result"]
            pending.clear()

        session.commit = AsyncMock(side_effect=handle_commit)

        async def handle_rollback() -> None:
            pending.clear()

        session.rollback = AsyncMock(side_effect=handle_rollback)

        async def handle_refresh(obj) -> None:
            return None

        session.refresh = AsyncMock(side_effect=handle_refresh)

        async def handle_execute(stmt):
            from sqlalchemy.sql.dml import Update

            from llamatrade_db.models.backtest import Backtest, BacktestResult
            from llamatrade_db.models.strategy import Strategy, StrategyVersion

            if isinstance(stmt, Update):
                # 3A conditional terminal write (WHERE status=RUNNING).
                if store.cancel_on_finalize:
                    if store.backtest is not None:
                        store.backtest.status = backtest_pb2.BACKTEST_STATUS_CANCELLED
                    return MagicMock(rowcount=0)
                if store.backtest is not None:
                    for col, val in stmt._values.items():
                        setattr(store.backtest, col.name, getattr(val, "value", val))
                return MagicMock(rowcount=1)

            entity = stmt.column_descriptions[0]["entity"]
            if entity is Strategy:
                value = store.strategy
            elif entity is StrategyVersion:
                value = store.strategy_version
            elif entity is Backtest:
                value = store.backtest
            elif entity is BacktestResult:
                value = store.result
            else:  # pragma: no cover - unexpected query
                raise AssertionError(f"Unexpected query entity: {entity}")
            return MagicMock(scalar_one_or_none=MagicMock(return_value=value))

        session.execute = AsyncMock(side_effect=handle_execute)
        return session


def make_fake_market_client(fail: bool = False) -> AsyncMock:
    """Deterministic market data: 40 trending days of AAPL + SPY."""
    client = AsyncMock()

    if fail:
        client.fetch_bars = AsyncMock(side_effect=MarketDataError("market data down"))
        return client

    def bars_for(base: float) -> list[dict]:
        out = []
        for i in range(40):
            close = base * (1 + 0.002 * i)
            out.append(
                {
                    "timestamp": datetime(2024, 1, 1, 16, tzinfo=UTC) + dt.timedelta(days=i),
                    "open": close * 0.999,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "volume": 1_000_000,
                }
            )
        return out

    client.fetch_bars = AsyncMock(return_value={"AAPL": bars_for(150.0), "SPY": bars_for(400.0)})
    return client


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def eager_celery():
    """Run Celery tasks synchronously inside .delay()."""
    from src.celery_app import celery_app

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False
    yield celery_app
    celery_app.conf.task_always_eager = False


@pytest.fixture
def quiet_progress(monkeypatch):
    """Capture progress publishes (with status) instead of hitting Redis."""
    published: list[tuple[float, str, int | None]] = []

    async def fake_publish(self, backtest_id, progress, message, eta_seconds=None, status=None):
        published.append((progress, message, status))

    monkeypatch.setattr("src.progress.ProgressPublisher.publish", fake_publish)
    monkeypatch.setattr("src.progress.ProgressPublisher.close", AsyncMock())
    return published


@pytest.fixture
def servicer(store, monkeypatch):
    """Servicer whose DB sessions come from the fake store."""
    from src.grpc.servicer import BacktestServicer

    servicer = BacktestServicer()

    @asynccontextmanager
    async def fake_get_db():
        yield store.make_session()

    monkeypatch.setattr(servicer, "_get_db", fake_get_db)
    return servicer


def make_run_request() -> backtest_pb2.RunBacktestRequest:
    start = int(datetime(2024, 1, 20, 12, tzinfo=UTC).timestamp())
    end = int(datetime(2024, 2, 9, 12, tzinfo=UTC).timestamp())
    return backtest_pb2.RunBacktestRequest(
        context=common_pb2.TenantContext(
            tenant_id=str(TEST_TENANT_ID),
            user_id=str(TEST_USER_ID),
        ),
        config=backtest_pb2.BacktestConfig(
            strategy_id=str(TEST_STRATEGY_ID),
            start_date=common_pb2.Timestamp(seconds=start),
            end_date=common_pb2.Timestamp(seconds=end),
            initial_capital=common_pb2.Decimal(value="100000"),
            symbols=["AAPL"],
            timeframe="1D",
            benchmark_symbol="SPY",
            include_benchmark=True,
        ),
    )


def patch_worker_dependencies(monkeypatch, store: FakeStore, market_client) -> None:
    """Point the Celery task's session/market-data factories at the fakes."""
    from src.workers import celery_tasks

    @asynccontextmanager
    async def fake_session_scope():
        yield store.make_session()

    monkeypatch.setattr(celery_tasks, "_session_scope", fake_session_scope)
    monkeypatch.setattr(celery_tasks, "_create_market_data_client", lambda: market_client)


class TestE2ELifecycle:
    """Full product flow: create → execute → results."""

    async def test_run_backtest_executes_and_results_reach_get_backtest(
        self, servicer, store, eager_celery, quiet_progress, monkeypatch
    ):
        patch_worker_dependencies(monkeypatch, store, make_fake_market_client())
        context = MockServicerContext()

        # 1. RunBacktest creates the backtest AND triggers execution
        run_response = await servicer.run_backtest(make_run_request(), context)
        backtest_id = run_response.backtest.id
        assert backtest_id

        # Execution happened (eager Celery): status is terminal, not PENDING
        assert store.backtest is not None
        assert store.backtest.status == BACKTEST_STATUS_COMPLETED, (
            f"Backtest was never executed (status={store.backtest.status}); "
            "RunBacktest must enqueue the run"
        )
        assert store.result is not None, "No BacktestResult row was persisted"

        # 2. GetBacktest returns the run WITH populated results
        get_response = await servicer.get_backtest(
            backtest_pb2.GetBacktestRequest(
                context=common_pb2.TenantContext(tenant_id=str(TEST_TENANT_ID)),
                backtest_id=str(store.backtest.id),
            ),
            MockServicerContext(),
        )

        backtest_msg = get_response.backtest
        assert backtest_msg.status == BACKTEST_STATUS_COMPLETED
        assert backtest_msg.HasField("results"), (
            "GetBacktest must populate BacktestRun.results for completed runs"
        )
        results = backtest_msg.results
        assert len(results.equity_curve) > 0
        assert len(results.trades) >= 1
        assert results.metrics.total_trades >= 1
        # The buy-and-hold AAPL strategy on trending data is profitable
        assert float(results.metrics.total_return.value) > 0
        # Benchmark comparison present
        assert results.benchmark_symbol == "SPY"

    async def test_failed_run_is_marked_failed_with_error_message(
        self, servicer, store, eager_celery, quiet_progress, monkeypatch
    ):
        patch_worker_dependencies(monkeypatch, store, make_fake_market_client(fail=True))
        context = MockServicerContext()

        await servicer.run_backtest(make_run_request(), context)

        assert store.backtest is not None
        assert store.backtest.status == BACKTEST_STATUS_FAILED
        assert store.backtest.error_message
        assert "market data" in store.backtest.error_message.lower()
        # A failure progress update was published WITH explicit FAILED status —
        # consumers must never have to infer status from the progress number
        assert any(status == BACKTEST_STATUS_FAILED for _, _, status in quiet_progress)

    async def test_cancel_during_finalize_discards_result(
        self, eager_celery, quiet_progress, monkeypatch
    ):
        """3A: a cancel that lands during finalize keeps CANCELLED and drops the result."""
        from src.grpc.servicer import BacktestServicer

        store = FakeStore(cancel_on_finalize=True)
        servicer = BacktestServicer()

        @asynccontextmanager
        async def fake_get_db():
            yield store.make_session()

        monkeypatch.setattr(servicer, "_get_db", fake_get_db)
        patch_worker_dependencies(monkeypatch, store, make_fake_market_client())

        await servicer.run_backtest(make_run_request(), MockServicerContext())

        assert store.backtest is not None
        assert store.backtest.status == backtest_pb2.BACKTEST_STATUS_CANCELLED
        assert store.result is None, (
            "A result must not be persisted when a cancel wins the finalize race"
        )

    async def test_get_backtest_for_pending_run_has_no_results(self, servicer, store):
        """List/poll responses for unexecuted runs must stay slim."""
        from llamatrade_db.models.backtest import Backtest

        store.backtest = Backtest(
            tenant_id=TEST_TENANT_ID,
            strategy_id=TEST_STRATEGY_ID,
            strategy_version=1,
            name="pending",
            status=backtest_pb2.BACKTEST_STATUS_PENDING,
            config={},
            symbols=["AAPL"],
            start_date=date(2024, 1, 20),
            end_date=date(2024, 2, 9),
            initial_capital=100000,
            created_by=TEST_USER_ID,
        )
        store.backtest.id = uuid4()
        store.backtest.created_at = datetime.now(UTC)

        get_response = await servicer.get_backtest(
            backtest_pb2.GetBacktestRequest(
                context=common_pb2.TenantContext(tenant_id=str(TEST_TENANT_ID)),
                backtest_id=str(store.backtest.id),
            ),
            MockServicerContext(),
        )

        assert not get_response.backtest.HasField("results")
