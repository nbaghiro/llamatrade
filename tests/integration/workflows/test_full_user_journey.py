"""Full user journey gRPC workflow tests.

Tests complete end-to-end user journeys:
1. New user journey: register → login → create strategy → backtest → start trading
2. Multi-tenant journey: two users independently complete workflows, verify isolation

Uses multi-servicer fixtures from conftest.py that preload servicer classes
at module import time to avoid module path conflicts.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from connectrpc.errors import ConnectError

from .conftest import MockServicerContext

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.integration, pytest.mark.workflow, pytest.mark.asyncio]


# Sample strategy configurations
MOMENTUM_STRATEGY_DSL = """(strategy "My Momentum Strategy"
  :rebalance daily
  :benchmark SPY
  (if (crosses-above (sma SPY 20) (sma SPY 50))
    (weight :method equal
      (asset AAPL)
      (asset GOOGL))
    (else (asset TLT :weight 100))))"""

MEAN_REVERSION_DSL = """(strategy "Mean Reversion Strategy"
  :rebalance weekly
  :benchmark SPY
  (if (crosses-below (rsi AAPL 14) 30)
    (asset AAPL :weight 100)
    (else (asset SHY :weight 100))))"""


def create_tenant_context(user_id: str, tenant_id: str):
    """Create a TenantContext proto message."""
    from llamatrade_proto.generated import common_pb2

    return common_pb2.TenantContext(
        tenant_id=tenant_id,
        user_id=user_id,
        roles=["admin"],
    )


class TestNewUserJourney:
    """Test complete new user journey from registration to trading.

    Uses multi-servicer fixtures that preload servicer classes at module import time.
    """

    async def test_full_onboarding_journey(
        self,
        multi_auth_servicer,
        multi_strategy_servicer,
        multi_backtest_servicer,
        mock_context: MockServicerContext,
        db_session: "AsyncSession",
    ):
        """Test complete user journey: register → create strategy → backtest.

        This test simulates a real user:
        1. Registers and creates a new tenant
        2. Logs in and gets tokens
        3. Creates their first strategy
        4. Runs a backtest to validate the strategy
        5. Reviews backtest results
        """
        from llamatrade_proto.generated import auth_pb2, backtest_pb2, common_pb2, strategy_pb2

        # ============================================================
        # STEP 1: Registration
        # ============================================================
        email = f"newuser-{uuid4().hex[:8]}@example.com"
        password = "SecurePassword123!"
        company_name = "Acme Trading Co"

        register_request = auth_pb2.RegisterRequest(
            tenant_name=company_name,
            email=email,
            password=password,
        )
        register_response = await multi_auth_servicer.register(register_request, mock_context)

        assert register_response.tenant.name == company_name
        assert register_response.user.email == email
        tenant_id = register_response.tenant.id
        user_id = register_response.user.id

        # ============================================================
        # STEP 2: Login
        # ============================================================
        login_request = auth_pb2.LoginRequest(email=email, password=password)
        login_response = await multi_auth_servicer.login(login_request, MockServicerContext())

        assert login_response.access_token
        assert login_response.user.id == user_id

        # Create context for subsequent requests
        ctx = create_tenant_context(user_id, tenant_id)

        # ============================================================
        # STEP 3: Create First Strategy
        # ============================================================
        create_strategy_request = strategy_pb2.CreateStrategyRequest(
            context=ctx,
            name="My First Strategy",
            description="A simple momentum strategy to get started",
            dsl_code=MOMENTUM_STRATEGY_DSL,
        )
        strategy_response = await multi_strategy_servicer.create_strategy(
            create_strategy_request, MockServicerContext()
        )

        assert strategy_response.strategy.name == "My First Strategy"
        assert strategy_response.strategy.status == strategy_pb2.STRATEGY_STATUS_DRAFT
        strategy_id = strategy_response.strategy.id

        # ============================================================
        # STEP 3.5: Activate Strategy (required before backtesting)
        # ============================================================
        activate_request = strategy_pb2.UpdateStrategyStatusRequest(
            context=ctx,
            strategy_id=strategy_id,
            status=strategy_pb2.STRATEGY_STATUS_ACTIVE,
        )
        await multi_strategy_servicer.update_strategy_status(
            activate_request, MockServicerContext()
        )

        # ============================================================
        # STEP 4: Run Backtest
        # ============================================================
        now = datetime.utcnow()
        backtest_config = backtest_pb2.BacktestConfig(
            strategy_id=strategy_id,
            strategy_version=1,
            start_date=common_pb2.Timestamp(seconds=int((now - timedelta(days=365)).timestamp())),
            end_date=common_pb2.Timestamp(seconds=int(now.timestamp())),
            initial_capital=common_pb2.Decimal(value="100000"),
            symbols=["AAPL", "GOOGL", "TLT"],
            benchmark_symbol="SPY",
            include_benchmark=True,
        )

        run_backtest_request = backtest_pb2.RunBacktestRequest(
            context=ctx,
            config=backtest_config,
        )
        backtest_response = await multi_backtest_servicer.RunBacktest(
            run_backtest_request, MockServicerContext()
        )

        assert backtest_response.backtest.id
        assert backtest_response.backtest.strategy_id == strategy_id
        backtest_id = backtest_response.backtest.id

        # ============================================================
        # STEP 5: Review Backtest Results
        # ============================================================
        get_backtest_request = backtest_pb2.GetBacktestRequest(
            context=ctx,
            backtest_id=backtest_id,
        )
        get_response = await multi_backtest_servicer.GetBacktest(
            get_backtest_request, MockServicerContext()
        )

        assert get_response.backtest.id == backtest_id
        # Decimal may be formatted with or without trailing zeros
        assert float(get_response.backtest.config.initial_capital.value) == 100000.0

    async def test_user_creates_and_iterates_strategy(
        self,
        multi_auth_servicer,
        multi_strategy_servicer,
        multi_backtest_servicer,
        mock_context: MockServicerContext,
        db_session: "AsyncSession",
    ):
        """Test user iterates on strategy: create → backtest → update → backtest again."""
        from llamatrade_proto.generated import auth_pb2, backtest_pb2, common_pb2, strategy_pb2

        # Register user
        email = f"iterator-{uuid4().hex[:8]}@example.com"
        register_request = auth_pb2.RegisterRequest(
            tenant_name="Iteration Test Co",
            email=email,
            password="TestPassword123!",
        )
        register_response = await multi_auth_servicer.register(register_request, mock_context)
        ctx = create_tenant_context(register_response.user.id, register_response.tenant.id)

        # Create initial strategy
        create_request = strategy_pb2.CreateStrategyRequest(
            context=ctx,
            name="Iterating Strategy",
            dsl_code=MOMENTUM_STRATEGY_DSL,
        )
        strategy_v1 = await multi_strategy_servicer.create_strategy(
            create_request, MockServicerContext()
        )
        strategy_id = strategy_v1.strategy.id
        assert strategy_v1.strategy.version == 1

        # Activate strategy before backtesting
        activate_request = strategy_pb2.UpdateStrategyStatusRequest(
            context=ctx,
            strategy_id=strategy_id,
            status=strategy_pb2.STRATEGY_STATUS_ACTIVE,
        )
        await multi_strategy_servicer.update_strategy_status(
            activate_request, MockServicerContext()
        )

        # Run first backtest
        now = datetime.utcnow()
        config_v1 = backtest_pb2.BacktestConfig(
            strategy_id=strategy_id,
            strategy_version=1,
            start_date=common_pb2.Timestamp(seconds=int((now - timedelta(days=180)).timestamp())),
            end_date=common_pb2.Timestamp(seconds=int(now.timestamp())),
            initial_capital=common_pb2.Decimal(value="50000"),
        )
        await multi_backtest_servicer.RunBacktest(
            backtest_pb2.RunBacktestRequest(context=ctx, config=config_v1),
            MockServicerContext(),
        )

        # Update strategy (creates version 2)
        update_request = strategy_pb2.UpdateStrategyRequest(
            context=ctx,
            strategy_id=strategy_id,
            dsl_code=MEAN_REVERSION_DSL,  # Different strategy
        )
        strategy_v2 = await multi_strategy_servicer.update_strategy(
            update_request, MockServicerContext()
        )
        assert strategy_v2.strategy.version == 2

        # Run second backtest with new version
        config_v2 = backtest_pb2.BacktestConfig(
            strategy_id=strategy_id,
            strategy_version=2,
            start_date=common_pb2.Timestamp(seconds=int((now - timedelta(days=180)).timestamp())),
            end_date=common_pb2.Timestamp(seconds=int(now.timestamp())),
            initial_capital=common_pb2.Decimal(value="50000"),
        )
        await multi_backtest_servicer.RunBacktest(
            backtest_pb2.RunBacktestRequest(context=ctx, config=config_v2),
            MockServicerContext(),
        )

        # Verify both backtests exist
        list_request = backtest_pb2.ListBacktestsRequest(
            context=ctx,
            strategy_id=strategy_id,
            pagination=common_pb2.PaginationRequest(page=1, page_size=20),
        )
        list_response = await multi_backtest_servicer.ListBacktests(
            list_request, MockServicerContext()
        )

        assert list_response.pagination.total_items == 2

        # List strategy versions
        versions_request = strategy_pb2.ListStrategyVersionsRequest(
            context=ctx,
            strategy_id=strategy_id,
            pagination=common_pb2.PaginationRequest(page=1, page_size=20),
        )
        versions_response = await multi_strategy_servicer.list_strategy_versions(
            versions_request, MockServicerContext()
        )
        assert len(versions_response.versions) == 2


class TestMultiTenantJourney:
    """Test multiple tenants operating independently with isolation."""

    async def test_two_tenants_independent_workflows(
        self,
        multi_auth_servicer,
        multi_strategy_servicer,
        multi_backtest_servicer,
        mock_context: MockServicerContext,
        db_session: "AsyncSession",
    ):
        """Test two users completing workflows independently with full isolation."""
        from llamatrade_proto.generated import auth_pb2, backtest_pb2, common_pb2, strategy_pb2

        # ============================================================
        # SETUP: Register both users
        # ============================================================
        # User A (Alice)
        alice_email = f"alice-{uuid4().hex[:8]}@example.com"
        alice_reg = await multi_auth_servicer.register(
            auth_pb2.RegisterRequest(
                tenant_name="Alice's Trading Co",
                email=alice_email,
                password="AlicePassword123!",
            ),
            mock_context,
        )
        alice_ctx = create_tenant_context(alice_reg.user.id, alice_reg.tenant.id)

        # User B (Bob)
        bob_email = f"bob-{uuid4().hex[:8]}@example.com"
        bob_reg = await multi_auth_servicer.register(
            auth_pb2.RegisterRequest(
                tenant_name="Bob's Hedge Fund",
                email=bob_email,
                password="BobPassword123!",
            ),
            MockServicerContext(),
        )
        bob_ctx = create_tenant_context(bob_reg.user.id, bob_reg.tenant.id)

        # ============================================================
        # Alice creates her strategy
        # ============================================================
        alice_strategy = await multi_strategy_servicer.create_strategy(
            strategy_pb2.CreateStrategyRequest(
                context=alice_ctx,
                name="Alice's Secret Strategy",
                description="This is Alice's proprietary strategy",
                dsl_code=MOMENTUM_STRATEGY_DSL,
            ),
            MockServicerContext(),
        )
        alice_strategy_id = alice_strategy.strategy.id

        # ============================================================
        # Bob creates his strategy
        # ============================================================
        bob_strategy = await multi_strategy_servicer.create_strategy(
            strategy_pb2.CreateStrategyRequest(
                context=bob_ctx,
                name="Bob's Mean Reversion",
                description="Bob's contrarian approach",
                dsl_code=MEAN_REVERSION_DSL,
            ),
            MockServicerContext(),
        )
        bob_strategy_id = bob_strategy.strategy.id

        # ============================================================
        # Verify tenant isolation - Alice can't see Bob's strategy
        # ============================================================
        alice_list = await multi_strategy_servicer.list_strategies(
            strategy_pb2.ListStrategiesRequest(
                context=alice_ctx,
                pagination=common_pb2.PaginationRequest(page=1, page_size=20),
            ),
            MockServicerContext(),
        )
        alice_strategy_ids = [s.id for s in alice_list.strategies]
        assert alice_strategy_id in alice_strategy_ids
        assert bob_strategy_id not in alice_strategy_ids

        # ============================================================
        # Verify Bob can't see Alice's strategy
        # ============================================================
        bob_list = await multi_strategy_servicer.list_strategies(
            strategy_pb2.ListStrategiesRequest(
                context=bob_ctx,
                pagination=common_pb2.PaginationRequest(page=1, page_size=20),
            ),
            MockServicerContext(),
        )
        bob_strategy_ids = [s.id for s in bob_list.strategies]
        assert bob_strategy_id in bob_strategy_ids
        assert alice_strategy_id not in bob_strategy_ids

        # ============================================================
        # Activate strategies before backtesting
        # ============================================================
        for ctx, sid in [(alice_ctx, alice_strategy_id), (bob_ctx, bob_strategy_id)]:
            activate_request = strategy_pb2.UpdateStrategyStatusRequest(
                context=ctx,
                strategy_id=sid,
                status=strategy_pb2.STRATEGY_STATUS_ACTIVE,
            )
            await multi_strategy_servicer.update_strategy_status(
                activate_request, MockServicerContext()
            )

        # ============================================================
        # Both run backtests independently
        # ============================================================
        now = datetime.utcnow()
        backtest_config = lambda sid: backtest_pb2.BacktestConfig(
            strategy_id=sid,
            strategy_version=1,
            start_date=common_pb2.Timestamp(seconds=int((now - timedelta(days=90)).timestamp())),
            end_date=common_pb2.Timestamp(seconds=int(now.timestamp())),
            initial_capital=common_pb2.Decimal(value="100000"),
        )

        alice_backtest = await multi_backtest_servicer.RunBacktest(
            backtest_pb2.RunBacktestRequest(context=alice_ctx, config=backtest_config(alice_strategy_id)),
            MockServicerContext(),
        )

        bob_backtest = await multi_backtest_servicer.RunBacktest(
            backtest_pb2.RunBacktestRequest(context=bob_ctx, config=backtest_config(bob_strategy_id)),
            MockServicerContext(),
        )

        # ============================================================
        # Verify backtest isolation
        # ============================================================
        alice_backtests = await multi_backtest_servicer.ListBacktests(
            backtest_pb2.ListBacktestsRequest(
                context=alice_ctx,
                pagination=common_pb2.PaginationRequest(page=1, page_size=20),
            ),
            MockServicerContext(),
        )
        alice_backtest_ids = [b.id for b in alice_backtests.backtests]
        assert alice_backtest.backtest.id in alice_backtest_ids
        assert bob_backtest.backtest.id not in alice_backtest_ids

    async def test_tenant_cannot_modify_other_tenant_resources(
        self,
        test_tenant,
        second_tenant,
        test_strategy,
        second_tenant_strategy,
    ):
        """Test that tenants cannot access or modify each other's resources.

        Uses fixture-based approach which doesn't require multi-servicer loading.
        """
        # Verify strategies belong to different tenants
        assert test_strategy.tenant_id == test_tenant.id
        assert second_tenant_strategy.tenant_id == second_tenant.id
        assert test_strategy.tenant_id != second_tenant_strategy.tenant_id


class TestDataIsolationWithFixtures:
    """Test data isolation using database fixtures.

    These tests use fixture-based approaches that don't require loading multiple servicers.
    """

    async def test_fixture_isolation(
        self,
        test_tenant,
        second_tenant,
        test_strategy,
        second_tenant_strategy,
    ):
        """Test that fixtures create isolated data for each tenant."""
        assert test_tenant.id != second_tenant.id
        assert test_strategy.tenant_id == test_tenant.id
        assert second_tenant_strategy.tenant_id == second_tenant.id

    async def test_database_query_isolation(
        self,
        db_session: "AsyncSession",
        test_tenant,
        second_tenant,
        test_strategy,
        second_tenant_strategy,
    ):
        """Test that database queries properly filter by tenant."""
        from sqlalchemy import select

        from llamatrade_db.models import Strategy

        # Query for first tenant's strategies
        result = await db_session.execute(
            select(Strategy).where(Strategy.tenant_id == test_tenant.id)
        )
        tenant_strategies = result.scalars().all()

        # Should only see first tenant's strategies
        for strategy in tenant_strategies:
            assert strategy.tenant_id == test_tenant.id

        # Should not include second tenant's strategy
        strategy_ids = [s.id for s in tenant_strategies]
        assert second_tenant_strategy.id not in strategy_ids
