"""Health and readiness endpoint tests for auth service."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

import src.main as main
from src.main import app


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _healthy() -> bool:
    return True


async def _failing() -> bool:
    return False


async def test_health_check(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Health check reports healthy when all dependencies are up."""
    monkeypatch.setattr(main, "_check_database", _healthy)
    monkeypatch.setattr(main, "_check_revocation_redis", _healthy)
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "auth"


async def test_readiness_passes_when_dependencies_healthy(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Readiness returns 200 with healthy checks."""
    monkeypatch.setattr(main, "_check_database", _healthy)
    monkeypatch.setattr(main, "_check_revocation_redis", _healthy)
    response = await client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"]["healthy"] is True


async def test_readiness_degrades_when_database_down(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing database probe flips readiness to 503 not_ready."""
    monkeypatch.setattr(main, "_check_database", _failing)
    monkeypatch.setattr(main, "_check_revocation_redis", _healthy)
    response = await client.get("/health/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["checks"]["database"]["healthy"] is False


async def test_redis_down_degrades_but_stays_ready(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Redis is non-critical (revocation store): readiness holds, health degrades."""
    monkeypatch.setattr(main, "_check_database", _healthy)
    monkeypatch.setattr(main, "_check_revocation_redis", _failing)
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"

    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
