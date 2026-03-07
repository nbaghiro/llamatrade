"""Integration test configuration with database session and migration fixtures.

This module provides:
- Database session fixtures with transaction rollback for test isolation
- Migration runner to set up schema using Alembic
- Service-specific fixtures for testing against real databases
"""

import os
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

# Re-export root conftest fixtures
from tests.conftest import (
    database_url,
    postgres_container,
    redis_container,
    redis_url,
    set_test_environment,
)

__all__ = [
    "database_url",
    "postgres_container",
    "redis_container",
    "redis_url",
    "set_test_environment",
]


@pytest.fixture(scope="session")
def run_migrations(database_url: str) -> None:
    """Create all tables in the test database using SQLAlchemy metadata.

    We use create_all() instead of Alembic migrations for tests because:
    1. It's faster than running all migration steps
    2. It avoids issues with migration scripts that have SQL bind parameters
    3. It ensures we're testing against the current model definitions

    Note: This means integration tests verify the ORM models, not the migrations.
    Migration testing should be done separately.

    Note: Market data tables (bars, quotes, trades) are excluded because they use
    PostgreSQL partitioning which requires special setup. These tables are not
    needed for security/isolation tests.
    """
    import asyncio

    from sqlalchemy.ext.asyncio import create_async_engine

    from llamatrade_db.base import Base

    # Import all models to register them with Base.metadata
    # Note: Bar, Quote, Trade are imported but excluded from creation
    # because they use PostgreSQL partitioning
    from llamatrade_db.models import (  # noqa: F401
        AlpacaCredentials,
        APIKey,
        Backtest,
        BacktestResult,
        Bar,
        Invoice,
        Order,
        PaymentMethod,
        PerformanceMetrics,
        Plan,
        PortfolioHistory,
        PortfolioSummary,
        Position,
        Quote,
        Strategy,
        StrategyTemplate,
        StrategyVersion,
        Subscription,
        Tenant,
        Trade,
        TradingSession,
        Transaction,
        UsageRecord,
        User,
    )

    # Tables to exclude from creation (use PostgreSQL partitioning)
    excluded_tables = {"bars", "quotes", "trades"}

    async def create_tables():
        engine = create_async_engine(database_url)

        async with engine.begin() as conn:
            # Drop and recreate public schema for truly clean state
            await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
            await conn.execute(text("GRANT ALL ON SCHEMA public TO postgres"))
            await conn.execute(text("GRANT ALL ON SCHEMA public TO public"))

        # Now create tables (excluding partitioned ones)
        async with engine.begin() as conn:
            # Get tables to create (excluding partitioned tables)
            tables_to_create = [
                table for table in Base.metadata.sorted_tables if table.name not in excluded_tables
            ]

            # Use create_all with tables parameter to handle indexes properly
            await conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(
                    sync_conn,
                    tables=tables_to_create,
                    checkfirst=False,
                )
            )

        await engine.dispose()

    asyncio.run(create_tables())


@pytest.fixture
async def async_engine(database_url: str, run_migrations: None) -> AsyncGenerator[AsyncEngine]:
    """Create async engine for each test.

    Uses NullPool to avoid connection pool issues with different event loops.
    Depends on run_migrations to ensure schema exists.
    """
    engine = create_async_engine(
        database_url,
        echo=os.getenv("SQL_ECHO", "false").lower() == "true",
        poolclass=NullPool,  # Avoid connection pool issues with async
    )
    yield engine
    await engine.dispose()


@pytest.fixture
def session_maker(async_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create session maker for each test."""
    return async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture
async def db_session(
    async_engine: AsyncEngine,
    session_maker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession]:
    """Create a database session with transaction rollback for test isolation.

    Each test gets its own transaction that is rolled back at the end,
    ensuring tests don't affect each other's data.
    """
    # Start a connection with a transaction
    async with async_engine.connect() as connection:
        # Begin a nested transaction (savepoint)
        await connection.begin()

        # Create session bound to this connection
        async with session_maker(bind=connection) as session:
            yield session

        # Rollback the transaction (cleans up all test data)
        await connection.rollback()


@pytest.fixture
async def clean_db_session(
    async_engine: AsyncEngine,
    session_maker: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession]:
    """Create a database session that commits (for tests that need persistence).

    Use sparingly - prefer db_session with rollback for test isolation.
    This fixture truncates tables after the test.
    """
    async with session_maker() as session:
        yield session
        await session.commit()

    # Clean up tables after test (order matters for foreign keys)
    async with async_engine.connect() as conn:
        # Get all table names
        result = await conn.execute(
            text("""
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
                AND tablename NOT LIKE 'alembic%'
            """)
        )
        tables = [row[0] for row in result]

        if tables:
            # Truncate all tables with CASCADE
            await conn.execute(text(f"TRUNCATE TABLE {', '.join(tables)} CASCADE"))
            await conn.commit()


# Fixture plugins are registered in tests/conftest.py (root level)
# to satisfy pytest's requirement that pytest_plugins be in top-level conftest
