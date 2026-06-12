"""Database connection and session management."""

import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from llamatrade_db.base import Base

# Module-level engine and session maker (initialized lazily)
_engine: AsyncEngine | None = None
_async_session_maker: async_sessionmaker[AsyncSession] | None = None


def get_database_url() -> str:
    """Get database URL from environment."""
    return os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/llamatrade",
    )


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
        )
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
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connection and cleanup resources."""
    global _engine, _async_session_maker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_maker = None


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
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
