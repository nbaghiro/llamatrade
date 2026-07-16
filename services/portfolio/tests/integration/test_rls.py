"""Postgres row-level security enforcement for the ledger tables (real DB).

Proves the RLS policy from ``llamatrade_db.rls`` actually isolates tenants at the
database layer — a query with the wrong (or no) tenant GUC cannot see another
tenant's rows even if the application forgets its ``WHERE tenant_id`` filter.

Enforcement requires a **non-superuser** role (superusers bypass RLS), so the
fixture provisions a dedicated app role and connects the session factory as it —
mirroring the production role model.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import make_url, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from llamatrade_common import TenantContext, reset_context, set_context
from llamatrade_db import system_session, tenant_session
from llamatrade_proto.generated import common_pb2, ledger_pb2

pytestmark = pytest.mark.integration

_APP_ROLE = "rls_app"
_APP_PASSWORD = "rls_app_pw"


@pytest_asyncio.fixture
async def rls_maker(postgres_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Ledger schema with RLS enabled, yielded via a NON-superuser app role.

    The admin (container superuser) creates the tables, applies the RLS policy,
    and provisions a plain login role; the returned factory connects as that role
    so the policies actually apply.
    """
    import llamatrade_db.models.auth
    import llamatrade_db.models.ledger
    import llamatrade_db.models.strategy
    from llamatrade_db.base import Base
    from llamatrade_db.rls import LEDGER_RLS_TABLES, enable_rls_statements

    # Touch the modules so they aren't pruned; imported for table registration.
    _ = (llamatrade_db.models.auth, llamatrade_db.models.ledger, llamatrade_db.models.strategy)

    admin = create_async_engine(postgres_url)
    async with admin.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        for table in LEDGER_RLS_TABLES:
            for statement in enable_rls_statements(table):
                await conn.execute(text(statement))
        # The Postgres container is session-scoped, so the role persists across
        # tests; create it only once, then (re-)grant on the freshly built tables.
        role_exists = await conn.scalar(
            text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": _APP_ROLE}
        )
        if not role_exists:
            await conn.execute(text(f"CREATE ROLE {_APP_ROLE} LOGIN PASSWORD '{_APP_PASSWORD}'"))
        await conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {_APP_ROLE}"))
        await conn.execute(
            text(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
                f"IN SCHEMA public TO {_APP_ROLE}"
            )
        )
        await conn.execute(
            text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {_APP_ROLE}")
        )
    await admin.dispose()

    app_url = make_url(postgres_url).set(username=_APP_ROLE, password=_APP_PASSWORD)
    app_engine = create_async_engine(app_url, poolclass=NullPool)
    try:
        yield async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await app_engine.dispose()


def _account(tenant):
    from llamatrade_db.models.ledger import Account

    return Account(tenant_id=tenant, credentials_id=uuid4(), base_currency="USD")


async def test_rls_scopes_reads_across_tenants(
    rls_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A tenant-bound session sees only its rows on an UN-filtered query; an
    un-bound session sees nothing (fail-closed); a system session sees all."""
    from llamatrade_db.models.ledger import Account

    a, b = uuid4(), uuid4()
    async with tenant_session(a, rls_maker) as db:
        db.add(_account(a))
        await db.commit()
    async with tenant_session(b, rls_maker) as db:
        db.add(_account(b))
        await db.commit()

    # Deliberately NO WHERE tenant_id — RLS must scope it.
    async with tenant_session(a, rls_maker) as db:
        seen = {row.tenant_id for row in (await db.scalars(select(Account))).all()}
        assert seen == {a}

    async with tenant_session(b, rls_maker) as db:
        seen = {row.tenant_id for row in (await db.scalars(select(Account))).all()}
        assert seen == {b}

    # No GUC bound → zero rows (fail-closed).
    async with rls_maker() as db:
        assert (await db.scalars(select(Account))).all() == []

    # Trusted system bypass → every tenant's rows.
    async with system_session(rls_maker) as db:
        seen = {row.tenant_id for row in (await db.scalars(select(Account))).all()}
        assert seen == {a, b}


async def test_rls_blocks_cross_tenant_insert(
    rls_maker: async_sessionmaker[AsyncSession],
) -> None:
    """WITH CHECK: a session bound to A cannot write a row owned by B."""
    a, b = uuid4(), uuid4()
    with pytest.raises(Exception) as exc:  # asyncpg raises an RLS-violation error
        async with tenant_session(a, rls_maker) as db:
            db.add(_account(b))
            await db.commit()
    assert "row-level security" in str(exc.value).lower()


async def test_servicer_service_token_happy_path_under_rls(
    rls_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A service token (S2S) supplies the tenant on the wire; the servicer resolves
    it, binds the RLS GUC to it, and the write/read succeed under RLS."""
    from src.grpc.ledger_servicer import LedgerServicer

    servicer = LedgerServicer()
    servicer._session_factory = rls_maker

    tenant = uuid4()
    wire = common_pb2.TenantContext(tenant_id=str(tenant), user_id=str(uuid4()))
    token = set_context(TenantContext(tenant_id=UUID(int=0), user_id=UUID(int=0), is_service=True))
    try:
        created = await servicer.get_or_create_account(
            ledger_pb2.GetOrCreateAccountRequest(context=wire, credentials_id=str(uuid4())),
            None,
        )
        assert created.account.tenant_id == str(tenant)
        assert len(created.base_sleeves) == 3

        listed = await servicer.list_sleeves(
            ledger_pb2.ListSleevesRequest(context=wire, account_id=created.account.id), None
        )
        assert len(listed.sleeves) == 3  # RLS-visible under the resolved tenant
    finally:
        reset_context(token)
