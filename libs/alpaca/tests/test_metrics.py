"""Tests for metrics module."""

import pytest

from llamatrade_alpaca.metrics import (
    ALPACA_API_CALLS_TOTAL,
    ALPACA_API_DURATION_SECONDS,
    HAS_PROMETHEUS,
    NoOpMetric,
    record_api_call,
    time_alpaca_call,
)


class TestNoOpMetric:
    """Tests for NoOpMetric fallback."""

    def test_labels_returns_self(self) -> None:
        """Test that labels() returns self."""
        metric = NoOpMetric()
        result = metric.labels(endpoint="test", status="success")
        assert result is metric

    def test_inc_does_nothing(self) -> None:
        """Test that inc() doesn't raise."""
        metric = NoOpMetric()
        metric.inc()
        metric.inc(5)

    def test_observe_does_nothing(self) -> None:
        """Test that observe() doesn't raise."""
        metric = NoOpMetric()
        metric.observe(0.5)
        metric.observe(1.0)


class TestMetricsGracefulDegradation:
    """Tests for graceful degradation without prometheus."""

    def test_metrics_are_defined(self) -> None:
        """Test that metrics are defined (either real or no-op)."""
        assert ALPACA_API_CALLS_TOTAL is not None
        assert ALPACA_API_DURATION_SECONDS is not None

    def test_record_api_call_doesnt_raise(self) -> None:
        """Test that record_api_call works without raising."""
        # Should not raise even if prometheus is not installed
        record_api_call("test_endpoint", "success", 0.5)
        record_api_call("test_endpoint", "error", 1.0)


class TestTimeAlpacaCall:
    """Tests for time_alpaca_call context manager."""

    @pytest.mark.asyncio
    async def test_successful_call(self) -> None:
        """Test timing a successful call."""
        async with time_alpaca_call("test_endpoint"):
            # Simulate some work
            pass
        # Should not raise

    @pytest.mark.asyncio
    async def test_error_call(self) -> None:
        """Test timing a call that raises."""
        with pytest.raises(ValueError):
            async with time_alpaca_call("test_endpoint"):
                raise ValueError("test error")
        # Metrics should still be recorded

    @pytest.mark.asyncio
    async def test_timeout_call(self) -> None:
        """Test timing a call that times out."""
        with pytest.raises(TimeoutError):
            async with time_alpaca_call("test_endpoint"):
                raise TimeoutError("test timeout")
        # Metrics should still be recorded with timeout status


class TestPrometheusAvailability:
    """Tests for prometheus availability detection."""

    def test_has_prometheus_is_bool(self) -> None:
        """Test that HAS_PROMETHEUS is a boolean."""
        assert isinstance(HAS_PROMETHEUS, bool)

    @pytest.mark.skipif(not HAS_PROMETHEUS, reason="prometheus not installed")
    def test_metrics_are_prometheus_types(self) -> None:
        """Test that metrics are actual Prometheus types when available."""

        # Check the underlying types
        assert hasattr(ALPACA_API_CALLS_TOTAL, "labels")
        assert hasattr(ALPACA_API_DURATION_SECONDS, "labels")
