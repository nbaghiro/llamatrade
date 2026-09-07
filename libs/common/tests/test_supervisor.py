"""Tests for crash-restart supervision (``supervise``)."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine

import pytest

from llamatrade_common.supervisor import supervise


class TestRestartBehavior:
    async def test_clean_completion_returns_without_restart(self) -> None:
        calls = 0

        async def loop() -> None:
            nonlocal calls
            calls += 1

        await supervise(loop, name="clean", stop_event=asyncio.Event(), base_delay=0.001)

        assert calls == 1

    async def test_restarts_after_crashes_until_clean_exit(self) -> None:
        calls = 0

        async def flaky() -> None:
            nonlocal calls
            calls += 1
            if calls < 3:
                raise RuntimeError("boom")

        await supervise(flaky, name="flaky", stop_event=asyncio.Event(), base_delay=0.001)

        assert calls == 3

    async def test_preset_stop_event_skips_run(self) -> None:
        stop = asyncio.Event()
        stop.set()
        calls = 0

        async def loop() -> None:
            nonlocal calls
            calls += 1

        await supervise(loop, name="preset", stop_event=stop)

        assert calls == 0


class TestBackoff:
    async def test_backoff_doubles_and_caps(self, monkeypatch: pytest.MonkeyPatch) -> None:
        delays: list[float] = []

        async def instant_timeout(
            awaitable: Coroutine[object, object, bool], timeout: float
        ) -> None:
            awaitable.close()
            delays.append(timeout)
            raise TimeoutError

        monkeypatch.setattr("llamatrade_common.supervisor.asyncio.wait_for", instant_timeout)

        stop = asyncio.Event()
        crashes = 0

        async def always_crash() -> None:
            nonlocal crashes
            crashes += 1
            if crashes == 6:
                stop.set()
            raise RuntimeError("boom")

        await supervise(
            always_crash, name="crashy", stop_event=stop, base_delay=1.0, max_delay=30.0
        )

        assert delays == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0]

    async def test_stop_during_backoff_prevents_restart(self) -> None:
        stop = asyncio.Event()
        crashed = asyncio.Event()
        calls = 0

        async def crash_once() -> None:
            nonlocal calls
            calls += 1
            crashed.set()
            raise RuntimeError("boom")

        # base_delay far exceeds the guard timeout: only the stop_event can unblock it.
        task = asyncio.create_task(
            supervise(crash_once, name="stopped", stop_event=stop, base_delay=30.0)
        )
        await crashed.wait()
        stop.set()

        await asyncio.wait_for(task, timeout=1.0)
        assert calls == 1


class TestCancellation:
    async def test_cancellation_propagates_from_running_coroutine(self) -> None:
        started = asyncio.Event()

        async def hang() -> None:
            started.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(supervise(hang, name="hang", stop_event=asyncio.Event()))
        await started.wait()
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_cancellation_propagates_during_backoff(self) -> None:
        crashed = asyncio.Event()

        async def crash() -> None:
            crashed.set()
            raise RuntimeError("boom")

        task = asyncio.create_task(
            supervise(crash, name="backoff", stop_event=asyncio.Event(), base_delay=30.0)
        )
        await crashed.wait()
        await asyncio.sleep(0.01)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
