"""Integration tests: migration idempotency and the Timescale objects they create."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.store.migrate import discover_migrations, run_migrations

pytestmark = pytest.mark.integration


async def _scalars(engine: AsyncEngine, sql: str) -> set[str]:
    async with engine.connect() as conn:
        return set((await conn.execute(text(sql))).scalars())


class TestMigrationIdempotency:
    async def test_rerun_applies_nothing(self, timescale_engine: AsyncEngine) -> None:
        # The engine fixture already migrated; a second run must be a no-op.
        assert await run_migrations(timescale_engine) == []

    async def test_every_discovered_version_is_recorded(
        self, timescale_engine: AsyncEngine
    ) -> None:
        recorded = await _scalars(timescale_engine, "SELECT version FROM schema_migrations")
        assert recorded == {path.stem for path in discover_migrations()}


class TestTimescaleObjects:
    async def test_base_tables_are_hypertables(self, timescale_engine: AsyncEngine) -> None:
        hypertables = await _scalars(
            timescale_engine,
            "SELECT hypertable_name FROM timescaledb_information.hypertables",
        )
        assert {"bars_1m", "bars_daily"}.issubset(hypertables)

    async def test_continuous_aggregates_exist(self, timescale_engine: AsyncEngine) -> None:
        aggregates = await _scalars(
            timescale_engine,
            "SELECT view_name FROM timescaledb_information.continuous_aggregates",
        )
        expected = {"bars_5m", "bars_15m", "bars_30m", "bars_1h", "bars_4h", "bars_1w", "bars_1mo"}
        assert expected.issubset(aggregates)

    async def test_compression_and_retention_policies_installed(
        self, timescale_engine: AsyncEngine
    ) -> None:
        async with timescale_engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT proc_name, hypertable_name "
                        "FROM timescaledb_information.jobs WHERE proc_name LIKE 'policy_%'"
                    )
                )
            ).all()
        jobs = {(proc, table) for proc, table in rows}

        assert ("policy_compression", "bars_1m") in jobs
        assert ("policy_compression", "bars_daily") in jobs
        assert ("policy_retention", "bars_1m") in jobs
        # Daily bars are kept forever: no retention policy may exist for them.
        assert ("policy_retention", "bars_daily") not in jobs

    async def test_every_aggregate_has_a_refresh_policy(
        self, timescale_engine: AsyncEngine
    ) -> None:
        async with timescale_engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT ca.view_name FROM timescaledb_information.jobs j "
                        "JOIN timescaledb_information.continuous_aggregates ca "
                        "ON ca.materialization_hypertable_name = j.hypertable_name "
                        "WHERE j.proc_name = 'policy_refresh_continuous_aggregate'"
                    )
                )
            ).all()
        refreshed = {row[0] for row in rows}
        expected = {"bars_5m", "bars_15m", "bars_30m", "bars_1h", "bars_4h", "bars_1w", "bars_1mo"}
        assert expected.issubset(refreshed)
