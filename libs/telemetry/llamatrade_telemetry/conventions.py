"""Naming, label-cardinality, and histogram-bucket conventions.

This module is the single source of truth for *what is allowed* in a LlamaTrade
metric. The metric facade (``registry.py``) calls these validators when an
instrument is created, so a violation fails fast (and in tests) rather than
silently shipping a cardinality bomb to Prometheus.

Rules (see ``.docs/telemetry.md`` §4):

* Names match ``llamatrade_<domain>_<noun>_<unit>`` — lowercase snake_case.
* Label keys come from a bounded allow-list; high-cardinality keys
  (``tenant_id``, ``symbol``, ids, emails, …) are forbidden — they belong on
  logs and traces, never on a metric label.
* Every histogram declares its buckets here, so the MeterProvider can build the
  matching OTel ``View`` at startup.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

METRIC_NAME_RE = re.compile(r"^llamatrade_[a-z][a-z0-9_]*[a-z0-9]$")
LABEL_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# Bounded label keys allowed on metrics (low cardinality by construction).
ALLOWED_LABEL_KEYS: frozenset[str] = frozenset(
    {
        # cross-cutting
        "service",
        "transport",
        "method",
        "route",
        "operation",
        "target",
        "status",
        "status_code",
        "status_class",
        "result",
        "plan",
        "state",
        "mode",
        "stream",
        "group",
        "cache",
        "op",
        "queue",
        "task",
        "table",
        "direction",
        # domain enums (each small and bounded)
        "kind",
        "type",
        "side",
        "reason",
        "event_type",
        "channel",
        "model",
        "data_type",
        "signal_type",
        "error_type",
        "drift_type",
        "fill_type",
        "indicator",
        "template",
        "tier",
        "limit",
        "bracket_type",
        "violation_type",
        "action",
        "outcome",
        "status_change",
    }
)

# High-cardinality keys that must NEVER become metric labels. Per-entity slicing
# is served by logs/traces (and the ledger for business data); a bounded top-N
# gauge may opt in via ``allow_high_cardinality=True``.
FORBIDDEN_LABEL_KEYS: frozenset[str] = frozenset(
    {
        "tenant_id",
        "session_id",
        "user_id",
        "order_id",
        "client_order_id",
        "symbol",
        "backtest_id",
        "request_id",
        "strategy_id",
        "sleeve_id",
        "account_id",
        "api_key",
        "email",
        "url",
        "ip",
        "path",
        "query",
        "trace_id",
    }
)

# ---------------------------------------------------------------------------
# Histogram bucket sets (seconds unless the name says otherwise).
# ---------------------------------------------------------------------------
LATENCY_RPC = (0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0)
LATENCY_DEP = (0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5)
LATENCY_TIGHT = (0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0)
DURATION_JOB = (1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0)
SLIPPAGE_BPS = (1.0, 2.0, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0)
LOOKBACK_BARS = (10.0, 20.0, 50.0, 100.0, 200.0, 500.0, 1000.0)
SIZE_BYTES = (64.0, 256.0, 1024.0, 4096.0, 16384.0, 65536.0, 262144.0, 1048576.0)
PERCENT = (0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 25.0, 50.0, 100.0)
STALENESS_SECONDS = (1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0, 900.0)
DELIVERY_SECONDS = (0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)
BCRYPT_SECONDS = (0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0)
LLM_SECONDS = (0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0)
THROUGHPUT_BARS = (100.0, 1_000.0, 10_000.0, 100_000.0, 1_000_000.0)

# Every histogram instrument the platform defines → its buckets. The registry
# builds one OTel View per entry at MeterProvider construction. Creating a
# histogram whose name is absent here raises (forces a deliberate bucket choice).
HISTOGRAM_BUCKETS: dict[str, tuple[float, ...]] = {
    # cross-cutting
    "llamatrade_http_request_duration_seconds": LATENCY_RPC,
    "llamatrade_http_request_size_bytes": SIZE_BYTES,
    "llamatrade_http_response_size_bytes": SIZE_BYTES,
    "llamatrade_grpc_stream_duration_seconds": LATENCY_RPC,
    "llamatrade_dependency_duration_seconds": LATENCY_DEP,
    "llamatrade_db_query_duration_seconds": LATENCY_DEP,
    "llamatrade_db_pool_acquire_wait_seconds": LATENCY_DEP,
    "llamatrade_cache_op_duration_seconds": LATENCY_DEP,
    "llamatrade_eventbus_processing_duration_seconds": LATENCY_DEP,
    "llamatrade_runtime_event_loop_lag_seconds": LATENCY_TIGHT,
    "llamatrade_celery_task_duration_seconds": DURATION_JOB,
    "llamatrade_celery_task_queue_wait_seconds": DURATION_JOB,
    # trading
    "llamatrade_trading_order_submission_latency_seconds": LATENCY_TIGHT,
    "llamatrade_trading_order_fill_latency_seconds": LATENCY_RPC,
    "llamatrade_trading_order_slippage_bps": SLIPPAGE_BPS,
    "llamatrade_trading_bar_processing_duration_seconds": LATENCY_TIGHT,
    "llamatrade_trading_bar_stream_latency_seconds": LATENCY_TIGHT,
    "llamatrade_trading_risk_check_duration_seconds": LATENCY_TIGHT,
    "llamatrade_trading_fill_processing_duration_seconds": LATENCY_TIGHT,
    "llamatrade_trading_position_drift_quantity_pct": PERCENT,
    "llamatrade_trading_order_sync_duration_seconds": LATENCY_DEP,
    "llamatrade_trading_signal_processing_duration_seconds": LATENCY_TIGHT,
    "llamatrade_trading_position_reconciliation_duration_seconds": LATENCY_DEP,
    # ledger / portfolio
    "llamatrade_ledger_event_append_latency_seconds": LATENCY_DEP,
    "llamatrade_ledger_projection_fold_duration_seconds": LATENCY_DEP,
    # market data
    "llamatrade_marketdata_stream_message_lag_seconds": LATENCY_TIGHT,
    "llamatrade_marketdata_data_staleness_seconds": STALENESS_SECONDS,
    # strategy / compiler
    "llamatrade_strategy_compile_duration_seconds": LATENCY_DEP,
    "llamatrade_strategy_indicator_compute_duration_seconds": LATENCY_TIGHT,
    "llamatrade_strategy_signal_eval_duration_seconds": LATENCY_TIGHT,
    "llamatrade_strategy_max_lookback_bars": LOOKBACK_BARS,
    # backtest
    "llamatrade_backtest_execution_duration_seconds": DURATION_JOB,
    "llamatrade_backtest_bar_throughput_bars_per_second": THROUGHPUT_BARS,
    # billing
    "llamatrade_billing_webhook_handler_duration_seconds": LATENCY_DEP,
    # auth
    "llamatrade_auth_bcrypt_hash_duration_seconds": BCRYPT_SECONDS,
    # notification
    "llamatrade_notification_alert_eval_latency_seconds": LATENCY_DEP,
    "llamatrade_notification_delivery_latency_seconds": DELIVERY_SECONDS,
    # agent / llm
    "llamatrade_agent_llm_latency_seconds": LLM_SECONDS,
    "llamatrade_agent_llm_ttft_seconds": LATENCY_RPC,
}


class MetricNameError(ValueError):
    """Raised when a metric name violates the naming convention."""


class LabelError(ValueError):
    """Raised when a label key is forbidden or malformed."""


def validate_metric_name(name: str) -> None:
    """Assert ``name`` matches ``llamatrade_<...>`` snake_case."""
    if not METRIC_NAME_RE.match(name):
        raise MetricNameError(
            f"metric name {name!r} must match {METRIC_NAME_RE.pattern} "
            "(lowercase snake_case, 'llamatrade_' prefix)"
        )


def validate_label_keys(
    keys: Iterable[str],
    *,
    allow_high_cardinality: bool = False,
) -> None:
    """Assert every label key is allowed and low-cardinality.

    Args:
        keys: the label keys used on a metric.
        allow_high_cardinality: set True only for deliberately bounded top-N
            gauges that need an entity dimension (e.g. ``symbol``).
    """
    for key in keys:
        if not LABEL_KEY_RE.match(key):
            raise LabelError(f"label key {key!r} must be lowercase snake_case")
        if key in FORBIDDEN_LABEL_KEYS and not allow_high_cardinality:
            raise LabelError(
                f"label key {key!r} is high-cardinality and forbidden on metrics; "
                "use logs/traces (or a bounded top-N gauge) instead"
            )
        if not allow_high_cardinality and key not in ALLOWED_LABEL_KEYS:
            raise LabelError(
                f"label key {key!r} is not on the allow-list "
                "(add it to conventions.ALLOWED_LABEL_KEYS if it is genuinely bounded)"
            )


def buckets_for(name: str) -> tuple[float, ...]:
    """Return the declared buckets for a histogram, or raise if undeclared."""
    try:
        return HISTOGRAM_BUCKETS[name]
    except KeyError:
        raise MetricNameError(
            f"histogram {name!r} has no buckets declared in "
            "conventions.HISTOGRAM_BUCKETS — add one before creating it"
        ) from None
