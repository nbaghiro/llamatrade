"""Tests for the strategy background stranded-sleeve sweep.

A terminal execution whose ledger close failed keeps ``sleeve_id`` set as a
"needs release" marker, and this loop is the only thing that retries it, so the
capital stays trapped if the schedule ever stops. The advisory lock is what keeps
scaled replicas from issuing the same ledger release twice.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src import tasks

pytestmark = pytest.mark.asyncio


async def test_try_run_pass_standby_when_lock_not_won() -> None:
    lock_db = AsyncMock()
    lock_db.scalar = AsyncMock(return_value=False)  # advisory lock held elsewhere

    with (
        patch.object(tasks, "get_session_maker", return_value=(lambda: lock_db)),
        patch.object(tasks, "_run_sweep", AsyncMock()) as sweep,
    ):
        result = await tasks._try_run_pass()

    assert result is None
    sweep.assert_not_called()
    lock_db.close.assert_awaited_once()


async def test_try_run_pass_runs_and_unlocks_when_won() -> None:
    lock_db = AsyncMock()
    lock_db.scalar = AsyncMock(return_value=True)  # lock acquired, then unlocked

    with (
        patch.object(tasks, "get_session_maker", return_value=(lambda: lock_db)),
        patch.object(tasks, "_run_sweep", AsyncMock(return_value=3)) as sweep,
    ):
        result = await tasks._try_run_pass()

    assert result == 3
    sweep.assert_awaited_once()
    assert lock_db.scalar.await_count == 2  # try_advisory_lock + advisory_unlock
    lock_db.close.assert_awaited_once()


async def test_try_run_pass_unlocks_when_the_sweep_raises() -> None:
    """A held lock would park the sweep on every replica for good."""
    lock_db = AsyncMock()
    lock_db.scalar = AsyncMock(return_value=True)

    with (
        patch.object(tasks, "get_session_maker", return_value=(lambda: lock_db)),
        patch.object(tasks, "_run_sweep", AsyncMock(side_effect=RuntimeError("ledger down"))),
        pytest.raises(RuntimeError),
    ):
        await tasks._try_run_pass()

    assert lock_db.scalar.await_count == 2  # the unlock still ran
    lock_db.close.assert_awaited_once()


async def test_loop_stops_promptly_when_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    """The interval wait must be interruptible, not a fixed sleep."""
    monkeypatch.setattr(tasks, "RECONCILE_INTERVAL_SECONDS", 30.0)
    monkeypatch.setattr(tasks, "_try_run_pass", AsyncMock(return_value=0))
    stop = asyncio.Event()

    task = asyncio.create_task(tasks.stranded_sleeve_loop(stop))
    await asyncio.sleep(0.01)
    stop.set()

    await asyncio.wait_for(task, timeout=5)


async def test_an_erroring_pass_does_not_stop_the_schedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One bad pass must not end the only retry path for trapped capital."""
    monkeypatch.setattr(tasks, "RECONCILE_INTERVAL_SECONDS", 0.01)
    calls = {"n": 0}

    async def _pass() -> int:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return 1

    monkeypatch.setattr(tasks, "_try_run_pass", _pass)
    stop = asyncio.Event()

    task = asyncio.create_task(tasks.stranded_sleeve_loop(stop))
    while calls["n"] < 2:
        await asyncio.sleep(0.01)
    stop.set()
    await asyncio.wait_for(task, timeout=5)

    assert calls["n"] >= 2


async def test_loop_reports_how_many_sleeves_were_released(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(tasks, "RECONCILE_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(tasks, "_try_run_pass", AsyncMock(return_value=2))
    stop = asyncio.Event()

    with caplog.at_level("INFO"):
        task = asyncio.create_task(tasks.stranded_sleeve_loop(stop))
        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(task, timeout=5)

    assert "released 2 stranded sleeve(s)" in caplog.text


async def test_run_sweep_uses_a_system_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """The sweep spans tenants, so it must not run under a tenant-scoped session."""
    service = MagicMock()
    service.reconcile_stranded_sleeves = AsyncMock(return_value=4)
    captured: dict[str, Any] = {}

    class _SystemSession:
        def __init__(self, *, reason: str) -> None:
            captured["reason"] = reason

        async def __aenter__(self) -> Any:
            return MagicMock()

        async def __aexit__(self, *_exc: object) -> None:
            return None

    with (
        patch("src.services.strategy_service.StrategyService", MagicMock(return_value=service)),
        patch("llamatrade_proto.clients.ledger.LedgerClient", MagicMock()),
        patch.object(tasks, "system_session", _SystemSession),
    ):
        released = await tasks._run_sweep()

    assert released == 4
    assert "stranded" in captured["reason"]
    assert service.reconcile_stranded_sleeves.await_args.kwargs["ledger"] is not None
