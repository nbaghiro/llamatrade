"""Tests for the strategy background stranded-sleeve sweep."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

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
