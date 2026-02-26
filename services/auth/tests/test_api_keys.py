"""Tests for API keys router endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from llamatrade_common.middleware import require_auth
from llamatrade_common.models import TenantContext
from src.main import app
from src.models import APIKeyCreatedResponse, APIKeyResponse
from src.services.api_key_service import APIKeyService, get_api_key_service

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
def mock_api_key_service():
    """Create a mock API key service."""
    return AsyncMock(spec=APIKeyService)


def make_auth_context(tenant_id, user_id):
    """Create a mock TenantContext for auth override."""
    return TenantContext(
        tenant_id=tenant_id,
        user_id=user_id,
        email="user@example.com",
        roles=["user"],
    )


def make_api_key_response(key_id=None, name="Test Key"):
    """Create a mock APIKeyResponse."""
    return APIKeyResponse(
        id=key_id or uuid4(),
        name=name,
        key_prefix="lt_****",
        scopes=["read"],
        created_at=datetime.now(UTC),
        last_used_at=None,
    )


def make_api_key_created_response(key_id=None, name="Test Key"):
    """Create a mock APIKeyCreatedResponse."""
    return APIKeyCreatedResponse(
        id=key_id or uuid4(),
        name=name,
        api_key="lt_test_key_full_value_12345",
        scopes=["read"],
        created_at=datetime.now(UTC),
    )


# ===================
# List API Keys Tests
# ===================


class TestListAPIKeys:
    """Tests for GET /api-keys endpoint."""

    @pytest.mark.asyncio
    async def test_list_api_keys_success(self, tenant_id, user_id, mock_api_key_service):
        """Test listing API keys successfully."""
        ctx = make_auth_context(tenant_id, user_id)
        keys = [
            make_api_key_response(name="Key 1"),
            make_api_key_response(name="Key 2"),
        ]
        mock_api_key_service.list_api_keys.return_value = (keys, 2)

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_api_key_service] = lambda: mock_api_key_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api-keys")
                assert response.status_code == 200
                data = response.json()
                assert len(data["items"]) == 2
                assert data["total"] == 2
                mock_api_key_service.list_api_keys.assert_called_once_with(
                    user_id=user_id,
                    page=1,
                    page_size=20,
                )
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_api_keys_empty(self, tenant_id, user_id, mock_api_key_service):
        """Test listing API keys when none exist."""
        ctx = make_auth_context(tenant_id, user_id)
        mock_api_key_service.list_api_keys.return_value = ([], 0)

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_api_key_service] = lambda: mock_api_key_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api-keys")
                assert response.status_code == 200
                data = response.json()
                assert data["items"] == []
                assert data["total"] == 0
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_api_keys_pagination(self, tenant_id, user_id, mock_api_key_service):
        """Test listing API keys with pagination."""
        ctx = make_auth_context(tenant_id, user_id)
        mock_api_key_service.list_api_keys.return_value = ([], 0)

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_api_key_service] = lambda: mock_api_key_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api-keys?page=2&page_size=10")
                assert response.status_code == 200
                mock_api_key_service.list_api_keys.assert_called_once_with(
                    user_id=user_id,
                    page=2,
                    page_size=10,
                )
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_api_keys_unauthorized(self, client):
        """Test listing API keys without authentication."""
        response = await client.get("/api-keys")
        assert response.status_code == 401


# ===================
# Create API Key Tests
# ===================


class TestCreateAPIKey:
    """Tests for POST /api-keys endpoint."""

    @pytest.mark.asyncio
    async def test_create_api_key_success(self, tenant_id, user_id, mock_api_key_service):
        """Test creating an API key successfully."""
        ctx = make_auth_context(tenant_id, user_id)
        new_key = make_api_key_created_response(name="My API Key")
        mock_api_key_service.create_api_key.return_value = new_key

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_api_key_service] = lambda: mock_api_key_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api-keys",
                    json={
                        "name": "My API Key",
                        "scopes": ["read", "write"],
                    },
                )
                assert response.status_code == 201
                data = response.json()
                assert data["name"] == "My API Key"
                assert "api_key" in data  # Full key shown only on creation
                assert data["api_key"].startswith("lt_")
                mock_api_key_service.create_api_key.assert_called_once_with(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    name="My API Key",
                    scopes=["read", "write"],
                )
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_api_key_default_scopes(self, tenant_id, user_id, mock_api_key_service):
        """Test creating an API key with default scopes."""
        ctx = make_auth_context(tenant_id, user_id)
        new_key = make_api_key_created_response(name="Default Scopes Key")
        mock_api_key_service.create_api_key.return_value = new_key

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_api_key_service] = lambda: mock_api_key_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api-keys",
                    json={"name": "Default Scopes Key"},
                )
                assert response.status_code == 201
                # Default scope should be ["read"]
                mock_api_key_service.create_api_key.assert_called_once_with(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    name="Default Scopes Key",
                    scopes=["read"],
                )
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_api_key_missing_name(self, tenant_id, user_id):
        """Test creating an API key without a name."""
        ctx = make_auth_context(tenant_id, user_id)
        app.dependency_overrides[require_auth] = lambda: ctx

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api-keys",
                    json={"scopes": ["read"]},
                )
                assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_api_key_empty_name(self, tenant_id, user_id):
        """Test creating an API key with empty name."""
        ctx = make_auth_context(tenant_id, user_id)
        app.dependency_overrides[require_auth] = lambda: ctx

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api-keys",
                    json={"name": ""},
                )
                assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_api_key_unauthorized(self, client):
        """Test creating an API key without authentication."""
        response = await client.post(
            "/api-keys",
            json={"name": "Test Key"},
        )
        assert response.status_code == 401


# ===================
# Delete API Key Tests
# ===================


class TestDeleteAPIKey:
    """Tests for DELETE /api-keys/{key_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_api_key_success(self, tenant_id, user_id, mock_api_key_service):
        """Test deleting an API key successfully."""
        ctx = make_auth_context(tenant_id, user_id)
        key_id = uuid4()
        mock_api_key_service.delete_api_key.return_value = True

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_api_key_service] = lambda: mock_api_key_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.delete(f"/api-keys/{key_id}")
                assert response.status_code == 204
                mock_api_key_service.delete_api_key.assert_called_once_with(
                    key_id=key_id,
                    user_id=user_id,
                )
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_delete_api_key_not_found(self, tenant_id, user_id, mock_api_key_service):
        """Test deleting a non-existent API key."""
        ctx = make_auth_context(tenant_id, user_id)
        mock_api_key_service.delete_api_key.return_value = False

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_api_key_service] = lambda: mock_api_key_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.delete(f"/api-keys/{uuid4()}")
                assert response.status_code == 404
                assert "not found" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_delete_api_key_unauthorized(self, client):
        """Test deleting an API key without authentication."""
        response = await client.delete(f"/api-keys/{uuid4()}")
        assert response.status_code == 401


# ===================
# API Key Service Unit Tests
# ===================


class TestAPIKeyServiceUnit:
    """Unit tests for APIKeyService."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def api_key_service(self, mock_db):
        """Create APIKeyService with mocked dependencies."""
        return APIKeyService(mock_db)

    @pytest.mark.asyncio
    async def test_create_api_key_generates_key(self, api_key_service):
        """Test that create_api_key generates a proper API key."""
        result = await api_key_service.create_api_key(
            user_id=uuid4(),
            tenant_id=uuid4(),
            name="Test Key",
            scopes=["read"],
        )

        assert result.name == "Test Key"
        assert result.api_key.startswith("lt_")
        assert len(result.api_key) > 20  # Should be a reasonably long key
        assert result.scopes == ["read"]

    @pytest.mark.asyncio
    async def test_create_api_key_default_scopes(self, api_key_service):
        """Test that create_api_key uses default scopes when none provided."""
        result = await api_key_service.create_api_key(
            user_id=uuid4(),
            tenant_id=uuid4(),
            name="Default Scopes",
            scopes=None,
        )

        assert result.scopes == ["read"]

    @pytest.mark.asyncio
    async def test_list_api_keys_returns_empty(self, api_key_service):
        """Test that list_api_keys returns empty list (stubbed)."""
        keys, total = await api_key_service.list_api_keys(
            user_id=uuid4(),
            page=1,
            page_size=20,
        )

        assert keys == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_delete_api_key_returns_false(self, api_key_service):
        """Test that delete_api_key returns False (stubbed)."""
        result = await api_key_service.delete_api_key(
            key_id=uuid4(),
            user_id=uuid4(),
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_validate_api_key_returns_none(self, api_key_service):
        """Test that validate_api_key returns None (stubbed)."""
        result = await api_key_service.validate_api_key(
            api_key="lt_invalid_key",
        )

        assert result is None
