"""Tests for health endpoint."""

import pytest


class TestHealthEndpoint:
    """Tests for the shared HealthChecker /health endpoint."""

    @pytest.mark.asyncio
    async def test_health_reports_service_identity(self, client):
        """Health returns the service identity and an overall status."""
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "market-data"
        assert data["version"] == "0.1.0"
        # Deps are unavailable in the unit env, so the (non-critical) overall
        # status may be healthy or degraded — never unhealthy (nothing critical).
        assert data["status"] in {"healthy", "degraded"}

    @pytest.mark.asyncio
    async def test_health_includes_dependency_checks(self, client):
        """Redis and live-bar checks are reported as non-critical dependencies."""
        response = await client.get("/health")

        checks = response.json()["checks"]
        assert "redis" in checks
        assert "live_bars" in checks
        assert checks["redis"]["critical"] is False
        assert checks["live_bars"]["critical"] is False

    @pytest.mark.asyncio
    async def test_health_stays_200_when_deps_unavailable(self, client):
        """Non-critical dependencies never fail the probe (graceful degradation)."""
        response = await client.get("/health")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_liveness_probe_always_ok(self, client):
        """The liveness probe reports ok regardless of dependency state."""
        response = await client.get("/health/live")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
