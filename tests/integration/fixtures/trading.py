"""Trading fixtures for integration tests.

Provides fixtures for trading sessions and Alpaca credentials.
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models import AlpacaCredentials, Strategy, Tenant, TradingSession, User
from tests.factories import (
    EXECUTION_MODE_PAPER,
    SESSION_STATUS_ACTIVE,
    SESSION_STATUS_STOPPED,
    TradingSessionFactory,
)


@pytest.fixture
async def test_alpaca_credentials(
    db_session: AsyncSession,
    test_tenant: Tenant,
) -> AlpacaCredentials:
    """Create test Alpaca credentials in the database.

    Credentials are stored with mock encrypted values for testing.
    In production, these would be encrypted with Fernet.

    Returns:
        AlpacaCredentials model instance for paper trading
    """
    credentials = AlpacaCredentials(
        id=uuid4(),
        tenant_id=test_tenant.id,
        name="Test Paper Account",
        api_key_encrypted="test_encrypted_key",  # Mock encrypted value
        api_secret_encrypted="test_encrypted_secret",  # Mock encrypted value
        is_paper=True,
        is_active=True,
    )
    db_session.add(credentials)
    await db_session.flush()
    await db_session.refresh(credentials)
    return credentials


@pytest.fixture
async def test_live_alpaca_credentials(
    db_session: AsyncSession,
    test_tenant: Tenant,
) -> AlpacaCredentials:
    """Create test Alpaca credentials for live trading.

    Returns:
        AlpacaCredentials model instance for live trading
    """
    credentials = AlpacaCredentials(
        id=uuid4(),
        tenant_id=test_tenant.id,
        name="Test Live Account",
        api_key_encrypted="test_live_encrypted_key",
        api_secret_encrypted="test_live_encrypted_secret",
        is_paper=False,
        is_active=True,
    )
    db_session.add(credentials)
    await db_session.flush()
    await db_session.refresh(credentials)
    return credentials


@pytest.fixture
async def test_trading_session(
    db_session: AsyncSession,
    test_tenant: Tenant,
    test_user: User,
    test_strategy: Strategy,
    test_alpaca_credentials: AlpacaCredentials,
) -> TradingSession:
    """Create a test trading session in STOPPED state.

    Returns:
        TradingSession model instance (not yet started)
    """
    session = TradingSessionFactory.create(
        tenant_id=test_tenant.id,
        strategy_id=test_strategy.id,
        credentials_id=test_alpaca_credentials.id,
        created_by=test_user.id,
        name="Test Trading Session",
        status=SESSION_STATUS_STOPPED,
        mode=EXECUTION_MODE_PAPER,
        symbols=["AAPL", "GOOGL"],
    )
    db_session.add(session)
    await db_session.flush()
    await db_session.refresh(session)
    return session


@pytest.fixture
async def active_trading_session(
    db_session: AsyncSession,
    test_tenant: Tenant,
    test_user: User,
    test_strategy: Strategy,
    test_alpaca_credentials: AlpacaCredentials,
) -> TradingSession:
    """Create an active trading session.

    Returns:
        TradingSession model instance in RUNNING state
    """
    from datetime import UTC, datetime

    session = TradingSessionFactory.create(
        tenant_id=test_tenant.id,
        strategy_id=test_strategy.id,
        credentials_id=test_alpaca_credentials.id,
        created_by=test_user.id,
        name="Active Trading Session",
        status=SESSION_STATUS_ACTIVE,
        mode=EXECUTION_MODE_PAPER,
        symbols=["AAPL", "GOOGL", "MSFT"],
    )
    session.started_at = datetime.now(UTC)
    session.last_heartbeat = datetime.now(UTC)
    db_session.add(session)
    await db_session.flush()
    await db_session.refresh(session)
    return session


@pytest.fixture
async def second_tenant_trading_session(
    db_session: AsyncSession,
    second_tenant: Tenant,
    second_tenant_user: User,
    second_tenant_strategy: Strategy,
) -> TradingSession:
    """Create a trading session for the second tenant.

    Used for tenant isolation testing.
    """
    # First create credentials for second tenant
    credentials = AlpacaCredentials(
        id=uuid4(),
        tenant_id=second_tenant.id,
        name="Second Tenant Paper Account",
        api_key_encrypted="second_tenant_encrypted_key",
        api_secret_encrypted="second_tenant_encrypted_secret",
        is_paper=True,
        is_active=True,
    )
    db_session.add(credentials)
    await db_session.flush()

    session = TradingSessionFactory.create(
        tenant_id=second_tenant.id,
        strategy_id=second_tenant_strategy.id,
        credentials_id=credentials.id,
        created_by=second_tenant_user.id,
        name="Other Tenant Session",
        status=SESSION_STATUS_ACTIVE,
        mode=EXECUTION_MODE_PAPER,
    )
    db_session.add(session)
    await db_session.flush()
    await db_session.refresh(session)
    return session


@pytest.fixture
async def multiple_trading_sessions(
    db_session: AsyncSession,
    test_tenant: Tenant,
    test_user: User,
    test_strategy: Strategy,
    test_alpaca_credentials: AlpacaCredentials,
) -> list[TradingSession]:
    """Create multiple trading sessions for pagination testing.

    Returns:
        List of 5 TradingSession model instances
    """
    sessions = []
    for i in range(5):
        session = TradingSessionFactory.create(
            tenant_id=test_tenant.id,
            strategy_id=test_strategy.id,
            credentials_id=test_alpaca_credentials.id,
            created_by=test_user.id,
            name=f"Test Session {i + 1}",
            status=SESSION_STATUS_STOPPED,
            mode=EXECUTION_MODE_PAPER,
        )
        db_session.add(session)
        sessions.append(session)

    await db_session.flush()
    for session in sessions:
        await db_session.refresh(session)

    return sessions
