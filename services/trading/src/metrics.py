"""Trading-service metrics, backed by ``llamatrade_telemetry``.

This module is a thin, service-local facade over the unified telemetry library.
It keeps the historical public helper API (``record_order_submission``,
``record_risk_check``, …) so existing call sites stay unchanged, but every
metric is now an OTel instrument exported in Prometheus format via
``llamatrade_telemetry``.

Most signals route through the shared ``metrics.trading`` domain namespace.
A handful of trading-only counters (order sync, bracket orders, trade-stream
events, circuit-breaker resets) and the pre-declared "extra" histograms
(order-sync / signal-processing / reconciliation duration) are created here via
the validated registry factories.

Notes:
* Per-session financial gauges (daily P&L, drawdown, position value/count keyed
  by tenant/session) were **removed** — tenant_id/session_id are forbidden as
  metric labels. Those values live in the ledger and structured logs. The
  process-level ``active_runners`` gauge remains (no labels).
* Alpaca API call metrics are emitted by the alpaca client lib
  (``llamatrade_dependency_*``, ``target="alpaca"``) and are no longer
  duplicated here. Code that wraps an Alpaca call itself should use
  ``llamatrade_telemetry.instrumentation.dependency.time_dependency``.
"""

from __future__ import annotations

from llamatrade_telemetry import counter, histogram, metrics

# ---------------------------------------------------------------------------
# Shared domain handles (histograms/gauges exposed for direct ``.observe()``
# / ``.set()`` use by call sites that already held a handle reference).
# ---------------------------------------------------------------------------
ORDER_SUBMISSION_DURATION = metrics.trading.order_submission_latency
ACTIVE_RUNNERS = metrics.trading.active_runners
BAR_STREAM_CONNECTED = metrics.trading.bar_stream_connected
TRADE_STREAM_CONNECTED = metrics.trading.trade_stream_connected

# ---------------------------------------------------------------------------
# Pre-declared "extra" histograms (buckets registered in telemetry conventions).
# ---------------------------------------------------------------------------
ORDER_SYNC_DURATION = histogram(
    "llamatrade_trading_order_sync_duration_seconds",
    (),
    "Time to sync order status with Alpaca",
)
SIGNAL_PROCESSING_DURATION = histogram(
    "llamatrade_trading_signal_processing_duration_seconds",
    (),
    "Time to process a trading signal",
)
POSITION_RECONCILIATION_DURATION = histogram(
    "llamatrade_trading_position_reconciliation_duration_seconds",
    (),
    "Time to perform position reconciliation",
)

# ---------------------------------------------------------------------------
# Trading-only counters not covered by the shared domain namespace.
# ---------------------------------------------------------------------------
ORDERS_SYNCED_TOTAL = counter(
    "llamatrade_trading_orders_synced_total",
    ["status_change"],  # filled, cancelled, partial, no_change
    "Orders synced with Alpaca by resulting status change",
)
BRACKET_ORDERS_SUBMITTED = counter(
    "llamatrade_trading_bracket_orders_submitted_total",
    ["bracket_type"],  # stop_loss, take_profit
    "Bracket orders submitted",
)
BRACKET_ORDERS_TRIGGERED = counter(
    "llamatrade_trading_bracket_orders_triggered_total",
    ["bracket_type"],  # stop_loss, take_profit
    "Bracket orders that filled",
)
BRACKET_OCO_CONFLICTS = counter(
    "llamatrade_trading_bracket_oco_conflicts_total",
    ["outcome"],  # both_filled, cancelled_already, lock_contention
    "OCO conflicts during bracket order handling",
)
TRADE_STREAM_EVENTS_TOTAL = counter(
    "llamatrade_trading_trade_stream_events_total",
    ["event_type"],  # new, fill, partial_fill, canceled, rejected, ...
    "Trade-stream events by type",
)
CIRCUIT_BREAKER_RESETS_TOTAL = counter(
    "llamatrade_trading_circuit_breaker_resets_total",
    (),
    "Circuit breaker reset events",
)


# ---------------------------------------------------------------------------
# Order metrics
# ---------------------------------------------------------------------------
def record_order_submission(
    side: str,
    order_type: str,
    status: str,
    duration: float,
) -> None:
    """Record an order submission attempt.

    Args:
        side: Order side (buy, sell).
        order_type: Order type (market, limit, stop, stop_limit).
        status: Result status (success, rejected_risk, rejected_api).
        duration: Time taken in seconds.
    """
    metrics.trading.order_submitted(side=side, type=order_type, status=status)
    ORDER_SUBMISSION_DURATION.observe(duration)


def record_ledger_publish(kind: str, status: str) -> None:
    """Record a ledger payload publish attempt (watch failures during rollout)."""
    metrics.trading.ledger_event_published(kind=kind, status=status)


def record_idempotent_replay() -> None:
    """Record an idempotent order replay.

    Emitted when a deterministic ``client_order_id`` lookup finds an order we
    already recorded, so re-submission is skipped (crash-recovery / dedup path).
    """
    metrics.trading.idempotent_replay()


# ---------------------------------------------------------------------------
# Bracket order metrics
# ---------------------------------------------------------------------------
def record_bracket_order_submitted(bracket_type: str) -> None:
    """Record a bracket order submission (bracket_type: stop_loss, take_profit)."""
    BRACKET_ORDERS_SUBMITTED.labels(bracket_type=bracket_type).inc()


def record_bracket_order_triggered(bracket_type: str) -> None:
    """Record a bracket order that was triggered/filled."""
    BRACKET_ORDERS_TRIGGERED.labels(bracket_type=bracket_type).inc()


def record_bracket_oco_conflict(outcome: str) -> None:
    """Record an OCO conflict during bracket order handling.

    Args:
        outcome: Type of conflict (both_filled, cancelled_already, lock_contention).
    """
    BRACKET_OCO_CONFLICTS.labels(outcome=outcome).inc()


# ---------------------------------------------------------------------------
# Risk metrics
# ---------------------------------------------------------------------------
def _classify_violation(violation: str) -> str:
    """Normalize a free-text violation message to a bounded violation type."""
    lowered = violation.lower()
    if "order value" in lowered:
        return "max_order_value"
    if "position" in lowered:
        return "max_position_size"
    if "daily loss" in lowered:
        return "daily_loss"
    if "rate limit" in lowered:
        return "rate_limit"
    if "symbol" in lowered or "allowed" in lowered:
        return "symbol"
    return "other"


def record_risk_check(passed: bool, violations: list[str], duration: float) -> None:
    """Record a risk check result.

    Args:
        passed: Whether the risk check passed.
        violations: List of violation messages if failed.
        duration: Time taken in seconds.
    """
    metrics.trading.risk_check(result="passed" if passed else "failed")
    metrics.trading.risk_check_duration.observe(duration)

    for violation in violations:
        metrics.trading.risk_violation(violation_type=_classify_violation(violation))


# ---------------------------------------------------------------------------
# Strategy runner metrics
# ---------------------------------------------------------------------------
def record_signal(signal_type: str) -> None:
    """Record a generated trading signal (buy, sell, short, cover)."""
    metrics.trading.signal_generated(signal_type=signal_type)


def record_bar_processed(duration: float) -> None:
    """Record a processed bar.

    Args:
        duration: Processing time in seconds.
    """
    metrics.trading.bar_processed()
    metrics.trading.bar_processing_duration.observe(duration)


def record_strategy_error(error_type: str) -> None:
    """Record a strategy execution error (signal_generation, order_submission, ...)."""
    metrics.trading.strategy_error(error_type=error_type)


def update_runner_gauge(active_count: int) -> None:
    """Update the process-level active runners gauge."""
    ACTIVE_RUNNERS.set(active_count)


# ---------------------------------------------------------------------------
# Bar stream metrics
# ---------------------------------------------------------------------------
def record_bar_latency(latency_seconds: float) -> None:
    """Record bar-stream latency (bar timestamp -> receipt)."""
    metrics.trading.bar_stream_latency.observe(latency_seconds)


def record_bar_stream_reconnect() -> None:
    """Record a bar stream reconnection."""
    metrics.trading.bar_stream_reconnect()


def set_bar_stream_connected(connected: bool) -> None:
    """Set bar-stream connection status (1 connected / 0 disconnected)."""
    BAR_STREAM_CONNECTED.set(1 if connected else 0)


# ---------------------------------------------------------------------------
# Trade stream metrics
# ---------------------------------------------------------------------------
def record_trade_stream_event(event_type: str) -> None:
    """Record a trade-stream event (new, fill, partial_fill, canceled, ...)."""
    TRADE_STREAM_EVENTS_TOTAL.labels(event_type=event_type).inc()


def record_trade_stream_reconnect() -> None:
    """Record a trade stream reconnection."""
    metrics.trading.trade_stream_reconnect()


def set_trade_stream_connected(connected: bool) -> None:
    """Set trade-stream connection status (1 connected / 0 disconnected)."""
    TRADE_STREAM_CONNECTED.set(1 if connected else 0)


def record_fill_processed(side: str, fill_type: str, duration: float) -> None:
    """Record a fill event processing.

    Args:
        side: Order side (buy, sell).
        fill_type: Type of fill (full, partial).
        duration: Processing time in seconds.
    """
    metrics.trading.fill(side=side, fill_type=fill_type)
    metrics.trading.fill_processing_duration.observe(duration)


def record_slippage(side: str, fill_price: float, est_price: float) -> None:
    """Record execution slippage of a fill versus its pre-trade estimate.

    Slippage is reported in basis points relative to the estimated price.
    A non-positive estimate (no usable reference price for the signal) is
    silently skipped — there is nothing meaningful to compare against.

    Args:
        side: Order side (buy, sell).
        fill_price: The price the order actually filled at.
        est_price: The pre-trade estimated/expected price for the signal.
    """
    if est_price <= 0:
        return
    bps = abs(fill_price - est_price) / est_price * 10_000
    metrics.trading.slippage_bps.labels(side=side).observe(bps)


# ---------------------------------------------------------------------------
# Position reconciliation metrics
# ---------------------------------------------------------------------------
def record_position_reconciliation(
    result: str,
    duration: float,
    drift_type: str | None = None,
    drift_percent: float | None = None,
) -> None:
    """Record a position reconciliation check.

    The drift magnitude is observed on a no-label histogram.

    Args:
        result: Reconciliation result (match, drift_corrected, drift_alerted, error).
        duration: Time taken in seconds.
        drift_type: Type of drift if detected (missing_local, missing_broker,
            quantity_mismatch, side_mismatch).
        drift_percent: Percentage drift in quantity (if applicable).
    """
    metrics.trading.position_reconciled(result=result)
    POSITION_RECONCILIATION_DURATION.observe(duration)

    if drift_type:
        metrics.trading.position_drift(drift_type=drift_type)

    if drift_percent is not None:
        metrics.trading.position_drift_quantity_pct.observe(abs(drift_percent))
