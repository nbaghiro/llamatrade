"""Auth → Strategy gRPC workflow tests.

Tests the complete workflow using gRPC servicers:
1. Register/login via Auth gRPC servicer
2. CRUD operations via Strategy gRPC servicer
3. Tenant isolation verification
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import grpc.aio
import pytest

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.integration, pytest.mark.workflow, pytest.mark.asyncio]


class MockServicerContext:
    """Mock gRPC servicer context for testing."""

    def __init__(self) -> None:
        self._metadata: list[tuple[str, str]] = []
        self._aborted = False
        self._abort_code: grpc.StatusCode | None = None
        self._abort_details: str | None = None

    def invocation_metadata(self) -> list[tuple[str, str]]:
        return self._metadata

    def set_metadata(self, metadata: list[tuple[str, str]]) -> None:
        self._metadata = metadata

    def HasField(self, field_name: str) -> bool:
        """Check if a field exists (for proto compatibility)."""
        return False

    async def abort(self, code: grpc.StatusCode, details: str) -> None:
        self._aborted = True
        self._abort_code = code
        self._abort_details = details
        raise grpc.aio.AioRpcError(
            code=code,
            initial_metadata=None,
            trailing_metadata=None,
            details=details,
            debug_error_string=None,
        )

    @property
    def aborted(self) -> bool:
        return self._aborted


@pytest.fixture
def grpc_context() -> MockServicerContext:
    """Create a mock gRPC context."""
    return MockServicerContext()


def _load_auth_servicer():
    """Load the auth servicer, clearing module cache to avoid conflicts."""
    auth_path = Path(__file__).parents[3] / "services" / "auth"
    auth_path_str = str(auth_path)

    # Remove other service paths
    service_paths = [
        str(Path(__file__).parents[3] / "services" / svc)
        for svc in ["billing", "strategy", "backtest", "market-data", "trading", "portfolio"]
    ]
    for svc_path in service_paths:
        if svc_path in sys.path:
            sys.path.remove(svc_path)

    # Clear cached src modules
    modules_to_remove = [
        k for k in list(sys.modules.keys())
        if k == "src" or k.startswith("src.")
    ]
    for mod in modules_to_remove:
        del sys.modules[mod]

    # Add auth service path
    if auth_path_str in sys.path:
        sys.path.remove(auth_path_str)
    sys.path.insert(0, auth_path_str)

    from src.grpc.servicer import AuthServicer
    return AuthServicer


def _load_strategy_servicer():
    """Load the strategy servicer, clearing module cache to avoid conflicts."""
    strategy_path = Path(__file__).parents[3] / "services" / "strategy"
    strategy_path_str = str(strategy_path)

    # Remove other service paths
    service_paths = [
        str(Path(__file__).parents[3] / "services" / svc)
        for svc in ["auth", "billing", "backtest", "market-data", "trading", "portfolio"]
    ]
    for svc_path in service_paths:
        if svc_path in sys.path:
            sys.path.remove(svc_path)

    # Clear cached src modules
    modules_to_remove = [
        k for k in list(sys.modules.keys())
        if k == "src" or k.startswith("src.")
    ]
    for mod in modules_to_remove:
        del sys.modules[mod]

    # Add strategy service path
    if strategy_path_str in sys.path:
        sys.path.remove(strategy_path_str)
    sys.path.insert(0, strategy_path_str)

    from src.grpc.servicer import StrategyServicer
    return StrategyServicer


@pytest.fixture
def auth_servicer(db_session: AsyncSession):
    """Create an auth servicer with test database session."""
    AuthServicer = _load_auth_servicer()
    servicer = AuthServicer()

    async def mock_get_db():
        return db_session

    servicer._get_db = mock_get_db
    return servicer


@pytest.fixture
def strategy_servicer(db_session: AsyncSession):
    """Create a strategy servicer with test database session."""
    StrategyServicer = _load_strategy_servicer()
    servicer = StrategyServicer()

    async def mock_get_db():
        return db_session

    servicer._get_db = mock_get_db
    return servicer


# Sample valid S-expression strategy config
VALID_STRATEGY_SEXPR = """
(strategy
  :name "Test Momentum Strategy"
  :type momentum
  :symbols ["AAPL" "GOOGL"]
  :timeframe "1D"
  :entry (and
           (cross-above (sma close 20) (sma close 50))
           (> volume 1000000))
  :exit (cross-below (sma close 20) (sma close 50))
  :risk {:stop-loss-pct 5
         :take-profit-pct 15
         :max-position-pct 10})
"""


async def register_and_login(auth_servicer, context):
    """Helper to register and login, returning tokens and user info."""
    from llamatrade.v1 import auth_pb2

    email = f"test-{uuid4().hex[:8]}@example.com"

    # Register
    register_request = auth_pb2.RegisterRequest(
        tenant_name=f"Test Co {uuid4().hex[:6]}",
        email=email,
        password="TestPassword123!",
    )
    register_response = await auth_servicer.Register(register_request, context)

    # Login
    login_request = auth_pb2.LoginRequest(
        email=email,
        password="TestPassword123!",
    )
    login_response = await auth_servicer.Login(login_request, context)

    return {
        "access_token": login_response.access_token,
        "user_id": register_response.user.id,
        "tenant_id": register_response.tenant.id,
    }


def create_tenant_context(user_id: str, tenant_id: str):
    """Create a TenantContext proto message."""
    from llamatrade.v1 import common_pb2

    return common_pb2.TenantContext(
        tenant_id=tenant_id,
        user_id=user_id,
        roles=["admin"],
    )


class TestStrategyCreationWorkflow:
    """Test strategy creation via gRPC."""

    async def test_create_strategy_with_valid_config(
        self,
        auth_servicer,
        strategy_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test creating a strategy with valid S-expression config."""
        from llamatrade.v1 import strategy_pb2

        # First, register and login
        auth_info = await register_and_login(auth_servicer, grpc_context)

        # Create strategy
        ctx = create_tenant_context(auth_info["user_id"], auth_info["tenant_id"])
        request = strategy_pb2.CreateStrategyRequest(
            context=ctx,
            name="My Momentum Strategy",
            description="A simple momentum strategy",
            dsl_code=VALID_STRATEGY_SEXPR,
        )

        response = await strategy_servicer.CreateStrategy(request, grpc_context)

        assert response.strategy.name == "My Momentum Strategy"
        assert response.strategy.description == "A simple momentum strategy"
        assert response.strategy.status == strategy_pb2.STRATEGY_STATUS_DRAFT
        assert response.strategy.version == 1
        assert response.strategy.id

    async def test_create_strategy_requires_auth_context(
        self,
        strategy_servicer,
        grpc_context: MockServicerContext,
    ):
        """Test that strategy creation requires valid tenant context."""
        from llamatrade.v1 import common_pb2, strategy_pb2

        # Create with empty context
        request = strategy_pb2.CreateStrategyRequest(
            context=common_pb2.TenantContext(tenant_id="", user_id=""),
            name="Unauthorized Strategy",
            dsl_code=VALID_STRATEGY_SEXPR,
        )

        with pytest.raises(grpc.aio.AioRpcError):
            await strategy_servicer.CreateStrategy(request, grpc_context)


class TestStrategyListWorkflow:
    """Test strategy listing via gRPC."""

    async def test_list_strategies_empty(
        self,
        auth_servicer,
        strategy_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test listing strategies when none exist."""
        from llamatrade.v1 import common_pb2, strategy_pb2

        auth_info = await register_and_login(auth_servicer, grpc_context)
        ctx = create_tenant_context(auth_info["user_id"], auth_info["tenant_id"])

        request = strategy_pb2.ListStrategiesRequest(
            context=ctx,
            pagination=common_pb2.PaginationRequest(page=1, page_size=20),
        )

        response = await strategy_servicer.ListStrategies(request, grpc_context)

        assert response.pagination.total_items == 0
        assert len(response.strategies) == 0

    async def test_list_strategies_with_data(
        self,
        auth_servicer,
        strategy_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test listing strategies after creating some."""
        from llamatrade.v1 import common_pb2, strategy_pb2

        auth_info = await register_and_login(auth_servicer, grpc_context)
        ctx = create_tenant_context(auth_info["user_id"], auth_info["tenant_id"])

        # Create two strategies
        for i in range(2):
            create_request = strategy_pb2.CreateStrategyRequest(
                context=ctx,
                name=f"Strategy {i+1}",
                dsl_code=VALID_STRATEGY_SEXPR,
            )
            await strategy_servicer.CreateStrategy(create_request, grpc_context)

        # List strategies
        list_request = strategy_pb2.ListStrategiesRequest(
            context=ctx,
            pagination=common_pb2.PaginationRequest(page=1, page_size=20),
        )
        response = await strategy_servicer.ListStrategies(list_request, grpc_context)

        assert response.pagination.total_items == 2
        assert len(response.strategies) == 2

    async def test_list_strategies_pagination(
        self,
        auth_servicer,
        strategy_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test pagination for strategy listing."""
        from llamatrade.v1 import common_pb2, strategy_pb2

        auth_info = await register_and_login(auth_servicer, grpc_context)
        ctx = create_tenant_context(auth_info["user_id"], auth_info["tenant_id"])

        # Create 5 strategies
        for i in range(5):
            create_request = strategy_pb2.CreateStrategyRequest(
                context=ctx,
                name=f"Paginated Strategy {i+1}",
                dsl_code=VALID_STRATEGY_SEXPR,
            )
            await strategy_servicer.CreateStrategy(create_request, grpc_context)

        # Get page 1 with page_size=2
        list_request = strategy_pb2.ListStrategiesRequest(
            context=ctx,
            pagination=common_pb2.PaginationRequest(page=1, page_size=2),
        )
        response = await strategy_servicer.ListStrategies(list_request, grpc_context)

        assert response.pagination.total_items == 5
        assert len(response.strategies) == 2
        assert response.pagination.current_page == 1
        assert response.pagination.has_next is True


class TestStrategyVersionWorkflow:
    """Test strategy version management via gRPC."""

    async def test_update_strategy_creates_new_version(
        self,
        auth_servicer,
        strategy_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test that updating config creates a new version."""
        from llamatrade.v1 import strategy_pb2

        auth_info = await register_and_login(auth_servicer, grpc_context)
        ctx = create_tenant_context(auth_info["user_id"], auth_info["tenant_id"])

        # Create initial strategy
        create_request = strategy_pb2.CreateStrategyRequest(
            context=ctx,
            name="Versioned Strategy",
            dsl_code=VALID_STRATEGY_SEXPR,
        )
        create_response = await strategy_servicer.CreateStrategy(create_request, grpc_context)
        strategy_id = create_response.strategy.id
        assert create_response.strategy.version == 1

        # Update with new config
        updated_sexpr = VALID_STRATEGY_SEXPR.replace(
            ':symbols ["AAPL" "GOOGL"]',
            ':symbols ["MSFT" "AMZN" "NVDA"]',
        )
        update_request = strategy_pb2.UpdateStrategyRequest(
            context=ctx,
            strategy_id=strategy_id,
            dsl_code=updated_sexpr,
        )
        update_response = await strategy_servicer.UpdateStrategy(update_request, grpc_context)

        assert update_response.strategy.version == 2

    async def test_list_strategy_versions(
        self,
        auth_servicer,
        strategy_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test listing all versions of a strategy."""
        from llamatrade.v1 import common_pb2, strategy_pb2

        auth_info = await register_and_login(auth_servicer, grpc_context)
        ctx = create_tenant_context(auth_info["user_id"], auth_info["tenant_id"])

        # Create strategy and update it twice
        create_request = strategy_pb2.CreateStrategyRequest(
            context=ctx,
            name="Multi-Version Strategy",
            dsl_code=VALID_STRATEGY_SEXPR,
        )
        create_response = await strategy_servicer.CreateStrategy(create_request, grpc_context)
        strategy_id = create_response.strategy.id

        # Update twice
        for i in range(2):
            updated_sexpr = VALID_STRATEGY_SEXPR.replace(
                ':name "Test Momentum Strategy"',
                f':name "Version {i+2}"',
            )
            update_request = strategy_pb2.UpdateStrategyRequest(
                context=ctx,
                strategy_id=strategy_id,
                dsl_code=updated_sexpr,
            )
            await strategy_servicer.UpdateStrategy(update_request, grpc_context)

        # List versions
        list_request = strategy_pb2.ListStrategyVersionsRequest(
            context=ctx,
            strategy_id=strategy_id,
            pagination=common_pb2.PaginationRequest(page=1, page_size=20),
        )
        response = await strategy_servicer.ListStrategyVersions(list_request, grpc_context)

        assert len(response.versions) == 3


class TestStrategyTenantIsolation:
    """Test tenant isolation for strategy operations."""

    async def test_cannot_access_other_tenant_strategy(
        self,
        auth_servicer,
        strategy_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test that one tenant cannot access another tenant's strategy."""
        from llamatrade.v1 import strategy_pb2

        # Create strategy as tenant A
        auth_info_a = await register_and_login(auth_servicer, grpc_context)
        ctx_a = create_tenant_context(auth_info_a["user_id"], auth_info_a["tenant_id"])

        create_request = strategy_pb2.CreateStrategyRequest(
            context=ctx_a,
            name="Tenant A Strategy",
            dsl_code=VALID_STRATEGY_SEXPR,
        )
        create_response = await strategy_servicer.CreateStrategy(create_request, grpc_context)
        strategy_id = create_response.strategy.id

        # Try to access as tenant B
        auth_info_b = await register_and_login(auth_servicer, MockServicerContext())
        ctx_b = create_tenant_context(auth_info_b["user_id"], auth_info_b["tenant_id"])

        get_request = strategy_pb2.GetStrategyRequest(
            context=ctx_b,
            strategy_id=strategy_id,
        )

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await strategy_servicer.GetStrategy(get_request, MockServicerContext())

        assert exc_info.value.code() == grpc.StatusCode.NOT_FOUND

    async def test_cannot_modify_other_tenant_strategy(
        self,
        auth_servicer,
        strategy_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test that one tenant cannot modify another tenant's strategy."""
        from llamatrade.v1 import strategy_pb2

        # Create strategy as tenant A
        auth_info_a = await register_and_login(auth_servicer, grpc_context)
        ctx_a = create_tenant_context(auth_info_a["user_id"], auth_info_a["tenant_id"])

        create_request = strategy_pb2.CreateStrategyRequest(
            context=ctx_a,
            name="Protected Strategy",
            dsl_code=VALID_STRATEGY_SEXPR,
        )
        create_response = await strategy_servicer.CreateStrategy(create_request, grpc_context)
        strategy_id = create_response.strategy.id

        # Try to update as tenant B
        auth_info_b = await register_and_login(auth_servicer, MockServicerContext())
        ctx_b = create_tenant_context(auth_info_b["user_id"], auth_info_b["tenant_id"])

        update_request = strategy_pb2.UpdateStrategyRequest(
            context=ctx_b,
            strategy_id=strategy_id,
            name="Hacked Strategy",
        )

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await strategy_servicer.UpdateStrategy(update_request, MockServicerContext())

        assert exc_info.value.code() == grpc.StatusCode.NOT_FOUND

    async def test_cannot_delete_other_tenant_strategy(
        self,
        auth_servicer,
        strategy_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test that one tenant cannot delete another tenant's strategy."""
        from llamatrade.v1 import strategy_pb2

        # Create strategy as tenant A
        auth_info_a = await register_and_login(auth_servicer, grpc_context)
        ctx_a = create_tenant_context(auth_info_a["user_id"], auth_info_a["tenant_id"])

        create_request = strategy_pb2.CreateStrategyRequest(
            context=ctx_a,
            name="Cannot Delete This",
            dsl_code=VALID_STRATEGY_SEXPR,
        )
        create_response = await strategy_servicer.CreateStrategy(create_request, grpc_context)
        strategy_id = create_response.strategy.id

        # Try to delete as tenant B
        auth_info_b = await register_and_login(auth_servicer, MockServicerContext())
        ctx_b = create_tenant_context(auth_info_b["user_id"], auth_info_b["tenant_id"])

        delete_request = strategy_pb2.DeleteStrategyRequest(
            context=ctx_b,
            strategy_id=strategy_id,
        )

        with pytest.raises(grpc.aio.AioRpcError) as exc_info:
            await strategy_servicer.DeleteStrategy(delete_request, MockServicerContext())

        assert exc_info.value.code() == grpc.StatusCode.NOT_FOUND

        # Verify strategy still exists for tenant A
        get_request = strategy_pb2.GetStrategyRequest(
            context=ctx_a,
            strategy_id=strategy_id,
        )
        get_response = await strategy_servicer.GetStrategy(get_request, grpc_context)
        assert get_response.strategy.id == strategy_id

    async def test_list_only_shows_own_tenant_strategies(
        self,
        auth_servicer,
        strategy_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test that listing only shows the requesting tenant's strategies."""
        from llamatrade.v1 import common_pb2, strategy_pb2

        # Create strategies for tenant A
        auth_info_a = await register_and_login(auth_servicer, grpc_context)
        ctx_a = create_tenant_context(auth_info_a["user_id"], auth_info_a["tenant_id"])

        for i in range(2):
            create_request = strategy_pb2.CreateStrategyRequest(
                context=ctx_a,
                name=f"Tenant A Strategy {i+1}",
                dsl_code=VALID_STRATEGY_SEXPR,
            )
            await strategy_servicer.CreateStrategy(create_request, grpc_context)

        # Create strategy for tenant B
        auth_info_b = await register_and_login(auth_servicer, MockServicerContext())
        ctx_b = create_tenant_context(auth_info_b["user_id"], auth_info_b["tenant_id"])

        create_request = strategy_pb2.CreateStrategyRequest(
            context=ctx_b,
            name="Tenant B Strategy",
            dsl_code=VALID_STRATEGY_SEXPR,
        )
        await strategy_servicer.CreateStrategy(create_request, MockServicerContext())

        # List as tenant A - should see 2
        list_request_a = strategy_pb2.ListStrategiesRequest(
            context=ctx_a,
            pagination=common_pb2.PaginationRequest(page=1, page_size=20),
        )
        response_a = await strategy_servicer.ListStrategies(list_request_a, grpc_context)
        assert response_a.pagination.total_items == 2

        # List as tenant B - should see 1
        list_request_b = strategy_pb2.ListStrategiesRequest(
            context=ctx_b,
            pagination=common_pb2.PaginationRequest(page=1, page_size=20),
        )
        response_b = await strategy_servicer.ListStrategies(list_request_b, MockServicerContext())
        assert response_b.pagination.total_items == 1


class TestStrategyStatusWorkflow:
    """Test strategy status transitions via gRPC."""

    async def test_activate_strategy(
        self,
        auth_servicer,
        strategy_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test activating a strategy."""
        from llamatrade.v1 import strategy_pb2

        auth_info = await register_and_login(auth_servicer, grpc_context)
        ctx = create_tenant_context(auth_info["user_id"], auth_info["tenant_id"])

        # Create strategy (starts as draft)
        create_request = strategy_pb2.CreateStrategyRequest(
            context=ctx,
            name="Activatable Strategy",
            dsl_code=VALID_STRATEGY_SEXPR,
        )
        create_response = await strategy_servicer.CreateStrategy(create_request, grpc_context)
        strategy_id = create_response.strategy.id
        assert create_response.strategy.status == strategy_pb2.STRATEGY_STATUS_DRAFT

        # Activate
        status_request = strategy_pb2.UpdateStrategyStatusRequest(
            context=ctx,
            strategy_id=strategy_id,
            status=strategy_pb2.STRATEGY_STATUS_ACTIVE,
        )
        response = await strategy_servicer.UpdateStrategyStatus(status_request, grpc_context)

        assert response.strategy.status == strategy_pb2.STRATEGY_STATUS_ACTIVE

    async def test_pause_strategy(
        self,
        auth_servicer,
        strategy_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test pausing an active strategy."""
        from llamatrade.v1 import strategy_pb2

        auth_info = await register_and_login(auth_servicer, grpc_context)
        ctx = create_tenant_context(auth_info["user_id"], auth_info["tenant_id"])

        # Create and activate
        create_request = strategy_pb2.CreateStrategyRequest(
            context=ctx,
            name="Pausable Strategy",
            dsl_code=VALID_STRATEGY_SEXPR,
        )
        create_response = await strategy_servicer.CreateStrategy(create_request, grpc_context)
        strategy_id = create_response.strategy.id

        # Activate first
        await strategy_servicer.UpdateStrategyStatus(
            strategy_pb2.UpdateStrategyStatusRequest(
                context=ctx,
                strategy_id=strategy_id,
                status=strategy_pb2.STRATEGY_STATUS_ACTIVE,
            ),
            grpc_context,
        )

        # Pause
        response = await strategy_servicer.UpdateStrategyStatus(
            strategy_pb2.UpdateStrategyStatusRequest(
                context=ctx,
                strategy_id=strategy_id,
                status=strategy_pb2.STRATEGY_STATUS_PAUSED,
            ),
            grpc_context,
        )

        assert response.strategy.status == strategy_pb2.STRATEGY_STATUS_PAUSED

    async def test_delete_archives_strategy(
        self,
        auth_servicer,
        strategy_servicer,
        grpc_context: MockServicerContext,
        db_session: AsyncSession,
    ):
        """Test that delete soft-archives the strategy."""
        from llamatrade.v1 import common_pb2, strategy_pb2

        auth_info = await register_and_login(auth_servicer, grpc_context)
        ctx = create_tenant_context(auth_info["user_id"], auth_info["tenant_id"])

        # Create strategy
        create_request = strategy_pb2.CreateStrategyRequest(
            context=ctx,
            name="Deletable Strategy",
            dsl_code=VALID_STRATEGY_SEXPR,
        )
        create_response = await strategy_servicer.CreateStrategy(create_request, grpc_context)
        strategy_id = create_response.strategy.id

        # Delete
        delete_request = strategy_pb2.DeleteStrategyRequest(
            context=ctx,
            strategy_id=strategy_id,
        )
        delete_response = await strategy_servicer.DeleteStrategy(delete_request, grpc_context)

        assert delete_response.success is True

        # Strategy should not appear in default list (excludes archived)
        list_request = strategy_pb2.ListStrategiesRequest(
            context=ctx,
            pagination=common_pb2.PaginationRequest(page=1, page_size=20),
        )
        list_response = await strategy_servicer.ListStrategies(list_request, grpc_context)

        strategy_ids = [s.id for s in list_response.strategies]
        assert strategy_id not in strategy_ids


class TestStrategyValidation:
    """Test strategy validation endpoint."""

    async def test_validate_valid_config(
        self,
        strategy_servicer,
        grpc_context: MockServicerContext,
    ):
        """Test validating a valid strategy configuration."""
        from llamatrade.v1 import common_pb2, strategy_pb2

        request = strategy_pb2.CompileStrategyRequest(
            context=common_pb2.TenantContext(tenant_id="", user_id=""),
            dsl_code=VALID_STRATEGY_SEXPR,
            validate_only=True,
        )

        response = await strategy_servicer.CompileStrategy(request, grpc_context)

        assert response.result.success is True
        assert len(response.result.errors) == 0

    async def test_validate_invalid_config(
        self,
        strategy_servicer,
        grpc_context: MockServicerContext,
    ):
        """Test validating an invalid strategy configuration."""
        from llamatrade.v1 import common_pb2, strategy_pb2

        request = strategy_pb2.CompileStrategyRequest(
            context=common_pb2.TenantContext(tenant_id="", user_id=""),
            dsl_code="(strategy (missing required fields))",
            validate_only=True,
        )

        response = await strategy_servicer.CompileStrategy(request, grpc_context)

        assert response.result.success is False
        assert len(response.result.errors) > 0
