"""Tests for Prometheus metrics utilities."""

import asyncio
import time
from dataclasses import dataclass

import pytest

from llamatrade_common.metrics import (
    CACHE_HITS_TOTAL,
    CACHE_MISSES_TOTAL,
    DB_QUERY_DURATION_SECONDS,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_IN_PROGRESS,
    HTTP_REQUESTS_TOTAL,
    MetricsTimer,
    get_metrics,
    init_service_info,
    record_http_request,
    record_order,
    register_db_pool_observer,
    time_function,
)


@dataclass
class _FakePoolStats:
    """Stand-in matching the PoolStatsLike protocol."""

    checked_out: int
    checked_in: int
    max_connections: int


class TestDbPoolObserver:
    """Tests for DB connection-pool gauge registration."""

    def test_registered_provider_populates_gauges(self) -> None:
        """A registered provider's snapshot is exported on the next scrape."""
        register_db_pool_observer(
            "unittest-pool-svc",
            lambda: _FakePoolStats(checked_out=3, checked_in=5, max_connections=30),
        )

        text = get_metrics().decode()

        assert 'llamatrade_db_connections_active{service="unittest-pool-svc"} 3.0' in text
        assert 'llamatrade_db_connections_idle{service="unittest-pool-svc"} 5.0' in text
        assert 'llamatrade_db_connections_max{service="unittest-pool-svc"} 30.0' in text

    def test_provider_returning_none_is_skipped(self) -> None:
        """A provider with no engine yet (None) must not raise or emit a sample."""
        register_db_pool_observer("none-pool-svc", lambda: None)

        text = get_metrics().decode()

        assert 'service="none-pool-svc"' not in text

    def test_provider_exception_never_breaks_metrics(self) -> None:
        """A throwing provider must not break the /metrics endpoint."""

        def boom() -> _FakePoolStats:
            raise RuntimeError("provider exploded")

        register_db_pool_observer("boom-pool-svc", boom)

        # Must not raise; other metrics still serialize.
        result = get_metrics()
        assert isinstance(result, bytes)

    def test_registration_is_idempotent_per_service(self) -> None:
        """Re-registering a service replaces, not duplicates, its provider."""
        register_db_pool_observer(
            "dup-pool-svc",
            lambda: _FakePoolStats(checked_out=1, checked_in=1, max_connections=10),
        )
        register_db_pool_observer(
            "dup-pool-svc",
            lambda: _FakePoolStats(checked_out=9, checked_in=0, max_connections=10),
        )

        text = get_metrics().decode()

        # Only the latest value should be present.
        assert 'llamatrade_db_connections_active{service="dup-pool-svc"} 9.0' in text
        assert 'llamatrade_db_connections_active{service="dup-pool-svc"} 1.0' not in text


class TestServiceInfo:
    """Tests for service info initialization."""

    def test_init_service_info(self):
        """Test initializing service info metric."""
        init_service_info(
            service_name="test-service",
            version="1.2.3",
            environment="testing",
        )

        metrics = get_metrics()
        assert b"llamatrade_service_info" in metrics


class TestGetMetrics:
    """Tests for metrics export."""

    def test_get_metrics_returns_bytes(self):
        """Test that get_metrics returns bytes."""
        result = get_metrics()

        assert isinstance(result, bytes)
        # Should contain Prometheus format
        assert b"# HELP" in result or b"# TYPE" in result or len(result) > 0


class TestTimeFunction:
    """Tests for time_function decorator."""

    def test_time_sync_function(self):
        """Test timing a synchronous function."""

        @time_function(
            DB_QUERY_DURATION_SECONDS,
            {"service": "test", "operation": "select", "table": "users"},
        )
        def slow_query():
            time.sleep(0.01)
            return "result"

        result = slow_query()

        assert result == "result"

    @pytest.mark.asyncio
    async def test_time_async_function(self):
        """Test timing an asynchronous function."""

        @time_function(
            DB_QUERY_DURATION_SECONDS,
            {"service": "test", "operation": "insert", "table": "orders"},
        )
        async def async_query():
            await asyncio.sleep(0.01)
            return "async_result"

        result = await async_query()

        assert result == "async_result"

    def test_time_function_preserves_exceptions(self):
        """Test that decorator preserves exceptions."""

        @time_function(
            DB_QUERY_DURATION_SECONDS,
            {"service": "test", "operation": "delete", "table": "temp"},
        )
        def failing_query():
            raise ValueError("Query failed")

        with pytest.raises(ValueError, match="Query failed"):
            failing_query()


class TestMetricsTimer:
    """Tests for MetricsTimer context manager."""

    def test_metrics_timer_basic(self):
        """Test basic metrics timer usage."""
        with MetricsTimer(
            DB_QUERY_DURATION_SECONDS,
            {"service": "test", "operation": "update", "table": "config"},
        ):
            time.sleep(0.01)

        # Timer records duration to histogram

    def test_metrics_timer_with_exception(self):
        """Test metrics timer records even on exception."""
        with pytest.raises(RuntimeError):
            with MetricsTimer(
                DB_QUERY_DURATION_SECONDS,
                {"service": "test", "operation": "error", "table": "test"},
            ):
                raise RuntimeError("Intentional error")

        # Duration still recorded


class TestRecordHttpRequest:
    """Tests for HTTP request recording."""

    def test_record_http_request(self):
        """Test recording an HTTP request."""
        record_http_request(
            service="api",
            method="GET",
            endpoint="/users",
            status_code=200,
            duration=0.05,
        )

        # Metrics are recorded

    def test_record_http_request_error(self):
        """Test recording a failed HTTP request."""
        record_http_request(
            service="api",
            method="POST",
            endpoint="/orders",
            status_code=500,
            duration=1.5,
        )


class TestRecordOrder:
    """Tests for order metrics recording."""

    def test_record_order_basic(self):
        """Test recording a basic order."""
        record_order(
            tenant_id="tenant-123",
            side="buy",
            order_type="market",
            status="filled",
        )

    def test_record_order_with_value(self):
        """Test recording an order with value."""
        record_order(
            tenant_id="tenant-123",
            side="sell",
            order_type="limit",
            status="accepted",
            value=10000.50,
        )


class TestMetricLabels:
    """Tests for metric labels."""

    def test_http_requests_total_labels(self):
        """Test HTTP requests counter has correct labels."""
        # Increment with labels
        HTTP_REQUESTS_TOTAL.labels(
            service="test",
            method="GET",
            endpoint="/test",
            status_code="200",
        ).inc()

    def test_http_request_duration_labels(self):
        """Test HTTP request duration has correct labels."""
        HTTP_REQUEST_DURATION_SECONDS.labels(
            service="test",
            method="POST",
            endpoint="/create",
        ).observe(0.1)

    def test_http_requests_in_progress_labels(self):
        """Test in-progress gauge has correct labels."""
        gauge = HTTP_REQUESTS_IN_PROGRESS.labels(
            service="test",
            method="GET",
            endpoint="/long",
        )
        gauge.inc()
        gauge.dec()

    def test_cache_metrics_labels(self):
        """Test cache metrics have correct labels."""
        CACHE_HITS_TOTAL.labels(service="test", cache_name="users").inc()
        CACHE_MISSES_TOTAL.labels(service="test", cache_name="users").inc()
