"""Tests for health check endpoint."""

import pytest

import src.main as main


async def _healthy() -> bool:
    return True


async def _failing() -> bool:
    return False


async def _redis_healthy(url: str) -> bool:
    return True


async def _redis_failing(url: str) -> bool:
    return False


@pytest.mark.asyncio
async def test_health_check(client, monkeypatch):
    """Test health check endpoint returns healthy status."""
    monkeypatch.setattr(main, "_check_database", _healthy)
    monkeypatch.setattr(main, "check_redis", _redis_healthy)
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "backtest"
    assert "version" in data


@pytest.mark.asyncio
async def test_readiness_passes_when_dependencies_healthy(client, monkeypatch):
    """Readiness returns 200 with healthy database and broker checks."""
    monkeypatch.setattr(main, "_check_database", _healthy)
    monkeypatch.setattr(main, "check_redis", _redis_healthy)
    response = await client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"]["healthy"] is True
    assert data["checks"]["redis"]["healthy"] is True


@pytest.mark.asyncio
async def test_readiness_degrades_when_database_down(client, monkeypatch):
    """A failing database probe flips readiness to 503 not_ready."""
    monkeypatch.setattr(main, "_check_database", _failing)
    monkeypatch.setattr(main, "check_redis", _redis_healthy)
    response = await client.get("/health/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["checks"]["database"]["healthy"] is False


@pytest.mark.asyncio
async def test_readiness_degrades_when_broker_down(client, monkeypatch):
    """Redis is the Celery broker (critical): its failure makes the pod not ready."""
    monkeypatch.setattr(main, "_check_database", _healthy)
    monkeypatch.setattr(main, "check_redis", _redis_failing)
    response = await client.get("/health/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["checks"]["redis"]["healthy"] is False
