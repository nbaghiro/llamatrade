"""Minimal SQL migration runner for the dedicated Timescale database.

Timescale DDL (``create_hypertable``, continuous aggregates, policy functions)
cannot run inside a wrapping transaction, so statements are applied one at a
time on an AUTOCOMMIT connection. Applied files are tracked in
``schema_migrations`` so re-runs are idempotent.

Run standalone:  ``python -m src.store.migrate``
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.store.config import close_engine, get_engine

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def split_statements(sql: str) -> list[str]:
    """Split a SQL file into individual statements, stripping ``--`` comments.

    Pure and side-effect free so it is unit-testable without a database. Our
    DDL contains no string literals with embedded ``--`` or ``;``, so a simple
    line-comment strip + semicolon split is sufficient and predictable.
    """
    cleaned_lines: list[str] = []
    for line in sql.splitlines():
        comment_at = line.find("--")
        if comment_at != -1:
            line = line[:comment_at]
        cleaned_lines.append(line)
    body = "\n".join(cleaned_lines)
    return [stmt.strip() for stmt in body.split(";") if stmt.strip()]


def discover_migrations(migrations_dir: Path = MIGRATIONS_DIR) -> list[Path]:
    """Ordered list of ``*.sql`` migration files."""
    return sorted(migrations_dir.glob("*.sql"))


async def run_migrations(engine: AsyncEngine | None = None) -> list[str]:
    """Apply pending migrations in order; return the versions newly applied."""
    engine = engine or get_engine()
    autocommit = engine.execution_options(isolation_level="AUTOCOMMIT")
    newly_applied: list[str] = []

    async with autocommit.connect() as conn:
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version TEXT PRIMARY KEY, "
                "applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
        )
        existing = set(
            (await conn.execute(text("SELECT version FROM schema_migrations"))).scalars()
        )

        for path in discover_migrations():
            version = path.stem
            if version in existing:
                continue
            logger.info("Applying migration %s", version)
            for statement in split_statements(path.read_text()):
                await conn.execute(text(statement))
            await conn.execute(
                text("INSERT INTO schema_migrations (version) VALUES (:v)"),
                {"v": version},
            )
            newly_applied.append(version)

    return newly_applied


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    async def _run() -> None:
        try:
            applied = await run_migrations()
            if applied:
                logger.info("Applied migrations: %s", ", ".join(applied))
            else:
                logger.info("Database already up to date")
        finally:
            await close_engine()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
