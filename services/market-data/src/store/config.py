"""Dedicated async engine for the market-data Timescale database.

Deliberately separate from ``llamatrade_db`` — this is a different database
(time-series workload, its own retention/compression) reached via
``MARKET_DATA_DB_URL``. Both the ingest and serving roles share this engine
within their own process.
"""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_market_data_db_url() -> str:
    """URL for the dedicated Timescale instance."""
    return os.getenv(
        "MARKET_DATA_DB_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/market_data",
    )


def get_engine() -> AsyncEngine:
    """Get or lazily create the dedicated Timescale engine."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_market_data_db_url(),
            echo=os.getenv("SQL_ECHO", "false").lower() == "true",
            pool_pre_ping=True,
            pool_size=int(os.getenv("MARKET_DATA_DB_POOL_SIZE", "5")),
            max_overflow=int(os.getenv("MARKET_DATA_DB_MAX_OVERFLOW", "5")),
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Get or lazily create the session factory bound to the dedicated engine."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def close_engine() -> None:
    """Dispose the engine (call on shutdown)."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
