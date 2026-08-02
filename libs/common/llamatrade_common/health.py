"""Health check utilities for LlamaTrade services.

This module provides standardized health check endpoints and
dependency health checking for databases, caches, and external services.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, TypedDict

from fastapi import APIRouter, Response
from pydantic import BaseModel

if TYPE_CHECKING:
    from aiokafka.abc import AbstractTokenProvider
    from sqlalchemy.ext.asyncio import AsyncEngine


class CheckDetails(TypedDict, total=False):
    """Optional details from a health check."""

    connection_count: int
    pool_size: int
    version: str
    lag_ms: float


class CheckResultDict(TypedDict, total=False):
    """Dictionary representation of check result."""

    healthy: bool
    latency_ms: float
    critical: bool
    message: str


logger = logging.getLogger(__name__)


class HealthStatus(StrEnum):
    """Health status values."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class DependencyCheck:
    """A health check for a dependency."""

    name: str
    check_fn: Callable[[], Awaitable[bool]]
    critical: bool = True
    timeout: float = 5.0


@dataclass
class CheckResult:
    """Result of a health check."""

    name: str
    healthy: bool
    latency_ms: float
    message: str | None = None
    details: CheckDetails = field(default_factory=CheckDetails)


class HealthCheckResponse(BaseModel):
    """Health check response model."""

    status: HealthStatus
    timestamp: str
    service: str
    version: str
    checks: dict[str, CheckResultDict]


class HealthChecker:
    """Health checker that manages dependency checks.

    Example:
        health_checker = HealthChecker(
            service_name="auth",
            version="1.0.0",
        )

        # Add database check
        health_checker.add_check(
            "database",
            check_database,
            critical=True,
        )

        # Add cache check
        health_checker.add_check(
            "redis",
            check_redis,
            critical=False,  # Service can work without cache
        )

        # Create router with health endpoints
        router = health_checker.create_router()
        app.include_router(router)
    """

    def __init__(
        self,
        service_name: str,
        version: str = "0.0.0",
    ):
        self.service_name = service_name
        self.version = version
        self.checks: list[DependencyCheck] = []

    def add_check(
        self,
        name: str,
        check_fn: Callable[[], Awaitable[bool]],
        critical: bool = True,
        timeout: float = 5.0,
    ) -> None:
        """Add a health check.

        Args:
            name: Name of the dependency
            check_fn: Async function that returns True if healthy
            critical: Whether this dependency is critical for service operation
            timeout: Timeout for the check in seconds
        """
        self.checks.append(
            DependencyCheck(
                name=name,
                check_fn=check_fn,
                critical=critical,
                timeout=timeout,
            )
        )

    async def _run_check(self, check: DependencyCheck) -> CheckResult:
        """Run a single health check with timeout."""
        start = time.perf_counter()

        try:
            result = await asyncio.wait_for(
                check.check_fn(),
                timeout=check.timeout,
            )
            latency_ms = (time.perf_counter() - start) * 1000

            return CheckResult(
                name=check.name,
                healthy=result,
                latency_ms=round(latency_ms, 2),
            )

        except TimeoutError:
            latency_ms = check.timeout * 1000
            return CheckResult(
                name=check.name,
                healthy=False,
                latency_ms=round(latency_ms, 2),
                message=f"Check timed out after {check.timeout}s",
            )

        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.warning("Health check %s failed: %s", check.name, e)
            return CheckResult(
                name=check.name,
                healthy=False,
                latency_ms=round(latency_ms, 2),
                message=str(e),
            )

    async def check_health(self) -> tuple[HealthStatus, dict[str, CheckResultDict]]:
        """Run all health checks and return overall status.

        Returns:
            Tuple of (overall_status, check_results)
        """
        if not self.checks:
            return HealthStatus.HEALTHY, {}

        # Run all checks concurrently
        results = await asyncio.gather(*[self._run_check(check) for check in self.checks])

        # Build response
        checks_dict: dict[str, CheckResultDict] = {}
        has_critical_failure = False
        has_any_failure = False

        for check, result in zip(self.checks, results, strict=True):
            checks_dict[result.name] = {
                "healthy": result.healthy,
                "latency_ms": result.latency_ms,
                "critical": check.critical,
            }
            if result.message:
                checks_dict[result.name]["message"] = result.message

            if not result.healthy:
                has_any_failure = True
                if check.critical:
                    has_critical_failure = True

        # Determine overall status
        if has_critical_failure:
            status = HealthStatus.UNHEALTHY
        elif has_any_failure:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.HEALTHY

        return status, checks_dict

    def create_router(self) -> APIRouter:
        """Create a FastAPI router with health endpoints.

        Endpoints:
            GET /health - Full health check with dependencies
            GET /health/live - Kubernetes liveness probe (always returns 200)
            GET /health/ready - Kubernetes readiness probe

        Returns:
            FastAPI router
        """
        router = APIRouter(tags=["Health"])

        @router.get("/health", response_model=HealthCheckResponse)
        async def health_check(
            response: Response,
        ) -> HealthCheckResponse:
            """Full health check including all dependencies."""
            status, checks = await self.check_health()

            if status == HealthStatus.UNHEALTHY:
                response.status_code = 503
            elif status == HealthStatus.DEGRADED:
                response.status_code = 200  # Still operational

            return HealthCheckResponse(
                status=status,
                timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                service=self.service_name,
                version=self.version,
                checks=checks,
            )

        @router.get("/health/live")
        async def liveness_probe() -> dict[str, str]:
            """Kubernetes liveness probe.

            Always returns 200 if the process is running.
            """
            return {"status": "ok"}

        @router.get("/health/ready")
        async def readiness_probe(
            response: Response,
        ) -> dict[str, str | dict[str, CheckResultDict]]:
            """Kubernetes readiness probe.

            Returns 200 if all critical dependencies are healthy.
            """
            status, checks = await self.check_health()

            if status == HealthStatus.UNHEALTHY:
                response.status_code = 503
                return {"status": "not_ready", "checks": checks}

            return {"status": "ready", "checks": checks}

        # Mark handlers as used (they're registered via decorators)
        _ = (health_check, liveness_probe, readiness_probe)
        return router


# Common Health Check Functions


def cached_engine_check(
    engine_provider: Callable[[], AsyncEngine],
    *,
    ttl_seconds: float = 10.0,
) -> Callable[[], Awaitable[bool]]:
    """Build a ``SELECT 1`` probe over a service's shared engine.

    The engine is resolved per call, so the check can be registered before the
    pool exists. Results are cached for ``ttl_seconds`` so frequent kubelet
    probes do not each take a connection out of the pool. Any failure is logged
    and reported as unhealthy rather than raised.

    Args:
        engine_provider: Returns the shared engine (e.g. ``llamatrade_db.get_engine``)
        ttl_seconds: How long a result is reused before the engine is probed again

    Returns:
        An async callable suitable for :meth:`HealthChecker.add_check`
    """
    from sqlalchemy import text

    statement = text("SELECT 1")
    cache: tuple[float, bool] | None = None

    async def check_database() -> bool:
        """SELECT 1 on the service's shared engine, cached briefly so probes stay cheap."""
        nonlocal cache
        now = time.monotonic()
        if cache is not None and now - cache[0] < ttl_seconds:
            return cache[1]
        try:
            async with engine_provider().connect() as conn:
                await conn.execute(statement)
            healthy = True
        except Exception:
            logger.warning("Database readiness check failed", exc_info=True)
            healthy = False
        cache = (now, healthy)
        return healthy

    return check_database


async def check_postgres(database_url: str) -> bool:
    """Check PostgreSQL connection.

    Args:
        database_url: Database connection string

    Returns:
        True if healthy
    """
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(database_url, pool_pre_ping=True)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await engine.dispose()
        return True
    except Exception as e:
        logger.warning("PostgreSQL health check failed: %s", e)
        return False


async def check_redis(redis_url: str) -> bool:
    """Check Redis connection.

    Args:
        redis_url: Redis connection string

    Returns:
        True if healthy
    """
    try:
        import inspect

        from redis.asyncio import Redis

        client = Redis.from_url(redis_url)
        try:
            # ping() returns Awaitable[bool] from async client
            result = client.ping()
            if inspect.isawaitable(result):
                await result
            return True
        finally:
            await client.aclose()
    except Exception as e:
        logger.warning("Redis health check failed: %s", e)
        return False


_KAFKA_SASL_MECHANISM = "OAUTHBEARER"


class _KafkaSecurityConfig(TypedDict, total=False):
    """SASL kwargs shared with the aiokafka client (empty for PLAINTEXT).

    A TypedDict (not ``dict[str, object]``) so ``**``-spreading it into the typed
    ``AIOKafkaProducer`` constructor stays type-checked, matching the events
    transport's ``_SecurityConfig``.
    """

    security_protocol: str
    sasl_mechanism: str
    sasl_oauth_token_provider: AbstractTokenProvider


def _kafka_security_kwargs(token_provider: AbstractTokenProvider | None) -> _KafkaSecurityConfig:
    """SASL kwargs matching the events transport (empty for PLAINTEXT).

    Mirrors ``KafkaTransport._security_kwargs`` from ``KAFKA_SECURITY_PROTOCOL`` so
    an in-cluster probe speaks the cluster's protocol instead of a plaintext
    handshake against a TLS/SASL listener (which never completes and burns the
    whole timeout). The OAUTHBEARER token provider is optional so the reader can
    stay free of ``google.auth``; a caller with a live transport passes its own.
    """
    protocol = os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT").upper()
    if protocol == "PLAINTEXT":
        return {}
    kwargs: _KafkaSecurityConfig = {
        "security_protocol": protocol,
        "sasl_mechanism": _KAFKA_SASL_MECHANISM,
    }
    if token_provider is not None:
        kwargs["sasl_oauth_token_provider"] = token_provider
    return kwargs


async def check_kafka(
    bootstrap_servers: str | None = None,
    *,
    timeout: float = 2.0,
    is_alive: Callable[[], bool | Awaitable[bool]] | None = None,
    token_provider: AbstractTokenProvider | None = None,
) -> bool:
    """Check Kafka broker connectivity (the event backbone).

    Prefer ``is_alive``: a service holding a live shared ``KafkaTransport`` passes
    a callable reporting whether that transport's producer/consumer is connected,
    so the probe opens no second broker connection. Without it a short-lived
    producer is started under ``timeout`` using the same SASL kwargs the events
    transport uses (``KAFKA_SECURITY_PROTOCOL`` plus ``token_provider``), so the
    handshake matches the cluster instead of stalling.

    ``aiokafka`` is not a dependency of llamatrade-common; it is imported lazily,
    so only Kafka-using services (which get it via llamatrade-events) should
    register this check.

    Wire ``is_alive`` only for a role that holds a producer or a group consumer;
    a tail-only role tracks no client, so ``KafkaTransport.is_connected`` reports
    permanently ``False`` and would make this check permanently red.

    Args:
        bootstrap_servers: Broker list; defaults to ``KAFKA_BOOTSTRAP_SERVERS``.
        timeout: Seconds to wait for the connection before failing.
        is_alive: Optional liveness probe answered from the shared transport;
            wire it only for a producer/group-consumer role (not tail-only).
        token_provider: SASL/OAUTHBEARER token provider for the fallback probe.

    Returns:
        True if the shared transport reports live, or a probe producer connects
        within the timeout.
    """
    if is_alive is not None:
        try:
            outcome = is_alive()
            alive = await outcome if inspect.isawaitable(outcome) else outcome
            return bool(alive)
        except Exception as e:
            logger.warning("Kafka health check (transport liveness) failed: %s", e)
            return False

    try:
        from aiokafka import AIOKafkaProducer
    except ImportError as e:
        raise ImportError(
            "check_kafka requires aiokafka (shipped with llamatrade-events); "
            "register this check only in Kafka-using services"
        ) from e

    servers = bootstrap_servers or os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    producer = AIOKafkaProducer(
        bootstrap_servers=servers,
        request_timeout_ms=int(timeout * 1000),
        **_kafka_security_kwargs(token_provider),
    )
    try:
        await asyncio.wait_for(producer.start(), timeout=timeout)
        return True
    except Exception as e:
        logger.warning("Kafka health check failed: %s", e)
        return False
    finally:
        try:
            await producer.stop()
        except Exception:
            logger.debug("Kafka health probe close failed", exc_info=True)
