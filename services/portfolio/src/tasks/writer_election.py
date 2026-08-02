"""Continuous single-writer election for the ledger sweep loops.

The reconciliation, equity-snapshot and corporate-action sweeps must run on
exactly one pod: two writers double-write drift events, duplicate equity-curve
points and report the same corporate action twice. A ``pg_try_advisory_lock``
picks the leader, but taking it once at startup is not enough — a leader whose
backend dies (failover, a server-side timeout) reconnects through the pre-pinging
pool and keeps sweeping alongside the peer that won the freed lock.

So election runs for the life of the process: acquire, sweep while the lease
proves out on its own connection before every pass, then release and stand for
election again. The sweeps stop themselves the moment the probe fails; the lease
loss also wakes them out of their interval sleeps, so re-election is prompt
rather than one reconcile interval later.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.ports import PriceProvider
from src.tasks.corporate_actions import corporate_actions_loop
from src.tasks.equity_snapshot import snapshot_loop
from src.tasks.fill_ingestion import LEDGER_WRITER_ACTIVE, acquire_ledger_writer_lease
from src.tasks.reconciliation import reconciliation_loop
from src.tasks.supervisor import supervise

logger = logging.getLogger(__name__)

DEFAULT_ELECTION_INTERVAL_SECONDS = 30.0


async def _mirror(source: asyncio.Event, target: asyncio.Event) -> None:
    """Set ``target`` once ``source`` fires (used to fold two stop signals into one)."""
    await source.wait()
    target.set()


async def ledger_writer_loop(
    session_factory: async_sessionmaker[AsyncSession],
    prices_provider: PriceProvider,
    *,
    stop_event: asyncio.Event,
    reconcile_interval_seconds: float,
    snapshot_interval_seconds: float,
    corporate_actions_interval_seconds: float,
    election_interval_seconds: float = DEFAULT_ELECTION_INTERVAL_SECONDS,
    on_leadership: Callable[[bool], None] | None = None,
) -> None:  # pragma: no cover - election shell, fencing covered by the failover suite
    """Lead the ledger writes while this pod holds the lock; re-elect when it doesn't.

    ``on_leadership`` reports each transition so the health surface can say
    whether this pod is the writer. Returns when ``stop_event`` is set.
    """
    while not stop_event.is_set():
        candidate = await acquire_ledger_writer_lease(session_factory)
        if candidate is None:
            logger.info("ledger-writer lock held by another pod; this pod ingests fills only")
            await _wait(stop_event, election_interval_seconds)
            continue
        lease = candidate

        logger.info("acquired ledger-writer lock; this pod writes reconciliation + snapshots")
        LEDGER_WRITER_ACTIVE.set(1.0)
        if on_leadership is not None:
            on_leadership(True)
        # One stop signal for the sweeps: process shutdown OR leadership loss.
        leader_stop = asyncio.Event()
        mirrors = [
            asyncio.create_task(_mirror(stop_event, leader_stop)),
            asyncio.create_task(_mirror(lease.lost, leader_stop)),
        ]
        try:
            await asyncio.gather(
                supervise(
                    lambda: reconciliation_loop(
                        session_factory,
                        interval_seconds=reconcile_interval_seconds,
                        stop_event=leader_stop,
                        is_leader=lease.is_leader,
                    ),
                    name="reconciliation",
                    stop_event=leader_stop,
                ),
                supervise(
                    lambda: snapshot_loop(
                        session_factory,
                        prices_provider,
                        stop_event=leader_stop,
                        interval_seconds=snapshot_interval_seconds,
                        is_leader=lease.is_leader,
                    ),
                    name="snapshot",
                    stop_event=leader_stop,
                ),
                # Detection only proposes corporate actions but reads the whole account set once a night — one pod is enough, and the operator-facing log line must not appear once per replica.
                supervise(
                    lambda: corporate_actions_loop(
                        session_factory,
                        stop_event=leader_stop,
                        interval_seconds=corporate_actions_interval_seconds,
                        is_leader=lease.is_leader,
                    ),
                    name="corporate-actions",
                    stop_event=leader_stop,
                ),
            )
        finally:
            for task in mirrors:
                task.cancel()
            await asyncio.gather(*mirrors, return_exceptions=True)
            LEDGER_WRITER_ACTIVE.set(0.0)
            if on_leadership is not None:
                on_leadership(False)
            await lease.release()

        if not stop_event.is_set():
            logger.warning("ledger-writer leadership ended; standing for election again")
            await _wait(stop_event, election_interval_seconds)


async def _wait(stop_event: asyncio.Event, seconds: float) -> None:
    """Sleep up to ``seconds``, waking early on shutdown."""
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except TimeoutError:
        pass
