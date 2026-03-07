"""Shared test fixtures for db library."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from llamatrade_db.base import Base


@pytest.fixture(scope="session")
def engine():
    """Create a test database engine using SQLite in-memory."""
    # Use SQLite for testing - it's fast and doesn't require a server
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
    )
    # Create all tables
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine):
    """Create a database session for testing."""
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def sample_tenant_id():
    """Sample tenant UUID."""
    return uuid4()


@pytest.fixture
def sample_user_id():
    """Sample user UUID."""
    return uuid4()


@pytest.fixture
def sample_strategy_id():
    """Sample strategy UUID."""
    return uuid4()


@pytest.fixture
def sample_session_id():
    """Sample trading session UUID."""
    return uuid4()


@pytest.fixture
def sample_datetime():
    """Sample datetime for testing."""
    return datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)


@pytest.fixture
def sample_date():
    """Sample date for testing."""
    from datetime import date

    return date(2024, 1, 15)
