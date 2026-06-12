"""Prometheus metrics for LlamaTrade services.

This module provides standardized metrics for HTTP requests, gRPC calls,
database operations, and custom business metrics.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from functools import wraps
from types import TracebackType
from typing import ParamSpec, Protocol, TypeVar, cast

from prometheus_client import Counter, Gauge, Histogram, Info, generate_latest

P = ParamSpec("P")
R = TypeVar("R")

# =============================================================================
# Standard Metrics
# =============================================================================

# Service info
SERVICE_INFO = Info(
    "llamatrade_service",
    "Service information",
)

# HTTP Request metrics
HTTP_REQUESTS_TOTAL = Counter(
    "llamatrade_http_requests_total",
    "Total HTTP requests",
    ["service", "method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "llamatrade_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["service", "method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0),
)

HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "llamatrade_http_requests_in_progress",
    "HTTP requests currently being processed",
    ["service", "method", "endpoint"],
)

# gRPC metrics
GRPC_REQUESTS_TOTAL = Counter(
    "llamatrade_grpc_requests_total",
    "Total gRPC requests",
    ["service", "method", "status_code"],
)

GRPC_REQUEST_DURATION_SECONDS = Histogram(
    "llamatrade_grpc_request_duration_seconds",
    "gRPC request duration in seconds",
    ["service", "method"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

# Database metrics
DB_QUERY_DURATION_SECONDS = Histogram(
    "llamatrade_db_query_duration_seconds",
    "Database query duration in seconds",
    ["service", "operation", "table"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

DB_CONNECTIONS_ACTIVE = Gauge(
    "llamatrade_db_connections_active",
    "Database connections currently checked out (in use)",
    ["service"],
)

DB_CONNECTIONS_IDLE = Gauge(
    "llamatrade_db_connections_idle",
    "Database connections idle in the pool (checked in)",
    ["service"],
)

DB_CONNECTIONS_MAX = Gauge(
    "llamatrade_db_connections_max",
    "Maximum connections the pool may open (pool_size + max_overflow)",
    ["service"],
)

# Cache metrics
CACHE_HITS_TOTAL = Counter(
    "llamatrade_cache_hits_total",
    "Total cache hits",
    ["service", "cache_name"],
)

CACHE_MISSES_TOTAL = Counter(
    "llamatrade_cache_misses_total",
    "Total cache misses",
    ["service", "cache_name"],
)

# =============================================================================
# Business Metrics
# =============================================================================

# Trading metrics
ORDERS_TOTAL = Counter(
    "llamatrade_orders_total",
    "Total orders submitted",
    ["tenant_id", "side", "type", "status"],
)

ORDERS_VALUE_TOTAL = Counter(
    "llamatrade_orders_value_total",
    "Total value of orders",
    ["tenant_id", "side"],
)

POSITIONS_ACTIVE = Gauge(
    "llamatrade_positions_active",
    "Active positions",
    ["tenant_id"],
)

# Backtest metrics
BACKTESTS_TOTAL = Counter(
    "llamatrade_backtests_total",
    "Total backtests run",
    ["tenant_id", "status"],
)

BACKTESTS_DURATION_SECONDS = Histogram(
    "llamatrade_backtest_duration_seconds",
    "Backtest execution duration",
    ["tenant_id"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800),
)

# Market data metrics
MARKET_DATA_MESSAGES_TOTAL = Counter(
    "llamatrade_market_data_messages_total",
    "Total market data messages received",
    ["data_type"],  # bars, quotes, trades
)

MARKET_DATA_LATENCY_SECONDS = Histogram(
    "llamatrade_market_data_latency_seconds",
    "Market data latency (time from exchange to receipt)",
    ["data_type"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)


# =============================================================================
# Helper Functions
# =============================================================================


def init_service_info(service_name: str, version: str, environment: str) -> None:
    """Initialize service info metric.

    Args:
        service_name: Name of the service
        version: Service version
        environment: Deployment environment
    """
    SERVICE_INFO.info(
        {
            "service": service_name,
            "version": version,
            "environment": environment,
        }
    )


class PoolStatsLike(Protocol):
    """Structural type for a DB connection-pool snapshot.

    Matches ``llamatrade_db.PoolStats`` without importing it, so this
    observability layer stays decoupled from the database layer.
    """

    @property
    def checked_out(self) -> int: ...

    @property
    def checked_in(self) -> int: ...

    @property
    def max_connections(self) -> int: ...


# Registered per service so /metrics can sample live pool counts at scrape time.
# Keyed by service name → idempotent across repeated registration (e.g. tests).
_pool_stats_providers: dict[str, Callable[[], PoolStatsLike | None]] = {}


def register_db_pool_observer(
    service_name: str,
    provider: Callable[[], PoolStatsLike | None],
) -> None:
    """Register a pool-stats provider whose values are exported on /metrics.

    The provider is sampled on every metrics scrape (see ``get_metrics``).
    Pass ``llamatrade_db.get_pool_stats`` here from the service that owns
    the engine; this module never imports the DB layer itself.
    """
    _pool_stats_providers[service_name] = provider


def _collect_db_pool_metrics() -> None:
    """Sample every registered provider and set the pool gauges."""
    for service_name, provider in _pool_stats_providers.items():
        try:
            stats = provider()
        except Exception:
            # Observability must never break the metrics endpoint.
            continue
        if stats is None:
            continue
        DB_CONNECTIONS_ACTIVE.labels(service=service_name).set(stats.checked_out)
        DB_CONNECTIONS_IDLE.labels(service=service_name).set(stats.checked_in)
        DB_CONNECTIONS_MAX.labels(service=service_name).set(stats.max_connections)


def get_metrics() -> bytes:
    """Generate Prometheus metrics in text format.

    Refreshes DB pool gauges from registered providers immediately before
    serialization so the exported counts are accurate at scrape time.

    Returns:
        Metrics in Prometheus exposition format
    """
    _collect_db_pool_metrics()
    result: bytes = generate_latest()
    return result


def time_function(
    metric: Histogram,
    labels: dict[str, str],
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to time a function and record duration.

    Args:
        metric: Histogram metric to record to
        labels: Labels to apply to the metric

    Example:
        @time_function(DB_QUERY_DURATION_SECONDS, {"service": "auth", "operation": "select"})
        async def get_user(user_id: str):
            ...
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start_time = time.perf_counter()
            try:
                # func is an async function, so we await the coroutine it returns
                coro = func(*args, **kwargs)
                result = await cast(Awaitable[R], coro)
                return result
            finally:
                duration = time.perf_counter() - start_time
                metric.labels(**labels).observe(duration)

        @wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start_time = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.perf_counter() - start_time
                metric.labels(**labels).observe(duration)

        import inspect

        if inspect.iscoroutinefunction(func):
            return cast(Callable[P, R], async_wrapper)
        return sync_wrapper

    return decorator


class MetricsTimer:
    """Context manager for timing operations.

    Example:
        labels = {"service": "auth", "operation": "select", "table": "users"}
        with MetricsTimer(DB_QUERY_DURATION_SECONDS, labels):
            result = await db.execute(query)
    """

    def __init__(self, metric: Histogram, labels: dict[str, str]):
        self.metric = metric
        self.labels = labels
        self.start_time: float = 0

    def __enter__(self) -> MetricsTimer:
        self.start_time = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        duration = time.perf_counter() - self.start_time
        self.metric.labels(**self.labels).observe(duration)


def record_http_request(
    service: str,
    method: str,
    endpoint: str,
    status_code: int,
    duration: float,
) -> None:
    """Record an HTTP request.

    Args:
        service: Service name
        method: HTTP method
        endpoint: Endpoint path
        status_code: Response status code
        duration: Request duration in seconds
    """
    HTTP_REQUESTS_TOTAL.labels(
        service=service,
        method=method,
        endpoint=endpoint,
        status_code=str(status_code),
    ).inc()

    HTTP_REQUEST_DURATION_SECONDS.labels(
        service=service,
        method=method,
        endpoint=endpoint,
    ).observe(duration)


def record_order(
    tenant_id: str,
    side: str,
    order_type: str,
    status: str,
    value: float | None = None,
) -> None:
    """Record an order for metrics.

    Args:
        tenant_id: Tenant ID
        side: Order side (buy/sell)
        order_type: Order type (market/limit/etc)
        status: Order status
        value: Optional order value
    """
    ORDERS_TOTAL.labels(
        tenant_id=tenant_id,
        side=side,
        type=order_type,
        status=status,
    ).inc()

    if value is not None:
        ORDERS_VALUE_TOTAL.labels(
            tenant_id=tenant_id,
            side=side,
        ).inc(value)
