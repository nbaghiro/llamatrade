"""Tests for trading service Prometheus metrics."""

import pytest
from src.metrics import (
    ACTIVE_POSITIONS,
    ACTIVE_RUNNERS,
    ALPACA_API_CALLS_TOTAL,
    BAR_STREAM_CONNECTED,
    BAR_STREAM_RECONNECTS_TOTAL,
    BARS_PROCESSED_TOTAL,
    BRACKET_ORDERS_SUBMITTED,
    BRACKET_ORDERS_TRIGGERED,
    CURRENT_DRAWDOWN_GAUGE,
    DAILY_PNL_GAUGE,
    ORDER_SUBMISSION_DURATION,
    ORDER_SUBMISSIONS_TOTAL,
    POSITION_VALUE_GAUGE,
    RISK_CHECKS_TOTAL,
    RISK_VIOLATIONS_TOTAL,
    SIGNALS_GENERATED_TOTAL,
    STRATEGY_ERRORS_TOTAL,
    AsyncMetricsTimer,
    record_bar_latency,
    record_bar_processed,
    record_bar_stream_reconnect,
    record_bracket_order_submitted,
    record_bracket_order_triggered,
    record_order_submission,
    record_risk_check,
    record_signal,
    record_strategy_error,
    set_bar_stream_connected,
    time_alpaca_call,
    update_daily_pnl,
    update_drawdown,
    update_positions,
    update_runner_gauge,
)


class TestOrderMetrics:
    """Tests for order-related metrics."""

    def test_record_order_submission_success(self):
        """Test recording successful order submission."""
        # Get initial value
        initial = ORDER_SUBMISSIONS_TOTAL.labels(
            side="buy", order_type="market", status="success"
        )._value.get()

        record_order_submission(
            side="buy",
            order_type="market",
            status="success",
            duration=0.5,
        )

        # Verify counter incremented
        new_value = ORDER_SUBMISSIONS_TOTAL.labels(
            side="buy", order_type="market", status="success"
        )._value.get()
        assert new_value == initial + 1

    def test_record_order_submission_rejected(self):
        """Test recording rejected order submission."""
        initial = ORDER_SUBMISSIONS_TOTAL.labels(
            side="sell", order_type="limit", status="rejected_risk"
        )._value.get()

        record_order_submission(
            side="sell",
            order_type="limit",
            status="rejected_risk",
            duration=0.1,
        )

        new_value = ORDER_SUBMISSIONS_TOTAL.labels(
            side="sell", order_type="limit", status="rejected_risk"
        )._value.get()
        assert new_value == initial + 1


class TestBracketOrderMetrics:
    """Tests for bracket order metrics."""

    def test_record_bracket_order_submitted(self):
        """Test recording bracket order submission."""
        initial_sl = BRACKET_ORDERS_SUBMITTED.labels(bracket_type="stop_loss")._value.get()
        initial_tp = BRACKET_ORDERS_SUBMITTED.labels(bracket_type="take_profit")._value.get()

        record_bracket_order_submitted("stop_loss")
        record_bracket_order_submitted("take_profit")

        assert (
            BRACKET_ORDERS_SUBMITTED.labels(bracket_type="stop_loss")._value.get() == initial_sl + 1
        )
        assert (
            BRACKET_ORDERS_SUBMITTED.labels(bracket_type="take_profit")._value.get()
            == initial_tp + 1
        )

    def test_record_bracket_order_triggered(self):
        """Test recording bracket order triggered."""
        initial = BRACKET_ORDERS_TRIGGERED.labels(bracket_type="stop_loss")._value.get()

        record_bracket_order_triggered("stop_loss")

        assert BRACKET_ORDERS_TRIGGERED.labels(bracket_type="stop_loss")._value.get() == initial + 1


class TestRiskMetrics:
    """Tests for risk-related metrics."""

    def test_record_risk_check_passed(self):
        """Test recording passed risk check."""
        initial = RISK_CHECKS_TOTAL.labels(result="passed")._value.get()

        record_risk_check(passed=True, violations=[], duration=0.01)

        assert RISK_CHECKS_TOTAL.labels(result="passed")._value.get() == initial + 1

    def test_record_risk_check_failed_with_violations(self):
        """Test recording failed risk check with violations."""
        initial_failed = RISK_CHECKS_TOTAL.labels(result="failed")._value.get()
        initial_max_order = RISK_VIOLATIONS_TOTAL.labels(
            violation_type="max_order_value"
        )._value.get()
        initial_daily_loss = RISK_VIOLATIONS_TOTAL.labels(violation_type="daily_loss")._value.get()

        record_risk_check(
            passed=False,
            violations=[
                "Order value $10000 exceeds limit $5000",
                "Daily loss limit exceeded",
            ],
            duration=0.02,
        )

        assert RISK_CHECKS_TOTAL.labels(result="failed")._value.get() == initial_failed + 1
        assert (
            RISK_VIOLATIONS_TOTAL.labels(violation_type="max_order_value")._value.get()
            == initial_max_order + 1
        )
        assert (
            RISK_VIOLATIONS_TOTAL.labels(violation_type="daily_loss")._value.get()
            == initial_daily_loss + 1
        )

    def test_record_risk_check_position_violation(self):
        """Test recording position size violation."""
        initial = RISK_VIOLATIONS_TOTAL.labels(violation_type="max_position_size")._value.get()

        record_risk_check(
            passed=False,
            violations=["Position would exceed max size"],
            duration=0.01,
        )

        assert (
            RISK_VIOLATIONS_TOTAL.labels(violation_type="max_position_size")._value.get()
            == initial + 1
        )


class TestStrategyMetrics:
    """Tests for strategy runner metrics."""

    def test_record_signal(self):
        """Test recording trading signals."""
        initial_buy = SIGNALS_GENERATED_TOTAL.labels(signal_type="buy")._value.get()
        initial_sell = SIGNALS_GENERATED_TOTAL.labels(signal_type="sell")._value.get()

        record_signal("buy")
        record_signal("sell")
        record_signal("buy")

        assert SIGNALS_GENERATED_TOTAL.labels(signal_type="buy")._value.get() == initial_buy + 2
        assert SIGNALS_GENERATED_TOTAL.labels(signal_type="sell")._value.get() == initial_sell + 1

    def test_record_bar_processed(self):
        """Test recording bar processing."""
        initial = BARS_PROCESSED_TOTAL.labels(symbol="AAPL")._value.get()

        record_bar_processed("AAPL", duration=0.005)

        assert BARS_PROCESSED_TOTAL.labels(symbol="AAPL")._value.get() == initial + 1

    def test_record_strategy_error(self):
        """Test recording strategy errors."""
        initial = STRATEGY_ERRORS_TOTAL.labels(error_type="signal_generation")._value.get()

        record_strategy_error("signal_generation")

        assert (
            STRATEGY_ERRORS_TOTAL.labels(error_type="signal_generation")._value.get() == initial + 1
        )

    def test_update_runner_gauge(self):
        """Test updating active runners gauge."""
        update_runner_gauge(5)
        assert ACTIVE_RUNNERS._value.get() == 5

        update_runner_gauge(3)
        assert ACTIVE_RUNNERS._value.get() == 3


class TestBarStreamMetrics:
    """Tests for bar stream metrics."""

    def test_record_bar_latency(self):
        """Test recording bar latency."""
        # Just verify it doesn't raise
        record_bar_latency(0.5)
        record_bar_latency(1.2)

    def test_record_bar_stream_reconnect(self):
        """Test recording reconnection."""
        initial = BAR_STREAM_RECONNECTS_TOTAL._value.get()

        record_bar_stream_reconnect()

        assert BAR_STREAM_RECONNECTS_TOTAL._value.get() == initial + 1

    def test_set_bar_stream_connected(self):
        """Test setting connection status."""
        set_bar_stream_connected(True)
        assert BAR_STREAM_CONNECTED._value.get() == 1

        set_bar_stream_connected(False)
        assert BAR_STREAM_CONNECTED._value.get() == 0


class TestPositionMetrics:
    """Tests for position metrics."""

    def test_update_positions(self):
        """Test updating position metrics."""
        update_positions("tenant-1", "session-1", count=3, total_value=15000.0)

        assert (
            ACTIVE_POSITIONS.labels(tenant_id="tenant-1", session_id="session-1")._value.get() == 3
        )
        assert (
            POSITION_VALUE_GAUGE.labels(tenant_id="tenant-1", session_id="session-1")._value.get()
            == 15000.0
        )

    def test_update_daily_pnl(self):
        """Test updating daily P&L gauge."""
        update_daily_pnl("tenant-1", "session-1", pnl=1500.50)

        assert (
            DAILY_PNL_GAUGE.labels(tenant_id="tenant-1", session_id="session-1")._value.get()
            == 1500.50
        )

    def test_update_drawdown(self):
        """Test updating drawdown gauge."""
        update_drawdown("tenant-1", "session-1", drawdown_pct=2.5)

        assert (
            CURRENT_DRAWDOWN_GAUGE.labels(tenant_id="tenant-1", session_id="session-1")._value.get()
            == 2.5
        )


class TestAsyncMetricsTimer:
    """Tests for async metrics timer."""

    @pytest.mark.asyncio
    async def test_async_metrics_timer(self):
        """Test async context manager timing."""
        import asyncio

        async with AsyncMetricsTimer(
            ORDER_SUBMISSION_DURATION, {"side": "buy", "order_type": "market"}
        ):
            await asyncio.sleep(0.01)

        # Just verify it doesn't raise and completes


class TestAlpacaApiMetrics:
    """Tests for Alpaca API metrics."""

    @pytest.mark.asyncio
    async def test_time_alpaca_call_success(self):
        """Test timing successful API call."""
        initial = ALPACA_API_CALLS_TOTAL.labels(
            endpoint="test_endpoint", status="success"
        )._value.get()

        async with time_alpaca_call("test_endpoint"):
            pass

        assert (
            ALPACA_API_CALLS_TOTAL.labels(endpoint="test_endpoint", status="success")._value.get()
            == initial + 1
        )

    @pytest.mark.asyncio
    async def test_time_alpaca_call_error(self):
        """Test timing failed API call."""
        initial = ALPACA_API_CALLS_TOTAL.labels(endpoint="test_error", status="error")._value.get()

        with pytest.raises(ValueError):
            async with time_alpaca_call("test_error"):
                raise ValueError("Test error")

        assert (
            ALPACA_API_CALLS_TOTAL.labels(endpoint="test_error", status="error")._value.get()
            == initial + 1
        )

    @pytest.mark.asyncio
    async def test_time_alpaca_call_timeout(self):
        """Test timing timeout API call."""
        initial = ALPACA_API_CALLS_TOTAL.labels(
            endpoint="test_timeout", status="timeout"
        )._value.get()

        with pytest.raises(TimeoutError):
            async with time_alpaca_call("test_timeout"):
                raise TimeoutError("Test timeout")

        assert (
            ALPACA_API_CALLS_TOTAL.labels(endpoint="test_timeout", status="timeout")._value.get()
            == initial + 1
        )
