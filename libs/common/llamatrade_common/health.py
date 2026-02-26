"""Health check utilities for LlamaTrade services.

This module provides standardized health check endpoints and
dependency health checking for databases, caches, and external services.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TypedDict

from fastapi import APIRouter, Response
from pydantic import BaseModel


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
        import time

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
        async def health_check(response: Response) -> HealthCheckResponse:
            """Full health check including all dependencies."""
            status, checks = await self.check_health()

            if status == HealthStatus.UNHEALTHY:
                response.status_code = 503
            elif status == HealthStatus.DEGRADED:
                response.status_code = 200  # Still operational

            return HealthCheckResponse(
                status=status,
                timestamp=datetime.utcnow().isoformat() + "Z",
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

        return router


# =============================================================================
# Common Health Check Functions
# =============================================================================


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
        from collections.abc import Awaitable

        from redis.asyncio import Redis

        client = Redis.from_url(redis_url)
        result = client.ping()
        if isinstance(result, Awaitable):
            await result
        await client.aclose()
        return True
    except Exception as e:
        logger.warning("Redis health check failed: %s", e)
        return False


async def check_http_endpoint(url: str, timeout: float = 5.0) -> bool:
    """Check an HTTP endpoint.

    Args:
        url: URL to check
        timeout: Request timeout

    Returns:
        True if endpoint returns 2xx
    """
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=timeout)
            return bool(200 <= response.status_code < 300)
    except Exception as e:
        logger.warning("HTTP health check failed for %s: %s", url, e)
        return False
