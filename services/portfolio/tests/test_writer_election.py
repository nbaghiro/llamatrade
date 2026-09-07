"""The ledger-writer election loop, executed rather than inspected.

The three sweeps must run on exactly one pod: two writers double-write drift
events, duplicate equity-curve points and report the same corporate action
twice. ``ledger_writer_loop`` is what keeps that true over time, standing for
election again whenever the lease is lost.

Until now the loop had no executed coverage at all. Two tests parsed its source
with ``ast`` and asserted the shape of its calls, which pins the wiring but
passes regardless of what the loop does at runtime, and the failover suite it
defers to covers ``acquire_ledger_writer_lease``, the lease itself, not the
election around it. These drive the real coroutine with fake sweeps.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.tasks import writer_election
from src.tasks.writer_election import ledger_writer_loop

pytestmark = pytest.mark.asyncio

INTERVALS = {
    "reconcile_interval_seconds": 0.01,
    "snapshot_interval_seconds": 0.01,
    "corporate_actions_interval_seconds": 0.01,
    "election_interval_seconds": 0.01,
}


class FakeLease:
    """A leadership handle whose loss can be triggered from the test."""

    def __init__(self) -> None:
        self.lost = asyncio.Event()
        self.released = 0

    async def is_leader(self) -> bool:
        return not self.lost.is_set()

    async def release(self) -> None:
        self.released += 1


class SweepRecorder:
    """Stands in for a sweep loop: records its arguments, runs until stopped."""

    def __init__(self) -> None:
        self.starts = 0
        self.stop_events: list[asyncio.Event] = []
        self.probes: list[Any] = []
        self.running = asyncio.Event()

    async def __call__(self, *_args: Any, stop_event: asyncio.Event, is_leader: Any, **_kw: Any):
        self.starts += 1
        self.stop_events.append(stop_event)
        self.probes.append(is_leader)
        self.running.set()
        await stop_event.wait()


@pytest.fixture
def sweeps(monkeypatch: pytest.MonkeyPatch) -> dict[str, SweepRecorder]:
    """Replace the three writer-gated sweeps with recorders."""
    recorders = {
        "reconciliation_loop": SweepRecorder(),
        "snapshot_loop": SweepRecorder(),
        "corporate_actions_loop": SweepRecorder(),
    }
    for name, recorder in recorders.items():
        monkeypatch.setattr(writer_election, name, recorder)
    return recorders


def _run_loop(stop_event: asyncio.Event, **kwargs: Any) -> asyncio.Task[None]:
    return asyncio.create_task(
        ledger_writer_loop(
            AsyncMock(),
            AsyncMock(),
            stop_event=stop_event,
            **{**INTERVALS, **kwargs},
        )
    )


class TestLeadershipAcquired:
    async def test_winning_the_lock_starts_all_three_sweeps_with_the_probe(
        self, sweeps: dict[str, SweepRecorder], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lease = FakeLease()
        monkeypatch.setattr(
            writer_election, "acquire_ledger_writer_lease", AsyncMock(return_value=lease)
        )
        stop = asyncio.Event()
        task = _run_loop(stop)

        for recorder in sweeps.values():
            await asyncio.wait_for(recorder.running.wait(), timeout=5)

        for name, recorder in sweeps.items():
            assert recorder.starts == 1, name
            # A sweep started without the probe would keep writing after the
            # pod lost the lock, which is the failure election prevents.
            assert recorder.probes[0] == lease.is_leader, name

        stop.set()
        await asyncio.wait_for(task, timeout=5)

    async def test_leadership_is_reported_and_released_on_shutdown(
        self, sweeps: dict[str, SweepRecorder], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lease = FakeLease()
        monkeypatch.setattr(
            writer_election, "acquire_ledger_writer_lease", AsyncMock(return_value=lease)
        )
        transitions: list[bool] = []
        stop = asyncio.Event()
        task = _run_loop(stop, on_leadership=transitions.append)

        await asyncio.wait_for(sweeps["snapshot_loop"].running.wait(), timeout=5)
        assert transitions == [True]

        stop.set()
        await asyncio.wait_for(task, timeout=5)

        assert transitions == [True, False]
        assert lease.released == 1

    async def test_process_shutdown_stops_the_sweeps(
        self, sweeps: dict[str, SweepRecorder], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The sweeps take their own stop event, mirrored from the process one."""
        lease = FakeLease()
        monkeypatch.setattr(
            writer_election, "acquire_ledger_writer_lease", AsyncMock(return_value=lease)
        )
        stop = asyncio.Event()
        task = _run_loop(stop)
        await asyncio.wait_for(sweeps["reconciliation_loop"].running.wait(), timeout=5)

        sweep_stop = sweeps["reconciliation_loop"].stop_events[0]
        assert sweep_stop is not stop and not sweep_stop.is_set()

        stop.set()
        await asyncio.wait_for(task, timeout=5)

        assert sweep_stop.is_set()


class TestLeadershipLost:
    async def test_losing_the_lease_stops_the_sweeps_and_re_elects(
        self, sweeps: dict[str, SweepRecorder], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The failure this loop exists to prevent: sweeping past a lost lock."""
        first, second = FakeLease(), FakeLease()
        acquire = AsyncMock(side_effect=[first, second])
        monkeypatch.setattr(writer_election, "acquire_ledger_writer_lease", acquire)
        transitions: list[bool] = []
        stop = asyncio.Event()
        task = _run_loop(stop, on_leadership=transitions.append)

        await asyncio.wait_for(sweeps["snapshot_loop"].running.wait(), timeout=5)
        first_stop = sweeps["snapshot_loop"].stop_events[0]

        # The backend died: the lease latches lost.
        sweeps["snapshot_loop"].running.clear()
        first.lost.set()

        # The sweeps must stop, the lease must be released, and the pod stands again.
        await asyncio.wait_for(sweeps["snapshot_loop"].running.wait(), timeout=5)
        assert first_stop.is_set(), "the old sweeps kept running after the lease was lost"
        assert first.released == 1
        assert sweeps["snapshot_loop"].starts == 2
        assert sweeps["snapshot_loop"].stop_events[1] is not first_stop
        assert transitions[:3] == [True, False, True]

        stop.set()
        await asyncio.wait_for(task, timeout=5)

    async def test_the_second_term_uses_the_new_lease_probe(
        self, sweeps: dict[str, SweepRecorder], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Re-election must hand the sweeps the new lease, not the dead one."""
        first, second = FakeLease(), FakeLease()
        monkeypatch.setattr(
            writer_election,
            "acquire_ledger_writer_lease",
            AsyncMock(side_effect=[first, second]),
        )
        stop = asyncio.Event()
        task = _run_loop(stop)

        await asyncio.wait_for(sweeps["reconciliation_loop"].running.wait(), timeout=5)
        sweeps["reconciliation_loop"].running.clear()
        first.lost.set()
        await asyncio.wait_for(sweeps["reconciliation_loop"].running.wait(), timeout=5)

        probes = sweeps["reconciliation_loop"].probes
        assert probes[0] == first.is_leader
        assert probes[1] == second.is_leader

        stop.set()
        await asyncio.wait_for(task, timeout=5)


class TestLockHeldElsewhere:
    async def test_a_pod_that_loses_the_election_runs_no_sweeps(
        self, sweeps: dict[str, SweepRecorder], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        acquire = AsyncMock(return_value=None)
        monkeypatch.setattr(writer_election, "acquire_ledger_writer_lease", acquire)
        transitions: list[bool] = []
        stop = asyncio.Event()
        task = _run_loop(stop, on_leadership=transitions.append)

        await asyncio.sleep(0.05)
        stop.set()
        await asyncio.wait_for(task, timeout=5)

        assert all(r.starts == 0 for r in sweeps.values()), "a follower must not sweep"
        assert transitions == []
        assert acquire.await_count >= 2, "the follower must keep standing for election"

    async def test_shutdown_wakes_the_follower_out_of_its_wait(
        self, sweeps: dict[str, SweepRecorder], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The election wait must be interruptible, not a fixed sleep."""
        monkeypatch.setattr(
            writer_election, "acquire_ledger_writer_lease", AsyncMock(return_value=None)
        )
        stop = asyncio.Event()
        task = _run_loop(stop, election_interval_seconds=30.0)

        await asyncio.sleep(0.01)
        stop.set()

        await asyncio.wait_for(task, timeout=5)

    async def test_a_stop_before_the_first_election_never_acquires(
        self, sweeps: dict[str, SweepRecorder], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        acquire = AsyncMock(return_value=None)
        monkeypatch.setattr(writer_election, "acquire_ledger_writer_lease", acquire)
        stop = asyncio.Event()
        stop.set()

        await asyncio.wait_for(_run_loop(stop), timeout=5)

        acquire.assert_not_awaited()
