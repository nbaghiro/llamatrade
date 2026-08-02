"""Real-Postgres tests for the backtest_results tenant scope (migration 039).

Applies the full migration chain to a throwaway Postgres and asserts the
end-to-end behaviour: the BEFORE INSERT trigger copies ``tenant_id`` from the
parent backtest (writers never set it), and the fail-closed RLS policy exposes a
result only to the transaction bound to its tenant. Requires Docker
(testcontainers); skips cleanly where Docker is absent.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

# testcontainers is an optional integration dependency; skip the whole module
# rather than error at collection time when it (or Docker) is missing.
PostgresContainer = pytest.importorskip("testcontainers.postgres").PostgresContainer

_ALEMBIC_DIR = Path(__file__).resolve().parents[1] / "llamatrade_db" / "alembic"
_APP_ROLE = "backtest_rls_app_role"
_APP_PW = "rls-test-pw"


def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _docker_available(), reason="Docker not available for testcontainers"
)


def _apply_migrations(async_url: str) -> None:
    """Run ``alembic upgrade head`` against ``async_url`` (proves 001->039 apply)."""
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(_ALEMBIC_DIR))
    prev = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = async_url
    try:
        command.upgrade(cfg, "head")
    finally:
        if prev is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev


async def _seed_backtest(conn: AsyncConnection, tenant_id: uuid.UUID) -> uuid.UUID:
    """Insert a tenant + backtest under ``tenant_id``; return the backtest id."""
    backtest_id = uuid.uuid4()
    await conn.execute(
        text("INSERT INTO tenants (id, name, slug, is_active) VALUES (:id, 'T', :slug, true)"),
        {"id": tenant_id, "slug": f"t-{tenant_id.hex[:12]}"},
    )
    await conn.execute(
        text(
            "INSERT INTO backtests (id, tenant_id, strategy_id, strategy_version, name, "
            "status, config, symbols, start_date, end_date, initial_capital, created_by) "
            "VALUES (:id, :t, :sid, 1, 'bt', 'pending'::backtest_status, '{}'::jsonb, "
            "'[]'::jsonb, '2024-01-01', '2024-02-01', 1000, :cb)"
        ),
        {"id": backtest_id, "t": tenant_id, "sid": uuid.uuid4(), "cb": uuid.uuid4()},
    )
    return backtest_id


async def _insert_result(conn: AsyncConnection, backtest_id: uuid.UUID) -> None:
    """Insert a backtest_results row WITHOUT tenant_id (as the worker does)."""
    await conn.execute(
        text(
            "INSERT INTO backtest_results (id, backtest_id, total_return, annual_return, "
            "sharpe_ratio, max_drawdown, win_rate, total_trades, winning_trades, "
            "losing_trades, avg_trade_return, final_equity) "
            "VALUES (:id, :bt, 0.1, 0.1, 1, 0.05, 0.5, 0, 0, 0, 0, 1100)"
        ),
        {"id": uuid.uuid4(), "bt": backtest_id},
    )


@pytest.fixture(scope="module")
def pg_url():
    """Throwaway Postgres with the chain applied and a NOBYPASSRLS app role."""
    with PostgresContainer(
        image="postgres:16-alpine",
        username="postgres",
        password="postgres",
        dbname="backtest_rls",
        driver="asyncpg",
    ) as pg:
        url = pg.get_connection_url()
        _apply_migrations(url)

        async def _create_role() -> None:
            engine = create_async_engine(url, poolclass=NullPool)
            async with engine.connect() as conn:
                await conn.execution_options(isolation_level="AUTOCOMMIT")
                await conn.execute(
                    text(
                        f"CREATE ROLE {_APP_ROLE} LOGIN PASSWORD '{_APP_PW}' "
                        "NOSUPERUSER NOBYPASSRLS"
                    )
                )
                await conn.execute(
                    text(f"GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO {_APP_ROLE}")
                )
            await engine.dispose()

        asyncio.run(_create_role())
        yield url


@pytest_asyncio.fixture
async def admin_engine(pg_url: str) -> AsyncGenerator:
    engine = create_async_engine(pg_url, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def app_engine(pg_url: str) -> AsyncGenerator:
    url = make_url(pg_url).set(username=_APP_ROLE, password=_APP_PW)
    engine = create_async_engine(url, poolclass=NullPool)
    yield engine
    await engine.dispose()


async def test_trigger_backfills_tenant_id_from_parent(admin_engine) -> None:
    """A result inserted with no tenant_id inherits its backtest's tenant."""
    tenant = uuid.uuid4()
    async with admin_engine.begin() as conn:
        backtest_id = await _seed_backtest(conn, tenant)
        await _insert_result(conn, backtest_id)
    async with admin_engine.connect() as conn:
        stored = await conn.scalar(
            text("SELECT tenant_id FROM backtest_results WHERE backtest_id = :bt"),
            {"bt": backtest_id},
        )
    assert str(stored) == str(tenant)


async def test_rls_isolates_results_by_tenant(admin_engine, app_engine) -> None:
    """The RLS policy exposes a result only to its own tenant, fail-closed."""
    tenant = uuid.uuid4()
    other = uuid.uuid4()
    async with admin_engine.begin() as conn:
        backtest_id = await _seed_backtest(conn, tenant)
        await _insert_result(conn, backtest_id)

    async def _visible(tenant_guc: str | None) -> int:
        async with app_engine.begin() as conn:
            if tenant_guc is not None:
                await conn.execute(
                    text("SELECT set_config('app.current_tenant', :t, true)"),
                    {"t": tenant_guc},
                )
            count = await conn.scalar(
                text("SELECT count(*) FROM backtest_results WHERE backtest_id = :bt"),
                {"bt": backtest_id},
            )
            return int(count or 0)

    assert await _visible(str(tenant)) == 1
    assert await _visible(str(other)) == 0
    assert await _visible(None) == 0


async def test_rls_with_check_matches_parent_tenant(admin_engine, app_engine) -> None:
    """An app-role insert under the parent's tenant passes the WITH CHECK."""
    tenant = uuid.uuid4()
    async with admin_engine.begin() as conn:
        backtest_id = await _seed_backtest(conn, tenant)

    async with app_engine.begin() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tenant)}
        )
        await _insert_result(conn, backtest_id)

    async with admin_engine.connect() as conn:
        stored = await conn.scalar(
            text("SELECT tenant_id FROM backtest_results WHERE backtest_id = :bt"),
            {"bt": backtest_id},
        )
    assert str(stored) == str(tenant)
