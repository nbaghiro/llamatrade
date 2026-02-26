"""Tests for health check utilities."""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from llamatrade_common.health import (
    CheckResult,
    DependencyCheck,
    HealthChecker,
    HealthStatus,
)


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_status_values(self):
        """Test health status values."""
        assert HealthStatus.HEALTHY == "healthy"
        assert HealthStatus.DEGRADED == "degraded"
        assert HealthStatus.UNHEALTHY == "unhealthy"


class TestDependencyCheck:
    """Tests for DependencyCheck dataclass."""

    def test_dependency_check_defaults(self):
        """Test dependency check default values."""

        async def check_fn() -> bool:
            return True

        check = DependencyCheck(name="test", check_fn=check_fn)

        assert check.name == "test"
        assert check.critical is True
        assert check.timeout == 5.0

    def test_dependency_check_custom_values(self):
        """Test dependency check with custom values."""

        async def check_fn() -> bool:
            return True

        check = DependencyCheck(
            name="cache",
            check_fn=check_fn,
            critical=False,
            timeout=2.0,
        )

        assert check.name == "cache"
        assert check.critical is False
        assert check.timeout == 2.0


class TestCheckResult:
    """Tests for CheckResult dataclass."""

    def test_check_result_basic(self):
        """Test basic check result."""
        result = CheckResult(
            name="database",
            healthy=True,
            latency_ms=5.5,
        )

        assert result.name == "database"
        assert result.healthy is True
        assert result.latency_ms == 5.5
        assert result.message is None
        assert result.details == {}

    def test_check_result_with_message(self):
        """Test check result with error message."""
        result = CheckResult(
            name="redis",
            healthy=False,
            latency_ms=1000.0,
            message="Connection refused",
        )

        assert result.healthy is False
        assert result.message == "Connection refused"


class TestHealthChecker:
    """Tests for HealthChecker class."""

    @pytest.fixture
    def checker(self):
        """Create a health checker instance."""
        return HealthChecker(service_name="test-service", version="1.0.0")

    def test_init(self, checker):
        """Test health checker initialization."""
        assert checker.service_name == "test-service"
        assert checker.version == "1.0.0"
        assert checker.checks == []

    def test_add_check(self, checker):
        """Test adding a health check."""

        async def check_db() -> bool:
            return True

        checker.add_check("database", check_db, critical=True, timeout=3.0)

        assert len(checker.checks) == 1
        assert checker.checks[0].name == "database"
        assert checker.checks[0].critical is True
        assert checker.checks[0].timeout == 3.0

    @pytest.mark.asyncio
    async def test_check_health_no_checks(self, checker):
        """Test health check with no dependencies."""
        status, checks = await checker.check_health()

        assert status == HealthStatus.HEALTHY
        assert checks == {}

    @pytest.mark.asyncio
    async def test_check_health_all_healthy(self, checker):
        """Test health check when all dependencies are healthy."""

        async def check_db() -> bool:
            return True

        async def check_cache() -> bool:
            return True

        checker.add_check("database", check_db)
        checker.add_check("cache", check_cache)

        status, checks = await checker.check_health()

        assert status == HealthStatus.HEALTHY
        assert "database" in checks
        assert "cache" in checks
        assert checks["database"]["healthy"] is True
        assert checks["cache"]["healthy"] is True

    @pytest.mark.asyncio
    async def test_check_health_critical_failure(self, checker):
        """Test health check when critical dependency fails."""

        async def check_db() -> bool:
            return False

        checker.add_check("database", check_db, critical=True)

        status, checks = await checker.check_health()

        assert status == HealthStatus.UNHEALTHY
        assert checks["database"]["healthy"] is False
        assert checks["database"]["critical"] is True

    @pytest.mark.asyncio
    async def test_check_health_non_critical_failure(self, checker):
        """Test health check when non-critical dependency fails."""

        async def check_db() -> bool:
            return True

        async def check_cache() -> bool:
            return False

        checker.add_check("database", check_db, critical=True)
        checker.add_check("cache", check_cache, critical=False)

        status, checks = await checker.check_health()

        assert status == HealthStatus.DEGRADED
        assert checks["database"]["healthy"] is True
        assert checks["cache"]["healthy"] is False

    @pytest.mark.asyncio
    async def test_check_health_timeout(self, checker):
        """Test health check timeout handling."""

        async def slow_check() -> bool:
            await asyncio.sleep(10)
            return True

        checker.add_check("slow", slow_check, timeout=0.1)

        status, checks = await checker.check_health()

        assert status == HealthStatus.UNHEALTHY
        assert checks["slow"]["healthy"] is False
        assert "timed out" in checks["slow"].get("message", "")

    @pytest.mark.asyncio
    async def test_check_health_exception(self, checker):
        """Test health check exception handling."""

        async def failing_check() -> bool:
            raise RuntimeError("Connection failed")

        checker.add_check("broken", failing_check)

        status, checks = await checker.check_health()

        assert status == HealthStatus.UNHEALTHY
        assert checks["broken"]["healthy"] is False
        assert "Connection failed" in checks["broken"].get("message", "")


class TestHealthCheckerRouter:
    """Tests for health check router endpoints."""

    @pytest.fixture
    def app(self):
        """Create a FastAPI app with health endpoints."""
        app = FastAPI()
        checker = HealthChecker(service_name="test", version="1.0.0")

        async def always_healthy() -> bool:
            return True

        checker.add_check("database", always_healthy)

        router = checker.create_router()
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    def test_health_endpoint(self, client):
        """Test /health endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "test"
        assert data["version"] == "1.0.0"
        assert "checks" in data
        assert "timestamp" in data

    def test_liveness_endpoint(self, client):
        """Test /health/live endpoint."""
        response = client.get("/health/live")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_readiness_endpoint(self, client):
        """Test /health/ready endpoint."""
        response = client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert "checks" in data


class TestHealthCheckerUnhealthyRouter:
    """Tests for health check router with unhealthy dependencies."""

    @pytest.fixture
    def app(self):
        """Create a FastAPI app with failing health checks."""
        app = FastAPI()
        checker = HealthChecker(service_name="test", version="1.0.0")

        async def always_unhealthy() -> bool:
            return False

        checker.add_check("database", always_unhealthy, critical=True)

        router = checker.create_router()
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    def test_health_endpoint_unhealthy(self, client):
        """Test /health endpoint returns 503 when unhealthy."""
        response = client.get("/health")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"

    def test_readiness_endpoint_not_ready(self, client):
        """Test /health/ready endpoint returns 503 when not ready."""
        response = client.get("/health/ready")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
