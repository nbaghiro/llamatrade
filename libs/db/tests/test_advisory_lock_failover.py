"""Session-level advisory locks over the shared pooled engine, on real Postgres.

Three services elect a single writer with ``pg_try_advisory_lock`` taken on an
``AsyncSession`` from the process session maker, and rely on "the lock goes away
when the connection does". These tests pin the two halves of that assumption
against the real factory: what closing a *pooled* session actually releases, and
what the pool hands back after every backend has been torn.

Requires Docker (testcontainers); skips cleanly otherwise, like the other
Postgres-backed suites here.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from llamatrade_db.advisory import advisory_unlock, holds_advisory_lock, try_advisory_lock
from llamatrade_db.session import close_db, get_session_maker

POSTGRES_IMAGE = "postgres:16-alpine"
DBNAME = "advisory_locks"

# A stable key in the same shape the services use (a signed 64-bit bigint).
LOCK_KEY = 0x6C6F636B74657374  # "locktest"

_ENV_KEYS = ("DATABASE_URL", "DB_POOL_SIZE", "DB_MAX_OVERFLOW")

_ADVISORY_HOLDERS_SQL = """
SELECT pid FROM pg_locks
WHERE locktype = 'advisory'
  AND granted
  AND database = (SELECT oid FROM pg_database WHERE datname = current_database())
ORDER BY pid
"""


@pytest.fixture(scope="module")
def pg_dsn() -> Iterator[str]:
    postgres_mod: Any = pytest.importorskip("testcontainers.postgres")
    try:
        container = postgres_mod.PostgresContainer(
            POSTGRES_IMAGE, username="test", password="test", dbname=DBNAME
        )
        container.start()
    except Exception as exc:  # Docker down / image pull blocked
        pytest.skip(f"Postgres container unavailable: {exc}")
    try:
        raw = str(container.get_connection_url())
        yield raw.replace("+psycopg2", "+asyncpg").replace("postgresql://", "postgresql+asyncpg://")
    finally:
        container.stop()


class _Peer:
    """An independent connection used to observe and tear the cluster."""

    def __init__(self, dsn: str) -> None:
        self._engine = create_async_engine(dsn, poolclass=NullPool)

    async def _scalar(self, sql: str, params: dict[str, object] | None = None) -> object:
        async with self._engine.connect() as conn:
            return await conn.scalar(text(sql), params or {})

    async def advisory_holders(self) -> list[int]:
        async with self._engine.connect() as conn:
            rows = await conn.scalars(text(_ADVISORY_HOLDERS_SQL))
            return [int(pid) for pid in rows.all()]

    async def can_take(self, key: int) -> bool:
        """Whether a fresh connection can take the key (released again on close)."""
        async with self._engine.connect() as conn:
            return bool(await conn.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}))

    async def tear_everyone_else(self) -> int:
        """Terminate every other backend on this database (a failover, from the
        client's point of view)."""
        async with self._engine.connect() as conn:
            rows = await conn.scalars(
                text(
                    "SELECT pid FROM pg_stat_activity "
                    "WHERE datname = current_database() AND pid <> pg_backend_pid()"
                )
            )
            pids = [int(pid) for pid in rows.all()]
        for pid in pids:
            await self._scalar("SELECT pg_terminate_backend(:pid)", {"pid": pid})
        for pid in pids:
            await self.await_backend_gone(pid)
        return len(pids)

    async def await_backend_gone(self, pid: int, timeout: float = 15.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            alive = await self._scalar(
                "SELECT count(*) FROM pg_stat_activity WHERE pid = :pid", {"pid": pid}
            )
            assert isinstance(alive, int)
            if alive == 0:
                return
            await asyncio.sleep(0.05)
        raise AssertionError(f"backend {pid} still alive after {timeout}s")

    async def await_key_free(self, key: int, timeout: float = 15.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if await self.can_take(key):
                return True
            await asyncio.sleep(0.05)
        return False

    async def aclose(self) -> None:
        await self._engine.dispose()


@asynccontextmanager
async def _process_session_maker(
    dsn: str, *, pool_size: int = 1
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """The real process-wide session maker, pointed at the throwaway cluster.

    ``pool_size=1`` pins every session to one pooled connection, so a connection
    handed back is demonstrably the one the next session picks up.
    """
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    os.environ["DATABASE_URL"] = dsn
    os.environ["DB_POOL_SIZE"] = str(pool_size)
    os.environ["DB_MAX_OVERFLOW"] = "0"
    await close_db()
    try:
        yield get_session_maker()
    finally:
        await close_db()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


async def _backend_pid(session: AsyncSession) -> int:
    pid = await session.scalar(text("SELECT pg_backend_pid()"))
    assert isinstance(pid, int)
    return pid


async def test_advisory_lock_outlives_commit_and_rides_the_connection_back_into_the_pool(
    pg_dsn: str,
) -> None:
    """Closing a lock-holding session does not release its advisory lock.

    Session-level locks are not transactional and belong to the backend, while
    ``AsyncSession.close()`` only returns that backend to the pool. So a lock
    taken inside a scoped session (``system_session``/``tenant_session``/
    ``get_db`` all close on exit) stays held by an idle pooled connection that no
    caller owns any more; only disposing the pool, which actually closes the
    backend, gives it up.
    """
    peer = _Peer(pg_dsn)
    try:
        async with _process_session_maker(pg_dsn) as maker:
            holder = maker()
            try:
                assert await holder.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY})
                pid = await _backend_pid(holder)
                assert await peer.advisory_holders() == [pid]

                await holder.commit()
                assert await peer.can_take(LOCK_KEY) is False  # not transactional
                assert await peer.advisory_holders() == [pid]
            finally:
                await holder.close()

            # The connection is back in the pool, still holding the lock, and the
            # next session out of that pool is the same backend.
            assert await peer.advisory_holders() == [pid]
            reused = maker()
            try:
                assert await _backend_pid(reused) == pid
            finally:
                await reused.close()

        # close_db() disposed the pool, which closed the backend and freed it.
        assert await peer.await_key_free(LOCK_KEY) is True
    finally:
        await peer.aclose()


async def test_pool_heals_after_every_backend_dies_but_the_lock_does_not(pg_dsn: str) -> None:
    """After a failover the pool hands back a working connection and no lock.

    ``pool_pre_ping`` (set by ``get_engine``) replaces the dead pooled connection
    transparently, so the next query succeeds and nothing in the session layer
    signals that anything happened. The advisory lock taken before the tear is
    simply gone, which is why a holder has to re-acquire rather than trust that
    its connection still works.
    """
    peer = _Peer(pg_dsn)
    try:
        # Room for a second connection: the torn one may stay checked out if its
        # close fails, and the point here is the pool's own recovery.
        async with _process_session_maker(pg_dsn, pool_size=5) as maker:
            holder = maker()
            try:
                assert await holder.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY})
                original_pid = await _backend_pid(holder)
                assert await peer.advisory_holders() == [original_pid]

                assert await peer.tear_everyone_else() >= 1
                assert await peer.advisory_holders() == []
            finally:
                with contextlib.suppress(Exception):
                    await holder.close()

            # Same factory, same pool: the query just works again.
            healed = maker()
            try:
                assert await healed.scalar(text("SELECT 1")) == 1
                assert await _backend_pid(healed) != original_pid
                # ...but nothing re-took the lock on the caller's behalf.
                assert await peer.can_take(LOCK_KEY) is True
            finally:
                await healed.close()
    finally:
        await peer.aclose()


async def test_holds_advisory_lock_answers_only_for_the_holding_connection(pg_dsn: str) -> None:
    """The probe is per-connection, which is what makes it a fence.

    A leader has to be able to ask "do I still hold this?" of the exact
    connection that took the lock. A different connection — including one the
    pool hands back after the original died — must answer no, not "somebody
    holds it".
    """
    peer = _Peer(pg_dsn)
    try:
        async with _process_session_maker(pg_dsn, pool_size=5) as maker:
            holder = maker()
            other = maker()
            try:
                assert await try_advisory_lock(holder, LOCK_KEY) is True
                assert await holds_advisory_lock(holder, LOCK_KEY) is True
                assert await holds_advisory_lock(other, LOCK_KEY) is False  # not this backend
                assert await holds_advisory_lock(holder, LOCK_KEY + 1) is False  # not this key

                await holder.commit()
                assert await holds_advisory_lock(holder, LOCK_KEY) is True  # not transactional

                assert await advisory_unlock(holder, LOCK_KEY) is True
                assert await holds_advisory_lock(holder, LOCK_KEY) is False
                assert await peer.can_take(LOCK_KEY) is True
            finally:
                await holder.close()
                await other.close()
    finally:
        await peer.aclose()


async def test_holds_advisory_lock_reports_a_torn_connection_as_not_holding(pg_dsn: str) -> None:
    """A backend that went away cannot be asked, and "cannot ask" must read as
    "not the leader" — a caller about to write needs a verdict, not an error."""
    peer = _Peer(pg_dsn)
    try:
        async with _process_session_maker(pg_dsn, pool_size=5) as maker:
            holder = maker()
            try:
                assert await try_advisory_lock(holder, LOCK_KEY) is True
                assert await holds_advisory_lock(holder, LOCK_KEY) is True

                assert await peer.tear_everyone_else() >= 1

                assert await holds_advisory_lock(holder, LOCK_KEY) is False
            finally:
                with contextlib.suppress(Exception):
                    await holder.close()
    finally:
        await peer.aclose()


async def test_negative_keys_probe_correctly(pg_dsn: str) -> None:
    """Session lease keys are signed 64-bit (derived from a UUID), so the probe's
    classid/objid split has to survive the sign bit."""
    key = -(2**62) - 12345
    peer = _Peer(pg_dsn)
    try:
        async with _process_session_maker(pg_dsn, pool_size=5) as maker:
            holder = maker()
            try:
                assert await try_advisory_lock(holder, key) is True
                assert await holds_advisory_lock(holder, key) is True
                assert await advisory_unlock(holder, key) is True
                assert await holds_advisory_lock(holder, key) is False
            finally:
                await holder.close()
    finally:
        await peer.aclose()
