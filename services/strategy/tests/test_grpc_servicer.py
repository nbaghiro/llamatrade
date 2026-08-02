"""Tests for Strategy gRPC servicer methods."""

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from connectrpc.request import RequestContext

from llamatrade_db.models.strategy import Strategy, StrategyExecution, StrategyVersion
from llamatrade_proto.generated import common_pb2, strategy_pb2
from llamatrade_proto.generated.common_pb2 import (
    EXECUTION_MODE_PAPER,
    EXECUTION_STATUS_PAUSED,
    EXECUTION_STATUS_PENDING,
    EXECUTION_STATUS_RUNNING,
    EXECUTION_STATUS_STOPPED,
)
from llamatrade_proto.generated.strategy_pb2 import (
    STRATEGY_STATUS_ACTIVE,
    STRATEGY_STATUS_DRAFT,
    STRATEGY_STATUS_PAUSED,
)

from src.grpc.servicer import StrategyServicer

pytestmark = pytest.mark.asyncio

# Test UUIDs
TEST_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
TEST_USER_ID = UUID("22222222-2222-2222-2222-222222222222")
TEST_STRATEGY_ID = UUID("33333333-3333-3333-3333-333333333333")
NIL_UUID = UUID("00000000-0000-0000-0000-000000000000")


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


@pytest.fixture
def grpc_context() -> RequestContext:
    """Create a mock gRPC context."""
    return cast(RequestContext, MagicMock(spec=RequestContext))


class MockStrategyServicer(StrategyServicer):
    """Mock strategy servicer with injected database session for testing."""

    def __init__(self, mock_session: AsyncMock) -> None:
        super().__init__()
        self.mock_session = mock_session
        # Feed the mock session through the tenant_session/_maker path so the
        # RLS GUC set_config runs as a mocked no-op (no real DB connection).
        self._session_maker = lambda: mock_session


@pytest.fixture
def strategy_servicer() -> MockStrategyServicer:
    """Create a strategy servicer with mocked database."""
    # Mock the session factory
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.scalar = AsyncMock(return_value=0)  # plan-quota count: under limit

    return MockStrategyServicer(mock_session)


def _make_strategy_row(
    id: UUID,
    name: str,
    description: str,
    status: int,
    current_version: int,
) -> Strategy:
    now = datetime.now(UTC)
    return Strategy(
        id=id,
        tenant_id=TEST_TENANT_ID,
        name=name,
        description=description,
        status=int(status),
        current_version=current_version,
        created_by=TEST_USER_ID,
        created_at=now,
        updated_at=now,
    )


def make_strategy_response(
    id: UUID = TEST_STRATEGY_ID,
    name: str = "Test Strategy",
    description: str = "A test strategy",
    status: int = STRATEGY_STATUS_DRAFT,
    current_version: int = 1,
    config_sexpr: str = VALID_STRATEGY_SEXPR,
    symbols: list[str] | None = None,
    rebalance: str = "daily",
) -> tuple[Strategy, StrategyVersion]:
    """Build the (Strategy, current StrategyVersion) row pair the service returns."""
    strategy = _make_strategy_row(id, name, description, status, current_version)
    version = StrategyVersion(
        strategy_id=id,
        tenant_id=TEST_TENANT_ID,
        version=current_version,
        config_sexpr=config_sexpr,
        symbols=symbols or ["AAPL", "GOOGL"],
        rebalance=rebalance,
        created_by=TEST_USER_ID,
        created_at=strategy.created_at,
    )
    return strategy, version


def make_strategy_summary(
    id: UUID = TEST_STRATEGY_ID,
    name: str = "Test Strategy",
    description: str = "A test strategy",
    status: int = STRATEGY_STATUS_DRAFT,
    current_version: int = 1,
    symbols: list[str] | None = None,
    rebalance: str = "daily",
) -> tuple[Strategy, list[str], str]:
    """Build the (Strategy, symbols, rebalance) list row that list_strategies returns."""
    strategy = _make_strategy_row(id, name, description, status, current_version)
    return strategy, symbols or ["AAPL", "GOOGL"], rebalance


def make_execution(
    id: UUID,
    status: int,
    mode: int = EXECUTION_MODE_PAPER,
    started_at: datetime | None = None,
    stopped_at: datetime | None = None,
    error_message: str | None = None,
) -> StrategyExecution:
    """Build a StrategyExecution row as the execution service methods now return."""
    now = datetime.now(UTC)
    return StrategyExecution(
        id=id,
        tenant_id=TEST_TENANT_ID,
        strategy_id=TEST_STRATEGY_ID,
        version=1,
        mode=mode,
        status=status,
        config_override=None,
        error_message=error_message,
        started_at=started_at,
        stopped_at=stopped_at,
        created_at=now,
        updated_at=now,
    )


class TestTenantContextValidation:
    """Tests for tenant context validation."""

    async def test_create_strategy_requires_valid_tenant_context(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test that create_strategy requires valid tenant context."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        request = strategy_pb2.CreateStrategyRequest(
            context=common_pb2.TenantContext(
                tenant_id="",  # Empty
                user_id="",
            ),
            name="Test Strategy",
            dsl_code=VALID_STRATEGY_SEXPR,
        )

        with pytest.raises(ConnectError) as exc_info:
            await strategy_servicer.create_strategy(request, grpc_context)

        assert "UNAUTHENTICATED" in str(exc_info.value.code)

    async def test_create_strategy_rejects_nil_uuid(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test that create_strategy rejects nil UUIDs."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        request = strategy_pb2.CreateStrategyRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(NIL_UUID),
                user_id=str(NIL_UUID),
            ),
            name="Test Strategy",
            dsl_code=VALID_STRATEGY_SEXPR,
        )

        with pytest.raises(ConnectError) as exc_info:
            await strategy_servicer.create_strategy(request, grpc_context)

        assert "UNAUTHENTICATED" in str(exc_info.value.code)

    async def test_create_strategy_rejects_invalid_uuid(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test that create_strategy rejects invalid UUID format."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        request = strategy_pb2.CreateStrategyRequest(
            context=common_pb2.TenantContext(
                tenant_id="not-a-uuid",
                user_id="also-not-a-uuid",
            ),
            name="Test Strategy",
            dsl_code=VALID_STRATEGY_SEXPR,
        )

        with pytest.raises(ConnectError) as exc_info:
            await strategy_servicer.create_strategy(request, grpc_context)

        assert "INVALID_ARGUMENT" in str(exc_info.value.code)


class TestCreateStrategy:
    """Tests for create_strategy gRPC method."""

    async def test_create_strategy_success(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test creating a strategy successfully."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        mock_strategy = make_strategy_response()

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.create_strategy = AsyncMock(return_value=mock_strategy)

            request = strategy_pb2.CreateStrategyRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                name="My Strategy",
                description="A momentum strategy",
                dsl_code=VALID_STRATEGY_SEXPR,
            )

            response = await strategy_servicer.create_strategy(request, grpc_context)

            assert response.strategy.name == "Test Strategy"
            assert response.strategy.status == strategy_pb2.STRATEGY_STATUS_DRAFT
            mock_service.create_strategy.assert_called_once()

    async def test_create_strategy_invalid_config(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test creating a strategy with invalid config raises error."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.create_strategy = AsyncMock(
                side_effect=ValueError("Invalid config: missing entry condition")
            )

            request = strategy_pb2.CreateStrategyRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                name="Invalid Strategy",
                dsl_code="(strategy (missing entry))",
            )

            with pytest.raises(ConnectError) as exc_info:
                await strategy_servicer.create_strategy(request, grpc_context)

            assert "INVALID_ARGUMENT" in str(exc_info.value.code)


class TestGetStrategy:
    """Tests for get_strategy gRPC method."""

    async def test_get_strategy_success(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test getting a strategy by ID."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        mock_strategy = make_strategy_response()

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.get_strategy = AsyncMock(return_value=mock_strategy)

            request = strategy_pb2.GetStrategyRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                strategy_id=str(TEST_STRATEGY_ID),
            )

            response = await strategy_servicer.get_strategy(request, grpc_context)

            assert response.strategy.id == str(TEST_STRATEGY_ID)
            assert response.strategy.name == "Test Strategy"

    async def test_get_strategy_not_found(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test getting a nonexistent strategy returns NOT_FOUND."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.get_strategy = AsyncMock(return_value=None)

            request = strategy_pb2.GetStrategyRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                strategy_id=str(uuid4()),
            )

            with pytest.raises(ConnectError) as exc_info:
                await strategy_servicer.get_strategy(request, grpc_context)

            assert "NOT_FOUND" in str(exc_info.value.code)

    async def test_get_strategy_with_version(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test getting a specific version of a strategy."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        mock_strategy = make_strategy_response(current_version=2)
        mock_version = MagicMock()

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.get_strategy = AsyncMock(return_value=mock_strategy)
            mock_service.get_version = AsyncMock(return_value=mock_version)

            request = strategy_pb2.GetStrategyRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                strategy_id=str(TEST_STRATEGY_ID),
                version=2,
            )

            response = await strategy_servicer.get_strategy(request, grpc_context)

            assert response.strategy is not None
            mock_service.get_version.assert_called_once()


class TestListStrategies:
    """Tests for list_strategies gRPC method."""

    async def test_list_strategies_empty(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test listing strategies returns empty when none exist."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.list_strategies = AsyncMock(return_value=([], 0))

            request = strategy_pb2.ListStrategiesRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
            )

            response = await strategy_servicer.list_strategies(request, grpc_context)

            assert len(response.strategies) == 0
            assert response.pagination.total_items == 0

    async def test_list_strategies_with_data(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test listing strategies returns stored strategies."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        mock_strategies = [
            make_strategy_summary(id=uuid4(), name="Strategy 1"),
            make_strategy_summary(id=uuid4(), name="Strategy 2"),
        ]

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.list_strategies = AsyncMock(return_value=(mock_strategies, 2))

            request = strategy_pb2.ListStrategiesRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
            )

            response = await strategy_servicer.list_strategies(request, grpc_context)

            assert len(response.strategies) == 2
            assert response.pagination.total_items == 2

    async def test_list_strategies_pagination(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test pagination of strategies."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        mock_strategies = [make_strategy_summary()]

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.list_strategies = AsyncMock(return_value=(mock_strategies, 10))

            request = strategy_pb2.ListStrategiesRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                pagination=common_pb2.PaginationRequest(page=2, page_size=5),
            )

            response = await strategy_servicer.list_strategies(request, grpc_context)

            assert response.pagination.current_page == 2
            assert response.pagination.page_size == 5
            assert response.pagination.total_items == 10
            assert response.pagination.has_previous is True

    async def test_list_strategies_filter_by_status(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test filtering strategies by status."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        mock_strategies = [make_strategy_summary(status=STRATEGY_STATUS_ACTIVE)]

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.list_strategies = AsyncMock(return_value=(mock_strategies, 1))

            request = strategy_pb2.ListStrategiesRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                statuses=[strategy_pb2.STRATEGY_STATUS_ACTIVE],
            )

            response = await strategy_servicer.list_strategies(request, grpc_context)

            assert len(response.strategies) == 1
            assert mock_service.list_strategies.await_args.kwargs["status"] == (
                STRATEGY_STATUS_ACTIVE
            )

    async def test_list_strategies_without_a_status_filter_queries_every_status(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """An unset filter keeps its skip-the-filter meaning."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.list_strategies = AsyncMock(return_value=([], 0))

            request = strategy_pb2.ListStrategiesRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
            )

            await strategy_servicer.list_strategies(request, grpc_context)

            assert mock_service.list_strategies.await_args.kwargs["status"] is None

    @pytest.mark.parametrize("status", [0, 99])
    async def test_list_strategies_rejects_an_unspecified_or_unknown_status_filter(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext, status: int
    ) -> None:
        """An explicit UNSPECIFIED or an int outside the enum is INVALID_ARGUMENT, not a 500."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.list_strategies = AsyncMock(return_value=([], 0))

            request = strategy_pb2.ListStrategiesRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                statuses=[status],
            )

            with pytest.raises(ConnectError) as exc_info:
                await strategy_servicer.list_strategies(request, grpc_context)

            assert "INVALID_ARGUMENT" in str(exc_info.value.code)
            mock_service.list_strategies.assert_not_awaited()


class TestUpdateStrategy:
    """Tests for update_strategy gRPC method."""

    async def test_update_strategy_success(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test updating a strategy successfully."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        mock_strategy = make_strategy_response(name="Updated Strategy", current_version=2)

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.update_strategy = AsyncMock(return_value=mock_strategy)

            request = strategy_pb2.UpdateStrategyRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                strategy_id=str(TEST_STRATEGY_ID),
                name="Updated Strategy",
            )

            response = await strategy_servicer.update_strategy(request, grpc_context)

            assert response.strategy.name == "Updated Strategy"

    async def test_update_strategy_not_found(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test updating a nonexistent strategy returns NOT_FOUND."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.update_strategy = AsyncMock(return_value=None)

            request = strategy_pb2.UpdateStrategyRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                strategy_id=str(uuid4()),
                name="Updated Strategy",
            )

            with pytest.raises(ConnectError) as exc_info:
                await strategy_servicer.update_strategy(request, grpc_context)

            assert "NOT_FOUND" in str(exc_info.value.code)


class TestDeleteStrategy:
    """Tests for delete_strategy gRPC method."""

    async def test_delete_strategy_success(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test deleting a strategy successfully."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.delete_strategy = AsyncMock(return_value=True)

            request = strategy_pb2.DeleteStrategyRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                strategy_id=str(TEST_STRATEGY_ID),
            )

            response = await strategy_servicer.delete_strategy(request, grpc_context)

            assert response.success is True

    async def test_delete_strategy_not_found(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test deleting a nonexistent strategy returns NOT_FOUND."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.delete_strategy = AsyncMock(return_value=False)

            request = strategy_pb2.DeleteStrategyRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                strategy_id=str(uuid4()),
            )

            with pytest.raises(ConnectError) as exc_info:
                await strategy_servicer.delete_strategy(request, grpc_context)

            assert "NOT_FOUND" in str(exc_info.value.code)


class TestCompileStrategy:
    """Tests for compile_strategy gRPC method.

    Compilation is stateless: it resolves identity, bounds the input, and runs
    the real parser/serializer off the event loop (no DB session, no service).
    """

    # A parseable allocation strategy in the current DSL.
    VALID_SEXPR = '(strategy "Test" (weight :method equal (asset SPY) (asset AGG)))'

    def _request(
        self, dsl_code: str, *, tenant: str = str(TEST_TENANT_ID), user: str = str(TEST_USER_ID)
    ) -> strategy_pb2.CompileStrategyRequest:
        return strategy_pb2.CompileStrategyRequest(
            context=common_pb2.TenantContext(tenant_id=tenant, user_id=user),
            dsl_code=dsl_code,
        )

    async def test_compile_strategy_valid(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """A valid strategy compiles to JSON with no errors."""
        response = await strategy_servicer.compile_strategy(
            self._request(self.VALID_SEXPR), grpc_context
        )

        assert response.result.success is True
        assert len(response.result.errors) == 0
        assert response.result.compiled_json != ""

    async def test_compile_strategy_invalid(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Unparseable/invalid DSL reports failure with structured errors."""
        response = await strategy_servicer.compile_strategy(
            self._request("(strategy (invalid))"), grpc_context
        )

        assert response.result.success is False
        assert len(response.result.errors) > 0

    async def test_compile_strategy_surfaces_compile_error(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Valid DSL that fails to serialize reports an error, not silent success."""
        with patch("src.services.strategy_service.to_json", side_effect=RuntimeError("boom")):
            response = await strategy_servicer.compile_strategy(
                self._request(self.VALID_SEXPR), grpc_context
            )

        assert response.result.success is False
        assert response.result.compiled_json == ""
        assert any(e.code == "COMPILE_ERROR" for e in response.result.errors)

    async def test_compile_strategy_rejects_oversized_input(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """DSL longer than the cap is rejected before parsing."""
        from src.models import MAX_SEXPR_LEN

        with pytest.raises(ConnectError) as exc:
            await strategy_servicer.compile_strategy(
                self._request("x" * (MAX_SEXPR_LEN + 1)), grpc_context
            )
        assert exc.value.code == Code.INVALID_ARGUMENT

    async def test_compile_strategy_requires_identity(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """An empty tenant context is rejected (compile still requires auth)."""
        with pytest.raises(ConnectError) as exc:
            await strategy_servicer.compile_strategy(
                self._request(self.VALID_SEXPR, tenant="", user=""), grpc_context
            )
        assert exc.value.code == Code.UNAUTHENTICATED


class TestUpdateStrategyStatus:
    """Tests for update_strategy_status gRPC method."""

    async def test_activate_strategy(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test activating a strategy."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        mock_strategy = make_strategy_response(status=STRATEGY_STATUS_ACTIVE)

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.activate_strategy = AsyncMock(return_value=mock_strategy)
            mock_service.get_strategy = AsyncMock(return_value=mock_strategy)

            request = strategy_pb2.UpdateStrategyStatusRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                strategy_id=str(TEST_STRATEGY_ID),
                status=strategy_pb2.STRATEGY_STATUS_ACTIVE,
            )

            response = await strategy_servicer.update_strategy_status(request, grpc_context)

            assert response.strategy.status == strategy_pb2.STRATEGY_STATUS_ACTIVE
            mock_service.activate_strategy.assert_called_once()

    async def test_pause_strategy(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test pausing a strategy."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        mock_strategy = make_strategy_response(status=STRATEGY_STATUS_PAUSED)

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.pause_strategy = AsyncMock(return_value=mock_strategy)
            mock_service.get_strategy = AsyncMock(return_value=mock_strategy)

            request = strategy_pb2.UpdateStrategyStatusRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                strategy_id=str(TEST_STRATEGY_ID),
                status=strategy_pb2.STRATEGY_STATUS_PAUSED,
            )

            response = await strategy_servicer.update_strategy_status(request, grpc_context)

            assert response.strategy.status == strategy_pb2.STRATEGY_STATUS_PAUSED
            mock_service.pause_strategy.assert_called_once()


class TestListStrategyVersions:
    """Tests for list_strategy_versions gRPC method."""

    async def test_list_versions_success(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test listing strategy versions."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        now = datetime.now(UTC)
        mock_versions = [
            StrategyVersion(
                strategy_id=TEST_STRATEGY_ID,
                tenant_id=TEST_TENANT_ID,
                version=1,
                config_sexpr=VALID_STRATEGY_SEXPR,
                symbols=["AAPL"],
                rebalance="daily",
                changelog="Initial version",
                created_by=TEST_USER_ID,
                created_at=now,
            ),
            StrategyVersion(
                strategy_id=TEST_STRATEGY_ID,
                tenant_id=TEST_TENANT_ID,
                version=2,
                config_sexpr=VALID_STRATEGY_SEXPR,
                symbols=["AAPL"],
                rebalance="daily",
                changelog="Updated entry condition",
                created_by=TEST_USER_ID,
                created_at=now,
            ),
        ]

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.list_versions = AsyncMock(return_value=mock_versions)

            request = strategy_pb2.ListStrategyVersionsRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                strategy_id=str(TEST_STRATEGY_ID),
            )

            response = await strategy_servicer.list_strategy_versions(request, grpc_context)

            assert len(response.versions) == 2
            assert response.versions[0].version == 1
            assert response.versions[1].version == 2


class TestCloneStrategy:
    """Tests for clone_strategy gRPC method."""

    async def test_clone_strategy_success(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test cloning a strategy successfully."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        mock_strategy = make_strategy_response(name="Cloned Strategy")

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.clone_strategy = AsyncMock(return_value=mock_strategy)

            request = strategy_pb2.CloneStrategyRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                strategy_id=str(TEST_STRATEGY_ID),
                new_name="Cloned Strategy",
            )

            response = await strategy_servicer.clone_strategy(request, grpc_context)

            assert response.strategy.name == "Cloned Strategy"
            mock_service.clone_strategy.assert_called_once()

    async def test_clone_strategy_not_found(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test cloning a strategy that doesn't exist."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.clone_strategy = AsyncMock(return_value=None)

            request = strategy_pb2.CloneStrategyRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                strategy_id=str(TEST_STRATEGY_ID),
                new_name="Cloned Strategy",
            )

            with pytest.raises(ConnectError) as exc_info:
                await strategy_servicer.clone_strategy(request, grpc_context)

            assert "NOT_FOUND" in str(exc_info.value.code)

    async def test_clone_strategy_requires_new_name(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test that cloning requires a new name."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        request = strategy_pb2.CloneStrategyRequest(
            context=common_pb2.TenantContext(
                tenant_id=str(TEST_TENANT_ID),
                user_id=str(TEST_USER_ID),
            ),
            strategy_id=str(TEST_STRATEGY_ID),
            new_name="",  # Empty name
        )

        with pytest.raises(ConnectError) as exc_info:
            await strategy_servicer.clone_strategy(request, grpc_context)

        assert "INVALID_ARGUMENT" in str(exc_info.value.code)


class TestExecutionManagement:
    """Tests for execution management gRPC methods."""

    async def test_create_execution_success(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test creating an execution successfully."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        mock_execution = make_execution(uuid4(), EXECUTION_STATUS_PENDING)

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.create_execution = AsyncMock(return_value=mock_execution)

            request = strategy_pb2.CreateExecutionRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                strategy_id=str(TEST_STRATEGY_ID),
                mode=common_pb2.EXECUTION_MODE_PAPER,
            )

            response = await strategy_servicer.create_execution(request, grpc_context)

            assert response.execution.strategy_id == str(TEST_STRATEGY_ID)
            assert response.execution.mode == common_pb2.EXECUTION_MODE_PAPER
            assert response.execution.status == common_pb2.EXECUTION_STATUS_PENDING

    async def test_get_execution_success(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test getting an execution by ID."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        execution_id = uuid4()
        mock_execution = make_execution(
            execution_id, EXECUTION_STATUS_RUNNING, started_at=datetime.now(UTC)
        )

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.get_execution = AsyncMock(return_value=mock_execution)

            request = strategy_pb2.GetExecutionRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                execution_id=str(execution_id),
            )

            response = await strategy_servicer.get_execution(request, grpc_context)

            assert response.execution.id == str(execution_id)
            assert response.execution.status == common_pb2.EXECUTION_STATUS_RUNNING

    async def test_get_execution_not_found(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test getting a non-existent execution."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.get_execution = AsyncMock(return_value=None)

            request = strategy_pb2.GetExecutionRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                execution_id=str(uuid4()),
            )

            with pytest.raises(ConnectError) as exc_info:
                await strategy_servicer.get_execution(request, grpc_context)

            assert "NOT_FOUND" in str(exc_info.value.code)

    async def test_list_executions_success(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test listing executions."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        mock_executions = [
            make_execution(uuid4(), EXECUTION_STATUS_RUNNING, started_at=datetime.now(UTC)),
        ]

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.list_executions = AsyncMock(return_value=(mock_executions, 1))

            request = strategy_pb2.ListExecutionsRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                strategy_id=str(TEST_STRATEGY_ID),
            )

            response = await strategy_servicer.list_executions(request, grpc_context)

            assert len(response.executions) == 1
            assert response.pagination.total_items == 1
            assert mock_service.list_executions.await_args.kwargs["status"] is None
            assert mock_service.list_executions.await_args.kwargs["mode"] is None

    async def test_list_executions_applies_valid_status_and_mode_filters(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test filtering executions by status and mode."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.list_executions = AsyncMock(return_value=([], 0))

            request = strategy_pb2.ListExecutionsRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                statuses=[EXECUTION_STATUS_RUNNING],
                modes=[EXECUTION_MODE_PAPER],
            )

            await strategy_servicer.list_executions(request, grpc_context)

            assert mock_service.list_executions.await_args.kwargs["status"] == (
                EXECUTION_STATUS_RUNNING
            )
            assert mock_service.list_executions.await_args.kwargs["mode"] == EXECUTION_MODE_PAPER

    @pytest.mark.parametrize(("statuses", "modes"), [([0], []), ([99], []), ([], [0]), ([], [42])])
    async def test_list_executions_rejects_an_unspecified_or_unknown_filter(
        self,
        strategy_servicer: MockStrategyServicer,
        grpc_context: RequestContext,
        statuses: list[int],
        modes: list[int],
    ) -> None:
        """An explicit UNSPECIFIED or an int outside the enum is INVALID_ARGUMENT, not a 500."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.list_executions = AsyncMock(return_value=([], 0))

            request = strategy_pb2.ListExecutionsRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                statuses=statuses,
                modes=modes,
            )

            with pytest.raises(ConnectError) as exc_info:
                await strategy_servicer.list_executions(request, grpc_context)

            assert "INVALID_ARGUMENT" in str(exc_info.value.code)
            mock_service.list_executions.assert_not_awaited()

    async def test_start_execution_success(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test starting a pending execution."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        execution_id = uuid4()
        mock_execution = make_execution(
            execution_id, EXECUTION_STATUS_RUNNING, started_at=datetime.now(UTC)
        )

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.start_execution = AsyncMock(return_value=mock_execution)

            request = strategy_pb2.StartExecutionRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                execution_id=str(execution_id),
            )

            response = await strategy_servicer.start_execution(request, grpc_context)

            assert response.execution.status == common_pb2.EXECUTION_STATUS_RUNNING
            assert response.execution.started_at.seconds > 0

    async def test_start_execution_over_plan_limit(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Reject with RESOURCE_EXHAUSTED when the live-strategy limit is reached."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        # Running count == free-tier limit (1) -> at quota -> rejected before start.
        strategy_servicer.mock_session.scalar = AsyncMock(return_value=1)

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.start_execution = AsyncMock()

            request = strategy_pb2.StartExecutionRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                execution_id=str(uuid4()),
            )

            with pytest.raises(ConnectError) as exc_info:
                await strategy_servicer.start_execution(request, grpc_context)

            assert "RESOURCE_EXHAUSTED" in str(exc_info.value.code)
            mock_service.start_execution.assert_not_awaited()

    async def test_start_execution_invalid_state(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test starting an execution that's not pending."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.start_execution = AsyncMock(
                side_effect=ValueError("Cannot start: status is running")
            )

            request = strategy_pb2.StartExecutionRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                execution_id=str(uuid4()),
            )

            with pytest.raises(ConnectError) as exc_info:
                await strategy_servicer.start_execution(request, grpc_context)

            assert "FAILED_PRECONDITION" in str(exc_info.value.code)

    async def test_pause_execution_success(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test pausing a running execution."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        execution_id = uuid4()
        mock_execution = make_execution(
            execution_id, EXECUTION_STATUS_PAUSED, started_at=datetime.now(UTC)
        )

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.pause_execution = AsyncMock(return_value=mock_execution)

            request = strategy_pb2.PauseExecutionRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                execution_id=str(execution_id),
            )

            response = await strategy_servicer.pause_execution(request, grpc_context)

            assert response.execution.status == common_pb2.EXECUTION_STATUS_PAUSED

    async def test_stop_execution_success(
        self, strategy_servicer: MockStrategyServicer, grpc_context: RequestContext
    ) -> None:
        """Test stopping an execution."""
        from llamatrade_proto.generated import common_pb2, strategy_pb2

        execution_id = uuid4()
        mock_execution = make_execution(
            execution_id,
            EXECUTION_STATUS_STOPPED,
            started_at=datetime.now(UTC),
            stopped_at=datetime.now(UTC),
            error_message="Stopped: User requested stop",
        )

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.stop_execution = AsyncMock(return_value=mock_execution)

            request = strategy_pb2.StopExecutionRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                execution_id=str(execution_id),
                reason="User requested stop",
            )

            response = await strategy_servicer.stop_execution(request, grpc_context)

            assert response.execution.status == common_pb2.EXECUTION_STATUS_STOPPED
            assert response.execution.stopped_at.seconds > 0
