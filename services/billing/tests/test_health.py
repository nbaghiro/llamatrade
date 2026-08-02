"""Health and readiness endpoint tests for billing service."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

import src.main as main
from src.main import app


@pytest.fixture
async def health_client() -> AsyncGenerator[AsyncClient]:
    """Bare client: health endpoints need no mocked Stripe/DB dependencies."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _healthy() -> bool:
    return True


async def _failing() -> bool:
    return False


async def test_health_check(health_client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Health check reports healthy when the database is up."""
    monkeypatch.setattr(main, "_check_database", _healthy)
    response = await health_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "billing"


async def test_readiness_passes_when_database_healthy(
    health_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Readiness returns 200 with a healthy database check."""
    monkeypatch.setattr(main, "_check_database", _healthy)
    response = await health_client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"]["healthy"] is True


async def test_readiness_degrades_when_database_down(
    health_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing database probe flips readiness to 503 not_ready."""
    monkeypatch.setattr(main, "_check_database", _failing)
    response = await health_client.get("/health/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["checks"]["database"]["healthy"] is False
