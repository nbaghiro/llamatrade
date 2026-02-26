"""Auth → Strategy HTTP workflow tests.

These tests verify the complete flow of:
1. User authenticates (via JWT)
2. User creates a strategy (strategy service)
3. User manages strategy versions and deployments
4. Strategy operations respect tenant isolation

Uses ASGI transport for fast in-process testing.
"""

import sys
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models import Tenant, User
from tests.integration.fixtures.auth import (
    TEST_JWT_ALGORITHM,
    TEST_JWT_SECRET,
    create_auth_headers,
    create_jwt_token,
)

pytestmark = [pytest.mark.integration, pytest.mark.workflow]


def _load_strategy_app():
    """Import the strategy app fresh each time.

    Both billing and strategy services use 'src.main' as their module name.
    We need to clear the module cache and set up the correct path to ensure
    we import from the strategy service.
    """
    strategy_path = Path(__file__).parents[3] / "services" / "strategy"

    # Remove all other service paths to avoid conflicts
    service_paths = [
        str(Path(__file__).parents[3] / "services" / svc)
        for svc in ["auth", "billing", "backtest", "market-data", "trading", "portfolio"]
    ]
    for svc_path in service_paths:
        if svc_path in sys.path:
            sys.path.remove(svc_path)

    # Clear any cached src modules to avoid conflicts from other services
    # Must include bare 'src' module as well as all submodules
    modules_to_remove = [
        k for k in list(sys.modules.keys())
        if k == "src" or k.startswith("src.")
    ]
    for mod in modules_to_remove:
        del sys.modules[mod]

    # Add strategy service path at the beginning
    strategy_path_str = str(strategy_path)
    if strategy_path_str in sys.path:
        sys.path.remove(strategy_path_str)
    sys.path.insert(0, strategy_path_str)

    try:
        from src.main import app
        return app
    except ImportError as e:
        pytest.skip(f"Cannot import strategy service: {e}")


@pytest.fixture
async def strategy_client(db_session: AsyncSession):
    """Create an async client for the strategy service with database override.

    This fixture also overrides require_auth to properly decode JWT tokens
    since the middleware can't be added after app initialization.
    """
    # Load strategy app fresh (clears module cache to avoid conflicts)
    strategy_app = _load_strategy_app()
    if strategy_app is None:
        pytest.skip("Strategy app not available")

    from llamatrade_db import get_db
    from llamatrade_common.middleware import require_auth, set_tenant_context
    from llamatrade_common.models import TenantContext
    from fastapi import Request, Depends
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    import jwt

    bearer_scheme = HTTPBearer(auto_error=False)

    async def override_require_auth(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    ) -> TenantContext:
        """Override require_auth to decode JWT and set tenant context."""
        if not credentials:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            payload = jwt.decode(
                credentials.credentials,
                TEST_JWT_SECRET,
                algorithms=[TEST_JWT_ALGORITHM],
            )
            ctx = TenantContext(
                tenant_id=UUID(payload["tenant_id"]),
                user_id=UUID(payload["sub"]),
                email=payload["email"],
                roles=payload.get("roles", []),
            )
            set_tenant_context(ctx)
            return ctx
        except (jwt.InvalidTokenError, KeyError, ValueError) as e:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid or expired token: {e}",
                headers={"WWW-Authenticate": "Bearer"},
            )

    async def override_get_db():
        yield db_session

    strategy_app.dependency_overrides[get_db] = override_get_db
    strategy_app.dependency_overrides[require_auth] = override_require_auth

    transport = ASGITransport(app=strategy_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    strategy_app.dependency_overrides.clear()


# Sample valid S-expression strategy config (uses keyword syntax :name)
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


class TestStrategyCreationWorkflow:
    """Test strategy creation via HTTP."""

    async def test_create_strategy_with_valid_config(
        self,
        strategy_client: AsyncClient,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test creating a strategy with valid S-expression config."""
        token = create_jwt_token(
            user_id=test_user.id,
            tenant_id=test_tenant.id,
            email=test_user.email,
        )
        headers = create_auth_headers(token)

        response = await strategy_client.post(
            "/strategies",
            headers=headers,
            json={
                "name": "My Momentum Strategy",
                "description": "A simple momentum strategy",
                "config_sexpr": VALID_STRATEGY_SEXPR,
            },
        )

        assert response.status_code == 201
        data = response.json()

        assert data["name"] == "My Momentum Strategy"
        assert data["description"] == "A simple momentum strategy"
        assert data["strategy_type"] == "momentum"
        assert data["status"] == "draft"
        assert data["current_version"] == 1
        assert "id" in data
        assert "config_sexpr" in data
        assert "config_json" in data
        assert data["symbols"] == ["AAPL", "GOOGL"]
        assert data["timeframe"] == "1D"

    async def test_create_strategy_requires_auth(
        self,
        strategy_client: AsyncClient,
    ):
        """Test that strategy creation requires authentication."""
        response = await strategy_client.post(
            "/strategies",
            json={
                "name": "Unauthorized Strategy",
                "config_sexpr": VALID_STRATEGY_SEXPR,
            },
        )

        assert response.status_code == 401

    async def test_create_strategy_validates_sexpr(
        self,
        strategy_client: AsyncClient,
        auth_headers: dict[str, str],
    ):
        """Test that invalid S-expression config is rejected."""
        response = await strategy_client.post(
            "/strategies",
            headers=auth_headers,
            json={
                "name": "Invalid Strategy",
                "config_sexpr": "(strategy (invalid))",  # Invalid config
            },
        )

        assert response.status_code == 400
        assert "Invalid strategy" in response.json()["detail"]


class TestStrategyListWorkflow:
    """Test strategy listing via HTTP."""

    async def test_list_strategies_empty(
        self,
        strategy_client: AsyncClient,
        auth_headers: dict[str, str],
    ):
        """Test listing strategies when none exist."""
        response = await strategy_client.get(
            "/strategies",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()

        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    async def test_list_strategies_with_data(
        self,
        strategy_client: AsyncClient,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test listing strategies after creating some."""
        token = create_jwt_token(
            user_id=test_user.id,
            tenant_id=test_tenant.id,
            email=test_user.email,
        )
        headers = create_auth_headers(token)

        # Create two strategies
        for i in range(2):
            await strategy_client.post(
                "/strategies",
                headers=headers,
                json={
                    "name": f"Strategy {i+1}",
                    "config_sexpr": VALID_STRATEGY_SEXPR,
                },
            )

        # List strategies
        response = await strategy_client.get(
            "/strategies",
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 2
        assert len(data["items"]) == 2

    async def test_list_strategies_pagination(
        self,
        strategy_client: AsyncClient,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test pagination for strategy listing."""
        token = create_jwt_token(
            user_id=test_user.id,
            tenant_id=test_tenant.id,
            email=test_user.email,
        )
        headers = create_auth_headers(token)

        # Create 5 strategies
        for i in range(5):
            await strategy_client.post(
                "/strategies",
                headers=headers,
                json={
                    "name": f"Paginated Strategy {i+1}",
                    "config_sexpr": VALID_STRATEGY_SEXPR,
                },
            )

        # Get page 1 with page_size=2
        response = await strategy_client.get(
            "/strategies",
            headers=headers,
            params={"page": 1, "page_size": 2},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["total"] == 5
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["page_size"] == 2


class TestStrategyVersionWorkflow:
    """Test strategy version management via HTTP."""

    async def test_update_strategy_creates_new_version(
        self,
        strategy_client: AsyncClient,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test that updating config creates a new version."""
        token = create_jwt_token(
            user_id=test_user.id,
            tenant_id=test_tenant.id,
            email=test_user.email,
        )
        headers = create_auth_headers(token)

        # Create initial strategy
        create_response = await strategy_client.post(
            "/strategies",
            headers=headers,
            json={
                "name": "Versioned Strategy",
                "config_sexpr": VALID_STRATEGY_SEXPR,
            },
        )
        strategy_id = create_response.json()["id"]

        # Update with new config (changes symbols)
        updated_sexpr = VALID_STRATEGY_SEXPR.replace(
            ':symbols ["AAPL" "GOOGL"]',
            ':symbols ["MSFT" "AMZN" "NVDA"]',
        )

        update_response = await strategy_client.patch(
            f"/strategies/{strategy_id}",
            headers=headers,
            json={"config_sexpr": updated_sexpr},
        )

        assert update_response.status_code == 200
        data = update_response.json()

        assert data["current_version"] == 2
        assert data["symbols"] == ["MSFT", "AMZN", "NVDA"]

    async def test_list_strategy_versions(
        self,
        strategy_client: AsyncClient,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test listing all versions of a strategy."""
        token = create_jwt_token(
            user_id=test_user.id,
            tenant_id=test_tenant.id,
            email=test_user.email,
        )
        headers = create_auth_headers(token)

        # Create strategy and update it twice
        create_response = await strategy_client.post(
            "/strategies",
            headers=headers,
            json={
                "name": "Multi-Version Strategy",
                "config_sexpr": VALID_STRATEGY_SEXPR,
            },
        )
        strategy_id = create_response.json()["id"]

        # Update twice
        for i in range(2):
            updated_sexpr = VALID_STRATEGY_SEXPR.replace(
                ':name "Test Momentum Strategy"',
                f':name "Version {i+2}"',
            )
            await strategy_client.patch(
                f"/strategies/{strategy_id}",
                headers=headers,
                json={"config_sexpr": updated_sexpr},
            )

        # List versions
        response = await strategy_client.get(
            f"/strategies/{strategy_id}/versions",
            headers=headers,
        )

        assert response.status_code == 200
        versions = response.json()

        assert len(versions) == 3
        # Versions should be ordered by version desc
        assert versions[0]["version"] == 3
        assert versions[1]["version"] == 2
        assert versions[2]["version"] == 1


class TestStrategyTenantIsolation:
    """Test tenant isolation for strategy operations."""

    async def test_cannot_access_other_tenant_strategy(
        self,
        strategy_client: AsyncClient,
        test_tenant: Tenant,
        test_user: User,
        second_tenant: Tenant,
        second_tenant_user: User,
    ):
        """Test that one tenant cannot access another tenant's strategy."""
        # Create strategy as tenant A
        tenant_a_token = create_jwt_token(
            user_id=test_user.id,
            tenant_id=test_tenant.id,
            email=test_user.email,
        )
        tenant_a_headers = create_auth_headers(tenant_a_token)

        create_response = await strategy_client.post(
            "/strategies",
            headers=tenant_a_headers,
            json={
                "name": "Tenant A Strategy",
                "config_sexpr": VALID_STRATEGY_SEXPR,
            },
        )
        strategy_id = create_response.json()["id"]

        # Try to access as tenant B
        tenant_b_token = create_jwt_token(
            user_id=second_tenant_user.id,
            tenant_id=second_tenant.id,
            email=second_tenant_user.email,
        )
        tenant_b_headers = create_auth_headers(tenant_b_token)

        response = await strategy_client.get(
            f"/strategies/{strategy_id}",
            headers=tenant_b_headers,
        )

        # Should return 404 (not 403 to avoid leaking existence)
        assert response.status_code == 404

    async def test_cannot_modify_other_tenant_strategy(
        self,
        strategy_client: AsyncClient,
        test_tenant: Tenant,
        test_user: User,
        second_tenant: Tenant,
        second_tenant_user: User,
    ):
        """Test that one tenant cannot modify another tenant's strategy."""
        # Create strategy as tenant A
        tenant_a_token = create_jwt_token(
            user_id=test_user.id,
            tenant_id=test_tenant.id,
            email=test_user.email,
        )
        tenant_a_headers = create_auth_headers(tenant_a_token)

        create_response = await strategy_client.post(
            "/strategies",
            headers=tenant_a_headers,
            json={
                "name": "Protected Strategy",
                "config_sexpr": VALID_STRATEGY_SEXPR,
            },
        )
        strategy_id = create_response.json()["id"]

        # Try to update as tenant B
        tenant_b_token = create_jwt_token(
            user_id=second_tenant_user.id,
            tenant_id=second_tenant.id,
            email=second_tenant_user.email,
        )
        tenant_b_headers = create_auth_headers(tenant_b_token)

        response = await strategy_client.patch(
            f"/strategies/{strategy_id}",
            headers=tenant_b_headers,
            json={"name": "Hacked Strategy"},
        )

        assert response.status_code == 404

    async def test_cannot_delete_other_tenant_strategy(
        self,
        strategy_client: AsyncClient,
        test_tenant: Tenant,
        test_user: User,
        second_tenant: Tenant,
        second_tenant_user: User,
    ):
        """Test that one tenant cannot delete another tenant's strategy."""
        # Create strategy as tenant A
        tenant_a_token = create_jwt_token(
            user_id=test_user.id,
            tenant_id=test_tenant.id,
            email=test_user.email,
        )
        tenant_a_headers = create_auth_headers(tenant_a_token)

        create_response = await strategy_client.post(
            "/strategies",
            headers=tenant_a_headers,
            json={
                "name": "Cannot Delete This",
                "config_sexpr": VALID_STRATEGY_SEXPR,
            },
        )
        strategy_id = create_response.json()["id"]

        # Try to delete as tenant B
        tenant_b_token = create_jwt_token(
            user_id=second_tenant_user.id,
            tenant_id=second_tenant.id,
            email=second_tenant_user.email,
        )
        tenant_b_headers = create_auth_headers(tenant_b_token)

        response = await strategy_client.delete(
            f"/strategies/{strategy_id}",
            headers=tenant_b_headers,
        )

        assert response.status_code == 404

        # Verify strategy still exists for tenant A
        verify_response = await strategy_client.get(
            f"/strategies/{strategy_id}",
            headers=tenant_a_headers,
        )
        assert verify_response.status_code == 200

    async def test_list_only_shows_own_tenant_strategies(
        self,
        strategy_client: AsyncClient,
        test_tenant: Tenant,
        test_user: User,
        second_tenant: Tenant,
        second_tenant_user: User,
    ):
        """Test that listing only shows the requesting tenant's strategies."""
        # Create strategies for both tenants
        tenant_a_token = create_jwt_token(
            user_id=test_user.id,
            tenant_id=test_tenant.id,
            email=test_user.email,
        )
        tenant_a_headers = create_auth_headers(tenant_a_token)

        await strategy_client.post(
            "/strategies",
            headers=tenant_a_headers,
            json={
                "name": "Tenant A Strategy 1",
                "config_sexpr": VALID_STRATEGY_SEXPR,
            },
        )
        await strategy_client.post(
            "/strategies",
            headers=tenant_a_headers,
            json={
                "name": "Tenant A Strategy 2",
                "config_sexpr": VALID_STRATEGY_SEXPR,
            },
        )

        tenant_b_token = create_jwt_token(
            user_id=second_tenant_user.id,
            tenant_id=second_tenant.id,
            email=second_tenant_user.email,
        )
        tenant_b_headers = create_auth_headers(tenant_b_token)

        await strategy_client.post(
            "/strategies",
            headers=tenant_b_headers,
            json={
                "name": "Tenant B Strategy",
                "config_sexpr": VALID_STRATEGY_SEXPR,
            },
        )

        # List as tenant A - should see 2
        response_a = await strategy_client.get(
            "/strategies",
            headers=tenant_a_headers,
        )
        assert response_a.status_code == 200
        assert response_a.json()["total"] == 2

        # List as tenant B - should see 1
        response_b = await strategy_client.get(
            "/strategies",
            headers=tenant_b_headers,
        )
        assert response_b.status_code == 200
        assert response_b.json()["total"] == 1


class TestStrategyStatusWorkflow:
    """Test strategy status transitions via HTTP."""

    async def test_activate_strategy(
        self,
        strategy_client: AsyncClient,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test activating a strategy."""
        token = create_jwt_token(
            user_id=test_user.id,
            tenant_id=test_tenant.id,
            email=test_user.email,
        )
        headers = create_auth_headers(token)

        # Create strategy (starts as draft)
        create_response = await strategy_client.post(
            "/strategies",
            headers=headers,
            json={
                "name": "Activatable Strategy",
                "config_sexpr": VALID_STRATEGY_SEXPR,
            },
        )
        strategy_id = create_response.json()["id"]
        assert create_response.json()["status"] == "draft"

        # Activate
        response = await strategy_client.post(
            f"/strategies/{strategy_id}/activate",
            headers=headers,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "active"

    async def test_pause_strategy(
        self,
        strategy_client: AsyncClient,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test pausing an active strategy."""
        token = create_jwt_token(
            user_id=test_user.id,
            tenant_id=test_tenant.id,
            email=test_user.email,
        )
        headers = create_auth_headers(token)

        # Create and activate
        create_response = await strategy_client.post(
            "/strategies",
            headers=headers,
            json={
                "name": "Pausable Strategy",
                "config_sexpr": VALID_STRATEGY_SEXPR,
            },
        )
        strategy_id = create_response.json()["id"]

        await strategy_client.post(
            f"/strategies/{strategy_id}/activate",
            headers=headers,
        )

        # Pause
        response = await strategy_client.post(
            f"/strategies/{strategy_id}/pause",
            headers=headers,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "paused"

    async def test_delete_archives_strategy(
        self,
        strategy_client: AsyncClient,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test that delete soft-archives the strategy."""
        token = create_jwt_token(
            user_id=test_user.id,
            tenant_id=test_tenant.id,
            email=test_user.email,
        )
        headers = create_auth_headers(token)

        # Create strategy
        create_response = await strategy_client.post(
            "/strategies",
            headers=headers,
            json={
                "name": "Deletable Strategy",
                "config_sexpr": VALID_STRATEGY_SEXPR,
            },
        )
        strategy_id = create_response.json()["id"]

        # Delete
        delete_response = await strategy_client.delete(
            f"/strategies/{strategy_id}",
            headers=headers,
        )

        assert delete_response.status_code == 204

        # Strategy should not appear in default list (excludes archived)
        list_response = await strategy_client.get(
            "/strategies",
            headers=headers,
        )
        strategy_ids = [s["id"] for s in list_response.json()["items"]]
        assert strategy_id not in strategy_ids


class TestStrategyCloneWorkflow:
    """Test strategy cloning via HTTP."""

    async def test_clone_strategy(
        self,
        strategy_client: AsyncClient,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test cloning a strategy with a new name."""
        token = create_jwt_token(
            user_id=test_user.id,
            tenant_id=test_tenant.id,
            email=test_user.email,
        )
        headers = create_auth_headers(token)

        # Create original
        create_response = await strategy_client.post(
            "/strategies",
            headers=headers,
            json={
                "name": "Original Strategy",
                "description": "The original",
                "config_sexpr": VALID_STRATEGY_SEXPR,
            },
        )
        original_id = create_response.json()["id"]

        # Clone
        clone_response = await strategy_client.post(
            f"/strategies/{original_id}/clone",
            headers=headers,
            params={"name": "Cloned Strategy"},
        )

        assert clone_response.status_code == 201
        clone_data = clone_response.json()

        assert clone_data["name"] == "Cloned Strategy"
        assert "Cloned from: Original Strategy" in clone_data["description"]
        assert clone_data["id"] != original_id
        assert clone_data["current_version"] == 1  # Clones start at v1
        assert clone_data["symbols"] == ["AAPL", "GOOGL"]  # Same config


class TestStrategyValidation:
    """Test strategy validation endpoint."""

    async def test_validate_valid_config(
        self,
        strategy_client: AsyncClient,
    ):
        """Test validating a valid strategy configuration."""
        # Validation endpoint is public (no auth needed per the router)
        response = await strategy_client.post(
            "/strategies/validate",
            params={"config_sexpr": VALID_STRATEGY_SEXPR},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["valid"] is True
        assert data["errors"] == []

    async def test_validate_invalid_config(
        self,
        strategy_client: AsyncClient,
    ):
        """Test validating an invalid strategy configuration."""
        response = await strategy_client.post(
            "/strategies/validate",
            params={"config_sexpr": "(strategy (missing required fields))"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["valid"] is False
        assert len(data["errors"]) > 0
