"""Every RLS table carries the real policy, and the bypass GUC behaves as designed.

Two gaps this closes. First, ``test_rls`` proves ``RLS_TABLES`` matches the model
metadata, but nothing proved the migrated database actually carries the policy for
each one: a table added to the list without its migration, or a migration that
enabled RLS without FORCE, was invisible. Second, the bypass clause in the shipped
predicate was only ever asserted as a string; the probe policy in ``test_session_guc``
hand-rolls a predicate WITHOUT it, so ``system_session`` semantics (cross-tenant
visibility, transaction-local scope, fail-closed default) had no real-database proof.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from llamatrade_db.rls import BYPASS_GUC, RLS_TABLES, TENANT_GUC, enable_rls_statements
from tests._pg_tier import (
    APP_ROLE_PASSWORD,
    apply_migrations,
    create_app_role,
    docker_available,
    require_docker,
)

pytestmark = pytest.mark.integration

if not docker_available():
    if require_docker():
        pytest.fail("CI_REQUIRE_DOCKER=1: Docker is required but unavailable", pytrace=False)
    pytest.skip("Docker unavailable", allow_module_level=True)

testcontainers_pg = pytest.importorskip("testcontainers.postgres")

PROBE_TABLE = "rls_probe"
APP_ROLE = "rls_parity_app_role"


@pytest.fixture(scope="module")
def migrated_url() -> Iterator[str]:
    """A throwaway Postgres with the full migration chain applied."""
    with testcontainers_pg.PostgresContainer("postgres:16-alpine") as pg:
        url = pg.get_connection_url().replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        apply_migrations(url)
        yield url


@pytest.fixture(scope="module")
def app_url(migrated_url: str) -> str:
    """The migrated database reached as a NOSUPERUSER role, so RLS actually bites."""
    create_app_role(migrated_url, APP_ROLE)
    # render_as_string: str(URL) masks the password as '***'.
    return (
        make_url(migrated_url)
        .set(username=APP_ROLE, password=APP_ROLE_PASSWORD)
        .render_as_string(hide_password=False)
    )


@pytest_asyncio.fixture
async def conn(migrated_url: str) -> AsyncIterator[AsyncConnection]:
    """Owner connection: schema inspection only (a superuser bypasses RLS)."""
    engine = create_async_engine(migrated_url, poolclass=NullPool)
    async with engine.connect() as connection:
        yield connection
    await engine.dispose()


@pytest_asyncio.fixture
async def app_conn(app_url: str) -> AsyncIterator[AsyncConnection]:
    engine = create_async_engine(app_url, poolclass=NullPool)
    async with engine.connect() as connection:
        yield connection
    await engine.dispose()


class TestPolicyParity:
    """Each RLS_TABLES entry must carry the shipped policy in the migrated schema."""

    async def test_every_rls_table_has_rls_enabled_and_forced(self, conn: AsyncConnection) -> None:
        rows = await conn.execute(
            text(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = ANY(:tables)"
            ),
            {"tables": list(RLS_TABLES)},
        )
        state = {r.relname: (r.relrowsecurity, r.relforcerowsecurity) for r in rows}

        missing = sorted(set(RLS_TABLES) - set(state))
        assert not missing, f"tables absent from the migrated schema: {missing}"
        not_enabled = sorted(t for t, (enabled, _) in state.items() if not enabled)
        assert not not_enabled, f"RLS not enabled: {not_enabled}"
        not_forced = sorted(t for t, (_, forced) in state.items() if not forced)
        assert not not_forced, f"RLS not FORCEd (owner bypasses it): {not_forced}"

    async def test_every_rls_table_has_the_tenant_isolation_policy(
        self, conn: AsyncConnection
    ) -> None:
        rows = await conn.execute(
            text("SELECT tablename, policyname, qual, with_check FROM pg_policies")
        )
        policies = {r.tablename: r for r in rows}

        for table in RLS_TABLES:
            policy = policies.get(table)
            assert policy is not None, f"{table} has no RLS policy"
            assert policy.policyname == f"{table}_tenant_isolation"
            # Both directions guarded: a read filter without WITH CHECK would let
            # a bound session write rows belonging to another tenant.
            for clause in (policy.qual, policy.with_check):
                assert clause is not None
                assert TENANT_GUC in clause
                assert BYPASS_GUC in clause


class TestBypassSemantics:
    """The bypass clause is what ``system_session`` relies on; prove it on real SQL.

    Reads and writes run as the NOSUPERUSER app role: a superuser bypasses RLS
    outright, so the policy would never be exercised.
    """

    @pytest_asyncio.fixture(autouse=True)
    async def _probe_table(self, conn: AsyncConnection) -> AsyncIterator[None]:
        """A throwaway table carrying the SHIPPED policy, not a hand-rolled one."""
        await conn.execute(
            text(f"CREATE TABLE {PROBE_TABLE} (id uuid PRIMARY KEY, tenant_id uuid NOT NULL)")
        )
        for statement in enable_rls_statements(PROBE_TABLE):
            await conn.execute(text(statement))
        await conn.execute(text(f"GRANT SELECT, INSERT ON {PROBE_TABLE} TO {APP_ROLE}"))
        await conn.commit()
        yield
        await conn.rollback()
        await conn.execute(text(f"DROP TABLE IF EXISTS {PROBE_TABLE}"))
        await conn.commit()

    @staticmethod
    async def _seed(app_conn: AsyncConnection, tenants: list[uuid.UUID]) -> None:
        await app_conn.execute(text(f"SET LOCAL {BYPASS_GUC} = 'on'"))
        for tenant in tenants:
            await app_conn.execute(
                text(f"INSERT INTO {PROBE_TABLE} (id, tenant_id) VALUES (:i, :t)"),
                {"i": uuid.uuid4(), "t": tenant},
            )
        await app_conn.commit()

    @staticmethod
    async def _visible(app_conn: AsyncConnection) -> int:
        result = await app_conn.execute(text(f"SELECT count(*) FROM {PROBE_TABLE}"))
        return int(result.scalar_one())

    async def test_bypass_on_sees_every_tenant(self, app_conn: AsyncConnection) -> None:
        await self._seed(app_conn, [uuid.uuid4(), uuid.uuid4()])

        await app_conn.execute(text(f"SET LOCAL {BYPASS_GUC} = 'on'"))
        assert await self._visible(app_conn) == 2

    async def test_tenant_guc_scopes_without_bypass(self, app_conn: AsyncConnection) -> None:
        mine, theirs = uuid.uuid4(), uuid.uuid4()
        await self._seed(app_conn, [mine, theirs])

        await app_conn.execute(text(f"SET LOCAL {TENANT_GUC} = '{mine}'"))
        assert await self._visible(app_conn) == 1

    async def test_unbound_session_sees_nothing(self, app_conn: AsyncConnection) -> None:
        """Fail-closed: no bypass and no tenant GUC yields zero rows, never a cast error."""
        await self._seed(app_conn, [uuid.uuid4(), uuid.uuid4()])

        assert await self._visible(app_conn) == 0

    async def test_blank_tenant_guc_is_treated_as_unset(self, app_conn: AsyncConnection) -> None:
        """NULLIF maps a blank GUC to NULL so the uuid cast never raises."""
        await self._seed(app_conn, [uuid.uuid4()])

        await app_conn.execute(text(f"SET LOCAL {TENANT_GUC} = ''"))
        assert await self._visible(app_conn) == 0

    async def test_bypass_is_transaction_local(self, app_conn: AsyncConnection) -> None:
        """SET LOCAL dies with the transaction, so a bypass cannot leak into the next one."""
        await self._seed(app_conn, [uuid.uuid4(), uuid.uuid4()])

        await app_conn.execute(text(f"SET LOCAL {BYPASS_GUC} = 'on'"))
        assert await self._visible(app_conn) == 2
        await app_conn.commit()

        assert await self._visible(app_conn) == 0

    async def test_bypass_only_honors_the_exact_on_value(self, app_conn: AsyncConnection) -> None:
        await self._seed(app_conn, [uuid.uuid4()])

        await app_conn.execute(text(f"SET LOCAL {BYPASS_GUC} = 'true'"))
        assert await self._visible(app_conn) == 0

    async def test_write_check_refuses_a_foreign_tenant_row(
        self, app_conn: AsyncConnection
    ) -> None:
        """WITH CHECK is the write half: a bound session cannot insert for another tenant."""
        mine, theirs = uuid.uuid4(), uuid.uuid4()
        await app_conn.execute(text(f"SET LOCAL {TENANT_GUC} = '{mine}'"))

        with pytest.raises(Exception, match="row-level security"):
            await app_conn.execute(
                text(f"INSERT INTO {PROBE_TABLE} (id, tenant_id) VALUES (:i, :t)"),
                {"i": uuid.uuid4(), "t": theirs},
            )
        await app_conn.rollback()
