"""Tests for health check utilities."""

import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine

from llamatrade_common.health import (
    CheckResult,
    DependencyCheck,
    HealthChecker,
    HealthStatus,
    cached_engine_check,
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


class _FakeConnection:
    """Connection stand-in that records statements and can fail on demand."""

    def __init__(self, engine: _FakeEngine) -> None:
        self._engine = engine

    async def execute(self, statement: object) -> None:
        self._engine.executed.append(str(statement))
        if self._engine.fail:
            raise RuntimeError("database is down")


class _FakeEngine:
    """Minimal AsyncEngine stand-in: the probe only uses ``connect()``."""

    def __init__(self, *, fail: bool = False, hang: bool = False) -> None:
        self.fail = fail
        self.hang = hang
        self.connects = 0
        self.executed: list[str] = []

    @asynccontextmanager
    async def connect(self) -> AsyncGenerator[_FakeConnection]:
        self.connects += 1
        if self.hang:
            await asyncio.sleep(10)
        yield _FakeConnection(self)


def _provider(engine: _FakeEngine) -> Callable[[], AsyncEngine]:
    """Adapt the fake to the engine-provider signature the helper expects."""
    return lambda: cast(AsyncEngine, engine)


class TestCachedEngineCheck:
    """Tests for the shared database-connectivity probe."""

    @pytest.mark.asyncio
    async def test_healthy_engine_returns_true(self):
        """A working engine reports healthy and runs SELECT 1."""
        engine = _FakeEngine()
        check = cached_engine_check(_provider(engine))

        assert await check() is True
        assert engine.connects == 1
        assert engine.executed == ["SELECT 1"]

    @pytest.mark.asyncio
    async def test_failing_query_returns_false(self):
        """A query error is swallowed and reported as unhealthy."""
        engine = _FakeEngine(fail=True)
        check = cached_engine_check(_provider(engine))

        assert await check() is False

    @pytest.mark.asyncio
    async def test_provider_failure_returns_false(self):
        """An engine that cannot be built (pool not initialized) is unhealthy."""

        def provider() -> AsyncEngine:
            raise RuntimeError("engine not initialized")

        check = cached_engine_check(provider)

        assert await check() is False

    @pytest.mark.asyncio
    async def test_result_is_cached_within_ttl(self):
        """Repeat probes inside the TTL reuse the result without a connection."""
        engine = _FakeEngine()
        check = cached_engine_check(_provider(engine), ttl_seconds=60.0)

        assert await check() is True
        assert await check() is True
        assert engine.connects == 1

    @pytest.mark.asyncio
    async def test_failure_is_cached_within_ttl(self):
        """A failed probe is cached too, so a down database is not hammered."""
        engine = _FakeEngine(fail=True)
        check = cached_engine_check(_provider(engine), ttl_seconds=60.0)

        assert await check() is False
        engine.fail = False
        assert await check() is False
        assert engine.connects == 1

    @pytest.mark.asyncio
    async def test_expired_cache_reprobes(self):
        """Once the TTL lapses the engine is probed again and recovery shows up."""
        engine = _FakeEngine(fail=True)
        check = cached_engine_check(_provider(engine), ttl_seconds=0.0)

        assert await check() is False
        engine.fail = False
        assert await check() is True
        assert engine.connects == 2

    @pytest.mark.asyncio
    async def test_hung_engine_times_out_via_checker(self):
        """The checker's timeout bounds a hung probe; the copies had no inner timeout."""
        engine = _FakeEngine(hang=True)
        checker = HealthChecker(service_name="test", version="1.0.0")
        checker.add_check("database", cached_engine_check(_provider(engine)), timeout=0.1)

        status, checks = await checker.check_health()

        assert status == HealthStatus.UNHEALTHY
        assert checks["database"]["healthy"] is False
        assert "timed out" in checks["database"].get("message", "")

    @pytest.mark.asyncio
    async def test_registers_with_health_checker(self):
        """The returned callable plugs straight into add_check."""
        engine = _FakeEngine()
        checker = HealthChecker(service_name="test", version="1.0.0")
        checker.add_check("database", cached_engine_check(_provider(engine)))

        status, checks = await checker.check_health()

        assert status == HealthStatus.HEALTHY
        assert checks["database"]["healthy"] is True
        assert checks["database"]["critical"] is True


class TestCheckKafka:
    """Tests for the lazy-import Kafka connectivity probe."""

    @pytest.mark.asyncio
    async def test_unreachable_broker_returns_false(self):
        """A dead bootstrap address fails gracefully (no exception, False)."""
        from llamatrade_common.health import check_kafka

        assert await check_kafka("127.0.0.1:1", timeout=2.0) is False

    @pytest.mark.asyncio
    async def test_bootstrap_defaults_from_env(self, monkeypatch):
        """Without an explicit argument the probe reads KAFKA_BOOTSTRAP_SERVERS."""
        from llamatrade_common.health import check_kafka

        monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:1")
        assert await check_kafka(timeout=2.0) is False

    @pytest.mark.asyncio
    async def test_is_alive_true_answers_without_a_connection(self):
        """A live-transport probe returns True and opens no broker connection."""
        from llamatrade_common.health import check_kafka

        assert await check_kafka("127.0.0.1:1", is_alive=lambda: True) is True

    @pytest.mark.asyncio
    async def test_is_alive_false_returns_false(self):
        from llamatrade_common.health import check_kafka

        assert await check_kafka("127.0.0.1:1", is_alive=lambda: False) is False

    @pytest.mark.asyncio
    async def test_is_alive_async_supported(self):
        from llamatrade_common.health import check_kafka

        async def alive() -> bool:
            return True

        assert await check_kafka("127.0.0.1:1", is_alive=alive) is True

    @pytest.mark.asyncio
    async def test_is_alive_exception_returns_false(self):
        """A liveness probe that raises reports unhealthy, not an error."""
        from llamatrade_common.health import check_kafka

        def boom() -> bool:
            raise RuntimeError("transport gone")

        assert await check_kafka("127.0.0.1:1", is_alive=boom) is False


class TestKafkaSecurityKwargs:
    """The probe speaks the cluster's protocol, matching the events transport."""

    def test_plaintext_is_empty(self, monkeypatch):
        from llamatrade_common.health import _kafka_security_kwargs

        monkeypatch.delenv("KAFKA_SECURITY_PROTOCOL", raising=False)
        assert _kafka_security_kwargs(None) == {}

    def test_sasl_ssl_sets_mechanism(self, monkeypatch):
        from llamatrade_common.health import _kafka_security_kwargs

        monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "SASL_SSL")
        kwargs = _kafka_security_kwargs(None)
        assert kwargs["security_protocol"] == "SASL_SSL"
        assert kwargs["sasl_mechanism"] == "OAUTHBEARER"
        assert "sasl_oauth_token_provider" not in kwargs

    def test_token_provider_included_when_supplied(self, monkeypatch):
        from aiokafka.abc import AbstractTokenProvider

        from llamatrade_common.health import _kafka_security_kwargs

        class _StubTokenProvider(AbstractTokenProvider):
            async def token(self) -> str:
                return "stub"

        monkeypatch.setenv("KAFKA_SECURITY_PROTOCOL", "SASL_SSL")
        provider = _StubTokenProvider()
        assert _kafka_security_kwargs(provider)["sasl_oauth_token_provider"] is provider
