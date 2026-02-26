"""Tests for tenants router endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from llamatrade_common.middleware import require_auth
from llamatrade_common.models import TenantContext
from src.main import app
from src.models import TenantResponse
from src.services.tenant_service import TenantService, get_tenant_service

# ===================
# Fixtures
# ===================


@pytest.fixture
async def client():
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def tenant_id():
    return uuid4()


@pytest.fixture
def user_id():
    return uuid4()


@pytest.fixture
def mock_tenant_service():
    """Create a mock tenant service."""
    return AsyncMock(spec=TenantService)


def make_auth_context(tenant_id, user_id, roles=None):
    """Create a mock TenantContext for auth override."""
    return TenantContext(
        tenant_id=tenant_id,
        user_id=user_id,
        email="admin@example.com",
        roles=roles or ["admin"],
    )


def make_tenant_response(tenant_id=None, name="Test Tenant"):
    """Create a mock TenantResponse."""
    return TenantResponse(
        id=tenant_id or uuid4(),
        name=name,
        plan_id="free",
        settings={},
        created_at=datetime.now(UTC),
    )


# ===================
# Get Current Tenant Tests
# ===================


class TestGetCurrentTenant:
    """Tests for GET /tenants/current endpoint."""

    @pytest.mark.asyncio
    async def test_get_current_tenant_success(self, tenant_id, user_id, mock_tenant_service):
        """Test getting current tenant successfully."""
        ctx = make_auth_context(tenant_id, user_id)
        tenant = make_tenant_response(tenant_id=tenant_id)
        mock_tenant_service.get_tenant.return_value = tenant

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_tenant_service] = lambda: mock_tenant_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/tenants/current")
                assert response.status_code == 200
                data = response.json()
                assert data["id"] == str(tenant_id)
                assert data["name"] == "Test Tenant"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_current_tenant_not_found(self, tenant_id, user_id, mock_tenant_service):
        """Test getting current tenant when not found."""
        ctx = make_auth_context(tenant_id, user_id)
        mock_tenant_service.get_tenant.return_value = None

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_tenant_service] = lambda: mock_tenant_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/tenants/current")
                assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_current_tenant_unauthorized(self, client):
        """Test getting current tenant without authentication."""
        response = await client.get("/tenants/current")
        assert response.status_code == 401


# ===================
# Update Current Tenant Tests
# ===================


class TestUpdateCurrentTenant:
    """Tests for PATCH /tenants/current endpoint."""

    @pytest.mark.asyncio
    async def test_update_tenant_success(self, tenant_id, user_id, mock_tenant_service):
        """Test updating tenant settings successfully (admin only)."""
        ctx = make_auth_context(tenant_id, user_id, roles=["admin"])
        updated_tenant = make_tenant_response(tenant_id=tenant_id)
        mock_tenant_service.update_tenant_settings.return_value = updated_tenant

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_tenant_service] = lambda: mock_tenant_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.patch(
                    "/tenants/current",
                    json={"theme": "dark"},
                )
                assert response.status_code == 200
                mock_tenant_service.update_tenant_settings.assert_called_once()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_update_tenant_not_found(self, tenant_id, user_id, mock_tenant_service):
        """Test updating non-existent tenant."""
        ctx = make_auth_context(tenant_id, user_id, roles=["admin"])
        mock_tenant_service.update_tenant_settings.return_value = None

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_tenant_service] = lambda: mock_tenant_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.patch(
                    "/tenants/current",
                    json={"theme": "dark"},
                )
                assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()


# ===================
# Get Alpaca Credentials Tests
# ===================


class TestGetAlpacaCredentials:
    """Tests for GET /tenants/current/alpaca endpoint."""

    @pytest.mark.asyncio
    async def test_get_alpaca_credentials_success(self, tenant_id, user_id, mock_tenant_service):
        """Test getting Alpaca credentials successfully."""
        ctx = make_auth_context(tenant_id, user_id, roles=["admin"])
        mock_tenant_service.get_alpaca_credentials.return_value = {
            "paper_key": "PKTEST123",
            "paper_secret": "secret123",
            "live_key": None,
            "live_secret": None,
        }

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_tenant_service] = lambda: mock_tenant_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/tenants/current/alpaca")
                assert response.status_code == 200
                data = response.json()
                # Keys should be masked
                assert data["paper_key"] == "***"
                assert data["paper_secret"] == "***"
                assert data["live_key"] is None
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_alpaca_credentials_empty(self, tenant_id, user_id, mock_tenant_service):
        """Test getting Alpaca credentials when none are set."""
        ctx = make_auth_context(tenant_id, user_id, roles=["admin"])
        mock_tenant_service.get_alpaca_credentials.return_value = None

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_tenant_service] = lambda: mock_tenant_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/tenants/current/alpaca")
                assert response.status_code == 200
                data = response.json()
                # All should be None
                assert data["paper_key"] is None
                assert data["paper_secret"] is None
                assert data["live_key"] is None
                assert data["live_secret"] is None
        finally:
            app.dependency_overrides.clear()


# ===================
# Update Alpaca Credentials Tests
# ===================


class TestUpdateAlpacaCredentials:
    """Tests for PUT /tenants/current/alpaca endpoint."""

    @pytest.mark.asyncio
    async def test_update_alpaca_credentials_paper(self, tenant_id, user_id, mock_tenant_service):
        """Test updating paper trading credentials."""
        ctx = make_auth_context(tenant_id, user_id, roles=["admin"])

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_tenant_service] = lambda: mock_tenant_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.put(
                    "/tenants/current/alpaca",
                    json={
                        "paper_key": "PKTEST123",
                        "paper_secret": "secret123",
                    },
                )
                assert response.status_code == 200
                data = response.json()
                # Returned values should be masked
                assert data["paper_key"] == "***"
                assert data["paper_secret"] == "***"
                mock_tenant_service.update_alpaca_credentials.assert_called_once()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_update_alpaca_credentials_live(self, tenant_id, user_id, mock_tenant_service):
        """Test updating live trading credentials."""
        ctx = make_auth_context(tenant_id, user_id, roles=["admin"])

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_tenant_service] = lambda: mock_tenant_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.put(
                    "/tenants/current/alpaca",
                    json={
                        "live_key": "AKTEST123",
                        "live_secret": "livesecret123",
                    },
                )
                assert response.status_code == 200
                data = response.json()
                assert data["live_key"] == "***"
                assert data["live_secret"] == "***"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_update_alpaca_credentials_all(self, tenant_id, user_id, mock_tenant_service):
        """Test updating all credentials at once."""
        ctx = make_auth_context(tenant_id, user_id, roles=["admin"])

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_tenant_service] = lambda: mock_tenant_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.put(
                    "/tenants/current/alpaca",
                    json={
                        "paper_key": "PKTEST123",
                        "paper_secret": "papersecret",
                        "live_key": "AKTEST123",
                        "live_secret": "livesecret",
                    },
                )
                assert response.status_code == 200
                data = response.json()
                assert data["paper_key"] == "***"
                assert data["paper_secret"] == "***"
                assert data["live_key"] == "***"
                assert data["live_secret"] == "***"
                mock_tenant_service.update_alpaca_credentials.assert_called_once_with(
                    tenant_id=tenant_id,
                    paper_key="PKTEST123",
                    paper_secret="papersecret",
                    live_key="AKTEST123",
                    live_secret="livesecret",
                )
        finally:
            app.dependency_overrides.clear()


# ===================
# Delete Alpaca Credentials Tests
# ===================


class TestDeleteAlpacaCredentials:
    """Tests for DELETE /tenants/current/alpaca endpoint."""

    @pytest.mark.asyncio
    async def test_delete_alpaca_credentials_success(self, tenant_id, user_id, mock_tenant_service):
        """Test deleting Alpaca credentials successfully."""
        ctx = make_auth_context(tenant_id, user_id, roles=["admin"])

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_tenant_service] = lambda: mock_tenant_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.delete("/tenants/current/alpaca")
                assert response.status_code == 200
                assert "deleted" in response.json()["message"].lower()
                mock_tenant_service.delete_alpaca_credentials.assert_called_once_with(
                    tenant_id=tenant_id
                )
        finally:
            app.dependency_overrides.clear()


# ===================
# Tenant Service Unit Tests
# ===================


class TestTenantServiceUnit:
    """Unit tests for TenantService."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def tenant_service(self, mock_db):
        """Create TenantService with mocked dependencies."""
        return TenantService(mock_db)

    def test_slugify_helper(self):
        """Test that _slugify generates URL-safe slugs."""
        from src.services.tenant_service import _slugify

        assert _slugify("Test Company") == "test-company"
        assert _slugify("My Awesome Trading Firm") == "my-awesome-trading-firm"
        assert _slugify("Special!@#$Chars") == "specialchars"
        assert _slugify("   Spaces   ") == "spaces"
