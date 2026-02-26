"""Tests for health endpoint."""

from httpx import AsyncClient


async def test_health_check(client: AsyncClient):
    """Test health endpoint returns healthy status."""
    response = await client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "portfolio"
    assert data["version"] == "0.1.0"


async def test_health_check_no_auth_required(client: AsyncClient):
    """Test health endpoint doesn't require authentication."""
    # Health endpoint should be accessible without auth
    response = await client.get("/health")
    assert response.status_code == 200
