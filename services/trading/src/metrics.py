"""Prometheus metrics for the trading service.

This module provides trading-specific metrics beyond the standard metrics
from llamatrade_common. These metrics cover:
- Order submission and execution
- Risk checks and violations
- Strategy signals and execution
- Bar stream latency and reconnections
- Alpaca API performance
- Active runners and sessions
"""

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import TracebackType
from typing import ParamSpec, TypeVar

from prometheus_client import Counter, Gauge, Histogram

P = ParamSpec("P")
R = TypeVar("R")

# =============================================================================
# Order Metrics
# =============================================================================

ORDER_SUBMISSION_DURATION = Histogram(
    "trading_order_submission_duration_seconds",
    "Time to submit an order to Alpaca",
    ["side", "order_type"],
    buckets=(0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 10.0),
)

ORDER_SUBMISSIONS_TOTAL = Counter(
    "trading_order_submissions_total",
    "Total order submissions",
    ["side", "order_type", "status"],  # status: success, rejected_risk, rejected_api
)

ORDER_SYNC_DURATION = Histogram(
    "trading_order_sync_duration_seconds",
    "Time to sync order status with Alpaca",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0),
)

ORDERS_SYNCED_TOTAL = Counter(
    "trading_orders_synced_total",
    "Total orders synced with Alpaca",
    ["status_change"],  # filled, cancelled, partial, no_change
)

# =============================================================================
# Bracket Order Metrics
# =============================================================================

BRACKET_ORDERS_SUBMITTED = Counter(
    "trading_bracket_orders_submitted_total",
    "Total bracket orders submitted",
    ["bracket_type"],  # stop_loss, take_profit
)

BRACKET_ORDERS_TRIGGERED = Counter(
    "trading_bracket_orders_triggered_total",
    "Total bracket orders that filled",
    ["bracket_type"],  # stop_loss, take_profit
)

BRACKET_OCO_CONFLICTS = Counter(
    "trading_bracket_oco_conflicts_total",
    "Total OCO conflicts where both bracket orders filled simultaneously",
    ["outcome"],  # both_filled, cancelled_already, lock_contention
)

# =============================================================================
# Risk Metrics
# =============================================================================

RISK_CHECKS_TOTAL = Counter(
    "trading_risk_checks_total",
    "Total risk checks performed",
    ["result"],  # passed, failed
)

RISK_VIOLATIONS_TOTAL = Counter(
    "trading_risk_violations_total",
    "Risk violations by type",
    ["violation_type"],  # max_order_value, max_position_size, daily_loss, rate_limit, symbol
)

RISK_CHECK_DURATION = Histogram(
    "trading_risk_check_duration_seconds",
    "Time to perform risk checks",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25),
)

DAILY_PNL_GAUGE = Gauge(
    "trading_daily_pnl_dollars",
    "Current day's P&L in dollars",
    ["tenant_id", "session_id"],
)

CURRENT_DRAWDOWN_GAUGE = Gauge(
    "trading_current_drawdown_percent",
    "Current drawdown percentage from day's high",
    ["tenant_id", "session_id"],
)

# =============================================================================
# Strategy Runner Metrics
# =============================================================================

ACTIVE_RUNNERS = Gauge(
    "trading_active_runners",
    "Number of active strategy runners",
)

SIGNALS_GENERATED_TOTAL = Counter(
    "trading_signals_generated_total",
    "Total trading signals generated",
    ["signal_type"],  # buy, sell, short, cover
)

SIGNAL_PROCESSING_DURATION = Histogram(
    "trading_signal_processing_duration_seconds",
    "Time to process a trading signal",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5),
)

BAR_PROCESSING_DURATION = Histogram(
    "trading_bar_processing_duration_seconds",
    "Time to process an incoming bar",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1),
)

BARS_PROCESSED_TOTAL = Counter(
    "trading_bars_processed_total",
    "Total bars processed",
    ["symbol"],
)

STRATEGY_ERRORS_TOTAL = Counter(
    "trading_strategy_errors_total",
    "Strategy execution errors",
    ["error_type"],  # signal_generation, order_submission, other
)

# =============================================================================
# Bar Stream Metrics
# =============================================================================

BAR_STREAM_LATENCY = Histogram(
    "trading_bar_stream_latency_seconds",
    "Latency from bar timestamp to receipt",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

BAR_STREAM_RECONNECTS_TOTAL = Counter(
    "trading_bar_stream_reconnects_total",
    "Number of bar stream reconnections",
)

BAR_STREAM_CONNECTED = Gauge(
    "trading_bar_stream_connected",
    "Whether bar stream is connected (1) or not (0)",
)

# =============================================================================
# Trade Stream Metrics
# =============================================================================

TRADE_STREAM_EVENTS_TOTAL = Counter(
    "trading_trade_stream_events_total",
    "Total trade stream events by type",
    ["event_type"],  # new, fill, partial_fill, canceled, rejected, etc.
)

TRADE_STREAM_RECONNECTS_TOTAL = Counter(
    "trading_trade_stream_reconnects_total",
    "Number of trade stream reconnections",
)

TRADE_STREAM_CONNECTED = Gauge(
    "trading_trade_stream_connected",
    "Whether trade stream is connected (1) or not (0)",
)

FILL_PROCESSING_DURATION = Histogram(
    "trading_fill_processing_duration_seconds",
    "Time to process a fill event and update position",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25),
)

FILLS_PROCESSED_TOTAL = Counter(
    "trading_fills_processed_total",
    "Total fills processed",
    ["side", "fill_type"],  # fill_type: full, partial
)

# =============================================================================
# Alpaca API Metrics
# =============================================================================

ALPACA_API_CALLS_TOTAL = Counter(
    "trading_alpaca_api_calls_total",
    "Total Alpaca API calls",
    ["endpoint", "status"],  # status: success, error, timeout
)

ALPACA_API_DURATION = Histogram(
    "trading_alpaca_api_duration_seconds",
    "Alpaca API call duration",
    ["endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

# =============================================================================
# Position Metrics
# =============================================================================

ACTIVE_POSITIONS = Gauge(
    "trading_active_positions",
    "Number of active positions",
    ["tenant_id", "session_id"],
)

POSITION_VALUE_GAUGE = Gauge(
    "trading_position_value_dollars",
    "Total value of open positions",
    ["tenant_id", "session_id"],
)

# =============================================================================
# Position Reconciliation Metrics
# =============================================================================

POSITION_RECONCILIATION_TOTAL = Counter(
    "trading_position_reconciliation_total",
    "Total position reconciliation checks",
    ["result"],  # match, drift_corrected, drift_alerted, error
)

POSITION_DRIFT_DETECTED = Counter(
    "trading_position_drift_detected_total",
    "Position drifts detected by type",
    ["drift_type"],  # missing_local, missing_broker, quantity_mismatch, side_mismatch
)

POSITION_DRIFT_QUANTITY_PERCENT = Histogram(
    "trading_position_drift_quantity_percent",
    "Percentage drift in position quantity",
    ["symbol"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 25.0, 50.0, 100.0),
)

POSITION_RECONCILIATION_DURATION = Histogram(
    "trading_position_reconciliation_duration_seconds",
    "Time to perform position reconciliation",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)


# =============================================================================
# Helper Functions and Decorators
# =============================================================================


class AsyncMetricsTimer:
    """Async context manager for timing operations and recording to Prometheus histogram.

    Usage:
        async with AsyncMetricsTimer(ORDER_SUBMISSION_DURATION, {"side": "buy", "order_type": "market"}):
            await submit_order(...)
    """

    def __init__(self, metric: Histogram, labels: dict[str, str]):
        self.metric = metric
        self.labels = labels
        self.start_time: float = 0

    async def __aenter__(self) -> AsyncMetricsTimer:
        self.start_time = time.perf_counter()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        duration = time.perf_counter() - self.start_time
        self.metric.labels(**self.labels).observe(duration)


@asynccontextmanager
async def time_alpaca_call(endpoint: str) -> AsyncIterator[None]:
    """Context manager to time Alpaca API calls.

    Usage:
        async with time_alpaca_call("submit_order"):
            result = await client.post("/orders", ...)
    """
    start = time.perf_counter()
    status = "success"
    try:
        yield
    except TimeoutError:
        status = "timeout"
        raise
    except Exception:
        status = "error"
        raise
    finally:
        duration = time.perf_counter() - start
        ALPACA_API_DURATION.labels(endpoint=endpoint).observe(duration)
        ALPACA_API_CALLS_TOTAL.labels(endpoint=endpoint, status=status).inc()


def record_order_submission(
    side: str,
    order_type: str,
    status: str,
    duration: float,
) -> None:
    """Record an order submission attempt.

    Args:
        side: Order side (buy, sell)
        order_type: Order type (market, limit, stop, stop_limit)
        status: Result status (success, rejected_risk, rejected_api)
        duration: Time taken in seconds
    """
    ORDER_SUBMISSIONS_TOTAL.labels(
        side=side,
        order_type=order_type,
        status=status,
    ).inc()

    ORDER_SUBMISSION_DURATION.labels(
        side=side,
        order_type=order_type,
    ).observe(duration)


def record_risk_check(passed: bool, violations: list[str], duration: float) -> None:
    """Record a risk check result.

    Args:
        passed: Whether the risk check passed
        violations: List of violation types if failed
        duration: Time taken in seconds
    """
    RISK_CHECKS_TOTAL.labels(result="passed" if passed else "failed").inc()
    RISK_CHECK_DURATION.observe(duration)

    for violation in violations:
        # Normalize violation messages to types
        if "order value" in violation.lower():
            violation_type = "max_order_value"
        elif "position" in violation.lower():
            violation_type = "max_position_size"
        elif "daily loss" in violation.lower():
            violation_type = "daily_loss"
        elif "rate limit" in violation.lower():
            violation_type = "rate_limit"
        elif "symbol" in violation.lower() or "allowed" in violation.lower():
            violation_type = "symbol"
        else:
            violation_type = "other"

        RISK_VIOLATIONS_TOTAL.labels(violation_type=violation_type).inc()


def record_signal(signal_type: str) -> None:
    """Record a generated trading signal.

    Args:
        signal_type: Type of signal (buy, sell, short, cover)
    """
    SIGNALS_GENERATED_TOTAL.labels(signal_type=signal_type).inc()


def record_bar_latency(latency_seconds: float) -> None:
    """Record bar stream latency.

    Args:
        latency_seconds: Time from bar timestamp to receipt
    """
    BAR_STREAM_LATENCY.observe(latency_seconds)


def record_bar_processed(symbol: str, duration: float) -> None:
    """Record a processed bar.

    Args:
        symbol: Trading symbol
        duration: Processing time in seconds
    """
    BARS_PROCESSED_TOTAL.labels(symbol=symbol).inc()
    BAR_PROCESSING_DURATION.observe(duration)


def update_runner_gauge(active_count: int) -> None:
    """Update the active runners gauge.

    Args:
        active_count: Number of active runners
    """
    ACTIVE_RUNNERS.set(active_count)


def update_daily_pnl(tenant_id: str, session_id: str, pnl: float) -> None:
    """Update daily P&L gauge.

    Args:
        tenant_id: Tenant identifier
        session_id: Session identifier
        pnl: Current P&L in dollars
    """
    DAILY_PNL_GAUGE.labels(tenant_id=tenant_id, session_id=session_id).set(pnl)


def update_drawdown(tenant_id: str, session_id: str, drawdown_pct: float) -> None:
    """Update drawdown gauge.

    Args:
        tenant_id: Tenant identifier
        session_id: Session identifier
        drawdown_pct: Current drawdown percentage
    """
    CURRENT_DRAWDOWN_GAUGE.labels(tenant_id=tenant_id, session_id=session_id).set(drawdown_pct)


def update_positions(tenant_id: str, session_id: str, count: int, total_value: float) -> None:
    """Update position metrics.

    Args:
        tenant_id: Tenant identifier
        session_id: Session identifier
        count: Number of open positions
        total_value: Total value of positions
    """
    ACTIVE_POSITIONS.labels(tenant_id=tenant_id, session_id=session_id).set(count)
    POSITION_VALUE_GAUGE.labels(tenant_id=tenant_id, session_id=session_id).set(total_value)


def record_bar_stream_reconnect() -> None:
    """Record a bar stream reconnection."""
    BAR_STREAM_RECONNECTS_TOTAL.inc()


def set_bar_stream_connected(connected: bool) -> None:
    """Set bar stream connection status.

    Args:
        connected: Whether stream is connected
    """
    BAR_STREAM_CONNECTED.set(1 if connected else 0)


def record_bracket_order_submitted(bracket_type: str) -> None:
    """Record a bracket order submission.

    Args:
        bracket_type: Type of bracket order (stop_loss, take_profit)
    """
    BRACKET_ORDERS_SUBMITTED.labels(bracket_type=bracket_type).inc()


def record_bracket_order_triggered(bracket_type: str) -> None:
    """Record a bracket order that was triggered/filled.

    Args:
        bracket_type: Type of bracket order (stop_loss, take_profit)
    """
    BRACKET_ORDERS_TRIGGERED.labels(bracket_type=bracket_type).inc()


def record_bracket_oco_conflict(outcome: str) -> None:
    """Record an OCO conflict during bracket order handling.

    Args:
        outcome: Type of conflict (both_filled, cancelled_already, lock_contention)
    """
    BRACKET_OCO_CONFLICTS.labels(outcome=outcome).inc()


def record_strategy_error(error_type: str) -> None:
    """Record a strategy execution error.

    Args:
        error_type: Type of error (signal_generation, order_submission, other)
    """
    STRATEGY_ERRORS_TOTAL.labels(error_type=error_type).inc()


def record_position_reconciliation(
    result: str,
    duration: float,
    drift_type: str | None = None,
    symbol: str | None = None,
    drift_percent: float | None = None,
) -> None:
    """Record a position reconciliation check.

    Args:
        result: Reconciliation result (match, drift_corrected, drift_alerted, error)
        duration: Time taken in seconds
        drift_type: Type of drift if detected (missing_local, missing_broker,
                   quantity_mismatch, side_mismatch)
        symbol: Symbol with drift (if any)
        drift_percent: Percentage drift in quantity (if applicable)
    """
    POSITION_RECONCILIATION_TOTAL.labels(result=result).inc()
    POSITION_RECONCILIATION_DURATION.observe(duration)

    if drift_type:
        POSITION_DRIFT_DETECTED.labels(drift_type=drift_type).inc()

    if symbol and drift_percent is not None:
        POSITION_DRIFT_QUANTITY_PERCENT.labels(symbol=symbol).observe(abs(drift_percent))


def record_trade_stream_event(event_type: str) -> None:
    """Record a trade stream event.

    Args:
        event_type: Type of event (new, fill, partial_fill, canceled, rejected, etc.)
    """
    TRADE_STREAM_EVENTS_TOTAL.labels(event_type=event_type).inc()


def record_trade_stream_reconnect() -> None:
    """Record a trade stream reconnection."""
    TRADE_STREAM_RECONNECTS_TOTAL.inc()


def set_trade_stream_connected(connected: bool) -> None:
    """Set trade stream connection status.

    Args:
        connected: Whether stream is connected
    """
    TRADE_STREAM_CONNECTED.set(1 if connected else 0)


def record_fill_processed(
    side: str,
    fill_type: str,
    duration: float,
) -> None:
    """Record a fill event processing.

    Args:
        side: Order side (buy, sell)
        fill_type: Type of fill (full, partial)
        duration: Processing time in seconds
    """
    FILLS_PROCESSED_TOTAL.labels(side=side, fill_type=fill_type).inc()
    FILL_PROCESSING_DURATION.observe(duration)
