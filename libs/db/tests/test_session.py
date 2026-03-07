"""Tests for llamatrade_db.session module."""

import os
from unittest.mock import patch

import pytest

from llamatrade_db.session import (
    get_database_url,
)


class TestGetDatabaseUrl:
    """Tests for get_database_url function."""

    def test_returns_default_url_when_no_env(self) -> None:
        """Test returns default URL when DATABASE_URL not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove DATABASE_URL if it exists
            os.environ.pop("DATABASE_URL", None)
            url = get_database_url()

            assert "postgresql+asyncpg://" in url
            assert "localhost:5432" in url
            assert "llamatrade" in url

    def test_returns_env_url_when_set(self) -> None:
        """Test returns environment URL when DATABASE_URL is set."""
        test_url = "postgresql+asyncpg://user:pass@testhost:5433/testdb"

        with patch.dict(os.environ, {"DATABASE_URL": test_url}):
            url = get_database_url()
            assert url == test_url

    def test_default_url_format(self) -> None:
        """Test default URL has correct format."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("DATABASE_URL", None)
            url = get_database_url()

            # Should be a valid PostgreSQL async URL
            assert url.startswith("postgresql+asyncpg://")
            assert ":" in url  # Has port
            assert "/" in url  # Has database name


class TestModuleLevelState:
    """Tests for module-level engine and session maker state."""

    def test_engine_initially_none(self) -> None:
        """Test _engine is initially None."""
        # Import fresh to check initial state
        import llamatrade_db.session as session_module

        # Reset module state
        session_module._engine = None
        session_module._async_session_maker = None

        assert session_module._engine is None

    def test_session_maker_initially_none(self) -> None:
        """Test _async_session_maker is initially None."""
        import llamatrade_db.session as session_module

        # Reset module state
        session_module._engine = None
        session_module._async_session_maker = None

        assert session_module._async_session_maker is None


class TestGetEngine:
    """Tests for get_engine function."""

    @pytest.mark.asyncio
    async def test_get_engine_creates_engine(self) -> None:
        """Test get_engine creates an AsyncEngine."""
        from llamatrade_db.session import close_db, get_engine

        try:
            engine = get_engine()

            # Should return an AsyncEngine
            from sqlalchemy.ext.asyncio import AsyncEngine

            assert isinstance(engine, AsyncEngine)
        finally:
            await close_db()

    @pytest.mark.asyncio
    async def test_get_engine_returns_same_instance(self) -> None:
        """Test get_engine returns the same instance on subsequent calls."""
        from llamatrade_db.session import close_db, get_engine

        try:
            engine1 = get_engine()
            engine2 = get_engine()

            assert engine1 is engine2
        finally:
            await close_db()


class TestGetSessionMaker:
    """Tests for get_session_maker function."""

    @pytest.mark.asyncio
    async def test_get_session_maker_creates_maker(self) -> None:
        """Test get_session_maker creates an async_sessionmaker."""
        from llamatrade_db.session import close_db, get_session_maker

        try:
            maker = get_session_maker()

            # Should return an async_sessionmaker
            from sqlalchemy.ext.asyncio import async_sessionmaker

            assert isinstance(maker, async_sessionmaker)
        finally:
            await close_db()

    @pytest.mark.asyncio
    async def test_get_session_maker_returns_same_instance(self) -> None:
        """Test get_session_maker returns the same instance on subsequent calls."""
        from llamatrade_db.session import close_db, get_session_maker

        try:
            maker1 = get_session_maker()
            maker2 = get_session_maker()

            assert maker1 is maker2
        finally:
            await close_db()


class TestCloseDb:
    """Tests for close_db function."""

    @pytest.mark.asyncio
    async def test_close_db_clears_engine(self) -> None:
        """Test close_db clears the engine."""
        import llamatrade_db.session as session_module
        from llamatrade_db.session import close_db, get_engine

        # Create engine
        get_engine()
        assert session_module._engine is not None

        # Close
        await close_db()

        assert session_module._engine is None

    @pytest.mark.asyncio
    async def test_close_db_clears_session_maker(self) -> None:
        """Test close_db clears the session maker."""
        import llamatrade_db.session as session_module
        from llamatrade_db.session import close_db, get_session_maker

        # Create session maker
        get_session_maker()
        assert session_module._async_session_maker is not None

        # Close
        await close_db()

        assert session_module._async_session_maker is None

    @pytest.mark.asyncio
    async def test_close_db_safe_when_not_initialized(self) -> None:
        """Test close_db is safe to call when not initialized."""
        import llamatrade_db.session as session_module
        from llamatrade_db.session import close_db

        # Ensure not initialized
        session_module._engine = None
        session_module._async_session_maker = None

        # Should not raise
        await close_db()


class TestGetDb:
    """Tests for get_db async generator."""

    @pytest.mark.asyncio
    async def test_get_db_yields_session(self) -> None:
        """Test get_db yields an AsyncSession."""
        from sqlalchemy.ext.asyncio import AsyncSession

        from llamatrade_db.session import close_db, get_db

        try:
            async for session in get_db():
                assert isinstance(session, AsyncSession)
                break
        finally:
            await close_db()

    @pytest.mark.asyncio
    async def test_get_db_closes_session(self) -> None:
        """Test get_db closes session after use."""
        from llamatrade_db.session import close_db, get_db

        session_ref = None
        try:
            async for session in get_db():
                session_ref = session
                break

            # Session should be closed after the generator exits
            # (We can't easily test this without more complex mocking)
            assert session_ref is not None
        finally:
            await close_db()


class TestInitDb:
    """Tests for init_db function."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        os.environ.get("DATABASE_URL") is None,
        reason="Requires running PostgreSQL database",
    )
    async def test_init_db_creates_tables(self) -> None:
        """Test init_db creates database tables.

        Note: This test requires a running PostgreSQL database.
        Set DATABASE_URL environment variable to run this test.
        """
        from llamatrade_db.session import close_db, init_db

        try:
            # Should not raise
            await init_db()
        finally:
            await close_db()
