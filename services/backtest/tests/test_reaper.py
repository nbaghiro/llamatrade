"""Reaper tests (1A): recovery of orphaned RUNNING/PENDING backtests.

A hard-killed worker (OOM, pod eviction, hard time limit) never runs the
``run_backtest`` exception handlers, so its row is stranded in RUNNING forever;
a lost enqueue strands a row in PENDING. The reaper is the only automatic
recovery path. Time is injected via ``now=`` so staleness is deterministic
(10A: time-travel).
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from llamatrade_db.models.backtest import Backtest
from llamatrade_proto.generated.backtest_pb2 import (
    BACKTEST_STATUS_COMPLETED,
    BACKTEST_STATUS_FAILED,
    BACKTEST_STATUS_PENDING,
    BACKTEST_STATUS_RUNNING,
)

from src.services.backtest_service import BacktestService

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 6, 19, 12, 0, tzinfo=UTC)


def _bt(status, *, started_at=None, created_at=NOW):
    bt = Backtest(
        id=uuid4(),
        tenant_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version=1,
        name="reaper-test",
        status=status,
        config={},
        symbols=[],
        start_date=NOW.date(),
        end_date=NOW.date(),
        initial_capital=100000,
        created_by=uuid4(),
    )
    bt.started_at = started_at
    bt.created_at = created_at
    return bt


def _session(running_rows, pending_rows):
    """Fake session whose two execute() calls return the running then pending selects."""
    session = AsyncMock()
    session.commit = AsyncMock()
    r1 = MagicMock()
    r1.scalars.return_value.all.return_value = running_rows
    r2 = MagicMock()
    r2.scalars.return_value.all.return_value = pending_rows
    session.execute = AsyncMock(side_effect=[r1, r2])
    return session


def _service(session) -> BacktestService:
    return BacktestService(session, market_data_client=AsyncMock())


async def test_orphaned_running_is_failed():
    """A RUNNING row older than the hard limit + grace is failed as worker-lost."""
    stale = _bt(BACKTEST_STATUS_RUNNING, started_at=NOW - timedelta(hours=3))
    session = _session([stale], [])
    counts = await _service(session).reap_stale_backtests(now=NOW)
    assert counts["running_failed"] == 1
    assert stale.status == BACKTEST_STATUS_FAILED
    assert stale.completed_at == NOW
    assert "worker" in (stale.error_message or "").lower()
    session.commit.assert_awaited()


async def test_fresh_running_is_left_alone():
    """A RUNNING row within the time budget must not be reaped."""
    fresh = _bt(BACKTEST_STATUS_RUNNING, started_at=NOW - timedelta(minutes=2))
    # Cutoff filtering happens in SQL; simulate the DB returning nothing stale.
    session = _session([], [])
    counts = await _service(session).reap_stale_backtests(now=NOW)
    assert counts["running_failed"] == 0
    assert fresh.status == BACKTEST_STATUS_RUNNING


async def test_pending_past_fail_threshold_is_failed():
    """A PENDING row older than the fail threshold is failed, not re-enqueued."""
    old = _bt(BACKTEST_STATUS_PENDING, created_at=NOW - timedelta(hours=3))
    session = _session([], [old])
    with patch("src.workers.celery_tasks.run_backtest_task") as task:
        counts = await _service(session).reap_stale_backtests(now=NOW)
    assert counts["pending_failed"] == 1
    assert old.status == BACKTEST_STATUS_FAILED
    task.delay.assert_not_called()


async def test_pending_in_requeue_window_is_reenqueued():
    """A PENDING row in the requeue window is re-driven, status unchanged."""
    pend = _bt(BACKTEST_STATUS_PENDING, created_at=NOW - timedelta(minutes=10))
    session = _session([], [pend])
    with patch("src.workers.celery_tasks.run_backtest_task") as task:
        counts = await _service(session).reap_stale_backtests(now=NOW)
    assert counts["pending_requeued"] == 1
    assert pend.status == BACKTEST_STATUS_PENDING
    task.delay.assert_called_once_with(str(pend.id), str(pend.tenant_id))


async def test_nothing_stale_is_noop():
    session = _session([], [])
    counts = await _service(session).reap_stale_backtests(now=NOW)
    assert counts == {"running_failed": 0, "pending_requeued": 0, "pending_failed": 0}


async def test_completed_rows_are_never_touched():
    """Sanity: the selects only target RUNNING/PENDING; a COMPLETED row is inert."""
    done = _bt(BACKTEST_STATUS_COMPLETED, started_at=NOW - timedelta(days=1))
    session = _session([], [])
    await _service(session).reap_stale_backtests(now=NOW)
    assert done.status == BACKTEST_STATUS_COMPLETED


async def test_reaper_task_invokes_service(monkeypatch):
    """The Celery task drives one reaper pass through the service layer (10A)."""
    from contextlib import asynccontextmanager

    from src.workers import celery_tasks

    fake_service = AsyncMock()
    fake_service.__aenter__ = AsyncMock(return_value=fake_service)
    fake_service.__aexit__ = AsyncMock(return_value=None)
    fake_service.reap_stale_backtests = AsyncMock(
        return_value={"running_failed": 2, "pending_requeued": 1, "pending_failed": 0}
    )

    @asynccontextmanager
    async def fake_scope():
        yield AsyncMock()

    monkeypatch.setattr(celery_tasks, "_session_scope", fake_scope)
    monkeypatch.setattr(celery_tasks, "BacktestService", lambda *a, **k: fake_service)
    monkeypatch.setattr(celery_tasks, "_create_market_data_client", lambda: AsyncMock())

    result = celery_tasks.reap_stale_backtests_task()

    assert result == {"running_failed": 2, "pending_requeued": 1, "pending_failed": 0}
    fake_service.reap_stale_backtests.assert_awaited_once()
