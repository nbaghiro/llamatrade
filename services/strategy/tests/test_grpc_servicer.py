"""Tests for Strategy gRPC servicer methods."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from connectrpc.errors import ConnectError

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


class MockServicerContext:
    """Mock Connect servicer context for testing."""

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}


@pytest.fixture
def grpc_context() -> MockServicerContext:
    """Create a mock gRPC context."""
    return MockServicerContext()


@pytest.fixture
def strategy_servicer():
    """Create a strategy servicer with mocked database."""
    from src.grpc.servicer import StrategyServicer

    servicer = StrategyServicer()

    # Mock the session factory
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    async def mock_get_db():
        return mock_session

    servicer._get_db = mock_get_db
    servicer._mock_session = mock_session

    return servicer


def make_strategy_response(
    id: UUID = TEST_STRATEGY_ID,
    name: str = "Test Strategy",
    description: str = "A test strategy",
    status: str = "draft",
    strategy_type: str = "momentum",
    current_version: int = 1,
    config_sexpr: str = VALID_STRATEGY_SEXPR,
    config_json: dict = None,
    symbols: list = None,
    timeframe: str = "1D",
) -> MagicMock:
    """Create a mock strategy detail response."""
    from src.models import StrategyDetailResponse, StrategyStatus, StrategyType

    return StrategyDetailResponse(
        id=id,
        name=name,
        description=description,
        status=StrategyStatus(status),
        strategy_type=StrategyType(strategy_type) if strategy_type else StrategyType.CUSTOM,
        current_version=current_version,
        config_sexpr=config_sexpr,
        config_json=config_json or {},
        symbols=symbols or ["AAPL", "GOOGL"],
        timeframe=timeframe,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def make_strategy_summary(
    id: UUID = TEST_STRATEGY_ID,
    name: str = "Test Strategy",
    description: str = "A test strategy",
    status: str = "draft",
    strategy_type: str = "momentum",
    current_version: int = 1,
) -> MagicMock:
    """Create a mock strategy summary response."""
    from src.models import StrategyResponse, StrategyStatus, StrategyType

    return StrategyResponse(
        id=id,
        name=name,
        description=description,
        status=StrategyStatus(status),
        strategy_type=StrategyType(strategy_type) if strategy_type else StrategyType.CUSTOM,
        current_version=current_version,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


class TestTenantContextValidation:
    """Tests for tenant context validation."""

    async def test_create_strategy_requires_valid_tenant_context(
        self, strategy_servicer, grpc_context
    ):
        """Test that create_strategy requires valid tenant context."""
        from llamatrade.v1 import common_pb2, strategy_pb2

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

    async def test_create_strategy_rejects_nil_uuid(self, strategy_servicer, grpc_context):
        """Test that create_strategy rejects nil UUIDs."""
        from llamatrade.v1 import common_pb2, strategy_pb2

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

    async def test_create_strategy_rejects_invalid_uuid(self, strategy_servicer, grpc_context):
        """Test that create_strategy rejects invalid UUID format."""
        from llamatrade.v1 import common_pb2, strategy_pb2

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

    async def test_create_strategy_success(self, strategy_servicer, grpc_context):
        """Test creating a strategy successfully."""
        from llamatrade.v1 import common_pb2, strategy_pb2

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

    async def test_create_strategy_invalid_config(self, strategy_servicer, grpc_context):
        """Test creating a strategy with invalid config raises error."""
        from llamatrade.v1 import common_pb2, strategy_pb2

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

    async def test_get_strategy_success(self, strategy_servicer, grpc_context):
        """Test getting a strategy by ID."""
        from llamatrade.v1 import common_pb2, strategy_pb2

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

    async def test_get_strategy_not_found(self, strategy_servicer, grpc_context):
        """Test getting a nonexistent strategy returns NOT_FOUND."""
        from llamatrade.v1 import common_pb2, strategy_pb2

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

    async def test_get_strategy_with_version(self, strategy_servicer, grpc_context):
        """Test getting a specific version of a strategy."""
        from llamatrade.v1 import common_pb2, strategy_pb2

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

    async def test_list_strategies_empty(self, strategy_servicer, grpc_context):
        """Test listing strategies returns empty when none exist."""
        from llamatrade.v1 import common_pb2, strategy_pb2

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

    async def test_list_strategies_with_data(self, strategy_servicer, grpc_context):
        """Test listing strategies returns stored strategies."""
        from llamatrade.v1 import common_pb2, strategy_pb2

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

    async def test_list_strategies_pagination(self, strategy_servicer, grpc_context):
        """Test pagination of strategies."""
        from llamatrade.v1 import common_pb2, strategy_pb2

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

    async def test_list_strategies_filter_by_status(self, strategy_servicer, grpc_context):
        """Test filtering strategies by status."""
        from llamatrade.v1 import common_pb2, strategy_pb2

        mock_strategies = [make_strategy_summary(status="active")]

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


class TestUpdateStrategy:
    """Tests for update_strategy gRPC method."""

    async def test_update_strategy_success(self, strategy_servicer, grpc_context):
        """Test updating a strategy successfully."""
        from llamatrade.v1 import common_pb2, strategy_pb2

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

    async def test_update_strategy_not_found(self, strategy_servicer, grpc_context):
        """Test updating a nonexistent strategy returns NOT_FOUND."""
        from llamatrade.v1 import common_pb2, strategy_pb2

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

    async def test_delete_strategy_success(self, strategy_servicer, grpc_context):
        """Test deleting a strategy successfully."""
        from llamatrade.v1 import common_pb2, strategy_pb2

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

    async def test_delete_strategy_not_found(self, strategy_servicer, grpc_context):
        """Test deleting a nonexistent strategy returns NOT_FOUND."""
        from llamatrade.v1 import common_pb2, strategy_pb2

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
    """Tests for compile_strategy gRPC method."""

    async def test_compile_strategy_valid(self, strategy_servicer, grpc_context):
        """Test compiling a valid strategy."""
        from llamatrade.v1 import common_pb2, strategy_pb2
        from src.models import ValidationResult

        mock_validation = ValidationResult(valid=True, errors=[], warnings=[])

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.validate_config = AsyncMock(return_value=mock_validation)

            request = strategy_pb2.CompileStrategyRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                dsl_code=VALID_STRATEGY_SEXPR,
            )

            response = await strategy_servicer.compile_strategy(request, grpc_context)

            assert response.result.success is True
            assert len(response.result.errors) == 0

    async def test_compile_strategy_invalid(self, strategy_servicer, grpc_context):
        """Test compiling an invalid strategy."""
        from llamatrade.v1 import common_pb2, strategy_pb2
        from src.models import ValidationResult

        mock_validation = ValidationResult(
            valid=False,
            errors=["Missing entry condition"],
            warnings=[],
        )

        with patch("src.services.strategy_service.StrategyService") as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.validate_config = AsyncMock(return_value=mock_validation)

            request = strategy_pb2.CompileStrategyRequest(
                context=common_pb2.TenantContext(
                    tenant_id=str(TEST_TENANT_ID),
                    user_id=str(TEST_USER_ID),
                ),
                dsl_code="(strategy (invalid))",
            )

            response = await strategy_servicer.compile_strategy(request, grpc_context)

            assert response.result.success is False
            assert len(response.result.errors) > 0


class TestUpdateStrategyStatus:
    """Tests for update_strategy_status gRPC method."""

    async def test_activate_strategy(self, strategy_servicer, grpc_context):
        """Test activating a strategy."""
        from llamatrade.v1 import common_pb2, strategy_pb2

        mock_strategy = make_strategy_response(status="active")

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

    async def test_pause_strategy(self, strategy_servicer, grpc_context):
        """Test pausing a strategy."""
        from llamatrade.v1 import common_pb2, strategy_pb2

        mock_strategy = make_strategy_response(status="paused")

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

    async def test_list_versions_success(self, strategy_servicer, grpc_context):
        """Test listing strategy versions."""
        from llamatrade.v1 import common_pb2, strategy_pb2
        from src.models import StrategyVersionResponse

        mock_versions = [
            StrategyVersionResponse(
                version=1,
                config_sexpr=VALID_STRATEGY_SEXPR,
                config_json={},
                symbols=["AAPL"],
                timeframe="1D",
                changelog="Initial version",
                created_at=datetime.now(UTC),
            ),
            StrategyVersionResponse(
                version=2,
                config_sexpr=VALID_STRATEGY_SEXPR,
                config_json={},
                symbols=["AAPL"],
                timeframe="1D",
                changelog="Updated entry condition",
                created_at=datetime.now(UTC),
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
