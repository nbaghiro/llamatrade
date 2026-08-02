"""Background tasks for the strategy service.

The stranded-sleeve sweep retries sleeve release for terminal executions whose
ledger close earlier failed (a ledger outage during stop leaves ``sleeve_id`` set
as a "needs release" marker). Without it that capital is trapped indefinitely.

Each pass is gated by a per-pass Postgres advisory lock so scaled replicas don't
duplicate the ledger calls; whichever pod wins the lock that cycle runs the sweep,
so a dead pod is transparently taken over on the next tick.
"""

from __future__ import annotations

import asyncio
import logging
import os

from sqlalchemy import text

from llamatrade_db import get_session_maker, system_session

logger = logging.getLogger(__name__)

RECONCILE_INTERVAL_SECONDS = float(os.getenv("STRATEGY_RECONCILE_INTERVAL_SECONDS", "300"))
# Stable advisory-lock id ("strat" in hex) for the single active sweeper.
_RECONCILE_LOCK_KEY = 0x7374726174


async def _run_sweep() -> int:
    from llamatrade_proto.clients.ledger import LedgerClient

    from src.services.strategy_service import StrategyService

    ledger = LedgerClient(
        os.getenv("PORTFOLIO_GRPC_TARGET", "portfolio:8860"), service_name="strategy"
    )
    async with system_session(reason="strategy stranded-sleeve sweep") as db:
        return await StrategyService(db).reconcile_stranded_sleeves(ledger=ledger)


async def _try_run_pass() -> int | None:
    """Run one sweep if this pod wins the advisory lock, else None (standby)."""
    lock_db = get_session_maker()()
    try:
        if not await lock_db.scalar(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": _RECONCILE_LOCK_KEY}
        ):
            return None
        try:
            return await _run_sweep()
        finally:
            await lock_db.scalar(text("SELECT pg_advisory_unlock(:k)"), {"k": _RECONCILE_LOCK_KEY})
    finally:
        await lock_db.close()


async def stranded_sleeve_loop(stop_event: asyncio.Event) -> None:
    """Sweep stranded sleeves on an interval until ``stop_event`` is set."""
    logger.info("stranded-sleeve sweep loop started (interval=%ss)", RECONCILE_INTERVAL_SECONDS)
    while not stop_event.is_set():
        try:
            released = await _try_run_pass()
            if released:
                logger.info("released %d stranded sleeve(s)", released)
        except Exception:
            logger.exception("stranded-sleeve sweep pass errored")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=RECONCILE_INTERVAL_SECONDS)
        except TimeoutError:
            pass
    logger.info("stranded-sleeve sweep loop stopped")
