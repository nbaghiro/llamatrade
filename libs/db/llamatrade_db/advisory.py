"""Session-level Postgres advisory locks (single-writer election, ownership leases).

A session-level lock belongs to the *connection*, not a transaction: it survives
commit and is released only by ``pg_advisory_unlock`` or by the backend going
away. Two consequences shape every caller here.

First, the holder must keep its own connection and unlock explicitly — closing a
pooled session hands the connection back still holding the lock. Second, "do I
still hold it?" is a question only the holding connection can answer, which is
what :func:`holds_advisory_lock` is for: a leader that lost its backend (failover,
server-side timeout) must fence itself before writing, and a reconnect through a
pre-pinging pool looks healthy while holding nothing.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

logger = logging.getLogger(__name__)

# Either kind of holder: services elect on an AsyncSession, per-session leases
# run on a dedicated AUTOCOMMIT AsyncConnection.
LockHolder = AsyncConnection | AsyncSession

_TRY_LOCK_SQL = text("SELECT pg_try_advisory_lock(cast(:key as bigint))")
_UNLOCK_SQL = text("SELECT pg_advisory_unlock(cast(:key as bigint))")
# ``pg_locks`` splits a 64-bit advisory key across classid (high half) and objid
# (low half); masking each half keeps the comparison exact for negative keys.
_HOLDS_SQL = text(
    """
    SELECT EXISTS (
        SELECT 1 FROM pg_locks
        WHERE locktype = 'advisory'
          AND granted
          AND pid = pg_backend_pid()
          AND classid = ((cast(:key as bigint) >> 32) & 4294967295)::oid
          AND objid = (cast(:key as bigint) & 4294967295)::oid
    )
    """
)


async def try_advisory_lock(holder: LockHolder, key: int) -> bool:
    """Take ``key`` on ``holder``'s connection, or return False if someone else has it."""
    return bool(await holder.scalar(_TRY_LOCK_SQL, {"key": key}))


async def advisory_unlock(holder: LockHolder, key: int) -> bool:
    """Release ``key`` on ``holder``'s connection."""
    return bool(await holder.scalar(_UNLOCK_SQL, {"key": key}))


async def holds_advisory_lock(holder: LockHolder, key: int) -> bool:
    """Whether ``holder``'s own connection still holds ``key``.

    False when the lock is gone AND when the connection can no longer be asked —
    a torn backend and a silently revoked lock are the same verdict to a caller
    that is about to write.
    """
    try:
        return bool(await holder.scalar(_HOLDS_SQL, {"key": key}))
    except Exception:
        logger.debug("advisory-lock probe failed for key %s", key, exc_info=True)
        return False
