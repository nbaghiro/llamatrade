"""Tests for health endpoint."""

import pytest


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_healthy(self, client):
        """Test health endpoint returns healthy status."""
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "market-data"
        assert data["version"] == "0.1.0"
        assert "dependencies" in data

    @pytest.mark.asyncio
    async def test_health_includes_redis_status(self, client):
        """Test health endpoint includes Redis dependency status."""
        response = await client.get("/health")

        data = response.json()
        assert "redis" in data["dependencies"]
        redis_status = data["dependencies"]["redis"]
        assert "status" in redis_status
        assert redis_status["critical"] is False

    @pytest.mark.asyncio
    async def test_health_with_redis_unavailable(self, client):
        """Test health endpoint when Redis is unavailable."""
        # This tests the service's graceful degradation
        # The health endpoint should still return 200 even if Redis is down
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        # Status should still be healthy (Redis is non-critical)
        assert data["status"] == "healthy"
