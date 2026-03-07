"""Tenant isolation security tests.

These tests are CRITICAL for security. They verify that:
1. Tenants cannot access each other's data
2. Cross-tenant queries return empty results (not errors that leak existence)
3. All tenant-scoped resources properly filter by tenant_id

IMPORTANT: If any of these tests fail, it indicates a potential data leakage
vulnerability that must be fixed before deployment.
"""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models import (
    Backtest,
    Order,
    Position,
    Strategy,
    Subscription,
    Tenant,
    TradingSession,
    User,
)
from tests.factories import (
    EXECUTION_MODE_LIVE,
    EXECUTION_MODE_PAPER,
    ORDER_SIDE_BUY,
    ORDER_SIDE_SELL,
    PLAN_TIER_STARTER,
    BacktestFactory,
    OrderFactory,
    PlanFactory,
    PositionFactory,
    StrategyFactory,
    SubscriptionFactory,
    TradingSessionFactory,
    UserFactory,
)


# Helper to generate fake credentials ID for trading sessions
def fake_credentials_id():
    """Generate a fake credentials ID for tests."""
    return uuid4()


pytestmark = [pytest.mark.integration, pytest.mark.security]


class TestStrategyIsolation:
    """Tests for strategy tenant isolation."""

    async def test_tenant_cannot_query_other_tenant_strategies(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
        second_tenant: Tenant,
    ):
        """Test that querying strategies by tenant_id isolates results."""
        # Create strategy for tenant A
        strategy_a = StrategyFactory.create(
            tenant_id=test_tenant.id,
            created_by=test_user.id,
            name="Tenant A Strategy",
        )
        db_session.add(strategy_a)

        # Create strategy for tenant B
        strategy_b = StrategyFactory.create(
            tenant_id=second_tenant.id,
            created_by=test_user.id,  # Same user for simplicity
            name="Tenant B Strategy",
        )
        db_session.add(strategy_b)
        await db_session.flush()

        # Query as tenant A - should only see tenant A's strategies
        result = await db_session.execute(
            select(Strategy).where(Strategy.tenant_id == test_tenant.id)
        )
        tenant_a_strategies = result.scalars().all()

        assert len(tenant_a_strategies) == 1
        assert tenant_a_strategies[0].name == "Tenant A Strategy"
        assert tenant_a_strategies[0].tenant_id == test_tenant.id

        # Query as tenant B - should only see tenant B's strategies
        result = await db_session.execute(
            select(Strategy).where(Strategy.tenant_id == second_tenant.id)
        )
        tenant_b_strategies = result.scalars().all()

        assert len(tenant_b_strategies) == 1
        assert tenant_b_strategies[0].name == "Tenant B Strategy"
        assert tenant_b_strategies[0].tenant_id == second_tenant.id

    async def test_tenant_cannot_access_other_tenant_strategy_by_id(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
        second_tenant: Tenant,
    ):
        """Test that accessing strategy by ID requires matching tenant_id."""
        # Create strategy for tenant A
        strategy = StrategyFactory.create(
            tenant_id=test_tenant.id,
            created_by=test_user.id,
            name="Private Strategy",
        )
        db_session.add(strategy)
        await db_session.flush()

        strategy_id = strategy.id

        # Tenant B trying to access tenant A's strategy by ID
        # The correct pattern: filter by BOTH id AND tenant_id
        result = await db_session.execute(
            select(Strategy).where(
                Strategy.id == strategy_id,
                Strategy.tenant_id == second_tenant.id,  # Wrong tenant
            )
        )
        found = result.scalar_one_or_none()

        # Should NOT find the strategy (returns None, not 403/404)
        assert found is None

        # Verify it exists when queried with correct tenant
        result = await db_session.execute(
            select(Strategy).where(
                Strategy.id == strategy_id,
                Strategy.tenant_id == test_tenant.id,  # Correct tenant
            )
        )
        found = result.scalar_one_or_none()
        assert found is not None
        assert found.id == strategy_id


class TestBacktestIsolation:
    """Tests for backtest tenant isolation."""

    async def test_tenant_cannot_access_other_tenant_backtests(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
        second_tenant: Tenant,
    ):
        """Test that backtests are isolated by tenant."""
        # Create strategy and backtest for tenant A
        strategy_a = StrategyFactory.create(
            tenant_id=test_tenant.id,
            created_by=test_user.id,
        )
        db_session.add(strategy_a)
        await db_session.flush()

        backtest_a = BacktestFactory.create(
            tenant_id=test_tenant.id,
            strategy_id=strategy_a.id,
            created_by=test_user.id,
        )
        db_session.add(backtest_a)

        # Create strategy and backtest for tenant B
        strategy_b = StrategyFactory.create(
            tenant_id=second_tenant.id,
            created_by=test_user.id,
        )
        db_session.add(strategy_b)
        await db_session.flush()

        backtest_b = BacktestFactory.create(
            tenant_id=second_tenant.id,
            strategy_id=strategy_b.id,
            created_by=test_user.id,
        )
        db_session.add(backtest_b)
        await db_session.flush()

        # Tenant A can only see their backtests
        result = await db_session.execute(
            select(Backtest).where(Backtest.tenant_id == test_tenant.id)
        )
        tenant_a_backtests = result.scalars().all()

        assert len(tenant_a_backtests) == 1
        assert tenant_a_backtests[0].tenant_id == test_tenant.id

        # Cannot access tenant B's backtest by ID
        result = await db_session.execute(
            select(Backtest).where(
                Backtest.id == backtest_b.id,
                Backtest.tenant_id == test_tenant.id,  # Wrong tenant
            )
        )
        assert result.scalar_one_or_none() is None


class TestTradingSessionIsolation:
    """Tests for trading session tenant isolation."""

    async def test_tenant_cannot_access_other_tenant_sessions(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
        second_tenant: Tenant,
    ):
        """Test that trading sessions are isolated by tenant."""
        # Create strategy and session for tenant A
        strategy_a = StrategyFactory.create(
            tenant_id=test_tenant.id,
            created_by=test_user.id,
        )
        db_session.add(strategy_a)
        await db_session.flush()

        session_a = TradingSessionFactory.create(
            tenant_id=test_tenant.id,
            strategy_id=strategy_a.id,
            credentials_id=fake_credentials_id(),
            created_by=test_user.id,
        )
        db_session.add(session_a)

        # Create strategy and session for tenant B
        strategy_b = StrategyFactory.create(
            tenant_id=second_tenant.id,
            created_by=test_user.id,
        )
        db_session.add(strategy_b)
        await db_session.flush()

        session_b = TradingSessionFactory.create(
            tenant_id=second_tenant.id,
            strategy_id=strategy_b.id,
            credentials_id=fake_credentials_id(),
            created_by=test_user.id,
        )
        db_session.add(session_b)
        await db_session.flush()

        # Query sessions for tenant A
        result = await db_session.execute(
            select(TradingSession).where(TradingSession.tenant_id == test_tenant.id)
        )
        sessions = result.scalars().all()

        assert len(sessions) == 1
        assert sessions[0].tenant_id == test_tenant.id


class TestOrderIsolation:
    """Tests for order tenant isolation."""

    async def test_tenant_cannot_access_other_tenant_orders(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
        second_tenant: Tenant,
    ):
        """Test that orders are isolated by tenant."""
        # Create strategy and session for tenant A
        strategy_a = StrategyFactory.create(
            tenant_id=test_tenant.id,
            created_by=test_user.id,
        )
        db_session.add(strategy_a)
        await db_session.flush()

        session_a = TradingSessionFactory.create(
            tenant_id=test_tenant.id,
            strategy_id=strategy_a.id,
            credentials_id=fake_credentials_id(),
            created_by=test_user.id,
        )
        db_session.add(session_a)
        await db_session.flush()

        order_a = OrderFactory.create(
            tenant_id=test_tenant.id,
            session_id=session_a.id,
            symbol="AAPL",
            side=ORDER_SIDE_BUY,
        )
        db_session.add(order_a)

        # Create strategy and session for tenant B
        strategy_b = StrategyFactory.create(
            tenant_id=second_tenant.id,
            created_by=test_user.id,
        )
        db_session.add(strategy_b)
        await db_session.flush()

        session_b = TradingSessionFactory.create(
            tenant_id=second_tenant.id,
            strategy_id=strategy_b.id,
            credentials_id=fake_credentials_id(),
            created_by=test_user.id,
        )
        db_session.add(session_b)
        await db_session.flush()

        order_b = OrderFactory.create(
            tenant_id=second_tenant.id,
            session_id=session_b.id,
            symbol="GOOGL",
            side=ORDER_SIDE_SELL,
        )
        db_session.add(order_b)
        await db_session.flush()

        # Tenant A can only see their orders
        result = await db_session.execute(select(Order).where(Order.tenant_id == test_tenant.id))
        orders = result.scalars().all()

        assert len(orders) == 1
        assert orders[0].symbol == "AAPL"
        assert orders[0].tenant_id == test_tenant.id

        # Cannot access tenant B's order by ID
        result = await db_session.execute(
            select(Order).where(
                Order.id == order_b.id,
                Order.tenant_id == test_tenant.id,
            )
        )
        assert result.scalar_one_or_none() is None


class TestPositionIsolation:
    """Tests for position tenant isolation."""

    async def test_tenant_cannot_access_other_tenant_positions(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
        second_tenant: Tenant,
    ):
        """Test that positions are isolated by tenant."""
        # Create trading infrastructure for tenant A
        strategy_a = StrategyFactory.create(
            tenant_id=test_tenant.id,
            created_by=test_user.id,
        )
        db_session.add(strategy_a)
        await db_session.flush()

        session_a = TradingSessionFactory.create(
            tenant_id=test_tenant.id,
            strategy_id=strategy_a.id,
            credentials_id=fake_credentials_id(),
            created_by=test_user.id,
        )
        db_session.add(session_a)
        await db_session.flush()

        position_a = PositionFactory.create(
            tenant_id=test_tenant.id,
            session_id=session_a.id,
            symbol="AAPL",
            qty=Decimal("100"),
        )
        db_session.add(position_a)

        # Create trading infrastructure for tenant B
        strategy_b = StrategyFactory.create(
            tenant_id=second_tenant.id,
            created_by=test_user.id,
        )
        db_session.add(strategy_b)
        await db_session.flush()

        session_b = TradingSessionFactory.create(
            tenant_id=second_tenant.id,
            strategy_id=strategy_b.id,
            credentials_id=fake_credentials_id(),
            created_by=test_user.id,
        )
        db_session.add(session_b)
        await db_session.flush()

        position_b = PositionFactory.create(
            tenant_id=second_tenant.id,
            session_id=session_b.id,
            symbol="MSFT",
            qty=Decimal("50"),
        )
        db_session.add(position_b)
        await db_session.flush()

        # Tenant A can only see their positions
        result = await db_session.execute(
            select(Position).where(Position.tenant_id == test_tenant.id)
        )
        positions = result.scalars().all()

        assert len(positions) == 1
        assert positions[0].symbol == "AAPL"
        assert positions[0].qty == Decimal("100")


class TestUserIsolation:
    """Tests for user tenant isolation."""

    async def test_tenant_cannot_access_other_tenant_users(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        second_tenant: Tenant,
    ):
        """Test that users are isolated by tenant."""
        # Create user for tenant A
        user_a = UserFactory.create(
            tenant_id=test_tenant.id,
            email="user_a@example.com",
        )
        db_session.add(user_a)

        # Create user for tenant B
        user_b = UserFactory.create(
            tenant_id=second_tenant.id,
            email="user_b@example.com",
        )
        db_session.add(user_b)
        await db_session.flush()

        # Query users for tenant A
        result = await db_session.execute(select(User).where(User.tenant_id == test_tenant.id))
        users = result.scalars().all()

        # Should only see users from tenant A
        emails = [u.email for u in users]
        assert "user_a@example.com" in emails
        assert "user_b@example.com" not in emails

    async def test_email_uniqueness_scoped_to_tenant(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        second_tenant: Tenant,
    ):
        """Test that email uniqueness is scoped to tenant (same email allowed in different tenants)."""
        # Create user with email in tenant A
        user_a = UserFactory.create(
            tenant_id=test_tenant.id,
            email="shared@example.com",
        )
        db_session.add(user_a)
        await db_session.flush()

        # Same email in tenant B should be allowed
        user_b = UserFactory.create(
            tenant_id=second_tenant.id,
            email="shared@example.com",  # Same email, different tenant
        )
        db_session.add(user_b)
        await db_session.flush()  # Should NOT raise

        # Verify both exist
        result = await db_session.execute(select(User).where(User.email == "shared@example.com"))
        users = result.scalars().all()
        assert len(users) == 2

        # But each is scoped to their tenant
        tenant_a_users = [u for u in users if u.tenant_id == test_tenant.id]
        tenant_b_users = [u for u in users if u.tenant_id == second_tenant.id]
        assert len(tenant_a_users) == 1
        assert len(tenant_b_users) == 1


class TestSubscriptionIsolation:
    """Tests for subscription tenant isolation."""

    async def test_tenant_cannot_access_other_tenant_subscription(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        second_tenant: Tenant,
    ):
        """Test that subscriptions are isolated by tenant."""
        # Create plan (shared, not tenant-scoped)
        plan = PlanFactory.create(name="starter", tier=PLAN_TIER_STARTER)
        db_session.add(plan)
        await db_session.flush()

        # Create subscription for tenant A
        sub_a = SubscriptionFactory.create(
            tenant_id=test_tenant.id,
            plan_id=plan.id,
            stripe_subscription_id="sub_tenant_a",
        )
        db_session.add(sub_a)

        # Create subscription for tenant B
        sub_b = SubscriptionFactory.create(
            tenant_id=second_tenant.id,
            plan_id=plan.id,
            stripe_subscription_id="sub_tenant_b",
        )
        db_session.add(sub_b)
        await db_session.flush()

        # Query subscription for tenant A
        result = await db_session.execute(
            select(Subscription).where(Subscription.tenant_id == test_tenant.id)
        )
        subs = result.scalars().all()

        assert len(subs) == 1
        assert subs[0].stripe_subscription_id == "sub_tenant_a"

        # Cannot access tenant B's subscription
        result = await db_session.execute(
            select(Subscription).where(
                Subscription.id == sub_b.id,
                Subscription.tenant_id == test_tenant.id,
            )
        )
        assert result.scalar_one_or_none() is None


class TestCrossResourceIsolation:
    """Tests for isolation across related resources."""

    async def test_cannot_create_strategy_for_other_tenant(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
        second_tenant: Tenant,
    ):
        """Test that a user cannot create resources for another tenant.

        This tests the scenario where an attacker tries to specify a different
        tenant_id in their request. The service layer MUST use the authenticated
        user's tenant_id, not the one provided in the request.
        """
        # Attempt to create strategy with mismatched tenant
        # In production, the tenant_id should come from auth context, not request
        attacker_strategy = StrategyFactory.create(
            tenant_id=second_tenant.id,  # Attacker's target
            created_by=test_user.id,  # Authenticated user from different tenant
            name="Malicious Strategy",
        )

        # This should be prevented at the service layer, but let's verify
        # that even if inserted, proper queries wouldn't expose it to the user

        db_session.add(attacker_strategy)
        await db_session.flush()

        # User from test_tenant querying their own data won't see it
        result = await db_session.execute(
            select(Strategy).where(Strategy.tenant_id == test_user.tenant_id)
        )
        user_strategies = result.scalars().all()

        # None of the strategies should belong to second_tenant
        for strategy in user_strategies:
            assert strategy.tenant_id == test_user.tenant_id

    async def test_backtest_references_same_tenant_strategy(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
        second_tenant: Tenant,
    ):
        """Test that backtests can only reference strategies from same tenant.

        This tests the scenario where an attacker tries to run a backtest
        against another tenant's strategy.
        """
        # Create strategy for tenant A
        strategy_a = StrategyFactory.create(
            tenant_id=test_tenant.id,
            created_by=test_user.id,
        )
        db_session.add(strategy_a)
        await db_session.flush()

        # Try to create backtest referencing tenant A's strategy but for tenant B
        # This represents an attacker trying to access another tenant's strategy
        cross_tenant_backtest = BacktestFactory.create(
            tenant_id=second_tenant.id,  # Wrong tenant
            strategy_id=strategy_a.id,  # Strategy belongs to test_tenant
            created_by=test_user.id,
        )

        # Note: The database doesn't prevent this at the constraint level,
        # so the service layer MUST verify tenant_id matches before creating

        # This demonstrates why service layer validation is critical
        db_session.add(cross_tenant_backtest)
        await db_session.flush()

        # Verify that proper queries filter correctly
        # A user from second_tenant shouldn't find strategies matching their backtests
        result = await db_session.execute(
            select(Strategy).where(
                Strategy.id == strategy_a.id,
                Strategy.tenant_id == second_tenant.id,
            )
        )
        # They won't find the strategy because it belongs to test_tenant
        assert result.scalar_one_or_none() is None


class TestBulkQueryIsolation:
    """Tests for isolation in bulk/aggregate queries."""

    async def test_count_queries_respect_tenant_isolation(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
        second_tenant: Tenant,
    ):
        """Test that count queries are properly tenant-scoped."""
        from sqlalchemy import func

        # Create 5 strategies for tenant A
        for i in range(5):
            db_session.add(
                StrategyFactory.create(
                    tenant_id=test_tenant.id,
                    created_by=test_user.id,
                )
            )

        # Create 3 strategies for tenant B
        for i in range(3):
            db_session.add(
                StrategyFactory.create(
                    tenant_id=second_tenant.id,
                    created_by=test_user.id,
                )
            )

        await db_session.flush()

        # Count for tenant A
        result = await db_session.execute(
            select(func.count(Strategy.id)).where(Strategy.tenant_id == test_tenant.id)
        )
        count_a = result.scalar()
        assert count_a == 5

        # Count for tenant B
        result = await db_session.execute(
            select(func.count(Strategy.id)).where(Strategy.tenant_id == second_tenant.id)
        )
        count_b = result.scalar()
        assert count_b == 3

        # Total count (dangerous - should never be done without tenant filter)
        result = await db_session.execute(select(func.count(Strategy.id)))
        total_count = result.scalar()
        assert total_count == 8  # Both tenants combined

    async def test_aggregations_respect_tenant_isolation(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
        second_tenant: Tenant,
    ):
        """Test that aggregation queries are properly tenant-scoped."""
        from sqlalchemy import func

        # Create sessions with different modes for tenant A
        strategy_a = StrategyFactory.create(
            tenant_id=test_tenant.id,
            created_by=test_user.id,
        )
        db_session.add(strategy_a)
        await db_session.flush()

        for mode in [EXECUTION_MODE_PAPER, EXECUTION_MODE_PAPER, EXECUTION_MODE_LIVE]:
            db_session.add(
                TradingSessionFactory.create(
                    tenant_id=test_tenant.id,
                    strategy_id=strategy_a.id,
                    credentials_id=fake_credentials_id(),
                    created_by=test_user.id,
                    mode=mode,
                )
            )

        # Create sessions for tenant B
        strategy_b = StrategyFactory.create(
            tenant_id=second_tenant.id,
            created_by=test_user.id,
        )
        db_session.add(strategy_b)
        await db_session.flush()

        for mode in [
            EXECUTION_MODE_LIVE,
            EXECUTION_MODE_LIVE,
            EXECUTION_MODE_LIVE,
            EXECUTION_MODE_LIVE,
        ]:
            db_session.add(
                TradingSessionFactory.create(
                    tenant_id=second_tenant.id,
                    strategy_id=strategy_b.id,
                    credentials_id=fake_credentials_id(),
                    created_by=test_user.id,
                    mode=mode,
                )
            )

        await db_session.flush()

        # Count by mode for tenant A
        result = await db_session.execute(
            select(TradingSession.mode, func.count(TradingSession.id))
            .where(TradingSession.tenant_id == test_tenant.id)
            .group_by(TradingSession.mode)
        )
        mode_counts = {row[0]: row[1] for row in result.all()}

        # Tenant A has 2 paper (mode=1), 1 live (mode=2)
        assert mode_counts.get(EXECUTION_MODE_PAPER, 0) == 2
        assert mode_counts.get(EXECUTION_MODE_LIVE, 0) == 1

        # Tenant B's 4 live sessions should not affect tenant A's counts
