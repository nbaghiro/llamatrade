"""Boot-time and periodic rehydration of live trading runners.

A ``StrategyRunner`` lives in-process (``RunnerManager``). When the pod that owns
a session dies, the ``trading_sessions`` row stays RUNNING/PAUSED but no runner
exists — the session looks alive yet trades nothing. This module re-attaches a
runner to every such session.

Cross-replica ownership is arbitrated by a per-session Postgres advisory lock
(the session-level ``pg_advisory_lock`` idiom the portfolio fill consumer uses):
only the pod that wins a session's lock rehydrates it, so a horizontally scaled
trading deployment never double-runs a session. The lock is held on a dedicated
connection for the runner's lifetime and frees automatically when the pod dies
(connection close) or when the runner is stopped here.

The pass runs on a supervised interval (not only at boot): a session whose owner
died is reclaimed by a survivor within one tick, a session stopped on another
replica is dropped here, and a transient failure (e.g. Alpaca briefly
unreachable) is retried next tick rather than poisoning the session.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db import get_session_maker, system_session
from llamatrade_db.models.trading import TradingSession
from llamatrade_proto.generated.common_pb2 import (
    EXECUTION_STATUS_PAUSED,
    EXECUTION_STATUS_RUNNING,
)

from src.runner.runner import RunnerManager

logger = logging.getLogger(__name__)

REHYDRATION_INTERVAL_SECONDS = int(os.getenv("TRADING_REHYDRATION_INTERVAL_SECONDS", "30"))

# Sessions this pod currently owns → the open connection holding that session's
# advisory lock. The connection stays open for the runner's lifetime; closing it
# (here or on pod death) releases the lock so another pod can claim the session.
_leases: dict[UUID, AsyncSession] = {}


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


async def _try_claim(session_id: UUID) -> bool:
    """Win exclusive ownership of a session via a session-level advisory lock.

    On success the holding connection is kept open in ``_leases`` for the
    runner's lifetime. Returns False if another pod already holds it.
    """
    if session_id in _leases:
        return True
    db = get_session_maker()()
    try:
        got = await db.scalar(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": _session_lock_key(session_id)}
        )
    except Exception:
        await db.close()
        raise
    if got:
        _leases[session_id] = db
        return True
    await db.close()
    return False


async def release_session_lease(session_id: UUID) -> None:
    """Release a session's advisory lock and close its holding connection.

    No-op if this pod holds no lease for the session (started here, or owned by
    another pod). Safe to call from the stop path.
    """
    db = _leases.pop(session_id, None)
    if db is None:
        return
    try:
        await db.scalar(text("SELECT pg_advisory_unlock(:k)"), {"k": _session_lock_key(session_id)})
    except Exception:
        logger.warning("Failed to release advisory lock for session %s", session_id, exc_info=True)
    finally:
        await db.close()


async def release_all_leases() -> None:
    """Release every held lease (shutdown)."""
    for session_id in list(_leases.keys()):
        await release_session_lease(session_id)


async def _load_live_specs() -> list[_RunnerSpec]:
    """Snapshot every RUNNING/PAUSED session (all tenants) into detachable specs."""
    async with system_session() as db:
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


async def rehydrate_pass(runner_manager: RunnerManager) -> int:
    """One reclaim pass: claim + start unowned live sessions, drop stopped ones.

    Returns the number of runners started this pass.
    """
    specs = await _load_live_specs()
    live_ids = {s.session_id for s in specs}

    # Drop leases for sessions no longer live (stopped/errored, possibly on
    # another replica): stop our runner and free the lock.
    for session_id in list(_leases.keys()):
        if session_id not in live_ids:
            if session_id in runner_manager.active_runners:
                await runner_manager.stop_runner(session_id)
            await release_session_lease(session_id)

    started = 0
    for spec in specs:
        # Already running here (started via StartSession or a prior pass).
        if runner_manager.get_runner(spec.session_id) is not None:
            continue
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
            # Free the lock so this or another pod retries, rather than holding a
            # session we couldn't start.
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
            await asyncio.wait_for(stop_event.wait(), timeout=REHYDRATION_INTERVAL_SECONDS)
        except TimeoutError:
            pass
