"""Ledger-writer election across a database failover, against real Postgres.

The reconciliation and equity-snapshot sweeps are single-writer: one pod holds
``pg_try_advisory_lock`` for its process lifetime, because two writers would
double-write drift events and duplicate equity-curve points. These tests tear the
holder's connections (backend termination, then a full container restart) and pin
what actually happens to ownership, and to the writes on the other side of it.

Each "pod" gets its own engine tagged with an ``application_name`` so a whole
replica's connections can be terminated in one step, the way a failover drops
them. Requires Docker (testcontainers); skips cleanly otherwise.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Table, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from llamatrade_db import tenant_session
from llamatrade_db.base import Base
from llamatrade_db.models.auth import AlpacaCredentials, Tenant
from llamatrade_db.models.ledger import (
    Account,
    LedgerEvent,
    LedgerEventType,
    Lot,
    ProjectionCheckpoint,
    Sleeve,
    SleeveSnapshot,
)
from llamatrade_proto.generated import common_pb2, ledger_pb2

from src.ledger.ingestion import LedgerAppend
from src.ledger.reconciliation import Drift, DriftKind
from src.ports import BrokerHolding, BrokerSnapshot
from src.repositories import SqlLedgerStore, SqlSleeveRepository
from src.tasks.drift_policy import apply_drift_action
from src.tasks.equity_snapshot import run_snapshot_pass
from src.tasks.fill_ingestion import (
    LedgerWriterLease,
    acquire_ledger_writer_lease,
    acquire_ledger_writer_lock,
    persist_append,
    release_ledger_writer_lock,
)

pytestmark = pytest.mark.integration

POSTGRES_IMAGE = "postgres:16-alpine"

# The ledger tables plus the two the account bootstrap reads through
# (credentials, and the tenants they hang off): a minimal schema for the sweeps.
_TABLES: list[Table] = [
    cast(Table, Tenant.__table__),
    cast(Table, AlpacaCredentials.__table__),
    cast(Table, Account.__table__),
    cast(Table, Sleeve.__table__),
    cast(Table, Lot.__table__),
    cast(Table, LedgerEvent.__table__),
    cast(Table, ProjectionCheckpoint.__table__),
    cast(Table, SleeveSnapshot.__table__),
]

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


# --------------------------------------------------------------------------- #
# Container / schema
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
def pg_container() -> Iterator[Any]:
    postgres_mod = pytest.importorskip("testcontainers.postgres")
    container = _start_container(postgres_mod, "writer_failover")
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="module")
def pg_dsn(pg_container: Any) -> str:
    raw = str(pg_container.get_connection_url())
    return raw.replace("+psycopg2", "+asyncpg").replace("postgresql://", "postgresql+asyncpg://")


@pytest.fixture(scope="module")
def pg_schema(pg_dsn: str) -> str:
    async def _create() -> None:
        engine = create_async_engine(pg_dsn, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
        await engine.dispose()

    asyncio.run(_create())
    return pg_dsn


# --------------------------------------------------------------------------- #
# Harness
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _Replica:
    """One pod: its own pool, tagged so every connection it owns can be torn."""

    name: str
    engine: AsyncEngine
    factory: async_sessionmaker[AsyncSession]

    async def aclose(self) -> None:
        await self.engine.dispose()


def _replica(dsn: str, name: str) -> _Replica:
    engine = create_async_engine(
        dsn,
        pool_pre_ping=True,  # mirrors llamatrade_db.get_engine()
        pool_size=5,
        max_overflow=5,
        connect_args={"server_settings": {"application_name": name}},
    )
    return _Replica(
        name=name,
        engine=engine,
        factory=async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False),
    )


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

    async def replica_pids(self, name: str) -> list[int]:
        return await self._pids(_REPLICA_PIDS_SQL, {"name": name})

    async def tear(self, replica: _Replica) -> int:
        """Terminate every backend the replica owns (what a failover does to it)."""
        pids = await self.replica_pids(replica.name)
        for pid in pids:
            await self._scalar("SELECT pg_terminate_backend(:pid)", {"pid": pid})
        for pid in pids:
            await self.await_backend_gone(pid)
        return len(pids)

    async def await_backend_gone(self, pid: int, timeout: float = 15.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            alive = await self.count(
                "SELECT count(*) FROM pg_stat_activity WHERE pid = :pid", {"pid": pid}
            )
            if alive == 0:
                return
            await asyncio.sleep(0.05)
        raise AssertionError(f"backend {pid} still alive after {timeout}s")

    async def aclose(self) -> None:
        await self._engine.dispose()


async def _backend_pid(session: AsyncSession) -> int:
    pid = await session.scalar(text("SELECT pg_backend_pid()"))
    assert isinstance(pid, int)
    return pid


async def _quiet_close(session: AsyncSession | None) -> None:
    """Close a session whose connection may already be torn."""
    if session is None:
        return
    with contextlib.suppress(Exception):
        await session.close()


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
# Ledger fixtures for the write paths under test
# --------------------------------------------------------------------------- #


def _dec(value: str) -> common_pb2.Decimal:
    return common_pb2.Decimal(value=value)


def _rpc_ctx() -> Any:
    return cast(Any, None)  # the servicers read request.context, never ctx


HELD_SYMBOL = "SPY"
HELD_PRICE = Decimal("120")


@dataclass(frozen=True)
class _FundedAccount:
    tenant_id: UUID
    account_id: UUID
    strategy_sleeve_id: UUID


async def _bootstrap_funded_account(factory: async_sessionmaker[AsyncSession]) -> _FundedAccount:
    """An account with base sleeves, cash, and one funded strategy sleeve."""
    from src.grpc.ledger_servicer import LedgerServicer

    servicer: Any = LedgerServicer()
    servicer._session_factory = factory
    tenant = uuid4()
    ctx = common_pb2.TenantContext(tenant_id=str(tenant), user_id=str(uuid4()))

    account = await servicer.get_or_create_account(
        ledger_pb2.GetOrCreateAccountRequest(context=ctx, credentials_id=str(uuid4())),
        _rpc_ctx(),
    )
    account_id = str(account.account.id)
    await servicer.deposit_funds(
        ledger_pb2.DepositFundsRequest(context=ctx, account_id=account_id, amount=_dec("100000")),
        _rpc_ctx(),
    )
    allocated = await servicer.allocate_capital(
        ledger_pb2.AllocateCapitalRequest(
            context=ctx,
            account_id=account_id,
            to_sleeve_id="",
            strategy_execution_id=str(uuid4()),
            amount=_dec("40000"),
            sleeve_name="Failover",
        ),
        _rpc_ctx(),
    )
    funded = _FundedAccount(
        tenant_id=tenant,
        account_id=UUID(account_id),
        strategy_sleeve_id=UUID(str(allocated.sleeve.id)),
    )

    # A real fill, so the sleeve holds a symbol: the snapshot pass only fetches
    # prices when some sleeve has a position, and that fetch is where the mid-pass
    # tests interrupt it.
    async with factory() as db:
        await persist_append(
            db,
            LedgerAppend(
                tenant_id=funded.tenant_id,
                account_id=funded.account_id,
                sleeve_id=funded.strategy_sleeve_id,
                event_type=LedgerEventType.ORDER_FILLED,
                data={
                    "sleeve_id": str(funded.strategy_sleeve_id),
                    "symbol": HELD_SYMBOL,
                    "side": "buy",
                    "qty": "5",
                    "price": "100",
                },
                event_id=uuid4(),
                occurred_at=datetime.now(UTC),
            ),
        )
    return funded


class _FixedPrices:
    """PriceProvider stub marking the held symbol at a constant price."""

    async def get_prices(self, symbols: list[str]) -> dict[str, Decimal]:
        return {symbol: HELD_PRICE for symbol in symbols}

    async def get_daily_closes(
        self, symbol: str, start: datetime, end: datetime
    ) -> dict[date, float]:
        return {}


class _BlockingPrices(_FixedPrices):
    """Freezes a snapshot pass between projecting and persisting.

    ``run_snapshot_pass`` projects every account, then fetches prices once, then
    persists. Blocking the price fetch parks the pass exactly mid-flight, with
    its writes still ahead of it.
    """

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def get_prices(self, symbols: list[str]) -> dict[str, Decimal]:
        self.entered.set()
        await self.release.wait()
        return await super().get_prices(symbols)


class _FakeBrokerSnapshots:
    """BrokerSnapshotProvider returning fixed truth (drift adoption needs a price)."""

    def __init__(self, holdings: list[BrokerHolding]) -> None:
        self._holdings = holdings

    async def snapshot(self, tenant_id: UUID, account: Account) -> BrokerSnapshot:
        return BrokerSnapshot(cash=Decimal("0"), holdings=list(self._holdings))


async def _snapshot_stats(
    factory: async_sessionmaker[AsyncSession], sleeve_id: UUID
) -> tuple[int, int]:
    """(rows, distinct sequences) of equity-curve points for one sleeve."""
    async with factory() as db:
        rows = await db.scalar(
            select(func.count())
            .select_from(SleeveSnapshot)
            .where(SleeveSnapshot.sleeve_id == sleeve_id)
        )
        sequences = await db.scalar(
            select(func.count(func.distinct(SleeveSnapshot.as_of_sequence)))
            .select_from(SleeveSnapshot)
            .where(SleeveSnapshot.sleeve_id == sleeve_id)
        )
    return int(rows or 0), int(sequences or 0)


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


async def test_writer_lock_admits_one_replica_and_frees_on_backend_death(
    pg_schema: str,
) -> None:
    """Two sweep candidates contend; the loser stays a standby until the holder's
    connection dies, which is the whole basis for failover."""
    first = _replica(pg_schema, "portfolio-elect-a")
    second = _replica(pg_schema, "portfolio-elect-b")
    admin = _Admin(pg_schema)
    holder: AsyncSession | None = None
    successor: AsyncSession | None = None
    try:
        holder = await acquire_ledger_writer_lock(first.factory)
        assert holder is not None
        assert await acquire_ledger_writer_lock(second.factory) is None  # standby

        holder_pid = await _backend_pid(holder)
        assert await admin.advisory_holders() == [holder_pid]

        torn = await admin.tear(first)
        assert torn >= 1  # the tear really removed the holder's connections
        await _quiet_close(holder)
        holder = None

        successor = await acquire_ledger_writer_lock(second.factory)
        assert successor is not None  # the lock died with the connection
        successor_pid = await _backend_pid(successor)
        assert successor_pid != holder_pid
        assert await admin.advisory_holders() == [successor_pid]  # exactly one holder
    finally:
        if successor is not None:
            await release_ledger_writer_lock(successor)
        await _quiet_close(holder)
        await admin.aclose()
        await first.aclose()
        await second.aclose()


async def test_mid_pass_failover_fences_the_old_leader_out_of_the_write_phase(
    pg_schema: str,
) -> None:
    """A leader torn mid-pass abandons its writes once a peer has taken the lock.

    The pass re-checks the lock on its own connection between the read/price
    phase and the first commit, so the leader that lost its backend discards the
    work in flight instead of racing the successor. Both halves of the fix show
    here: the fenced pass writes nothing, and a later unfenced sweep by the old
    leader cannot duplicate a point either, because ``(sleeve_id,
    as_of_sequence)`` is unique and the writer inserts ON CONFLICT DO NOTHING.
    """
    leader = _replica(pg_schema, "portfolio-dup-a")
    peer = _replica(pg_schema, "portfolio-dup-b")
    admin = _Admin(pg_schema)
    lease: LedgerWriterLease | None = None
    successor: AsyncSession | None = None
    try:
        funded = await _bootstrap_funded_account(leader.factory)

        lease = await acquire_ledger_writer_lease(leader.factory)
        assert lease is not None
        assert await lease.is_leader() is True  # the probe agrees while it holds

        blocking = _BlockingPrices()
        pass_task = asyncio.create_task(
            run_snapshot_pass(leader.factory, blocking, is_leader=lease.is_leader)
        )
        await asyncio.wait_for(blocking.entered.wait(), timeout=30)

        rows, _ = await _snapshot_stats(peer.factory, funded.strategy_sleeve_id)
        assert rows == 0  # still mid-pass: nothing persisted yet

        torn = await admin.tear(leader)
        assert torn >= 1

        successor = await acquire_ledger_writer_lock(peer.factory)
        assert successor is not None  # re-election succeeds
        successor_pid = await _backend_pid(successor)
        assert await admin.advisory_holders() == [successor_pid]  # exactly one holder

        # The torn leader resumes, finds the lock gone, and writes nothing.
        blocking.release.set()
        assert await asyncio.wait_for(pass_task, timeout=60) == 0
        assert await lease.is_leader() is False  # leadership loss latched
        assert await _snapshot_stats(peer.factory, funded.strategy_sleeve_id) == (0, 0)

        # The real leader's sweep lands one point...
        assert await run_snapshot_pass(peer.factory, _FixedPrices()) >= 1
        assert await _snapshot_stats(peer.factory, funded.strategy_sleeve_id) == (1, 1)

        # ...and an unfenced sweep by the old leader cannot add a second at the
        # same ledger sequence: the unique key absorbs it.
        assert await run_snapshot_pass(leader.factory, _FixedPrices()) >= 1
        rows, sequences = await _snapshot_stats(peer.factory, funded.strategy_sleeve_id)
        assert (rows, sequences) == (1, 1)
    finally:
        if successor is not None:
            await release_ledger_writer_lock(successor)
        if lease is not None:
            await lease.release()
        await admin.aclose()
        await leader.aclose()
        await peer.aclose()


async def test_repeat_sweeps_add_one_curve_point_per_sleeve_per_day(pg_schema: str) -> None:
    """The snapshot idempotency key admits a day's re-mark and nothing else.

    Two sweeps in one day at the same ledger sequence — a re-run, a handover, a
    torn leader that resumed — must leave a single point. The next day's mark of
    the same unchanged position is not a duplicate: it is the curve, and keying
    on (sleeve, sequence) alone would collapse an idle sleeve to one point for
    its whole life.
    """
    replica = _replica(pg_schema, "portfolio-idem-a")
    try:
        funded = await _bootstrap_funded_account(replica.factory)

        assert await run_snapshot_pass(replica.factory, _FixedPrices()) >= 1
        assert await run_snapshot_pass(replica.factory, _FixedPrices()) >= 1
        assert await _snapshot_stats(replica.factory, funded.strategy_sleeve_id) == (1, 1)

        # Age today's points by a day; the next sweep is that day's first mark.
        async with replica.factory() as db:
            await db.execute(
                text(
                    "UPDATE ledger_sleeve_snapshots SET created_at = created_at - interval '1 day'"
                )
            )
            await db.commit()

        assert await run_snapshot_pass(replica.factory, _FixedPrices()) >= 1
        rows, sequences = await _snapshot_stats(replica.factory, funded.strategy_sleeve_id)
        assert (rows, sequences) == (2, 1)  # two daily points at one ledger sequence
    finally:
        await replica.aclose()


async def test_drift_events_stay_single_across_a_writer_handover(pg_schema: str) -> None:
    """Two writers detecting the same drift append exactly one ledger event.

    Unlike equity points, the drift policy derives a deterministic event id from
    the drift, so the writer's unique constraint absorbs the second append. This
    is the property that has to survive an unfenced handover.
    """
    leader = _replica(pg_schema, "portfolio-drift-a")
    peer = _replica(pg_schema, "portfolio-drift-b")
    admin = _Admin(pg_schema)
    lease: AsyncSession | None = None
    successor: AsyncSession | None = None
    try:
        funded = await _bootstrap_funded_account(leader.factory)
        drift = Drift(
            symbol="SPY",
            ledger_qty=Decimal("0"),
            broker_qty=Decimal("5"),
            kind=DriftKind.MISSING_IN_LEDGER,
        )
        broker = _FakeBrokerSnapshots(
            [BrokerHolding(symbol="SPY", qty=Decimal("5"), avg_price=Decimal("100"))]
        )

        async def _apply(factory: async_sessionmaker[AsyncSession]) -> str:
            async with tenant_session(funded.tenant_id, factory) as db:
                account = await SqlSleeveRepository(db).get_account(
                    funded.tenant_id, funded.account_id
                )
                assert account is not None
                action = await apply_drift_action(
                    repo=SqlSleeveRepository(db),
                    store=SqlLedgerStore(db),
                    broker=broker,
                    account=account,
                    drift=drift,
                )
                await db.commit()
                return action

        lease = await acquire_ledger_writer_lock(leader.factory)
        assert lease is not None
        assert await _apply(leader.factory) == "adopted"

        assert await admin.tear(leader) >= 1
        await _quiet_close(lease)
        lease = None

        successor = await acquire_ledger_writer_lock(peer.factory)
        assert successor is not None
        # Both the new leader and the unfenced old one re-detect the same drift;
        # the deterministic (dated) event id dedups the repeats, now reported as
        # "deduped" rather than a fresh adoption.
        assert await _apply(peer.factory) == "deduped"
        assert await _apply(leader.factory) == "deduped"

        async with peer.factory() as db:
            adopted = await db.scalar(
                select(func.count())
                .select_from(LedgerEvent)
                .where(LedgerEvent.account_id == funded.account_id)
                .where(LedgerEvent.event_type == LedgerEventType.EXTERNAL_TRADE_DETECTED.value)
            )
        assert int(adopted or 0) == 1  # deterministic event id deduped the repeats
    finally:
        if successor is not None:
            await release_ledger_writer_lock(successor)
        await _quiet_close(lease)
        await admin.aclose()
        await leader.aclose()
        await peer.aclose()


# Restarts the shared container, so it runs last in this module.
async def test_container_restart_frees_the_lock_and_the_pool_re_elects(
    pg_container: Any, pg_schema: str
) -> None:
    """After the database restarts, no advisory lock survives, releasing on the
    torn connection never leaves one held, and only a pre-pinging pool can
    re-elect through the half-open window."""
    leader = _replica(pg_schema, "portfolio-restart-a")
    # A pool without pre-ping: its pooled connection looks usable after the
    # restart and only fails when it is next used.
    stale = create_async_engine(
        pg_schema,
        pool_pre_ping=False,
        pool_size=1,
        max_overflow=0,
        connect_args={"server_settings": {"application_name": "portfolio-restart-stale"}},
    )
    holder: AsyncSession | None = None
    reelected: AsyncSession | None = None
    admin: _Admin | None = None
    try:
        holder = await acquire_ledger_writer_lock(leader.factory)
        assert holder is not None
        holder_pid = await _backend_pid(holder)

        pre_restart = _Admin(pg_schema)
        try:
            assert await pre_restart.advisory_holders() == [holder_pid]
        finally:
            await pre_restart.aclose()

        async with stale.connect() as conn:
            assert await conn.scalar(text("SELECT 1")) == 1  # warm one pooled connection

        await asyncio.to_thread(pg_container.get_wrapped_container().restart, timeout=30)
        await _await_ready(pg_schema)

        admin = _Admin(pg_schema)
        assert await admin.advisory_holders() == []  # the cluster lost every session

        # The unlock rides the connection that just died, and must be absorbed:
        # shutdown still has a Kafka client and a connection pool to close.
        await release_ledger_writer_lock(holder)
        holder = None
        assert await admin.advisory_holders() == []

        with pytest.raises(DBAPIError):
            async with stale.connect() as conn:
                await conn.scalar(text("SELECT 1"))

        reelected = await acquire_ledger_writer_lock(leader.factory)
        assert reelected is not None  # pre-ping replaced the dead pooled connection
        assert await admin.advisory_holders() == [await _backend_pid(reelected)]
    finally:
        if reelected is not None:
            await release_ledger_writer_lock(reelected)
        await _quiet_close(holder)
        if admin is not None:
            await admin.aclose()
        await stale.dispose()
        await leader.aclose()
