"""Real-Postgres integration tests for the backtest service's money-path writes.

Covers the writes whose safety argument depends on real SQL semantics: the
``fail_backtest`` enqueue compensation, the conditional finalize ``UPDATE ...
WHERE status = RUNNING`` against a committed cancel, the reaper cutoffs, the
one-result-per-backtest unique constraint, and ``_reset_to_pending``'s
``WHERE status = FAILED`` guard.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from llamatrade_db.models.backtest import Backtest, BacktestResult
from llamatrade_proto.generated.backtest_pb2 import (
    BACKTEST_STATUS_CANCELLED,
    BACKTEST_STATUS_COMPLETED,
    BACKTEST_STATUS_FAILED,
    BACKTEST_STATUS_PENDING,
    BACKTEST_STATUS_RUNNING,
)
from llamatrade_runtime import RuntimeCancelled
from tests.integration.seeding import (
    bars_for,
    get_status,
    market_client,
    result_count,
    seed_backtest,
)

from src.services.backtest_service import BacktestService, MarketDataFetcher

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def no_cancel_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the engine's cancel polling off the network; cancellation here is DB-driven."""
    monkeypatch.setattr(
        "src.services.backtest_service.CancellationFlag.make_should_abort",
        lambda self, backtest_id, check_interval=1.0: lambda: False,
    )
    monkeypatch.setattr(
        "src.services.backtest_service.CancellationFlag.request_cancel",
        AsyncMock(),
    )


class TestFailBacktestCompensation:
    async def test_fail_backtest_persists_terminal_state(self, session_factory) -> None:
        tenant_id = uuid4()
        backtest_id = await seed_backtest(
            session_factory, tenant_id, status=BACKTEST_STATUS_PENDING
        )

        async with session_factory() as db:
            service = BacktestService(db, market_data_client=market_client())
            assert await service.fail_backtest(backtest_id, tenant_id, "enqueue exploded") is True

        async with session_factory() as db:
            row = (
                await db.execute(select(Backtest).where(Backtest.id == backtest_id))
            ).scalar_one()
        assert row.status == BACKTEST_STATUS_FAILED
        assert row.error_message == "enqueue exploded"
        assert row.completed_at is not None

    async def test_fail_backtest_unknown_id_returns_false(self, session_factory) -> None:
        async with session_factory() as db:
            service = BacktestService(db, market_data_client=market_client())
            assert await service.fail_backtest(uuid4(), uuid4(), "nope") is False

    async def test_fail_backtest_is_tenant_scoped(self, session_factory) -> None:
        tenant_id = uuid4()
        backtest_id = await seed_backtest(
            session_factory, tenant_id, status=BACKTEST_STATUS_PENDING
        )

        async with session_factory() as db:
            service = BacktestService(db, market_data_client=market_client())
            assert await service.fail_backtest(backtest_id, uuid4(), "cross-tenant") is False

        status, error = await get_status(session_factory, backtest_id)
        assert status == BACKTEST_STATUS_PENDING
        assert error is None


class TestFinalizeCancelRace:
    """The 3A conditional terminal write against a real committed cancel."""

    async def test_cancel_between_refresh_and_finalize_discards_result(
        self, session_factory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A cancel that commits inside the refresh-to-finalize window loses no state.

        The pre-save refresh observes RUNNING, the concurrent cancel then commits
        CANCELLED, and the conditional ``UPDATE ... WHERE status = RUNNING`` must
        match zero rows so the staged result INSERT is rolled back.
        """
        tenant_id = uuid4()
        backtest_id = await seed_backtest(
            session_factory, tenant_id, status=BACKTEST_STATUS_PENDING, with_strategy=True
        )

        async with session_factory() as db:
            service = BacktestService(db, market_data_client=market_client())
            real_refresh = db.refresh
            fired = False

            async def refresh_then_cancel(obj: object) -> None:
                nonlocal fired
                await real_refresh(obj)
                if (
                    not fired
                    and isinstance(obj, Backtest)
                    and obj.status == BACKTEST_STATUS_RUNNING
                ):
                    fired = True
                    async with session_factory() as other:
                        cancel_service = BacktestService(other, market_data_client=market_client())
                        assert await cancel_service.cancel_backtest(backtest_id, tenant_id) is True

            monkeypatch.setattr(db, "refresh", refresh_then_cancel)

            with pytest.raises(RuntimeCancelled):
                await service.run_backtest(backtest_id, tenant_id, publish_progress=False)

        assert fired is True
        status, _ = await get_status(session_factory, backtest_id)
        assert status == BACKTEST_STATUS_CANCELLED
        assert await result_count(session_factory, backtest_id) == 0

    async def test_finalize_first_then_cancel_is_refused(self, session_factory) -> None:
        """When the run completes first, the later cancel returns False and the result stays."""
        tenant_id = uuid4()
        backtest_id = await seed_backtest(
            session_factory, tenant_id, status=BACKTEST_STATUS_PENDING, with_strategy=True
        )

        async with session_factory() as db:
            service = BacktestService(db, market_data_client=market_client())
            result = await service.run_backtest(backtest_id, tenant_id, publish_progress=False)
            assert result.total_trades >= 1
            # The 039 trigger fills tenant_id from the parent row on insert.
            assert result.tenant_id == tenant_id

        async with session_factory() as db:
            cancel_service = BacktestService(db, market_data_client=market_client())
            assert await cancel_service.cancel_backtest(backtest_id, tenant_id) is False

        status, _ = await get_status(session_factory, backtest_id)
        assert status == BACKTEST_STATUS_COMPLETED
        assert await result_count(session_factory, backtest_id) == 1

    async def test_cancel_observed_at_refresh_discards_result(self, session_factory) -> None:
        """A cancel committed while the sim runs is seen by the pre-save refresh guard."""
        tenant_id = uuid4()
        backtest_id = await seed_backtest(
            session_factory, tenant_id, status=BACKTEST_STATUS_PENDING, with_strategy=True
        )

        cancelled_mid_run = False

        async def cancel_mid_fetch(
            symbols: list[str], timeframe: str, start_date: date, end_date: date
        ) -> dict[str, list[dict[str, object]]]:
            nonlocal cancelled_mid_run
            # The row is RUNNING here; commit a cancel from a second session
            # before returning the bars, so the pre-save refresh must see it.
            async with session_factory() as other:
                cancel_service = BacktestService(other, market_data_client=market_client())
                cancelled_mid_run = await cancel_service.cancel_backtest(backtest_id, tenant_id)
            return {"AAPL": bars_for(150.0), "SPY": bars_for(400.0)}

        client = AsyncMock(spec=MarketDataFetcher)
        client.fetch_bars.side_effect = cancel_mid_fetch

        async with session_factory() as db:
            service = BacktestService(db, market_data_client=client)
            with pytest.raises(RuntimeCancelled):
                await service.run_backtest(backtest_id, tenant_id, publish_progress=False)

        assert cancelled_mid_run is True
        status, _ = await get_status(session_factory, backtest_id)
        assert status == BACKTEST_STATUS_CANCELLED
        assert await result_count(session_factory, backtest_id) == 0


class TestReaperOnRealRows:
    async def test_cutoffs_recover_only_stale_rows_across_tenants(
        self, session_factory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        now = datetime.now(UTC)
        stale_running = await seed_backtest(
            session_factory,
            uuid4(),
            status=BACKTEST_STATUS_RUNNING,
            started_at=now - timedelta(hours=3),
        )
        fresh_running = await seed_backtest(
            session_factory,
            uuid4(),
            status=BACKTEST_STATUS_RUNNING,
            started_at=now - timedelta(minutes=1),
        )
        requeue_pending = await seed_backtest(
            session_factory,
            uuid4(),
            status=BACKTEST_STATUS_PENDING,
            created_at=now - timedelta(minutes=10),
        )
        dead_pending = await seed_backtest(
            session_factory,
            uuid4(),
            status=BACKTEST_STATUS_PENDING,
            created_at=now - timedelta(hours=2),
        )
        fresh_pending = await seed_backtest(
            session_factory, uuid4(), status=BACKTEST_STATUS_PENDING, created_at=now
        )
        completed = await seed_backtest(
            session_factory,
            uuid4(),
            status=BACKTEST_STATUS_COMPLETED,
            started_at=now - timedelta(days=2),
        )

        requeued: list[tuple[UUID, UUID]] = []

        def record_enqueue(backtest_id: UUID, tenant_id: UUID) -> str:
            requeued.append((backtest_id, tenant_id))
            return "task-r"

        monkeypatch.setattr("src.services.backtest_service._enqueue_run_backtest", record_enqueue)

        async with session_factory() as db:
            service = BacktestService(db, market_data_client=market_client())
            counts = await service.reap_stale_backtests(now=now)

        assert counts == {"running_failed": 1, "pending_requeued": 1, "pending_failed": 1}
        assert [backtest_id for backtest_id, _ in requeued] == [requeue_pending]

        status, error = await get_status(session_factory, stale_running)
        assert status == BACKTEST_STATUS_FAILED
        assert "worker" in (error or "").lower()

        status, error = await get_status(session_factory, dead_pending)
        assert status == BACKTEST_STATUS_FAILED
        assert "never picked up" in (error or "")

        for untouched, expected in (
            (fresh_running, BACKTEST_STATUS_RUNNING),
            (requeue_pending, BACKTEST_STATUS_PENDING),
            (fresh_pending, BACKTEST_STATUS_PENDING),
            (completed, BACKTEST_STATUS_COMPLETED),
        ):
            status, _ = await get_status(session_factory, untouched)
            assert status == expected


class TestOneResultPerBacktest:
    @staticmethod
    def _result_row(backtest_id: UUID) -> BacktestResult:
        return BacktestResult(
            backtest_id=backtest_id,
            total_return=Decimal("0.1"),
            annual_return=Decimal("0.1"),
            sharpe_ratio=Decimal("1.0"),
            max_drawdown=Decimal("0.05"),
            win_rate=Decimal("0.5"),
            total_trades=1,
            winning_trades=1,
            losing_trades=0,
            avg_trade_return=Decimal("0.1"),
            final_equity=Decimal("110000"),
        )

    async def test_second_result_row_is_rejected(self, session_factory) -> None:
        """The reaper's duplicate-run safety argument: one result row per backtest."""
        tenant_id = uuid4()
        backtest_id = await seed_backtest(
            session_factory, tenant_id, status=BACKTEST_STATUS_RUNNING
        )

        async with session_factory() as db:
            db.add(self._result_row(backtest_id))
            await db.commit()

        async with session_factory() as db:
            db.add(self._result_row(backtest_id))
            with pytest.raises(IntegrityError):
                await db.commit()

        assert await result_count(session_factory, backtest_id) == 1


class TestResetToPending:
    @pytest.fixture
    def worker_db(self, postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
        """Point the Celery worker's session scope at the container database."""
        from src.workers import celery_tasks

        monkeypatch.setattr(celery_tasks, "DATABASE_URL", postgres_url)

    async def test_failed_row_is_reset_to_pending(self, session_factory, worker_db) -> None:
        from src.workers import celery_tasks

        tenant_id = uuid4()
        backtest_id = await seed_backtest(session_factory, tenant_id, status=BACKTEST_STATUS_FAILED)
        async with session_factory() as db:
            row = (
                await db.execute(select(Backtest).where(Backtest.id == backtest_id))
            ).scalar_one()
            row.error_message = "market data down"
            await db.commit()

        await celery_tasks._reset_to_pending(str(backtest_id), str(tenant_id))

        status, error = await get_status(session_factory, backtest_id)
        assert status == BACKTEST_STATUS_PENDING
        assert error is None

    async def test_non_failed_rows_are_untouched(self, session_factory, worker_db) -> None:
        from src.workers import celery_tasks

        tenant_id = uuid4()
        completed = await seed_backtest(
            session_factory, tenant_id, status=BACKTEST_STATUS_COMPLETED
        )
        running = await seed_backtest(session_factory, tenant_id, status=BACKTEST_STATUS_RUNNING)

        await celery_tasks._reset_to_pending(str(completed), str(tenant_id))
        await celery_tasks._reset_to_pending(str(running), str(tenant_id))

        status, _ = await get_status(session_factory, completed)
        assert status == BACKTEST_STATUS_COMPLETED
        status, _ = await get_status(session_factory, running)
        assert status == BACKTEST_STATUS_RUNNING

    async def test_reset_is_tenant_scoped(self, session_factory, worker_db) -> None:
        from src.workers import celery_tasks

        tenant_id = uuid4()
        backtest_id = await seed_backtest(session_factory, tenant_id, status=BACKTEST_STATUS_FAILED)

        await celery_tasks._reset_to_pending(str(backtest_id), str(uuid4()))

        status, _ = await get_status(session_factory, backtest_id)
        assert status == BACKTEST_STATUS_FAILED
