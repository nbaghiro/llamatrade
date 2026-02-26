"""Integration tests for strategies router with mocked service."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from llamatrade_common.middleware import require_auth
from llamatrade_common.models import TenantContext
from src.main import app
from src.models import (
    DeploymentEnvironment,
    DeploymentStatus,
    StrategyDetailResponse,
    StrategyResponse,
    StrategyStatus,
    StrategyType,
    StrategyVersionResponse,
    ValidationResult,
)
from src.services.strategy_service import StrategyService, get_strategy_service

# Sample S-expression for tests
VALID_RSI_STRATEGY = """(strategy
  :name "RSI Mean Reversion"
  :type mean_reversion
  :symbols ["AAPL" "MSFT"]
  :timeframe "1D"
  :entry (< (rsi close 14) 30)
  :exit (> (rsi close 14) 70)
  :stop-loss-pct 2.0
  :take-profit-pct 6.0)"""


def make_auth_context(tenant_id, user_id):
    """Create a mock TenantContext for auth override."""
    return TenantContext(
        tenant_id=tenant_id,
        user_id=user_id,
        email="test@example.com",
        roles=["admin"],
    )


# ===================
# Test Fixtures
# ===================


@pytest.fixture
def tenant_id():
    return uuid4()


@pytest.fixture
def user_id():
    return uuid4()


@pytest.fixture
def strategy_id():
    return uuid4()


@pytest.fixture
def mock_strategy_service():
    """Create mock strategy service."""
    return AsyncMock(spec=StrategyService)


@pytest.fixture
async def authenticated_client(tenant_id, user_id, mock_strategy_service):
    """Create HTTP client with auth and service mocks."""
    # Override auth to return mock context
    ctx = make_auth_context(tenant_id, user_id)
    app.dependency_overrides[require_auth] = lambda: ctx
    app.dependency_overrides[get_strategy_service] = lambda: mock_strategy_service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ===================
# Create Strategy Tests
# ===================


class TestCreateStrategyEndpoint:
    """Tests for POST /strategies."""

    async def test_create_strategy_success(
        self, authenticated_client, mock_strategy_service, tenant_id, user_id
    ):
        """Test creating a strategy via API."""
        from datetime import datetime

        mock_response = StrategyDetailResponse(
            id=uuid4(),
            name="Test Strategy",
            description="A test",
            strategy_type=StrategyType.MEAN_REVERSION,
            status=StrategyStatus.DRAFT,
            current_version=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            config_sexpr=VALID_RSI_STRATEGY,
            config_json={"name": "Test"},
            symbols=["AAPL", "MSFT"],
            timeframe="1D",
        )
        mock_strategy_service.create_strategy.return_value = mock_response

        response = await authenticated_client.post(
            "/strategies",
            json={
                "name": "Test Strategy",
                "description": "A test",
                "config_sexpr": VALID_RSI_STRATEGY,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Strategy"
        assert data["strategy_type"] == "mean_reversion"
        mock_strategy_service.create_strategy.assert_called_once()

    async def test_create_strategy_validation_error(
        self, authenticated_client, mock_strategy_service
    ):
        """Test creating with invalid config returns 400."""
        mock_strategy_service.create_strategy.side_effect = ValueError(
            "Invalid strategy: missing :entry"
        )

        response = await authenticated_client.post(
            "/strategies",
            json={
                "name": "Bad Strategy",
                "config_sexpr": '(strategy :name "broken")',
            },
        )

        assert response.status_code == 400
        assert "Invalid strategy" in response.json()["detail"]

    async def test_create_strategy_missing_name(self, authenticated_client):
        """Test creating without name returns 422."""
        response = await authenticated_client.post(
            "/strategies",
            json={
                "config_sexpr": VALID_RSI_STRATEGY,
            },
        )

        assert response.status_code == 422


# ===================
# Get Strategy Tests
# ===================


class TestGetStrategyEndpoint:
    """Tests for GET /strategies/{strategy_id}."""

    async def test_get_strategy_found(
        self, authenticated_client, mock_strategy_service, strategy_id
    ):
        """Test getting an existing strategy."""
        from datetime import datetime

        mock_response = StrategyDetailResponse(
            id=strategy_id,
            name="Test Strategy",
            description=None,
            strategy_type=StrategyType.MEAN_REVERSION,
            status=StrategyStatus.DRAFT,
            current_version=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            config_sexpr=VALID_RSI_STRATEGY,
            config_json={},
            symbols=["AAPL"],
            timeframe="1D",
        )
        mock_strategy_service.get_strategy.return_value = mock_response

        response = await authenticated_client.get(f"/strategies/{strategy_id}")

        assert response.status_code == 200
        assert response.json()["id"] == str(strategy_id)

    async def test_get_strategy_not_found(self, authenticated_client, mock_strategy_service):
        """Test getting non-existent strategy returns 404."""
        mock_strategy_service.get_strategy.return_value = None

        response = await authenticated_client.get(f"/strategies/{uuid4()}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# ===================
# List Strategies Tests
# ===================


class TestListStrategiesEndpoint:
    """Tests for GET /strategies."""

    async def test_list_strategies_empty(self, authenticated_client, mock_strategy_service):
        """Test listing returns empty list when no strategies."""
        mock_strategy_service.list_strategies.return_value = ([], 0)

        response = await authenticated_client.get("/strategies")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_list_strategies_with_pagination(
        self, authenticated_client, mock_strategy_service
    ):
        """Test listing with pagination params."""
        from datetime import datetime

        mock_strategies = [
            StrategyResponse(
                id=uuid4(),
                name=f"Strategy {i}",
                description=None,
                strategy_type=StrategyType.CUSTOM,
                status=StrategyStatus.DRAFT,
                current_version=1,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            for i in range(3)
        ]
        mock_strategy_service.list_strategies.return_value = (mock_strategies, 3)

        response = await authenticated_client.get("/strategies?page=1&page_size=10")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3
        assert data["total"] == 3
        assert data["page"] == 1

    async def test_list_strategies_filter_by_status(
        self, authenticated_client, mock_strategy_service
    ):
        """Test filtering by status."""
        mock_strategy_service.list_strategies.return_value = ([], 0)

        response = await authenticated_client.get("/strategies?status=active")

        assert response.status_code == 200
        # Verify filter was passed to service
        call_kwargs = mock_strategy_service.list_strategies.call_args.kwargs
        assert call_kwargs.get("status") == StrategyStatus.ACTIVE


# ===================
# Update Strategy Tests
# ===================


class TestUpdateStrategyEndpoint:
    """Tests for PATCH /strategies/{strategy_id}."""

    async def test_update_strategy_success(
        self, authenticated_client, mock_strategy_service, strategy_id
    ):
        """Test updating a strategy."""
        from datetime import datetime

        mock_response = StrategyDetailResponse(
            id=strategy_id,
            name="Updated Name",
            description=None,
            strategy_type=StrategyType.MEAN_REVERSION,
            status=StrategyStatus.DRAFT,
            current_version=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            config_sexpr=VALID_RSI_STRATEGY,
            config_json={},
            symbols=["AAPL"],
            timeframe="1D",
        )
        mock_strategy_service.update_strategy.return_value = mock_response

        response = await authenticated_client.patch(
            f"/strategies/{strategy_id}",
            json={"name": "Updated Name"},
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"

    async def test_update_strategy_not_found(self, authenticated_client, mock_strategy_service):
        """Test updating non-existent strategy returns 404."""
        mock_strategy_service.update_strategy.return_value = None

        response = await authenticated_client.patch(
            f"/strategies/{uuid4()}",
            json={"name": "New Name"},
        )

        assert response.status_code == 404


# ===================
# Delete Strategy Tests
# ===================


class TestDeleteStrategyEndpoint:
    """Tests for DELETE /strategies/{strategy_id}."""

    async def test_delete_strategy_success(
        self, authenticated_client, mock_strategy_service, strategy_id
    ):
        """Test deleting a strategy."""
        mock_strategy_service.delete_strategy.return_value = True

        response = await authenticated_client.delete(f"/strategies/{strategy_id}")

        assert response.status_code == 204

    async def test_delete_strategy_not_found(self, authenticated_client, mock_strategy_service):
        """Test deleting non-existent strategy returns 404."""
        mock_strategy_service.delete_strategy.return_value = False

        response = await authenticated_client.delete(f"/strategies/{uuid4()}")

        assert response.status_code == 404


# ===================
# Status Endpoints Tests
# ===================


class TestStatusEndpoints:
    """Tests for activate and pause endpoints."""

    async def test_activate_strategy(
        self, authenticated_client, mock_strategy_service, strategy_id
    ):
        """Test activating a strategy."""
        from datetime import datetime

        mock_response = StrategyResponse(
            id=strategy_id,
            name="Test",
            description=None,
            strategy_type=StrategyType.CUSTOM,
            status=StrategyStatus.ACTIVE,
            current_version=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        mock_strategy_service.activate_strategy.return_value = mock_response

        response = await authenticated_client.post(f"/strategies/{strategy_id}/activate")

        assert response.status_code == 200
        assert response.json()["status"] == "active"

    async def test_pause_strategy(self, authenticated_client, mock_strategy_service, strategy_id):
        """Test pausing a strategy."""
        from datetime import datetime

        mock_response = StrategyResponse(
            id=strategy_id,
            name="Test",
            description=None,
            strategy_type=StrategyType.CUSTOM,
            status=StrategyStatus.PAUSED,
            current_version=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        mock_strategy_service.pause_strategy.return_value = mock_response

        response = await authenticated_client.post(f"/strategies/{strategy_id}/pause")

        assert response.status_code == 200
        assert response.json()["status"] == "paused"


# ===================
# Version Endpoints Tests
# ===================


class TestVersionEndpoints:
    """Tests for version listing and retrieval."""

    async def test_list_versions(self, authenticated_client, mock_strategy_service, strategy_id):
        """Test listing strategy versions."""
        from datetime import datetime

        mock_versions = [
            StrategyVersionResponse(
                version=2,
                config_sexpr=VALID_RSI_STRATEGY,
                config_json={},
                symbols=["AAPL"],
                timeframe="1D",
                changelog="Updated entry logic",
                created_at=datetime.utcnow(),
            ),
            StrategyVersionResponse(
                version=1,
                config_sexpr=VALID_RSI_STRATEGY,
                config_json={},
                symbols=["AAPL"],
                timeframe="1D",
                changelog=None,
                created_at=datetime.utcnow(),
            ),
        ]
        mock_strategy_service.list_versions.return_value = mock_versions

        response = await authenticated_client.get(f"/strategies/{strategy_id}/versions")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["version"] == 2

    async def test_get_version(self, authenticated_client, mock_strategy_service, strategy_id):
        """Test getting specific version."""
        from datetime import datetime

        mock_version = StrategyVersionResponse(
            version=1,
            config_sexpr=VALID_RSI_STRATEGY,
            config_json={},
            symbols=["AAPL"],
            timeframe="1D",
            changelog=None,
            created_at=datetime.utcnow(),
        )
        mock_strategy_service.get_version.return_value = mock_version

        response = await authenticated_client.get(f"/strategies/{strategy_id}/versions/1")

        assert response.status_code == 200
        assert response.json()["version"] == 1

    async def test_get_version_not_found(
        self, authenticated_client, mock_strategy_service, strategy_id
    ):
        """Test getting non-existent version returns 404."""
        mock_strategy_service.get_version.return_value = None

        response = await authenticated_client.get(f"/strategies/{strategy_id}/versions/999")

        assert response.status_code == 404


# ===================
# Clone Endpoint Tests
# ===================


class TestCloneEndpoint:
    """Tests for strategy cloning."""

    async def test_clone_strategy(self, authenticated_client, mock_strategy_service, strategy_id):
        """Test cloning a strategy."""
        from datetime import datetime

        mock_response = StrategyDetailResponse(
            id=uuid4(),
            name="Cloned Strategy",
            description="Cloned from: Original",
            strategy_type=StrategyType.MEAN_REVERSION,
            status=StrategyStatus.DRAFT,
            current_version=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            config_sexpr=VALID_RSI_STRATEGY,
            config_json={},
            symbols=["AAPL"],
            timeframe="1D",
        )
        mock_strategy_service.clone_strategy.return_value = mock_response

        response = await authenticated_client.post(
            f"/strategies/{strategy_id}/clone?name=Cloned+Strategy"
        )

        assert response.status_code == 201
        assert response.json()["name"] == "Cloned Strategy"

    async def test_clone_strategy_not_found(self, authenticated_client, mock_strategy_service):
        """Test cloning non-existent strategy returns 404."""
        mock_strategy_service.clone_strategy.return_value = None

        response = await authenticated_client.post(f"/strategies/{uuid4()}/clone?name=Clone")

        assert response.status_code == 404


# ===================
# Validate Endpoint Tests
# ===================


class TestValidateEndpoint:
    """Tests for config validation."""

    async def test_validate_valid_config(self, authenticated_client, mock_strategy_service):
        """Test validating valid config."""
        mock_strategy_service.validate_config.return_value = ValidationResult(
            valid=True,
            errors=[],
            warnings=[],
        )

        response = await authenticated_client.post(
            "/strategies/validate",
            params={"config_sexpr": VALID_RSI_STRATEGY},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["errors"] == []

    async def test_validate_invalid_config(self, authenticated_client, mock_strategy_service):
        """Test validating invalid config."""
        mock_strategy_service.validate_config.return_value = ValidationResult(
            valid=False,
            errors=["Missing :entry clause"],
            warnings=[],
        )

        response = await authenticated_client.post(
            "/strategies/validate",
            params={"config_sexpr": '(strategy :name "bad")'},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0


# ===================
# Deployment Endpoints Tests
# ===================


class TestDeploymentEndpoints:
    """Tests for deployment operations."""

    async def test_create_deployment(
        self, authenticated_client, mock_strategy_service, strategy_id
    ):
        """Test creating a deployment."""
        from datetime import datetime

        from src.models import DeploymentResponse

        mock_response = DeploymentResponse(
            id=uuid4(),
            strategy_id=strategy_id,
            version=1,
            environment=DeploymentEnvironment.PAPER,
            status=DeploymentStatus.PENDING,
            started_at=None,
            stopped_at=None,
            config_override=None,
            error_message=None,
            created_at=datetime.utcnow(),
        )
        mock_strategy_service.create_deployment.return_value = mock_response

        response = await authenticated_client.post(
            f"/strategies/{strategy_id}/deployments",
            json={"environment": "paper"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["environment"] == "paper"
        assert data["status"] == "pending"

    async def test_list_deployments(self, authenticated_client, mock_strategy_service, strategy_id):
        """Test listing deployments for a strategy."""
        mock_strategy_service.list_deployments.return_value = []

        response = await authenticated_client.get(f"/strategies/{strategy_id}/deployments")

        assert response.status_code == 200
        assert response.json() == []
