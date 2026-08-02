"""Health endpoint tests for notification service."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_health_check(client: AsyncClient) -> None:
    """Health reports the service identity; degraded (not down) without deps."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert data["service"] == "notification"
    assert data["version"] == "0.1.0"


async def test_readiness_registers_dependency_checks(client: AsyncClient) -> None:
    """DB and Kafka probes are registered; both non-critical so reads stay up."""
    response = await client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert set(data["checks"]) == {"database", "kafka"}
    assert all(not c["critical"] for c in data["checks"].values())


async def test_liveness(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
