"""Real-Postgres tests for RLS tenant-GUC session scoping.

SQLite can't exercise ``set_config``/``pg_roles``, so these run the actual SQL
against a throwaway Postgres. Requires Docker (testcontainers).
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from llamatrade_db.rls import TENANT_GUC, assert_rls_capable
from llamatrade_db.session import (
    bind_tenant_guc,
    bound_tenant_guc,
    set_tenant_guc,
    tenant_session,
    unbind_tenant_guc,
)

# testcontainers is an optional integration dependency; when it's absent this
# whole module skips instead of erroring at collection time.
PostgresContainer = pytest.importorskip("testcontainers.postgres").PostgresContainer


def _docker_available() -> bool:
    """True if a Docker daemon is reachable (testcontainers needs it)."""
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


# Skip cleanly (rather than error) where Docker isn't available — e.g. a
# pre-commit run on a machine without Docker. CI runs these with Docker up.
pytestmark = pytest.mark.skipif(
    not _docker_available(), reason="Docker not available for testcontainers"
)

_BYPASS_ROLE = "rls_bypass_role"
_APP_ROLE = "rls_app_role"
_ROLE_PASSWORD = "rls-test-pw"


@pytest.fixture(scope="module")
def pg_url():
    """Start a throwaway Postgres for the module."""
    with PostgresContainer(
        image="postgres:16-alpine",
        username="postgres",
        password="postgres",
        dbname="guc_test",
        driver="asyncpg",
    ) as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="module")
def roles(pg_url: str) -> str:
    """Create a BYPASSRLS role and a plain app role once for the module."""

    async def _create() -> None:
        engine = create_async_engine(pg_url, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.execute(
                text(f"CREATE ROLE {_BYPASS_ROLE} LOGIN PASSWORD '{_ROLE_PASSWORD}' BYPASSRLS")
            )
            await conn.execute(
                text(
                    f"CREATE ROLE {_APP_ROLE} LOGIN PASSWORD '{_ROLE_PASSWORD}' "
                    "NOSUPERUSER NOBYPASSRLS"
                )
            )
        await engine.dispose()

    asyncio.run(_create())
    return pg_url


@pytest_asyncio.fixture
async def session(pg_url: str) -> AsyncGenerator[AsyncSession]:
    """A session on a NullPool engine: every transaction may get a fresh connection."""
    engine = create_async_engine(pg_url, poolclass=NullPool)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _current_tenant(session: AsyncSession) -> str | None:
    return await session.scalar(text(f"SELECT current_setting('{TENANT_GUC}', true)"))


_PROBE_TABLE = "guc_probe"


@pytest.fixture(scope="module")
def rls_probe(roles: str) -> str:
    """Create a fail-closed RLS table and grant the app role, once for the module.

    The policy mirrors the platform's tenant isolation: a row is visible only when
    the tenant GUC matches its ``tenant_id`` (unset GUC sees nothing).
    """

    async def _setup() -> None:
        engine = create_async_engine(roles, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    f"CREATE TABLE {_PROBE_TABLE} "
                    "(id uuid PRIMARY KEY, tenant_id uuid NOT NULL, val text)"
                )
            )
            await conn.execute(text(f"ALTER TABLE {_PROBE_TABLE} ENABLE ROW LEVEL SECURITY"))
            await conn.execute(text(f"ALTER TABLE {_PROBE_TABLE} FORCE ROW LEVEL SECURITY"))
            match = f"tenant_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::uuid"
            await conn.execute(
                text(
                    f"CREATE POLICY {_PROBE_TABLE}_isolation ON {_PROBE_TABLE} "
                    f"USING ({match}) WITH CHECK ({match})"
                )
            )
            await conn.execute(text(f"GRANT SELECT, INSERT ON {_PROBE_TABLE} TO {_APP_ROLE}"))
        await engine.dispose()

    asyncio.run(_setup())
    return roles


@pytest_asyncio.fixture
async def admin_engine(rls_probe: str) -> AsyncGenerator[AsyncEngine]:
    """Superuser engine used to seed probe rows across tenants (bypasses RLS)."""
    engine = create_async_engine(rls_probe, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def app_maker(rls_probe: str) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    """Session maker for the NOBYPASSRLS app role on a NullPool engine."""
    url = make_url(rls_probe).set(username=_APP_ROLE, password=_ROLE_PASSWORD)
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _seed(admin_engine: AsyncEngine, tenant_id: UUID) -> None:
    async with admin_engine.begin() as conn:
        await conn.execute(
            text(f"INSERT INTO {_PROBE_TABLE} (id, tenant_id, val) VALUES (:i, :t, 'x')"),
            {"i": uuid4(), "t": tenant_id},
        )


class TestTenantGucScope:
    async def test_set_tenant_guc_scope_cleared_by_commit(self, session: AsyncSession) -> None:
        """Pins the hazard: the one-shot GUC is transaction-local."""
        tenant = uuid4()
        await set_tenant_guc(session, tenant)
        assert await _current_tenant(session) == str(tenant)

        await session.commit()

        assert (await _current_tenant(session)) in (None, "")

    async def test_bind_tenant_guc_survives_commits(self, session: AsyncSession) -> None:
        tenant = uuid4()
        bind_tenant_guc(session, tenant)
        assert await _current_tenant(session) == str(tenant)

        await session.commit()
        assert await _current_tenant(session) == str(tenant)

        await session.commit()
        assert await _current_tenant(session) == str(tenant)

    async def test_rebinding_switches_tenants(self, session: AsyncSession) -> None:
        tenant_a, tenant_b = uuid4(), uuid4()
        bind_tenant_guc(session, tenant_a)
        assert await _current_tenant(session) == str(tenant_a)
        await session.commit()

        bind_tenant_guc(session, tenant_b)
        assert bound_tenant_guc(session) == tenant_b
        assert await _current_tenant(session) == str(tenant_b)
        await session.commit()
        assert await _current_tenant(session) == str(tenant_b)

    async def test_unbind_removes_scope_for_later_transactions(self, session: AsyncSession) -> None:
        tenant = uuid4()
        bind_tenant_guc(session, tenant)
        assert await _current_tenant(session) == str(tenant)
        await session.commit()

        unbind_tenant_guc(session)
        assert bound_tenant_guc(session) is None
        assert (await _current_tenant(session)) in (None, "")


class TestTenantSessionDurability:
    """``tenant_session`` scopes its opening transaction; mid-commit callers must bind."""

    async def test_scopes_the_opening_transaction(
        self, admin_engine: AsyncEngine, app_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """The single-transaction path sees only the tenant's rows under RLS."""
        tenant, other = uuid4(), uuid4()
        await _seed(admin_engine, tenant)
        await _seed(admin_engine, other)

        async with tenant_session(tenant, app_maker) as db:
            assert await _current_tenant(db) == str(tenant)
            assert await db.scalar(text(f"SELECT count(*) FROM {_PROBE_TABLE}")) == 1

    async def test_mid_session_commit_needs_bind_not_the_one_shot(
        self, admin_engine: AsyncEngine, app_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """A commit inside ``tenant_session`` clears the one-shot GUC; ``bind_tenant_guc``
        on the same session re-applies it, which is the sanctioned mid-commit pattern."""
        tenant = uuid4()
        await _seed(admin_engine, tenant)

        async with tenant_session(tenant, app_maker) as db:
            await db.commit()
            assert (await _current_tenant(db)) in (None, "")
            bind_tenant_guc(db, tenant)
            await db.commit()
            assert await _current_tenant(db) == str(tenant)
            assert await db.scalar(text(f"SELECT count(*) FROM {_PROBE_TABLE}")) == 1

    async def test_one_shot_guc_loses_rows_after_commit(
        self, admin_engine: AsyncEngine, app_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """The one-shot GUC clears on commit, so the RLS follow-on read fails closed.

        Pins why the request path must not use ``set_tenant_guc`` on a session that
        commits mid-request.
        """
        tenant = uuid4()
        await _seed(admin_engine, tenant)

        async with app_maker() as db:
            await set_tenant_guc(db, tenant)
            assert await db.scalar(text(f"SELECT count(*) FROM {_PROBE_TABLE}")) == 1

            await db.commit()

            assert (await _current_tenant(db)) in (None, "")
            assert await db.scalar(text(f"SELECT count(*) FROM {_PROBE_TABLE}")) == 0


class TestEngineServerSettings:
    """The shared engine applies the connect-time transaction-idle bound."""

    async def _reset_engine(self) -> None:
        from llamatrade_db.session import close_db

        await close_db()

    async def test_idle_in_transaction_timeout_applied(
        self, pg_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamatrade_db.session import get_engine

        monkeypatch.setenv("DATABASE_URL", pg_url)
        monkeypatch.setenv("DB_IDLE_IN_TRANSACTION_TIMEOUT_MS", "90000")
        await self._reset_engine()
        try:
            async with get_engine().connect() as conn:
                raw = await conn.scalar(
                    text(
                        "SELECT setting FROM pg_settings "
                        "WHERE name = 'idle_in_transaction_session_timeout'"
                    )
                )
            assert raw == "90000"
        finally:
            await self._reset_engine()


class TestAssertRlsCapable:
    async def _run_as(self, url: str, username: str) -> None:
        engine = create_async_engine(
            make_url(url).set(username=username, password=_ROLE_PASSWORD), poolclass=NullPool
        )
        try:
            async with engine.connect() as conn:
                await assert_rls_capable(conn)
        finally:
            await engine.dispose()

    async def test_raises_for_bypass_role_in_production(
        self, roles: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")
        with pytest.raises(RuntimeError, match="bypasses RLS"):
            await self._run_as(roles, _BYPASS_ROLE)

    async def test_passes_for_nosuperuser_role_in_production(
        self, roles: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")
        await self._run_as(roles, _APP_ROLE)

    async def test_warns_for_bypass_role_in_development(
        self,
        roles: str,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", "development")
        with caplog.at_level(logging.WARNING, logger="llamatrade_db.rls"):
            await self._run_as(roles, _BYPASS_ROLE)
        assert any("bypasses RLS" in r.message for r in caplog.records)


class TestVerifyRlsEnforcement:
    async def _reset_engine(self) -> None:
        from llamatrade_db.session import close_db

        await close_db()

    async def test_raises_for_bypass_role_in_production(
        self, roles: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamatrade_db.session import verify_rls_enforcement

        url = make_url(roles).set(username=_BYPASS_ROLE, password=_ROLE_PASSWORD)
        monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
        monkeypatch.setenv("ENVIRONMENT", "production")
        await self._reset_engine()
        try:
            with pytest.raises(RuntimeError, match="bypasses RLS"):
                await verify_rls_enforcement()
        finally:
            await self._reset_engine()

    async def test_passes_for_app_role_in_production(
        self, roles: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from llamatrade_db.session import verify_rls_enforcement

        url = make_url(roles).set(username=_APP_ROLE, password=_ROLE_PASSWORD)
        monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
        monkeypatch.setenv("ENVIRONMENT", "production")
        await self._reset_engine()
        try:
            await verify_rls_enforcement()
        finally:
            await self._reset_engine()

    async def test_connection_failure_warns_in_development(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from llamatrade_db.session import verify_rls_enforcement

        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@127.0.0.1:1/nope")
        monkeypatch.setenv("ENVIRONMENT", "development")
        await self._reset_engine()
        try:
            with caplog.at_level(logging.WARNING, logger="llamatrade_db.session"):
                await verify_rls_enforcement()
            assert any("could not run" in r.message for r in caplog.records)
        finally:
            await self._reset_engine()
