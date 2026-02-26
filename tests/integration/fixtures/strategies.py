"""Strategy fixtures for integration tests."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models import Strategy, StrategyVersion, Tenant, User
from tests.factories import StrategyFactory, StrategyVersionFactory


@pytest.fixture
async def test_strategy(
    db_session: AsyncSession,
    test_tenant: Tenant,
    test_user: User,
) -> Strategy:
    """Create a test strategy in the database.

    Returns:
        Strategy model instance with ID persisted to database
    """
    strategy = StrategyFactory.create(
        tenant_id=test_tenant.id,
        created_by=test_user.id,
        name="Test Strategy",
        description="A test strategy for integration tests",
    )
    db_session.add(strategy)
    await db_session.flush()
    await db_session.refresh(strategy)
    return strategy


@pytest.fixture
async def test_strategy_with_versions(
    db_session: AsyncSession,
    test_tenant: Tenant,
    test_user: User,
) -> Strategy:
    """Create a test strategy with multiple versions.

    Returns:
        Strategy model instance with versions
    """
    strategy = StrategyFactory.create(
        tenant_id=test_tenant.id,
        created_by=test_user.id,
        name="Versioned Strategy",
        current_version=3,
    )
    db_session.add(strategy)
    await db_session.flush()

    # Create versions
    for version_num in range(1, 4):
        version = StrategyVersionFactory.create(
            strategy_id=strategy.id,
            created_by=test_user.id,
            version=version_num,
            changelog=f"Version {version_num} changes",
            config={
                "symbols": ["AAPL"],
                "version_specific_param": version_num,
            },
        )
        db_session.add(version)

    await db_session.flush()
    await db_session.refresh(strategy)
    return strategy


@pytest.fixture
async def second_tenant_strategy(
    db_session: AsyncSession,
    second_tenant: Tenant,
    second_tenant_user: User,
) -> Strategy:
    """Create a strategy belonging to the second tenant.

    Used for tenant isolation testing.
    """
    strategy = StrategyFactory.create(
        tenant_id=second_tenant.id,
        created_by=second_tenant_user.id,
        name="Other Tenant Strategy",
        description="Strategy belonging to another tenant",
    )
    db_session.add(strategy)
    await db_session.flush()
    await db_session.refresh(strategy)
    return strategy


@pytest.fixture
async def public_strategy(
    db_session: AsyncSession,
    test_tenant: Tenant,
    test_user: User,
) -> Strategy:
    """Create a public strategy that can be viewed by any tenant.

    Returns:
        Strategy model instance with is_public=True
    """
    strategy = StrategyFactory.create(
        tenant_id=test_tenant.id,
        created_by=test_user.id,
        name="Public Strategy",
        description="A public strategy visible to all",
        is_public=True,
    )
    db_session.add(strategy)
    await db_session.flush()
    await db_session.refresh(strategy)
    return strategy


@pytest.fixture
async def inactive_strategy(
    db_session: AsyncSession,
    test_tenant: Tenant,
    test_user: User,
) -> Strategy:
    """Create an inactive strategy.

    Returns:
        Strategy model instance with is_active=False
    """
    strategy = StrategyFactory.create(
        tenant_id=test_tenant.id,
        created_by=test_user.id,
        name="Inactive Strategy",
        is_active=False,
    )
    db_session.add(strategy)
    await db_session.flush()
    await db_session.refresh(strategy)
    return strategy


@pytest.fixture
async def multiple_strategies(
    db_session: AsyncSession,
    test_tenant: Tenant,
    test_user: User,
) -> list[Strategy]:
    """Create multiple strategies for pagination testing.

    Returns:
        List of 10 Strategy model instances
    """
    strategies = []
    for i in range(10):
        strategy = StrategyFactory.create(
            tenant_id=test_tenant.id,
            created_by=test_user.id,
            name=f"Strategy {i + 1}",
            description=f"Test strategy number {i + 1}",
        )
        db_session.add(strategy)
        strategies.append(strategy)

    await db_session.flush()
    for strategy in strategies:
        await db_session.refresh(strategy)

    return strategies
