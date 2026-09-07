"""Shared plumbing for the real-Postgres (testcontainers) test tier.

Modules on this tier follow one convention: check Docker availability at import
time, fail loudly under ``CI_REQUIRE_DOCKER=1`` and skip cleanly otherwise, then
build a throwaway Postgres with the full migration chain applied and a
``NOSUPERUSER NOBYPASSRLS`` app role so RLS is actually enforced.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

ALEMBIC_DIR = Path(__file__).resolve().parents[1] / "llamatrade_db" / "alembic"

APP_ROLE_PASSWORD = "rls-test-pw"


def docker_available() -> bool:
    """True if a Docker daemon is reachable (testcontainers needs it)."""
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


def require_docker() -> bool:
    """Whether CI demands Docker (``CI_REQUIRE_DOCKER=1`` fails instead of skipping)."""
    return os.environ.get("CI_REQUIRE_DOCKER") == "1"


def apply_migrations(async_url: str, revision: str = "head") -> None:
    """Run ``alembic upgrade`` to ``revision`` against ``async_url``."""
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    prev = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = async_url
    try:
        command.upgrade(cfg, revision)
    finally:
        if prev is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev


def downgrade_migrations(async_url: str, revision: str) -> None:
    """Run ``alembic downgrade`` to ``revision`` against ``async_url``."""
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    prev = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = async_url
    try:
        command.downgrade(cfg, revision)
    finally:
        if prev is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev


def create_app_role(url: str, role: str, *, password: str = APP_ROLE_PASSWORD) -> None:
    """Create a ``NOSUPERUSER NOBYPASSRLS`` role with DML grants on public tables."""

    async def _create() -> None:
        engine = create_async_engine(url, poolclass=NullPool)
        async with engine.connect() as conn:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            await conn.execute(
                text(f"CREATE ROLE {role} LOGIN PASSWORD '{password}' NOSUPERUSER NOBYPASSRLS")
            )
            await conn.execute(
                text(
                    f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}"
                )
            )
        await engine.dispose()

    asyncio.run(_create())
