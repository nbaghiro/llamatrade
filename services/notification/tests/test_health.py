"""Health endpoint tests for notification service."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_health_check(client: AsyncClient) -> None:
    """Test health check returns healthy status."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "notification"
    assert data["version"] == "0.1.0"
