"""Tests for authentication endpoints."""

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from src.main import app
from src.services.auth_service import get_auth_service


@pytest.fixture
async def client():
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_auth_service():
    """Create a mock auth service."""
    return AsyncMock()


@pytest.mark.asyncio
async def test_health_check(client):
    """Test health check endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "auth"


@pytest.mark.asyncio
async def test_register_success(mock_auth_service):
    """Test successful user registration."""
    mock_auth_service.register.return_value = {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "tenant_id": "123e4567-e89b-12d3-a456-426614174001",
        "email": "test@example.com",
        "role": "admin",
        "is_active": True,
        "created_at": "2024-01-01T00:00:00Z",
    }

    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/auth/register",
                json={
                    "tenant_name": "Test Company",
                    "email": "test@example.com",
                    "password": "SecurePass123",
                },
            )
            assert response.status_code == 201
            data = response.json()
            assert data["email"] == "test@example.com"
            assert data["role"] == "admin"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_register_invalid_password(client):
    """Test registration with invalid password."""
    response = await client.post(
        "/auth/register",
        json={
            "tenant_name": "Test Company",
            "email": "test@example.com",
            "password": "weak",
        },
    )
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_login_invalid_credentials(mock_auth_service):
    """Test login with invalid credentials."""
    mock_auth_service.login.return_value = None

    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/auth/login",
                json={
                    "email": "test@example.com",
                    "password": "WrongPassword123",
                },
            )
            assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()
