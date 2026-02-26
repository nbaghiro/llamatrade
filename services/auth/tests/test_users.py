"""Tests for users router endpoints."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from llamatrade_common.middleware import require_auth
from llamatrade_common.models import TenantContext
from src.main import app
from src.models import UserResponse
from src.services.user_service import UserService, get_user_service

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
def mock_user_service():
    """Create a mock user service."""
    return AsyncMock(spec=UserService)


def make_auth_context(tenant_id, user_id, roles=None):
    """Create a mock TenantContext for auth override."""
    return TenantContext(
        tenant_id=tenant_id,
        user_id=user_id,
        email="admin@example.com",
        roles=roles or ["admin"],
    )


def make_user_response(
    user_id=None,
    tenant_id=None,
    email="user@example.com",
    role="user",
    is_active=True,
):
    """Create a mock UserResponse."""
    return UserResponse(
        id=user_id or uuid4(),
        tenant_id=tenant_id or uuid4(),
        email=email,  # Pydantic validates automatically
        role=role,
        is_active=is_active,
        created_at=datetime.now(UTC),
    )


# ===================
# List Users Tests
# ===================


class TestListUsers:
    """Tests for GET /users endpoint."""

    @pytest.mark.asyncio
    async def test_list_users_success(self, tenant_id, user_id, mock_user_service):
        """Test listing users successfully."""
        ctx = make_auth_context(tenant_id, user_id)
        users = [
            make_user_response(tenant_id=tenant_id, email="user1@example.com"),
            make_user_response(tenant_id=tenant_id, email="user2@example.com"),
        ]
        mock_user_service.list_users.return_value = (users, 2)

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_user_service] = lambda: mock_user_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/users")
                assert response.status_code == 200
                data = response.json()
                assert len(data["items"]) == 2
                assert data["total"] == 2
                mock_user_service.list_users.assert_called_once_with(
                    tenant_id=tenant_id,
                    page=1,
                    page_size=20,
                )
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_users_empty(self, tenant_id, user_id, mock_user_service):
        """Test listing users when none exist."""
        ctx = make_auth_context(tenant_id, user_id)
        mock_user_service.list_users.return_value = ([], 0)

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_user_service] = lambda: mock_user_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/users")
                assert response.status_code == 200
                data = response.json()
                assert data["items"] == []
                assert data["total"] == 0
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_users_pagination(self, tenant_id, user_id, mock_user_service):
        """Test listing users with pagination."""
        ctx = make_auth_context(tenant_id, user_id)
        mock_user_service.list_users.return_value = ([], 0)

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_user_service] = lambda: mock_user_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/users?page=2&page_size=10")
                assert response.status_code == 200
                mock_user_service.list_users.assert_called_once_with(
                    tenant_id=tenant_id,
                    page=2,
                    page_size=10,
                )
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_list_users_unauthorized(self, client):
        """Test listing users without authentication."""
        response = await client.get("/users")
        assert response.status_code == 401


# ===================
# Get User Tests
# ===================


class TestGetUser:
    """Tests for GET /users/{user_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_user_success(self, tenant_id, user_id, mock_user_service):
        """Test getting a user successfully."""
        ctx = make_auth_context(tenant_id, user_id)
        target_user_id = uuid4()
        user = make_user_response(
            user_id=target_user_id,
            tenant_id=tenant_id,
        )
        mock_user_service.get_user.return_value = user

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_user_service] = lambda: mock_user_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(f"/users/{target_user_id}")
                assert response.status_code == 200
                data = response.json()
                assert data["id"] == str(target_user_id)
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_user_not_found(self, tenant_id, user_id, mock_user_service):
        """Test getting a non-existent user."""
        ctx = make_auth_context(tenant_id, user_id)
        mock_user_service.get_user.return_value = None

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_user_service] = lambda: mock_user_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(f"/users/{uuid4()}")
                assert response.status_code == 404
                assert "not found" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_get_user_unauthorized(self, client):
        """Test getting a user without authentication."""
        response = await client.get(f"/users/{uuid4()}")
        assert response.status_code == 401


# ===================
# Create User Tests
# ===================


class TestCreateUser:
    """Tests for POST /users endpoint."""

    @pytest.mark.asyncio
    async def test_create_user_success(self, tenant_id, user_id, mock_user_service):
        """Test creating a user successfully (admin only)."""
        ctx = make_auth_context(tenant_id, user_id, roles=["admin"])
        new_user = make_user_response(tenant_id=tenant_id, email="newuser@example.com")
        mock_user_service.create_user.return_value = new_user

        # Override require_auth to return admin context
        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_user_service] = lambda: mock_user_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/users",
                    json={
                        "email": "newuser@example.com",
                        "password": "SecurePass123",
                        "role": "user",
                    },
                )
                assert response.status_code == 201
                data = response.json()
                assert data["email"] == "newuser@example.com"
                mock_user_service.create_user.assert_called_once()
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_user_invalid_password(self, tenant_id, user_id):
        """Test creating user with invalid password."""
        ctx = make_auth_context(tenant_id, user_id, roles=["admin"])
        app.dependency_overrides[require_auth] = lambda: ctx

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/users",
                    json={
                        "email": "newuser@example.com",
                        "password": "weak",
                        "role": "user",
                    },
                )
                assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_user_invalid_email(self, tenant_id, user_id):
        """Test creating user with invalid email."""
        ctx = make_auth_context(tenant_id, user_id, roles=["admin"])
        app.dependency_overrides[require_auth] = lambda: ctx

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/users",
                    json={
                        "email": "invalid-email",
                        "password": "SecurePass123",
                        "role": "user",
                    },
                )
                assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email(self, tenant_id, user_id, mock_user_service):
        """Test creating user with existing email."""
        ctx = make_auth_context(tenant_id, user_id, roles=["admin"])
        mock_user_service.create_user.side_effect = ValueError("Email already exists")

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_user_service] = lambda: mock_user_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/users",
                    json={
                        "email": "existing@example.com",
                        "password": "SecurePass123",
                        "role": "user",
                    },
                )
                assert response.status_code == 400
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_user_non_admin(self, tenant_id, user_id):
        """Test that non-admin cannot create users."""
        # User with non-admin role should be blocked
        ctx = make_auth_context(tenant_id, user_id, roles=["user"])
        app.dependency_overrides[require_auth] = lambda: ctx

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/users",
                    json={
                        "email": "newuser@example.com",
                        "password": "SecurePass123",
                        "role": "user",
                    },
                )
                # Non-admin should be blocked with 403
                assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()


# ===================
# Update User Tests
# ===================


class TestUpdateUser:
    """Tests for PATCH /users/{user_id} endpoint."""

    @pytest.mark.asyncio
    async def test_update_user_success(self, tenant_id, user_id, mock_user_service):
        """Test updating a user successfully."""
        ctx = make_auth_context(tenant_id, user_id, roles=["admin"])
        target_user_id = uuid4()
        updated_user = make_user_response(
            user_id=target_user_id,
            tenant_id=tenant_id,
            role="admin",
        )
        mock_user_service.update_user.return_value = updated_user

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_user_service] = lambda: mock_user_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.patch(
                    f"/users/{target_user_id}",
                    json={"role": "admin"},
                )
                assert response.status_code == 200
                data = response.json()
                assert data["role"] == "admin"
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_update_user_not_found(self, tenant_id, user_id, mock_user_service):
        """Test updating a non-existent user."""
        ctx = make_auth_context(tenant_id, user_id, roles=["admin"])
        mock_user_service.update_user.return_value = None

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_user_service] = lambda: mock_user_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.patch(
                    f"/users/{uuid4()}",
                    json={"role": "admin"},
                )
                assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_update_user_deactivate(self, tenant_id, user_id, mock_user_service):
        """Test deactivating a user."""
        ctx = make_auth_context(tenant_id, user_id, roles=["admin"])
        target_user_id = uuid4()
        updated_user = make_user_response(
            user_id=target_user_id,
            tenant_id=tenant_id,
            is_active=False,
        )
        mock_user_service.update_user.return_value = updated_user

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_user_service] = lambda: mock_user_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.patch(
                    f"/users/{target_user_id}",
                    json={"is_active": False},
                )
                assert response.status_code == 200
                data = response.json()
                assert data["is_active"] is False
        finally:
            app.dependency_overrides.clear()


# ===================
# Delete User Tests
# ===================


class TestDeleteUser:
    """Tests for DELETE /users/{user_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_user_success(self, tenant_id, user_id, mock_user_service):
        """Test deleting a user successfully."""
        ctx = make_auth_context(tenant_id, user_id, roles=["admin"])
        target_user_id = uuid4()
        mock_user_service.delete_user.return_value = True

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_user_service] = lambda: mock_user_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.delete(f"/users/{target_user_id}")
                assert response.status_code == 204
                mock_user_service.delete_user.assert_called_once_with(
                    user_id=target_user_id,
                    tenant_id=tenant_id,
                )
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_delete_user_not_found(self, tenant_id, user_id, mock_user_service):
        """Test deleting a non-existent user."""
        ctx = make_auth_context(tenant_id, user_id, roles=["admin"])
        mock_user_service.delete_user.return_value = False

        app.dependency_overrides[require_auth] = lambda: ctx
        app.dependency_overrides[get_user_service] = lambda: mock_user_service

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.delete(f"/users/{uuid4()}")
                assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_delete_own_account(self, tenant_id, user_id):
        """Test that user cannot delete their own account."""
        ctx = make_auth_context(tenant_id, user_id, roles=["admin"])

        app.dependency_overrides[require_auth] = lambda: ctx

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.delete(f"/users/{user_id}")
                assert response.status_code == 400
                assert "own account" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()
