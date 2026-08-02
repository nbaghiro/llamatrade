"""Boot-time and periodic rehydration of live trading runners.

A ``StrategyRunner`` lives in-process (``RunnerManager``). When the pod that owns
a session dies, the ``trading_sessions`` row stays RUNNING/PAUSED but no runner
exists — the session looks alive yet trades nothing. This module re-attaches a
runner to every such session.

Cross-replica ownership is arbitrated by a per-session Postgres advisory lock
(the session-level ``pg_advisory_lock`` idiom the portfolio fill consumer uses):
only the pod that wins a session's lock runs it, so a horizontally scaled
trading deployment never double-runs a session. Both entry points take that
lock: this pass before it adopts a session, and ``StartSession`` for the
sessions it starts itself. The lock is held on a dedicated AUTOCOMMIT connection
for the runner's lifetime and frees automatically when the pod dies (connection
close) or when the runner is stopped here.

Holding the lease is not the same as still owning it. A backend can go away
under a live pod (failover, a server-side timeout), taking the lock with it
while the in-memory registry still says "mine" — so every claim, and every
rehydrate pass, re-asks the lease's own connection. A pod that lost its lease
stops the affected runner rather than trading against the peer that adopted the
session.

The pass runs on a supervised interval (not only at boot): a session whose owner
died is reclaimed by a survivor within one tick, a session stopped on another
replica is dropped here, and a transient failure (e.g. Alpaca briefly
unreachable) is retried next tick rather than poisoning the session.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from llamatrade_db import (
    advisory_unlock,
    get_engine,
    holds_advisory_lock,
    system_session,
    try_advisory_lock,
)
from llamatrade_db.models.strategy import Strategy, StrategyExecution
from llamatrade_db.models.trading import TradingSession
from llamatrade_proto.generated.common_pb2 import (
    EXECUTION_STATUS_PAUSED,
    EXECUTION_STATUS_RUNNING,
)
from llamatrade_telemetry import counter

from src.runner.runner import RunnerManager

logger = logging.getLogger(__name__)

REHYDRATION_INTERVAL_SECONDS = int(os.getenv("TRADING_REHYDRATION_INTERVAL_SECONDS", "30"))

# RUNNING executions younger than this are skipped by adoption — the client may still be mid-deploy, about to call StartSession itself.
ADOPT_EXECUTION_GRACE_SECONDS = int(os.getenv("TRADING_ADOPT_EXECUTION_GRACE_SECONDS", "120"))

# Sessions this pod owns → the open connection holding that session's advisory lock; closing it (here or on pod death) releases the lock so another pod can claim the session.
_leases: dict[UUID, AsyncConnection] = {}

SESSION_LEASES_LOST = counter(
    "llamatrade_trading_session_leases_lost_total",
    (),
    "Session ownership leases found dead on their own connection",
)


@dataclass(frozen=True)
class _RunnerSpec:
    """Immutable snapshot of a session row (read before its DB session closes)."""

    session_id: UUID
    tenant_id: UUID
    strategy_id: UUID
    strategy_version: int
    credentials_id: UUID
    mode: int
    symbols: tuple[str, ...]
    sleeve_id: UUID | None
    account_id: UUID | None
    paused: bool


def _session_lock_key(session_id: UUID) -> int:
    """Stable signed 64-bit advisory-lock key derived from a session id."""
    return int.from_bytes(session_id.bytes[:8], "big", signed=True)


async def _open_lease_connection() -> AsyncConnection:
    """A dedicated AUTOCOMMIT connection to hold one lease's advisory lock.

    Session-level locks live with the connection, not a transaction, so the lease
    needs no transaction at all. Running it in AUTOCOMMIT leaves the backend
    ``idle`` instead of ``idle in transaction``, which is what a managed
    Postgres' ``idle_in_transaction_session_timeout`` would otherwise kill —
    silently revoking the lease while this pod kept trading.
    """
    return await get_engine().execution_options(isolation_level="AUTOCOMMIT").connect()


async def _lease_is_live(session_id: UUID) -> bool:
    """Whether this pod's registered lease for ``session_id`` still holds its lock."""
    conn = _leases.get(session_id)
    if conn is None:
        return False
    return await holds_advisory_lock(conn, _session_lock_key(session_id))


async def _invalidate_lease(session_id: UUID) -> None:
    """Drop a lease whose connection no longer holds the lock (critical: split brain).

    The lock is already gone, so there is nothing to unlock — the entry is
    removed and the connection discarded. Callers stop whatever was running on
    the strength of that lease; a peer adopting the session is the recovery path.
    """
    conn = _leases.pop(session_id, None)
    SESSION_LEASES_LOST.inc()
    logger.critical(
        "lost the ownership lease for session %s (its connection no longer holds the lock); "
        "stopping local work so a peer can adopt it",
        session_id,
    )
    if conn is not None:
        with contextlib.suppress(Exception):
            await conn.close()


async def _try_claim(session_id: UUID) -> bool:
    """Win exclusive ownership of a session via a session-level advisory lock.

    On success the holding connection is kept open in ``_leases`` for the
    runner's lifetime. A registry entry is trusted only after its connection
    confirms it still holds the lock, so a torn holder re-claims for real (or
    finds the peer that took over) instead of answering from memory. Returns
    False if another pod already holds it.
    """
    if session_id in _leases:
        if await _lease_is_live(session_id):
            return True
        await _invalidate_lease(session_id)
    conn = await _open_lease_connection()
    try:
        got = await try_advisory_lock(conn, _session_lock_key(session_id))
    except Exception:
        await conn.close()
        raise
    if got:
        _leases[session_id] = conn
        return True
    await conn.close()
    return False


async def acquire_session_lease(session_id: UUID) -> bool:
    """Take a session's ownership lease from the normal start path.

    The rehydrate pass claims the same per-session advisory lock before adopting
    a session, so a session started here must hold it too: otherwise a peer
    replica sees a RUNNING row with no local runner and starts a second one.
    Returns False when another replica already owns the session.
    """
    return await _try_claim(session_id)


async def release_session_lease(session_id: UUID) -> None:
    """Release a session's advisory lock and close its holding connection.

    No-op if this pod holds no lease for the session (owned by another pod).
    Safe to call from the stop path: a torn connection is warned about, never
    raised, so shutdown after a failover still completes.
    """
    conn = _leases.pop(session_id, None)
    if conn is None:
        return
    try:
        await advisory_unlock(conn, _session_lock_key(session_id))
    except Exception:
        logger.warning("Failed to release advisory lock for session %s", session_id, exc_info=True)
    finally:
        with contextlib.suppress(Exception):
            await conn.close()


async def release_all_leases() -> None:
    """Release every held lease (shutdown)."""
    for session_id in list(_leases.keys()):
        await release_session_lease(session_id)


async def _load_live_specs() -> list[_RunnerSpec]:
    """Snapshot every RUNNING/PAUSED session (all tenants) into detachable specs."""
    async with system_session(reason="live-session rehydration sweep") as db:
        rows = list(
            await db.scalars(
                select(TradingSession).where(
                    TradingSession.status.in_([EXECUTION_STATUS_RUNNING, EXECUTION_STATUS_PAUSED])
                )
            )
        )
        return [
            _RunnerSpec(
                session_id=r.id,
                tenant_id=r.tenant_id,
                strategy_id=r.strategy_id,
                strategy_version=r.strategy_version,
                credentials_id=r.credentials_id,
                mode=r.mode,
                symbols=tuple(r.symbols or ()),
                sleeve_id=r.sleeve_id,
                account_id=r.account_id,
                paused=r.status == EXECUTION_STATUS_PAUSED,
            )
            for r in rows
        ]


async def _rehydrate_one(spec: _RunnerSpec) -> None:
    """Rebuild the runner for one claimed session via the normal start path."""
    from src.services.live_session_service import create_live_session_service

    service = await create_live_session_service(spec.tenant_id)
    try:
        await service.rehydrate_runner(
            session_id=spec.session_id,
            tenant_id=spec.tenant_id,
            strategy_id=spec.strategy_id,
            strategy_version=spec.strategy_version,
            credentials_id=spec.credentials_id,
            mode=spec.mode,
            symbols=list(spec.symbols) or None,
            sleeve_id=spec.sleeve_id,
            account_id=spec.account_id,
            paused=spec.paused,
        )
    finally:
        await service.aclose()


@dataclass(frozen=True)
class _ExecutionSpec:
    """Snapshot of an orphaned RUNNING execution eligible for adoption."""

    execution_id: UUID
    tenant_id: UUID
    strategy_id: UUID
    strategy_version: int
    mode: int
    credentials_id: UUID
    user_id: UUID


def _as_utc(dt: datetime) -> datetime:
    """Naive DB timestamps are UTC by convention; make them comparable."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _orphan_specs(
    rows: list[tuple[StrategyExecution, UUID]],
    live_sleeves: set[UUID],
    now: datetime,
) -> list[_ExecutionSpec]:
    """Filter RUNNING executions down to adoptable orphans.

    Drops executions whose sleeve is already traded by a live session, whose
    funding never completed (no credentials), or which are still inside the
    deploy grace window (the client may be about to call StartSession).
    """
    cutoff = now - timedelta(seconds=ADOPT_EXECUTION_GRACE_SECONDS)
    specs: list[_ExecutionSpec] = []
    for execution, created_by in rows:
        if execution.sleeve_id in live_sleeves:
            continue
        if execution.credentials_id is None:
            continue
        started = execution.started_at or execution.created_at
        if _as_utc(started) > cutoff:
            continue
        specs.append(
            _ExecutionSpec(
                execution_id=execution.id,
                tenant_id=execution.tenant_id,
                strategy_id=execution.strategy_id,
                strategy_version=execution.version,
                mode=execution.mode,
                credentials_id=execution.credentials_id,
                user_id=created_by,
            )
        )
    return specs


async def _load_orphaned_executions() -> list[_ExecutionSpec]:
    """Funded RUNNING executions (all tenants) with no live session on their sleeve."""
    async with system_session(reason="orphaned-execution adoption sweep") as db:
        live_sleeves = {
            sleeve_id
            for sleeve_id in await db.scalars(
                select(TradingSession.sleeve_id).where(
                    TradingSession.status.in_([EXECUTION_STATUS_RUNNING, EXECUTION_STATUS_PAUSED]),
                    TradingSession.sleeve_id.is_not(None),
                )
            )
            if sleeve_id is not None
        }
        rows = [
            (execution, created_by)
            for execution, created_by in await db.execute(
                select(StrategyExecution, Strategy.created_by)
                .join(Strategy, Strategy.id == StrategyExecution.strategy_id)
                .where(
                    StrategyExecution.status == EXECUTION_STATUS_RUNNING,
                    StrategyExecution.sleeve_id.is_not(None),
                )
            )
        ]
        return _orphan_specs(rows, live_sleeves, datetime.now(UTC))


async def _adopt_one(spec: _ExecutionSpec) -> UUID:
    """Start a session for one claimed orphaned execution via the normal start path."""
    from src.services.live_session_service import create_live_session_service

    service = await create_live_session_service(spec.tenant_id)
    try:
        response = await service.start_session(
            tenant_id=spec.tenant_id,
            user_id=spec.user_id,
            strategy_id=spec.strategy_id,
            strategy_version=spec.strategy_version,
            name="Recovered strategy session",
            mode=spec.mode,
            credentials_id=spec.credentials_id,
            execution_id=spec.execution_id,
        )
        return response.id
    finally:
        await service.aclose()


async def adopt_orphaned_executions() -> int:
    """Adopt funded RUNNING executions whose StartSession never happened.

    Without this, an execution funded and marked RUNNING whose start call was
    lost (client crash, deploy race) stays a permanently funded orphan. Each
    candidate is claimed via the same advisory-lock idiom as sessions — keyed
    off the execution id, since no session exists yet — so scaled replicas
    never double-adopt. Returns the number of sessions started.
    """
    adopted = 0
    for spec in await _load_orphaned_executions():
        if spec.execution_id in _leases:
            continue  # adoption already in flight on this pod
        try:
            if not await _try_claim(spec.execution_id):
                continue  # another pod is adopting it
        except Exception:
            logger.warning(
                "Advisory-lock claim failed for execution %s", spec.execution_id, exc_info=True
            )
            continue
        try:
            session_id = await _adopt_one(spec)
            adopted += 1
            logger.info(
                "Adopted orphaned RUNNING execution %s as session %s",
                spec.execution_id,
                session_id,
            )
            # Own the new session's lease so peers don't re-claim it next tick.
            try:
                await _try_claim(session_id)
            except Exception:
                logger.warning("Could not lease adopted session %s", session_id, exc_info=True)
        except Exception:
            logger.warning(
                "Adoption failed for execution %s; will retry next tick",
                spec.execution_id,
                exc_info=True,
            )
        finally:
            await release_session_lease(spec.execution_id)
    return adopted


async def sweep_dead_leases(runner_manager: RunnerManager) -> list[UUID]:
    """Probe every held lease and fail-safe the ones whose lock is gone.

    This is the heartbeat: a lease connection can die under a live pod without
    anything on the trading path noticing, leaving this pod trading a session a
    peer has already adopted. Each dead lease is dropped from the registry and
    its runner stopped; the peer's adoption is the recovery path. Returns the
    invalidated session ids.
    """
    lost: list[UUID] = []
    for session_id in list(_leases):
        if await _lease_is_live(session_id):
            continue
        await _invalidate_lease(session_id)
        lost.append(session_id)
        try:
            await runner_manager.stop_runner(session_id)
        except Exception:
            logger.exception("Failed to stop the runner for lost lease %s", session_id)
    return lost


async def rehydrate_pass(runner_manager: RunnerManager) -> int:
    """One reclaim pass: claim + start unowned live sessions, drop stopped ones.

    Starts by heartbeating the leases this pod holds, so a torn lease stops its
    runner before the pass decides what it still owns. Returns the number of
    runners started this pass.
    """
    await sweep_dead_leases(runner_manager)
    specs = await _load_live_specs()
    live_ids = {s.session_id for s in specs}

    # Drop leases for sessions no longer live (stopped/errored, possibly on another replica): stop our runner and free the lock.
    for session_id in list(_leases.keys()):
        if session_id not in live_ids:
            if session_id in runner_manager.active_runners:
                await runner_manager.stop_runner(session_id)
            await release_session_lease(session_id)

    started = 0
    for spec in specs:
        # Live only if a runner exists here AND is still running: a runner whose loops exited leaves the row RUNNING with a dead in-process runner, so evict it first and re-claim (presence alone would skip it forever).
        existing = runner_manager.get_runner(spec.session_id)
        if existing is not None and existing.running:
            continue
        if existing is not None:
            logger.warning(
                "Runner for session %s is present but not running; evicting before re-claim",
                spec.session_id,
            )
            with contextlib.suppress(Exception):
                await runner_manager.stop_runner(spec.session_id)
        try:
            if not await _try_claim(spec.session_id):
                continue  # another pod owns it
        except Exception:
            logger.warning(
                "Advisory-lock claim failed for session %s", spec.session_id, exc_info=True
            )
            continue
        try:
            await _rehydrate_one(spec)
            started += 1
            logger.info("Rehydrated runner for session %s", spec.session_id)
        except Exception:
            logger.warning(
                "Rehydration failed for session %s; will retry next tick",
                spec.session_id,
                exc_info=True,
            )
            # Free the lock so this or another pod retries, rather than holding a session we couldn't start.
            await release_session_lease(spec.session_id)
    return started


async def rehydration_loop(runner_manager: RunnerManager, stop_event: asyncio.Event) -> None:
    """Supervised loop: run a reclaim pass now and every interval until stopped."""
    while not stop_event.is_set():
        try:
            await rehydrate_pass(runner_manager)
        except Exception:
            logger.exception("Rehydration pass crashed; continuing")
        try:
            await adopt_orphaned_executions()
        except Exception:
            logger.exception("Execution adoption pass crashed; continuing")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=REHYDRATION_INTERVAL_SECONDS)
        except TimeoutError:
            pass
