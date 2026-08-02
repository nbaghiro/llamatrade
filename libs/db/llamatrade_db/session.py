"""Database connection and session management."""

import inspect
import json
import logging
import os
import re
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from time import perf_counter
from uuid import UUID
from weakref import WeakKeyDictionary

from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import TimeoutError as PoolCheckoutTimeout
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, SessionTransaction

from llamatrade_db.base import Base
from llamatrade_db.rls import BYPASS_GUC, PROD_ENVIRONMENTS, TENANT_GUC, assert_rls_capable
from llamatrade_telemetry.instrumentation.db import (
    DB_POOL_EXHAUSTED,
    DB_QUERY_DURATION,
    DB_RLS_BYPASS,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _count_pool_exhaustion() -> AsyncGenerator[None]:
    """Count a pool-checkout timeout (pool exhausted) for the DB-pool-exhausted alert.

    SQLAlchemy raises ``sqlalchemy.exc.TimeoutError`` when it can't acquire a pooled
    connection within ``pool_timeout``; that is the one signal the alert watches.
    """
    try:
        yield
    except PoolCheckoutTimeout:
        DB_POOL_EXHAUSTED.inc()
        raise


# Module-level engine and session maker (initialized lazily)
_engine: AsyncEngine | None = None
_async_session_maker: async_sessionmaker[AsyncSession] | None = None


def get_database_url() -> str:
    """Get database URL from environment."""
    return os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/llamatrade",
    )


_TABLE_RE = re.compile(
    r"\b(?:from|into|update|join)\s+\"?([a-zA-Z_][a-zA-Z0-9_]*)\"?", re.IGNORECASE
)
_OPERATIONS = frozenset({"SELECT", "INSERT", "UPDATE", "DELETE"})


def _operation(statement: str) -> str:
    word = statement.lstrip().split(" ", 1)[0].upper() if statement else ""
    return word if word in _OPERATIONS else "other"


def _table(statement: str) -> str:
    match = _TABLE_RE.search(statement or "")
    return match.group(1) if match else "unknown"


def _install_query_timing(engine: AsyncEngine) -> None:
    """Time every SQL statement into ``llamatrade_db_query_duration_seconds``.

    Uses SQLAlchemy cursor-execute events on the underlying sync engine, so all
    queries across the service are timed without per-call-site changes. Labels are
    bounded: ``operation`` (SELECT/INSERT/UPDATE/DELETE/other) and a best-effort
    ``table`` (schema tables are a finite set; falls back to ``unknown``).
    """
    sync_engine = engine.sync_engine

    def _before(
        conn: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        conn.info.setdefault("_lt_query_start", []).append(perf_counter())

    def _after(
        conn: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        stack = conn.info.get("_lt_query_start")
        if not stack:
            return
        elapsed = perf_counter() - stack.pop()
        DB_QUERY_DURATION.labels(operation=_operation(statement), table=_table(statement)).observe(
            elapsed
        )

    event.listen(sync_engine, "before_cursor_execute", _before)
    event.listen(sync_engine, "after_cursor_execute", _after)


def _json_serializer(obj: object) -> str:
    """JSONB serializer that renders Decimal (and other non-JSON types) as strings.

    The platform stores money as Decimal; JSONB columns (audit data, ledger event
    data) must serialize it exactly rather than raise or lose precision.
    """
    return json.dumps(obj, default=str)


_DEFAULT_IDLE_IN_TRANSACTION_TIMEOUT_MS = "120000"


def _connect_server_settings() -> dict[str, str]:
    """Postgres GUCs applied at connect time on every pooled connection.

    ``idle_in_transaction_session_timeout`` bounds how long a connection may sit
    idle inside an open transaction. The ledger checkpoint safety window (60s)
    assumes no open transaction outlives it, so the default (120s) is set above
    that window and above the multi-second backtest/sweep transactions.
    ``transaction_timeout`` (Postgres 17+, absent on the production PG16 server)
    is opt-in via ``DB_TRANSACTION_TIMEOUT_MS`` so it cannot break older servers
    or long read transactions.
    """
    settings = {
        "idle_in_transaction_session_timeout": os.getenv(
            "DB_IDLE_IN_TRANSACTION_TIMEOUT_MS", _DEFAULT_IDLE_IN_TRANSACTION_TIMEOUT_MS
        ),
    }
    transaction_timeout = os.getenv("DB_TRANSACTION_TIMEOUT_MS", "").strip()
    if transaction_timeout and transaction_timeout != "0":
        settings["transaction_timeout"] = transaction_timeout
    return settings


def get_engine() -> AsyncEngine:
    """Get or create the async database engine."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_database_url(),
            echo=os.getenv("SQL_ECHO", "false").lower() == "true",
            pool_pre_ping=True,
            pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
            json_serializer=_json_serializer,
            connect_args={"server_settings": _connect_server_settings()},
        )
        _install_query_timing(_engine)
    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session maker."""
    global _async_session_maker
    if _async_session_maker is None:
        _async_session_maker = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_maker


@dataclass(frozen=True)
class PoolStats:
    """Point-in-time snapshot of the connection pool.

    All counts come from the live SQLAlchemy pool, except the configured
    limits which mirror how ``get_engine`` was constructed.
    """

    checked_out: int  # connections currently in use
    checked_in: int  # connections idle in the pool
    pool_size: int  # configured base pool size
    max_overflow: int  # configured overflow allowance

    @property
    def total_open(self) -> int:
        """Physical connections currently held (in use + idle)."""
        return self.checked_out + self.checked_in

    @property
    def max_connections(self) -> int:
        """Upper bound this process may open against Postgres."""
        return self.pool_size + self.max_overflow


def get_pool_stats() -> PoolStats | None:
    """Return live connection-pool stats, or None if unavailable.

    Returns None when the engine has not been created yet, or when the
    configured pool type does not expose connection counters (e.g. NullPool
    in tests). Safe to call from anywhere — it only reads in-memory counters.
    """
    if _engine is None:
        return None

    pool = _engine.sync_engine.pool
    checked_out = getattr(pool, "checkedout", None)
    checked_in = getattr(pool, "checkedin", None)
    if checked_out is None or checked_in is None:
        return None

    return PoolStats(
        checked_out=checked_out(),
        checked_in=checked_in(),
        pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
    )


async def init_db() -> None:
    """Initialize database connection.

    Note: In production, use Alembic migrations instead of create_all.
    This is primarily for development/testing.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await assert_rls_capable(conn)
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connection and cleanup resources."""
    global _engine, _async_session_maker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_maker = None


async def set_tenant_guc(session: AsyncSession, tenant_id: UUID) -> None:
    """Bind the transaction-local RLS tenant GUC to ``tenant_id`` (fail-closed).

    Uses ``set_config(..., is_local => true)`` so the binding is scoped to the
    current transaction and cannot leak across pooled connections. Callers must
    not ``commit()`` between this and the queries it protects (commit clears it).
    """
    await session.execute(
        text(f"SELECT set_config('{TENANT_GUC}', :tenant, true)"),
        {"tenant": str(tenant_id)},
    )


# Frames belonging to the bypass plumbing itself; skipped when attributing a
# bypass to the code that asked for it.
_AUDIT_INTERNAL_MODULES = frozenset({__name__, "contextlib"})


def _bypass_caller() -> str:
    """``module.qualname`` of the nearest frame outside the bypass plumbing."""
    frame = inspect.currentframe()
    while frame is not None:
        module = str(frame.f_globals.get("__name__", ""))
        if module not in _AUDIT_INTERNAL_MODULES:
            return f"{module}.{frame.f_code.co_qualname}"
        frame = frame.f_back
    return "unknown"


def _audit_rls_bypass(operation: str, reason: str | None, tenant_scope: UUID | None) -> None:
    """Record one RLS-bypass use on the log stream and the bypass counter.

    The log line is the audit record: it carries the calling site, the caller's
    stated ``reason`` and the tenant the session is bound to (if any). The
    counter carries only the bounded ``operation`` label, so bypass frequency is
    graphable without putting identifiers on a metric.
    """
    logger.info(
        "RLS bypass",
        extra={
            "audit_event": "rls_bypass",
            "operation": operation,
            "caller": _bypass_caller(),
            "reason": reason,
            "tenant_scope": str(tenant_scope) if tenant_scope is not None else None,
        },
    )
    DB_RLS_BYPASS.labels(operation=operation).inc()


async def _apply_rls_bypass(session: AsyncSession) -> None:
    await session.execute(text(f"SELECT set_config('{BYPASS_GUC}', 'on', true)"))


async def set_rls_bypass(session: AsyncSession, *, reason: str | None = None) -> None:
    """Enable the transaction-local RLS system bypass for trusted cross-tenant work.

    Only server-owned background sweeps (equity snapshot, reconciliation) and the
    identity authority may use this; the value is never derived from request
    input. Every use is audited (see :func:`_audit_rls_bypass`); pass ``reason``
    to say why on the audit line.
    """
    await _apply_rls_bypass(session)
    _audit_rls_bypass("set_rls_bypass", reason, bound_tenant_guc(session))


_TenantGucHook = Callable[[Session, SessionTransaction, Connection], None]

# Per-session tenant binding installed by bind_tenant_guc (keyed weakly so a
# discarded session drops its entry).
_tenant_guc_hooks: WeakKeyDictionary[Session, tuple[UUID, _TenantGucHook]] = WeakKeyDictionary()


def bind_tenant_guc(session: AsyncSession, tenant_id: UUID) -> None:
    """Scope every transaction on ``session`` to ``tenant_id`` for RLS.

    The tenant GUC is transaction-local (cleared by each commit), so a one-shot
    :func:`set_tenant_guc` is unsafe on a long-lived session. This installs an
    ``after_begin`` hook on the underlying sync session that re-applies
    ``set_config('app.current_tenant', ..., is_local => true)`` at the start of every
    transaction for the session's lifetime. Rebinding replaces the previous
    tenant; :func:`unbind_tenant_guc` removes the binding. Takes effect from the
    next transaction begin (bind before the session's first query).
    """
    unbind_tenant_guc(session)
    tenant = str(tenant_id)

    def _apply(
        sync_session: Session, transaction: SessionTransaction, connection: Connection
    ) -> None:
        connection.execute(
            text(f"SELECT set_config('{TENANT_GUC}', :tenant, true)"), {"tenant": tenant}
        )

    event.listen(session.sync_session, "after_begin", _apply)
    _tenant_guc_hooks[session.sync_session] = (tenant_id, _apply)


def unbind_tenant_guc(session: AsyncSession) -> None:
    """Remove the per-transaction tenant binding installed by :func:`bind_tenant_guc`."""
    bound = _tenant_guc_hooks.pop(session.sync_session, None)
    if bound is not None:
        event.remove(session.sync_session, "after_begin", bound[1])


def bound_tenant_guc(session: AsyncSession) -> UUID | None:
    """The tenant ``session`` is bound to via :func:`bind_tenant_guc`, or None."""
    bound = _tenant_guc_hooks.get(session.sync_session)
    return bound[0] if bound is not None else None


async def verify_rls_enforcement() -> None:
    """Startup guard: assert the connected DB role cannot bypass RLS.

    Opens one connection from the shared engine and runs
    :func:`llamatrade_db.rls.assert_rls_capable` — no DDL. The check itself
    raises in production/staging and warns in development; connection failures
    follow the same environment split so a dev stack without a database boots.
    """
    try:
        async with get_engine().connect() as conn:
            await assert_rls_capable(conn)
    except RuntimeError:
        raise
    except Exception:
        if os.getenv("ENVIRONMENT", "development").lower() in PROD_ENVIRONMENTS:
            raise
        logger.warning("RLS enforcement startup check could not run", exc_info=True)


@asynccontextmanager
async def tenant_session(
    tenant_id: UUID,
    session_maker: async_sessionmaker[AsyncSession] | None = None,
) -> AsyncGenerator[AsyncSession]:
    """Open a session scoped to ``tenant_id`` for RLS (request / per-tenant paths).

    The GUC is set transaction-local on the opening transaction. A single
    handler transaction is the common case and stays scoped. A caller that
    ``commit()``s mid-request (releasing a row lock before a later read, a
    per-account persist loop) must use :func:`bind_tenant_guc` on the session
    instead, whose after-begin hook re-applies the GUC on every transaction; a
    bare ``set_tenant_guc`` is cleared by that first commit and the follow-on
    queries fail closed. Pass ``session_maker`` to reuse a specific factory
    (tests inject the test-DB factory); otherwise the process default is used.
    """
    maker = session_maker or get_session_maker()
    async with maker() as session:
        # set_tenant_guc is the first statement, so the pool checkout happens here.
        async with _count_pool_exhaustion():
            await set_tenant_guc(session, tenant_id)
        yield session


@asynccontextmanager
async def system_session(
    session_maker: async_sessionmaker[AsyncSession] | None = None,
    *,
    reason: str | None = None,
) -> AsyncGenerator[AsyncSession]:
    """Open a session with the RLS system bypass (trusted cross-tenant sweeps).

    Audited like :func:`set_rls_bypass`: one log line and one counter increment
    per use, attributed to the caller; pass ``reason`` to say why.
    """
    maker = session_maker or get_session_maker()
    async with maker() as session:
        async with _count_pool_exhaustion():
            await _apply_rls_bypass(session)
        _audit_rls_bypass("system_session", reason, None)
        yield session


async def get_db() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency to get database session.

    Usage:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            async with _count_pool_exhaustion():
                yield session
                await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
