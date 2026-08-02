"""Tests for health check endpoint."""

import pytest
from httpx import AsyncClient

import src.main as main


async def _healthy() -> bool:
    return True


async def _failing() -> bool:
    return False


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test health check returns healthy status."""
    monkeypatch.setattr(main, "_check_database", _healthy)
    response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "agent"
    assert data["version"] == "0.1.0"


@pytest.mark.asyncio
async def test_readiness_passes_when_database_healthy(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Readiness returns 200 with a healthy database check."""
    monkeypatch.setattr(main, "_check_database", _healthy)
    response = await client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"]["healthy"] is True


@pytest.mark.asyncio
async def test_readiness_degrades_when_database_down(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failing database probe flips readiness to 503 not_ready."""
    monkeypatch.setattr(main, "_check_database", _failing)
    response = await client.get("/health/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["checks"]["database"]["healthy"] is False
