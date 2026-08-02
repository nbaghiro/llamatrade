"""Per-session ownership leases across a database failover, against real Postgres.

``src.recovery`` arbitrates which pod runs a live trading session with a
session-level ``pg_try_advisory_lock`` held on a dedicated AUTOCOMMIT connection
for the runner's lifetime. These tests kill that connection (backend
termination, a server-side idle timeout, and a full container restart) and pin
what the real helpers do on both sides of the tear: whether a peer can take
over, and what the old holder still believes.

Each "pod" gets its own pool tagged with an ``application_name`` (so a whole
replica's connections can be terminated at once) and its own lease registry, the
way separate processes would. Requires Docker (testcontainers); skips otherwise.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from src import recovery
from src.recovery import _session_lock_key, release_session_lease, sweep_dead_leases

POSTGRES_IMAGE = "postgres:16-alpine"
DBNAME = "session_failover"

_ADVISORY_HOLDERS_SQL = """
SELECT pid FROM pg_locks
WHERE locktype = 'advisory'
  AND granted
  AND database = (SELECT oid FROM pg_database WHERE datname = current_database())
ORDER BY pid
"""

_REPLICA_PIDS_SQL = """
SELECT pid FROM pg_stat_activity
WHERE application_name = :name AND pid <> pg_backend_pid()
ORDER BY pid
"""

_BACKEND_STATE_SQL = "SELECT state FROM pg_stat_activity WHERE pid = :pid"


# --------------------------------------------------------------------------- #
# Container
# --------------------------------------------------------------------------- #


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_container(postgres_mod: Any, dbname: str) -> Any:
    """Start Postgres on a fixed host port so a restart keeps the same address."""
    last: Exception | None = None
    for _ in range(3):
        try:
            container = postgres_mod.PostgresContainer(
                POSTGRES_IMAGE, username="test", password="test", dbname=dbname
            ).with_bind_ports(5432, _free_port())
            container.start()
        except Exception as exc:  # Docker down, image pull blocked, or a port race
            last = exc
            continue
        return container
    pytest.skip(f"Postgres container unavailable: {last}")


@pytest.fixture(scope="module")
def failover_container() -> Iterator[Any]:
    postgres_mod = pytest.importorskip("testcontainers.postgres")
    container = _start_container(postgres_mod, DBNAME)
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="module")
def failover_dsn(failover_container: Any) -> str:
    raw = str(failover_container.get_connection_url())
    return raw.replace("+psycopg2", "+asyncpg").replace("postgresql://", "postgresql+asyncpg://")


# --------------------------------------------------------------------------- #
# Harness
# --------------------------------------------------------------------------- #


@dataclass
class _Pod:
    """One trading pod: its own pool and its own in-memory lease registry."""

    name: str
    engine: AsyncEngine
    leases: dict[UUID, AsyncConnection] = field(default_factory=dict)

    async def aclose(self) -> None:
        for conn in self.leases.values():
            await _quiet_close(conn)
        self.leases.clear()
        await self.engine.dispose()


def _pod(dsn: str, name: str) -> _Pod:
    engine = create_async_engine(
        dsn,
        pool_pre_ping=True,  # mirrors llamatrade_db.get_engine()
        pool_size=5,
        max_overflow=5,
        connect_args={"server_settings": {"application_name": name}},
    )
    return _Pod(name=name, engine=engine)


@contextlib.contextmanager
def _as_pod(pod: _Pod) -> Iterator[None]:
    """Run recovery's real lease helpers as this pod: its pool, its registry."""
    saved_engine = recovery.get_engine
    saved_leases = recovery._leases
    recovery.get_engine = lambda: pod.engine
    recovery._leases = pod.leases
    try:
        yield
    finally:
        recovery.get_engine = saved_engine
        recovery._leases = saved_leases


async def _claim(pod: _Pod, session_id: UUID) -> bool:
    """The real ``_try_claim`` executed as ``pod``."""
    with _as_pod(pod):
        return await recovery._try_claim(session_id)


async def _release(pod: _Pod, session_id: UUID) -> None:
    """The real ``release_session_lease`` executed as ``pod``."""
    with _as_pod(pod):
        await release_session_lease(session_id)


async def _heartbeat(pod: _Pod, runner_manager: Any) -> list[UUID]:
    """The real lease heartbeat executed as ``pod``."""
    with _as_pod(pod):
        return await sweep_dead_leases(runner_manager)


class _RecordingRunners:
    """Stand-in RunnerManager recording which runners the heartbeat stopped."""

    def __init__(self) -> None:
        self.stopped: list[UUID] = []

    async def stop_runner(self, session_id: UUID) -> bool:
        self.stopped.append(session_id)
        return True


class _Admin:
    """Out-of-band connection used to observe and tear the cluster."""

    def __init__(self, dsn: str) -> None:
        self._engine = create_async_engine(dsn, poolclass=NullPool)

    async def _scalar(self, sql: str, params: dict[str, object] | None = None) -> object:
        async with self._engine.connect() as conn:
            return await conn.scalar(text(sql), params or {})

    async def _pids(self, sql: str, params: dict[str, object] | None = None) -> list[int]:
        async with self._engine.connect() as conn:
            rows = await conn.scalars(text(sql), params or {})
            return [int(pid) for pid in rows.all()]

    async def count(self, sql: str, params: dict[str, object] | None = None) -> int:
        value = await self._scalar(sql, params)
        assert isinstance(value, int)
        return value

    async def advisory_holders(self) -> list[int]:
        return await self._pids(_ADVISORY_HOLDERS_SQL)

    async def backend_state(self, pid: int) -> str | None:
        value = await self._scalar(_BACKEND_STATE_SQL, {"pid": pid})
        return value if isinstance(value, str) else None

    async def probe_key(self, key: int) -> bool:
        """Whether a fresh connection can take this advisory key.

        The probe connection is closed immediately (NullPool), so anything it
        acquires is handed straight back.
        """
        async with self._engine.connect() as conn:
            return bool(await conn.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}))

    async def execute(self, sql: str) -> None:
        async with self._engine.connect() as conn:
            await conn.execute(text(sql))
            await conn.commit()

    async def tear(self, pod: _Pod) -> int:
        """Terminate every backend the pod owns (what a failover does to it)."""
        pids = await self._pids(_REPLICA_PIDS_SQL, {"name": pod.name})
        for pid in pids:
            await self._scalar("SELECT pg_terminate_backend(:pid)", {"pid": pid})
        for pid in pids:
            await self.await_backend_gone(pid)
        return len(pids)

    async def await_backend_gone(self, pid: int, timeout: float = 20.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            alive = await self.count(
                "SELECT count(*) FROM pg_stat_activity WHERE pid = :pid", {"pid": pid}
            )
            if alive == 0:
                return
            await asyncio.sleep(0.05)
        raise AssertionError(f"backend {pid} still alive after {timeout}s")

    async def await_backend_state(self, pid: int, state: str, timeout: float = 10.0) -> None:
        deadline = time.monotonic() + timeout
        observed: str | None = None
        while time.monotonic() < deadline:
            observed = await self.backend_state(pid)
            if observed == state:
                return
            await asyncio.sleep(0.05)
        raise AssertionError(f"backend {pid} is {observed!r}, expected {state!r}")

    async def aclose(self) -> None:
        await self._engine.dispose()


async def _backend_pid(conn: AsyncConnection) -> int:
    pid = await conn.scalar(text("SELECT pg_backend_pid()"))
    assert isinstance(pid, int)
    return pid


async def _quiet_close(conn: AsyncConnection | None) -> None:
    if conn is None:
        return
    with contextlib.suppress(Exception):
        await conn.close()


async def _await_ready(dsn: str, timeout: float = 90.0) -> None:
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        engine = create_async_engine(dsn, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                await conn.scalar(text("SELECT 1"))
            return
        except Exception as exc:
            last = exc
            await asyncio.sleep(0.25)
        finally:
            await engine.dispose()
    raise AssertionError(f"Postgres did not accept connections within {timeout}s: {last}")


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


async def test_peer_claims_the_session_after_the_holder_backend_dies(failover_dsn: str) -> None:
    """A session lease is exclusive while the holder lives and is reclaimable by a
    peer as soon as the holding connection dies, which is how a dead pod's
    sessions get picked up."""
    owner = _pod(failover_dsn, "trading-claim-a")
    peer = _pod(failover_dsn, "trading-claim-b")
    admin = _Admin(failover_dsn)
    session_id = uuid4()
    try:
        assert await _claim(owner, session_id) is True
        assert await _claim(peer, session_id) is False  # exclusive while held

        holder_pid = await _backend_pid(owner.leases[session_id])
        assert await admin.advisory_holders() == [holder_pid]

        assert await admin.tear(owner) >= 1

        assert await _claim(peer, session_id) is True  # the lock died with it
        peer_pid = await _backend_pid(peer.leases[session_id])
        assert peer_pid != holder_pid
        assert await admin.advisory_holders() == [peer_pid]  # exactly one owner

        await _release(peer, session_id)
        assert await admin.advisory_holders() == []
    finally:
        await admin.aclose()
        await owner.aclose()
        await peer.aclose()


async def test_torn_holder_stops_reporting_ownership_once_a_peer_holds_the_lock(
    failover_dsn: str,
) -> None:
    """A pod whose lease connection died stops answering "mine" for that session.

    ``_try_claim`` no longer trusts the in-memory ``_leases`` registry: it asks
    the lease's own connection whether it still holds the lock, so a torn entry
    is invalidated and the claim is re-run against Postgres. With the peer
    holding the lock the old pod is told no, which is what keeps two runners off
    one sleeve after a failover.
    """
    owner = _pod(failover_dsn, "trading-split-a")
    peer = _pod(failover_dsn, "trading-split-b")
    admin = _Admin(failover_dsn)
    session_id = uuid4()
    try:
        assert await _claim(owner, session_id) is True
        lease = owner.leases[session_id]
        holder_pid = await _backend_pid(lease)

        assert await admin.tear(owner) >= 1

        # The peer genuinely owns the lock now.
        assert await _claim(peer, session_id) is True
        peer_pid = await _backend_pid(peer.leases[session_id])
        assert peer_pid != holder_pid
        assert await admin.advisory_holders() == [peer_pid]

        # The contended resource really is this session's key, not an incidental one.
        assert await admin.probe_key(_session_lock_key(session_id)) is False
        assert await admin.probe_key(_session_lock_key(uuid4())) is True

        # The old holder's lease connection is unusable...
        assert session_id in owner.leases
        with pytest.raises(DBAPIError):
            await lease.scalar(text("SELECT 1"))

        # ...so the claim is refused and the dead entry dropped.
        assert await _claim(owner, session_id) is False
        assert session_id not in owner.leases
        assert await admin.advisory_holders() == [peer_pid]  # still only the peer

        await _release(peer, session_id)
    finally:
        await admin.aclose()
        await owner.aclose()
        await peer.aclose()


async def test_heartbeat_drops_a_torn_lease_and_stops_its_runner(
    failover_dsn: str, caplog: pytest.LogCaptureFixture
) -> None:
    """The periodic heartbeat is what fails a torn pod safe.

    Nothing on the trading path touches the lease connection, so a pod can hold
    a dead lease indefinitely between claims. ``sweep_dead_leases`` probes every
    lease each rehydrate tick: a lease whose lock is gone is dropped, logged at
    CRITICAL and its runner stopped, leaving the peer's adoption as the only
    live copy of the session. Leases that are still good are left alone.
    """
    owner = _pod(failover_dsn, "trading-heartbeat-a")
    peer = _pod(failover_dsn, "trading-heartbeat-b")
    admin = _Admin(failover_dsn)
    torn_id, healthy_id = uuid4(), uuid4()
    runners = _RecordingRunners()
    try:
        assert await _claim(owner, torn_id) is True
        assert await admin.tear(owner) >= 1
        # Taken after the tear, so this one's connection is alive.
        assert await _claim(owner, healthy_id) is True

        with caplog.at_level(logging.CRITICAL, logger="src.recovery"):
            lost = await _heartbeat(owner, runners)

        assert lost == [torn_id]
        assert runners.stopped == [torn_id]
        assert torn_id not in owner.leases
        assert healthy_id in owner.leases  # a live lease is never disturbed
        assert any(str(torn_id) in record.getMessage() for record in caplog.records)

        # The freed session is claimable by a peer; the surviving one is not.
        assert await _claim(peer, torn_id) is True
        assert await _claim(peer, healthy_id) is False

        await _release(peer, torn_id)
        await _release(owner, healthy_id)
        assert await admin.advisory_holders() == []
    finally:
        await admin.aclose()
        await owner.aclose()
        await peer.aclose()


async def test_release_session_lease_absorbs_a_torn_connection(
    failover_dsn: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Releasing a lease whose connection died drops the entry and warns instead
    of raising, so a shutdown after a failover still completes."""
    owner = _pod(failover_dsn, "trading-release-a")
    admin = _Admin(failover_dsn)
    session_id = uuid4()
    try:
        assert await _claim(owner, session_id) is True
        assert await admin.tear(owner) >= 1

        with caplog.at_level(logging.WARNING, logger="src.recovery"):
            await _release(owner, session_id)  # must not raise

        assert session_id not in owner.leases
        assert any("advisory lock" in record.getMessage().lower() for record in caplog.records)
        assert await admin.advisory_holders() == []
    finally:
        await admin.aclose()
        await owner.aclose()


async def test_each_lease_pins_an_idle_backend_with_no_open_transaction(
    failover_dsn: str,
) -> None:
    """Every held lease parks one connection, idle and outside any transaction.

    A session-level advisory lock belongs to the connection, not a transaction,
    so ``_try_claim`` takes it on an AUTOCOMMIT connection: the backend reports
    ``idle`` rather than ``idle in transaction``. One pooled connection per live
    session is still pinned — that ceiling is unchanged — but nothing about it
    looks like an abandoned transaction to the server.
    """
    owner = _pod(failover_dsn, "trading-idle-a")
    admin = _Admin(failover_dsn)
    session_ids = [uuid4() for _ in range(3)]
    try:
        pids: list[int] = []
        for session_id in session_ids:
            assert await _claim(owner, session_id) is True
            pids.append(await _backend_pid(owner.leases[session_id]))

        assert len(set(pids)) == 3  # one pinned connection per lease
        assert sorted(await admin.advisory_holders()) == sorted(pids)
        for pid in pids:
            await admin.await_backend_state(pid, "idle")
    finally:
        for session_id in session_ids:
            with contextlib.suppress(Exception):
                await _release(owner, session_id)
        await admin.aclose()
        await owner.aclose()


async def test_server_side_idle_timeout_no_longer_revokes_a_lease(failover_dsn: str) -> None:
    """A managed Postgres' ``idle_in_transaction_session_timeout`` cannot reach the
    lease: with no transaction open the backend is plain ``idle``, so it survives
    the window that used to end it (and the lock) without telling the pod."""
    admin = _Admin(failover_dsn)
    owner: _Pod | None = None
    peer: _Pod | None = None
    session_id = uuid4()
    try:
        await admin.execute(
            f"ALTER DATABASE {DBNAME} SET idle_in_transaction_session_timeout = '2s'"
        )
        # Built after the ALTER so its connections inherit the timeout.
        owner = _pod(failover_dsn, "trading-timeout-a")
        peer = _pod(failover_dsn, "trading-timeout-b")

        assert await _claim(owner, session_id) is True
        lease_pid = await _backend_pid(owner.leases[session_id])
        assert await admin.advisory_holders() == [lease_pid]
        assert await admin.backend_state(lease_pid) == "idle"

        await asyncio.sleep(5)  # well past the 2s timeout

        assert await admin.advisory_holders() == [lease_pid]  # the lease outlived it
        assert await _claim(owner, session_id) is True  # and it verifies for real
        assert await _claim(peer, session_id) is False  # no peer can take it

        await _release(owner, session_id)
        assert await admin.advisory_holders() == []
    finally:
        with contextlib.suppress(Exception):
            await admin.execute(
                f"ALTER DATABASE {DBNAME} RESET idle_in_transaction_session_timeout"
            )
        if owner is not None:
            await owner.aclose()
        if peer is not None:
            await peer.aclose()
        await admin.aclose()


# Restarts the shared container, so it runs last in this module.
async def test_container_restart_frees_every_lease_and_the_holder_retakes_them(
    failover_container: Any, failover_dsn: str
) -> None:
    """A database restart drops every session lock at once. The pods that held
    them re-verify each registry entry on its own connection, so a claim after
    the restart is a real re-acquisition rather than an answer from memory."""
    owner = _pod(failover_dsn, "trading-restart-a")
    peer = _pod(failover_dsn, "trading-restart-b")
    admin: _Admin | None = None
    session_ids = [uuid4(), uuid4()]
    try:
        for session_id in session_ids:
            assert await _claim(owner, session_id) is True

        # Warm the peer's pool so its connections are stale (not absent) after
        # the restart — that is the half-open window it has to reconnect through.
        async with peer.engine.connect() as conn:
            assert await conn.scalar(text("SELECT 1")) == 1

        pre_restart = _Admin(failover_dsn)
        try:
            assert len(await pre_restart.advisory_holders()) == 2
        finally:
            await pre_restart.aclose()

        await asyncio.to_thread(failover_container.get_wrapped_container().restart, timeout=30)
        await _await_ready(failover_dsn)

        admin = _Admin(failover_dsn)
        assert await admin.advisory_holders() == []  # every lease died with the cluster

        # The old owner re-verifies, finds nothing held, and takes the locks again
        # — this time they exist in Postgres, not only in its registry.
        for session_id in session_ids:
            assert await _claim(owner, session_id) is True
        owner_pids = [await _backend_pid(owner.leases[sid]) for sid in session_ids]
        assert sorted(await admin.advisory_holders()) == sorted(owner_pids)

        # ...and a peer is refused while those re-taken leases stand.
        for session_id in session_ids:
            assert await _claim(peer, session_id) is False

        for session_id in session_ids:
            await _release(owner, session_id)
        assert await admin.advisory_holders() == []
    finally:
        if admin is not None:
            await admin.aclose()
        await owner.aclose()
        await peer.aclose()
