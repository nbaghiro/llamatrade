"""Ledger-loop supervision + fill-lag tracking."""

import asyncio

import pytest

from src.tasks.fill_ingestion import FillLagTracker
from src.tasks.supervisor import supervise


async def test_supervise_restarts_until_clean_completion() -> None:
    calls = {"n": 0}
    stop = asyncio.Event()

    async def flaky() -> None:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("boom")  # crash twice, then return cleanly

    await supervise(flaky, name="t", stop_event=stop, base_delay=0.001, max_delay=0.001)
    assert calls["n"] == 3  # restarted after each crash, stopped on clean return


async def test_supervise_stops_when_stop_event_set() -> None:
    stop = asyncio.Event()

    async def crash_then_stop() -> None:
        stop.set()  # request shutdown, then crash
        raise RuntimeError("boom")

    # The post-crash backoff sees stop set, so the loop exits rather than restart.
    await asyncio.wait_for(
        supervise(crash_then_stop, name="t", stop_event=stop, base_delay=0.001), timeout=1.0
    )


async def test_supervise_propagates_cancellation() -> None:
    stop = asyncio.Event()

    async def runs_forever() -> None:
        await asyncio.Event().wait()

    task = asyncio.create_task(supervise(runs_forever, name="t", stop_event=stop))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_lag_tracker_trips_after_sustained_backlog() -> None:
    tracker = FillLagTracker(threshold=100, sustained_samples=3)
    tracker.record(200)
    assert tracker.is_backlogged is False
    tracker.record(200)
    assert tracker.is_backlogged is False
    tracker.record(200)
    assert tracker.is_backlogged is True


def test_lag_tracker_resets_when_drained() -> None:
    tracker = FillLagTracker(threshold=100, sustained_samples=2)
    tracker.record(200)
    tracker.record(200)
    assert tracker.is_backlogged is True
    tracker.record(50)  # drained below threshold
    assert tracker.is_backlogged is False


def test_lag_tracker_at_threshold_does_not_trip() -> None:
    tracker = FillLagTracker(threshold=100, sustained_samples=1)
    tracker.record(100)  # not strictly above threshold
    assert tracker.is_backlogged is False
