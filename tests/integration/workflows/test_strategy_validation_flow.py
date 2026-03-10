"""Strategy validation and lifecycle gRPC workflow tests.

Tests the complete strategy management workflow:
1. Strategy creation (from DSL, from template)
2. Strategy editing and versioning
3. Strategy-backtest integration

Uses auth_servicer and strategy_servicer fixtures from this file,
and multi_*_servicer fixtures from conftest.py for cross-service tests.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from connectrpc.errors import ConnectError

from .conftest import MockServicerContext

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.integration, pytest.mark.workflow, pytest.mark.asyncio]

# Base path for services
SERVICES_DIR = Path(__file__).parents[3] / "services"


def _load_auth_servicer():
    """Load the auth servicer, clearing module cache to avoid conflicts."""
    auth_path = SERVICES_DIR / "auth"
    auth_path_str = str(auth_path)

    service_paths = [
        str(SERVICES_DIR / svc)
        for svc in ["billing", "strategy", "backtest", "market-data", "trading", "portfolio"]
    ]
    for svc_path in service_paths:
        if svc_path in sys.path:
            sys.path.remove(svc_path)

    modules_to_remove = [k for k in list(sys.modules.keys()) if k == "src" or k.startswith("src.")]
    for mod in modules_to_remove:
        del sys.modules[mod]

    if auth_path_str in sys.path:
        sys.path.remove(auth_path_str)
    sys.path.insert(0, auth_path_str)

    from src.grpc.servicer import AuthServicer

    return AuthServicer


def _load_strategy_servicer():
    """Load the strategy servicer, clearing module cache to avoid conflicts."""
    strategy_path = SERVICES_DIR / "strategy"
    strategy_path_str = str(strategy_path)

    service_paths = [
        str(SERVICES_DIR / svc)
        for svc in ["auth", "billing", "backtest", "market-data", "trading", "portfolio"]
    ]
    for svc_path in service_paths:
        if svc_path in sys.path:
            sys.path.remove(svc_path)

    modules_to_remove = [k for k in list(sys.modules.keys()) if k == "src" or k.startswith("src.")]
    for mod in modules_to_remove:
        del sys.modules[mod]

    if strategy_path_str in sys.path:
        sys.path.remove(strategy_path_str)
    sys.path.insert(0, strategy_path_str)

    from src.grpc.servicer import StrategyServicer

    return StrategyServicer


@pytest.fixture
def auth_servicer(db_session: "AsyncSession"):
    """Create an auth servicer with test database session."""
    auth_servicer_cls = _load_auth_servicer()
    servicer = auth_servicer_cls()

    async def mock_get_db():
        return db_session

    servicer._get_db = mock_get_db
    return servicer


@pytest.fixture
def strategy_servicer(db_session: "AsyncSession"):
    """Create a strategy servicer with test database session."""
    strategy_servicer_cls = _load_strategy_servicer()
    servicer = strategy_servicer_cls()

    async def mock_get_db():
        return db_session

    servicer._get_db = mock_get_db
    return servicer


@pytest.fixture
def grpc_context() -> MockServicerContext:
    """Create a mock gRPC context (alias for mock_context)."""
    return MockServicerContext()


# Sample valid S-expression strategy configs
VALID_MOMENTUM_STRATEGY = """(strategy "Momentum Strategy"
  :rebalance daily
  :benchmark SPY
  (if (crosses-above (sma SPY 20) (sma SPY 50))
    (weight :method equal
      (asset AAPL)
      (asset GOOGL))
    (else (asset TLT :weight 100))))"""

VALID_MEAN_REVERSION_STRATEGY = """(strategy "Mean Reversion"
  :rebalance weekly
  :benchmark SPY
  (if (crosses-below (rsi AAPL 14) 30)
    (asset AAPL :weight 100)
    (else (asset SHY :weight 100))))"""

INVALID_STRATEGY_DSL = """(strategy (missing required fields))"""


async def register_and_login(auth_servicer, context):
    """Helper to register and login, returning tokens and user info."""
    from llamatrade_proto.generated import auth_pb2

    email = f"test-{uuid4().hex[:8]}@example.com"

    register_request = auth_pb2.RegisterRequest(
        tenant_name=f"Test Co {uuid4().hex[:6]}",
        email=email,
        password="TestPassword123!",
    )
    register_response = await auth_servicer.register(register_request, context)

    login_request = auth_pb2.LoginRequest(
        email=email,
        password="TestPassword123!",
    )
    login_response = await auth_servicer.login(login_request, context)

    return {
        "access_token": login_response.access_token,
        "user_id": register_response.user.id,
        "tenant_id": register_response.tenant.id,
    }


def create_tenant_context(user_id: str, tenant_id: str):
    """Create a TenantContext proto message."""
    from llamatrade_proto.generated import common_pb2

    return common_pb2.TenantContext(
        tenant_id=tenant_id,
        user_id=user_id,
        roles=["admin"],
    )


class TestStrategyCreationFlow:
    """Test strategy creation workflow."""

    async def test_create_strategy_from_dsl(
        self,
        auth_servicer,
        strategy_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test creating a strategy from DSL code."""
        from llamatrade_proto.generated import strategy_pb2

        auth_info = await register_and_login(auth_servicer, grpc_context)
        ctx = create_tenant_context(auth_info["user_id"], auth_info["tenant_id"])

        request = strategy_pb2.CreateStrategyRequest(
            context=ctx,
            name="My Momentum Strategy",
            description="A momentum-based trading strategy",
            dsl_code=VALID_MOMENTUM_STRATEGY,
        )

        response = await strategy_servicer.create_strategy(request, grpc_context)

        assert response.strategy.name == "My Momentum Strategy"
        assert response.strategy.description == "A momentum-based trading strategy"
        assert response.strategy.status == strategy_pb2.STRATEGY_STATUS_DRAFT
        assert response.strategy.version == 1
        assert response.strategy.id

    async def test_create_strategy_from_template(
        self,
        auth_servicer,
        strategy_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test creating a strategy from a template."""
        from llamatrade_proto.generated import strategy_pb2

        auth_info = await register_and_login(auth_servicer, grpc_context)
        ctx = create_tenant_context(auth_info["user_id"], auth_info["tenant_id"])

        # List available templates (no context field in this request)
        list_templates_request = strategy_pb2.ListTemplatesRequest()
        templates_response = await strategy_servicer.list_templates(
            list_templates_request, grpc_context
        )

        # Create from first template if available
        if templates_response.templates:
            template = templates_response.templates[0]

            # Use CreateStrategyRequest with template_id field for template-based creation
            create_request = strategy_pb2.CreateStrategyRequest(
                context=ctx,
                template_id=template.id,
                name="My Strategy From Template",
            )
            response = await strategy_servicer.create_strategy(
                create_request, MockServicerContext()
            )

            assert response.strategy.name == "My Strategy From Template"
            assert response.strategy.status == strategy_pb2.STRATEGY_STATUS_DRAFT

    async def test_create_strategy_invalid_dsl_fails(
        self,
        auth_servicer,
        strategy_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test that creating strategy with invalid DSL fails."""
        from llamatrade_proto.generated import strategy_pb2

        auth_info = await register_and_login(auth_servicer, grpc_context)
        ctx = create_tenant_context(auth_info["user_id"], auth_info["tenant_id"])

        request = strategy_pb2.CreateStrategyRequest(
            context=ctx,
            name="Invalid Strategy",
            dsl_code=INVALID_STRATEGY_DSL,
        )

        with pytest.raises(ConnectError) as exc_info:
            await strategy_servicer.create_strategy(request, grpc_context)

        assert "INVALID_ARGUMENT" in str(exc_info.value.code)

    async def test_create_strategy_requires_name(
        self,
        auth_servicer,
        strategy_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test that strategy creation requires a name."""
        from llamatrade_proto.generated import strategy_pb2

        auth_info = await register_and_login(auth_servicer, grpc_context)
        ctx = create_tenant_context(auth_info["user_id"], auth_info["tenant_id"])

        request = strategy_pb2.CreateStrategyRequest(
            context=ctx,
            name="",  # Empty name
            dsl_code=VALID_MOMENTUM_STRATEGY,
        )

        with pytest.raises(ConnectError) as exc_info:
            await strategy_servicer.create_strategy(request, grpc_context)

        assert "INVALID_ARGUMENT" in str(exc_info.value.code)


class TestStrategyEditingFlow:
    """Test strategy editing and versioning workflow."""

    async def test_update_strategy_creates_new_version(
        self,
        auth_servicer,
        strategy_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test that updating config creates a new version."""
        from llamatrade_proto.generated import strategy_pb2

        auth_info = await register_and_login(auth_servicer, grpc_context)
        ctx = create_tenant_context(auth_info["user_id"], auth_info["tenant_id"])

        # Create initial strategy
        create_request = strategy_pb2.CreateStrategyRequest(
            context=ctx,
            name="Versioned Strategy",
            dsl_code=VALID_MOMENTUM_STRATEGY,
        )
        create_response = await strategy_servicer.create_strategy(create_request, grpc_context)
        strategy_id = create_response.strategy.id
        assert create_response.strategy.version == 1

        # Update with new config
        update_request = strategy_pb2.UpdateStrategyRequest(
            context=ctx,
            strategy_id=strategy_id,
            dsl_code=VALID_MEAN_REVERSION_STRATEGY,
        )
        update_response = await strategy_servicer.update_strategy(update_request, grpc_context)

        assert update_response.strategy.version == 2

    async def test_list_strategy_versions(
        self,
        auth_servicer,
        strategy_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test listing all versions of a strategy."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        auth_info = await register_and_login(auth_servicer, grpc_context)
        ctx = create_tenant_context(auth_info["user_id"], auth_info["tenant_id"])

        # Create and update strategy multiple times
        create_request = strategy_pb2.CreateStrategyRequest(
            context=ctx,
            name="Multi-Version Strategy",
            dsl_code=VALID_MOMENTUM_STRATEGY,
        )
        create_response = await strategy_servicer.create_strategy(create_request, grpc_context)
        strategy_id = create_response.strategy.id

        # Update twice
        for i in range(2):
            updated_dsl = VALID_MOMENTUM_STRATEGY.replace(
                '"Momentum Strategy"',
                f'"Version {i + 2}"',
            )
            update_request = strategy_pb2.UpdateStrategyRequest(
                context=ctx,
                strategy_id=strategy_id,
                dsl_code=updated_dsl,
            )
            await strategy_servicer.update_strategy(update_request, MockServicerContext())

        # List versions
        list_request = strategy_pb2.ListStrategyVersionsRequest(
            context=ctx,
            strategy_id=strategy_id,
            pagination=common_pb2.PaginationRequest(page=1, page_size=20),
        )
        response = await strategy_servicer.list_strategy_versions(list_request, grpc_context)

        assert len(response.versions) == 3
        versions = sorted([v.version for v in response.versions])
        assert versions == [1, 2, 3]

    async def test_clone_strategy(
        self,
        auth_servicer,
        strategy_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test cloning an existing strategy."""
        from llamatrade_proto.generated import strategy_pb2

        auth_info = await register_and_login(auth_servicer, grpc_context)
        ctx = create_tenant_context(auth_info["user_id"], auth_info["tenant_id"])

        # Create original strategy
        create_request = strategy_pb2.CreateStrategyRequest(
            context=ctx,
            name="Original Strategy",
            description="The original",
            dsl_code=VALID_MOMENTUM_STRATEGY,
        )
        original = await strategy_servicer.create_strategy(create_request, grpc_context)

        # Clone it
        clone_request = strategy_pb2.CloneStrategyRequest(
            context=ctx,
            strategy_id=original.strategy.id,
            new_name="Cloned Strategy",
        )
        cloned = await strategy_servicer.clone_strategy(clone_request, MockServicerContext())

        assert cloned.strategy.name == "Cloned Strategy"
        assert cloned.strategy.id != original.strategy.id
        assert cloned.strategy.version == 1
        assert cloned.strategy.status == strategy_pb2.STRATEGY_STATUS_DRAFT

    async def test_update_strategy_metadata_only(
        self,
        auth_servicer,
        strategy_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test updating only name/description doesn't create new version."""
        from llamatrade_proto.generated import strategy_pb2

        auth_info = await register_and_login(auth_servicer, grpc_context)
        ctx = create_tenant_context(auth_info["user_id"], auth_info["tenant_id"])

        # Create strategy
        create_request = strategy_pb2.CreateStrategyRequest(
            context=ctx,
            name="Original Name",
            description="Original description",
            dsl_code=VALID_MOMENTUM_STRATEGY,
        )
        create_response = await strategy_servicer.create_strategy(create_request, grpc_context)
        strategy_id = create_response.strategy.id

        # Update only metadata
        update_request = strategy_pb2.UpdateStrategyRequest(
            context=ctx,
            strategy_id=strategy_id,
            name="Updated Name",
            description="Updated description",
            # No dsl_code change
        )
        update_response = await strategy_servicer.update_strategy(update_request, grpc_context)

        assert update_response.strategy.name == "Updated Name"
        assert update_response.strategy.description == "Updated description"
        # Version should not increment for metadata-only changes
        assert update_response.strategy.version == 1


class TestStrategyBacktestIntegration:
    """Test strategy-backtest integration workflow.

    Uses multi-servicer fixtures from conftest.py that preload servicer classes
    at module import time to avoid module path conflicts.
    """

    async def test_create_and_backtest_strategy(
        self,
        multi_auth_servicer,
        multi_strategy_servicer,
        multi_backtest_servicer,
        mock_context: MockServicerContext,
        db_session: "AsyncSession",
    ):
        """Test full workflow: create strategy → run backtest → review results."""
        from datetime import datetime, timedelta

        from llamatrade_proto.generated import backtest_pb2, common_pb2, strategy_pb2

        auth_info = await register_and_login(multi_auth_servicer, mock_context)
        ctx = create_tenant_context(auth_info["user_id"], auth_info["tenant_id"])

        # Step 1: Create strategy
        create_request = strategy_pb2.CreateStrategyRequest(
            context=ctx,
            name="Backtest Strategy",
            dsl_code=VALID_MOMENTUM_STRATEGY,
        )
        strategy_response = await multi_strategy_servicer.create_strategy(
            create_request, MockServicerContext()
        )
        strategy_id = strategy_response.strategy.id

        # Step 1.5: Activate strategy (required before backtesting)
        activate_request = strategy_pb2.UpdateStrategyStatusRequest(
            context=ctx,
            strategy_id=strategy_id,
            status=strategy_pb2.STRATEGY_STATUS_ACTIVE,
        )
        await multi_strategy_servicer.update_strategy_status(
            activate_request, MockServicerContext()
        )

        # Step 2: Run backtest
        now = datetime.utcnow()
        start_date = now - timedelta(days=365)
        end_date = now

        backtest_config = backtest_pb2.BacktestConfig(
            strategy_id=strategy_id,
            strategy_version=1,
            start_date=common_pb2.Timestamp(seconds=int(start_date.timestamp())),
            end_date=common_pb2.Timestamp(seconds=int(end_date.timestamp())),
            initial_capital=common_pb2.Decimal(value="100000"),
            symbols=["AAPL", "GOOGL"],
        )

        run_request = backtest_pb2.RunBacktestRequest(
            context=ctx,
            config=backtest_config,
        )
        backtest_response = await multi_backtest_servicer.RunBacktest(
            run_request, MockServicerContext()
        )

        assert backtest_response.backtest.id
        assert backtest_response.backtest.strategy_id == strategy_id

        # Step 3: Get backtest details
        get_request = backtest_pb2.GetBacktestRequest(
            context=ctx,
            backtest_id=backtest_response.backtest.id,
        )
        get_response = await multi_backtest_servicer.GetBacktest(
            get_request, MockServicerContext()
        )

        assert get_response.backtest.id == backtest_response.backtest.id

    async def test_list_backtests_for_strategy(
        self,
        multi_auth_servicer,
        multi_strategy_servicer,
        multi_backtest_servicer,
        mock_context: MockServicerContext,
        db_session: "AsyncSession",
    ):
        """Test listing backtests filtered by strategy."""
        from datetime import datetime, timedelta

        from llamatrade_proto.generated import backtest_pb2, common_pb2, strategy_pb2

        auth_info = await register_and_login(multi_auth_servicer, mock_context)
        ctx = create_tenant_context(auth_info["user_id"], auth_info["tenant_id"])

        # Create strategy
        create_request = strategy_pb2.CreateStrategyRequest(
            context=ctx,
            name="Strategy For Backtests",
            dsl_code=VALID_MOMENTUM_STRATEGY,
        )
        strategy_response = await multi_strategy_servicer.create_strategy(
            create_request, MockServicerContext()
        )
        strategy_id = strategy_response.strategy.id

        # Activate strategy before backtesting
        activate_request = strategy_pb2.UpdateStrategyStatusRequest(
            context=ctx,
            strategy_id=strategy_id,
            status=strategy_pb2.STRATEGY_STATUS_ACTIVE,
        )
        await multi_strategy_servicer.update_strategy_status(
            activate_request, MockServicerContext()
        )

        # Run multiple backtests
        for i in range(3):
            now = datetime.utcnow()
            config = backtest_pb2.BacktestConfig(
                strategy_id=strategy_id,
                strategy_version=1,
                start_date=common_pb2.Timestamp(
                    seconds=int((now - timedelta(days=365)).timestamp())
                ),
                end_date=common_pb2.Timestamp(seconds=int(now.timestamp())),
                initial_capital=common_pb2.Decimal(value=str(50000 + i * 10000)),
            )
            run_request = backtest_pb2.RunBacktestRequest(context=ctx, config=config)
            await multi_backtest_servicer.RunBacktest(run_request, MockServicerContext())

        # List backtests for this strategy
        list_request = backtest_pb2.ListBacktestsRequest(
            context=ctx,
            strategy_id=strategy_id,
            pagination=common_pb2.PaginationRequest(page=1, page_size=20),
        )
        list_response = await multi_backtest_servicer.ListBacktests(
            list_request, MockServicerContext()
        )

        assert list_response.pagination.total_items == 3


class TestStrategyValidation:
    """Test strategy validation endpoint."""

    async def test_validate_valid_dsl(
        self,
        strategy_servicer,
        grpc_context: MockServicerContext,
    ):
        """Test validating a valid DSL configuration."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        request = strategy_pb2.CompileStrategyRequest(
            context=common_pb2.TenantContext(tenant_id="", user_id=""),
            dsl_code=VALID_MOMENTUM_STRATEGY,
            validate_only=True,
        )

        response = await strategy_servicer.compile_strategy(request, grpc_context)

        assert response.result.success is True
        assert len(response.result.errors) == 0

    async def test_validate_invalid_dsl(
        self,
        strategy_servicer,
        grpc_context: MockServicerContext,
    ):
        """Test validating an invalid DSL configuration."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        request = strategy_pb2.CompileStrategyRequest(
            context=common_pb2.TenantContext(tenant_id="", user_id=""),
            dsl_code=INVALID_STRATEGY_DSL,
            validate_only=True,
        )

        response = await strategy_servicer.compile_strategy(request, grpc_context)

        assert response.result.success is False
        assert len(response.result.errors) > 0

    async def test_validate_empty_dsl(
        self,
        strategy_servicer,
        grpc_context: MockServicerContext,
    ):
        """Test validating empty DSL code."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        request = strategy_pb2.CompileStrategyRequest(
            context=common_pb2.TenantContext(tenant_id="", user_id=""),
            dsl_code="",
            validate_only=True,
        )

        response = await strategy_servicer.compile_strategy(request, grpc_context)

        assert response.result.success is False
