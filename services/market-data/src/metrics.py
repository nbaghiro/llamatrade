"""Domain-specific metrics for the market data service.

Thin helpers over :mod:`llamatrade_telemetry`. The unified telemetry stack owns
the OTel instruments and the Prometheus ``/metrics`` exposition; this module only
adapts the service's call sites to the shared ``metrics.marketdata.*`` namespace,
the cross-cutting cache instrumentation, and a couple of service-specific stream
counters.

Notes:

* Alpaca REST request counters/latency are **not** emitted here. Alpaca calls go
  through ``llamatrade_alpaca``, which is already instrumented
  (``llamatrade_dependency_*`` with ``target="alpaca"``). Duplicating them here
  would double-count.
* Cache operations reuse the cross-cutting cache instrumentation so they share a
  single ``llamatrade_cache_operations_total`` / ``llamatrade_cache_op_duration_seconds``
  series across the platform (labelled ``cache="marketdata"``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from llamatrade_telemetry import counter, metrics
from llamatrade_telemetry.instrumentation.cache import CACHE_OP_DURATION
from llamatrade_telemetry.instrumentation.cache import (
    record_cache_operation as _record_cache_operation,
)

from src.models import Bar

# Cache series share the platform-wide instrumentation; this service is the
# ``marketdata`` cache.
_CACHE = "marketdata"

# Service-specific stream-fan-out counters. These have no equivalent in the
# shared domain catalog because they count messages this service relays to its
# own clients (and what it receives upstream), so they live here via the
# registry factory (still validated by ``conventions``).
_STREAM_MESSAGES_TOTAL = counter(
    "llamatrade_marketdata_stream_messages_total",
    ["type"],
    "Stream messages relayed to clients by type (trade/quote/bar)",
)
_STREAM_ALPACA_MESSAGES_TOTAL = counter(
    "llamatrade_marketdata_stream_alpaca_messages_total",
    ["type"],
    "Messages received from the upstream Alpaca stream by type",
)

# Circuit-breaker state mapping (closed/half_open/open -> 0/1/2; unknown -> -1).
_CIRCUIT_BREAKER_STATES: dict[str, int] = {"closed": 0, "half_open": 1, "open": 2}

# Nominal bar duration per timeframe. Used only to spot *interior* holes in a
# served bar series (a missing bar => an inter-bar gap wider than one step). A
# small tolerance below avoids flagging the normal one-step cadence as a gap.
_TIMEFRAME_STEP: dict[str, timedelta] = {
    "1Min": timedelta(minutes=1),
    "5Min": timedelta(minutes=5),
    "15Min": timedelta(minutes=15),
    "30Min": timedelta(minutes=30),
    "1Hour": timedelta(hours=1),
    "4Hour": timedelta(hours=4),
    "1Day": timedelta(days=1),
    "1Week": timedelta(weeks=1),
    "1Month": timedelta(days=31),
}


def record_cache_operation(operation: str, result: str, latency: float) -> None:
    """Record a cache operation.

    Args:
        operation: Type of operation (get, set, delete).
        result: Result (hit, miss, error).
        latency: Operation duration in seconds.
    """
    _record_cache_operation(_CACHE, operation, result)
    CACHE_OP_DURATION.labels(cache=_CACHE, op=operation).observe(latency)


def update_stream_metrics(
    connections: int,
    trade_subs: int,
    quote_subs: int,
    bar_subs: int,
) -> None:
    """Update streaming gauges.

    Args:
        connections: Number of active upstream connections.
        trade_subs: Number of trade subscriptions.
        quote_subs: Number of quote subscriptions.
        bar_subs: Number of bar subscriptions.
    """
    metrics.marketdata.stream_connections.set(connections)
    metrics.marketdata.stream_subscriptions.labels(type="trades").set(trade_subs)
    metrics.marketdata.stream_subscriptions.labels(type="quotes").set(quote_subs)
    metrics.marketdata.stream_subscriptions.labels(type="bars").set(bar_subs)


def record_stream_message(msg_type: str) -> None:
    """Record a stream message relayed to clients.

    Args:
        msg_type: Type of message (trade, quote, bar).
    """
    _STREAM_MESSAGES_TOTAL.labels(type=msg_type).inc()


def record_alpaca_stream_message(msg_type: str) -> None:
    """Record a message received from the upstream Alpaca stream.

    Args:
        msg_type: Type of message (trade, quote, bar, error).
    """
    _STREAM_ALPACA_MESSAGES_TOTAL.labels(type=msg_type).inc()


def update_rate_limiter_metrics(available_tokens: float) -> None:
    """Update the rate-limiter token gauge.

    Args:
        available_tokens: Number of available tokens.
    """
    metrics.marketdata.rate_limit_tokens.set(available_tokens)


def update_circuit_breaker_metrics(state: str) -> None:
    """Update the circuit-breaker state gauge.

    Args:
        state: Circuit state (closed, half_open, open); unknown maps to -1.
    """
    metrics.marketdata.circuit_breaker_state.set(_CIRCUIT_BREAKER_STATES.get(state, -1))


# Interior-gap detection tolerance (fraction of a step) and the upper bound
# beyond which a delta is treated as a session boundary (overnight/weekend) and
# *not* counted as a missing-bar gap. Mirrors the ingest gap-repair contract.
_GAP_TOLERANCE = 0.5
_GAP_MAX_STEPS = 3


def _to_utc(ts: str | datetime) -> datetime:
    """Coerce an ISO string or datetime to a timezone-aware UTC datetime."""
    dt = ts if isinstance(ts, datetime) else datetime.fromisoformat(ts)
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _observe_staleness(data_type: str, latest_ts: str | datetime) -> None:
    """Observe ``now - latest_ts`` on the staleness histogram for ``data_type``.

    Negative ages (clock skew / a not-yet-closed bar timestamped in the future)
    are clamped to zero so the histogram never sees impossible values.
    """
    age = (datetime.now(UTC) - _to_utc(latest_ts)).total_seconds()
    metrics.marketdata.data_staleness.labels(data_type=data_type).observe(max(age, 0.0))


def record_bar_staleness(bars: list[Bar]) -> None:
    """Observe the age of the freshest bar in a served series.

    Args:
        bars: The bar series being returned (any order); no-op if empty.
    """
    if not bars:
        return
    latest = max(b.timestamp for b in bars)
    _observe_staleness("bars", latest)


def record_quote_staleness(latest_ts: str | datetime) -> None:
    """Observe the age of a served quote."""
    _observe_staleness("quotes", latest_ts)


def record_trade_staleness(latest_ts: str | datetime) -> None:
    """Observe the age of a served trade."""
    _observe_staleness("trades", latest_ts)


def record_stream_message_lag(timestamp: str | datetime) -> None:
    """Observe ``now - timestamp`` for a freshly received streamed message.

    Args:
        timestamp: The upstream (Alpaca) event timestamp on the streamed
            trade/quote/bar. Negative lag (clock skew) is clamped to zero.
    """
    lag = (datetime.now(UTC) - _to_utc(timestamp)).total_seconds()
    metrics.marketdata.stream_message_lag.observe(max(lag, 0.0))


def record_bar_series_gaps(timeframe: str, bars: list[Bar]) -> None:
    """Count interior holes in a served bar series and emit one gap per hole.

    A "hole" is a delta between consecutive bars wider than one timeframe step
    (with a small tolerance) but no wider than ``_GAP_MAX_STEPS`` steps — beyond
    that the gap is assumed to be a session boundary (overnight/weekend), not a
    missing bar, and is ignored. Detection runs only for intraday timeframes,
    where the in-session cadence is regular enough to make a missing bar
    unambiguous; daily+ series are skipped (no trading calendar available here).

    Args:
        timeframe: Timeframe string (e.g. ``"1Min"``).
        bars: The bar series being returned (any order).
    """
    step = _TIMEFRAME_STEP.get(timeframe)
    if step is None or step >= timedelta(days=1) or len(bars) < 2:
        return
    times = sorted(b.timestamp for b in bars)
    threshold = step * (1 + _GAP_TOLERANCE)
    max_gap = step * _GAP_MAX_STEPS
    for earlier, later in zip(times, times[1:], strict=False):
        delta = later - earlier
        if threshold < delta <= max_gap:
            metrics.marketdata.data_gap()


def record_missing_symbol() -> None:
    """Record that a requested symbol returned no data / was not found."""
    metrics.marketdata.missing_symbol()
