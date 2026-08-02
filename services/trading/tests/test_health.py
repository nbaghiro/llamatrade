"""Test health endpoint."""

import src.main as main


async def _healthy(*_args: object, **_kwargs: object) -> bool:
    return True


async def _failing(*_args: object, **_kwargs: object) -> bool:
    return False


async def test_health_endpoint(client, monkeypatch):
    """Test that health endpoint returns healthy status."""
    monkeypatch.setattr(main, "_check_database", _healthy)
    monkeypatch.setattr(main, "check_kafka", _healthy)
    response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "trading"
    assert "version" in data


async def test_readiness_passes_when_dependencies_healthy(client, monkeypatch):
    """Readiness returns 200 with healthy database and kafka checks."""
    monkeypatch.setattr(main, "_check_database", _healthy)
    monkeypatch.setattr(main, "check_kafka", _healthy)
    response = await client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"]["healthy"] is True


async def test_readiness_degrades_when_database_down(client, monkeypatch):
    """A failing database probe flips readiness to 503 not_ready."""
    monkeypatch.setattr(main, "_check_database", _failing)
    monkeypatch.setattr(main, "check_kafka", _healthy)
    response = await client.get("/health/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["checks"]["database"]["healthy"] is False


async def test_kafka_down_degrades_but_stays_ready(client, monkeypatch):
    """Kafka is non-critical: readiness holds while health reports degraded."""
    monkeypatch.setattr(main, "_check_database", _healthy)
    monkeypatch.setattr(main, "check_kafka", _failing)
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"

    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
