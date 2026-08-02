"""Tests for the market data metrics helpers.

These assert against the unified telemetry exposition (``get_metrics().decode()``)
rather than prometheus_client internals, so they verify the real
``llamatrade_marketdata_*`` / ``llamatrade_cache_*`` series the service emits.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from llamatrade_telemetry import get_metrics

from src.metrics import (
    record_bar_series_gaps,
    record_bar_staleness,
    record_cache_operation,
    record_ingest_universe_refresh_failure,
    record_ingest_universe_size,
    record_missing_symbol,
    record_quote_staleness,
    record_stream_message_lag,
    record_trade_staleness,
)
from src.models import Bar


def _exposition() -> str:
    """Render the current Prometheus exposition output."""
    return get_metrics().decode()


def _sample(text: str, name: str, **labels: str) -> float | None:
    """Return the value of a single Prometheus sample, or ``None`` if absent.

    Matches a line ``name{label="v",...} value`` regardless of label order.
    """
    label_parts = {f'{k}="{v}"' for k, v in labels.items()}
    for line in text.splitlines():
        if line.startswith("#") or not line.startswith(name):
            continue
        head, _, value = line.rpartition(" ")
        if not head.startswith(name):
            continue
        if "{" in head:
            inner = head[head.index("{") + 1 : head.rindex("}")]
            line_labels = {part for part in inner.split(",") if part}
            if not label_parts.issubset(line_labels):
                continue
        elif label_parts:
            continue
        return float(value)
    return None


class TestRecordCacheOperation:
    """Cache ops route through the cross-cutting cache instrumentation."""

    def test_records_cache_hit(self) -> None:
        before = _sample(
            _exposition(),
            "llamatrade_cache_operations_total",
            cache="marketdata",
            op="get",
            result="hit",
        )
        record_cache_operation("get", "hit", 0.001)
        after = _sample(
            _exposition(),
            "llamatrade_cache_operations_total",
            cache="marketdata",
            op="get",
            result="hit",
        )
        assert after == (before or 0.0) + 1.0

    def test_records_cache_miss_and_error(self) -> None:
        record_cache_operation("get", "miss", 0.002)
        record_cache_operation("delete", "error", 0.01)
        text = _exposition()
        assert (
            _sample(
                text,
                "llamatrade_cache_operations_total",
                cache="marketdata",
                op="get",
                result="miss",
            )
            is not None
        )
        assert (
            _sample(
                text,
                "llamatrade_cache_operations_total",
                cache="marketdata",
                op="delete",
                result="error",
            )
            is not None
        )

    def test_records_latency_histogram(self) -> None:
        record_cache_operation("set", "hit", 0.003)
        text = _exposition()
        # The duration histogram exposes a labelled count series.
        assert (
            _sample(
                text,
                "llamatrade_cache_op_duration_seconds_count",
                cache="marketdata",
                op="set",
            )
            is not None
        )


class TestNoDuplicateAlpacaMetrics:
    """The legacy ``market_data_alpaca_*`` duplicates must be gone.

    Alpaca REST calls are instrumented by ``llamatrade_alpaca`` itself
    (``llamatrade_dependency_*`` with ``target="alpaca"``); the service must not
    re-emit them.
    """

    def test_legacy_alpaca_request_metrics_absent(self) -> None:
        text = _exposition()
        assert "market_data_alpaca_requests_total" not in text
        assert "market_data_alpaca_latency_seconds" not in text
        assert "market_data_alpaca_rate_limit_tokens" not in text
        assert "market_data_alpaca_circuit_breaker_state" not in text


def _bar(ts: datetime) -> Bar:
    """Minimal bar at a given timestamp for staleness/gap tests."""
    return Bar(timestamp=ts, open=1.0, high=1.0, low=1.0, close=1.0, volume=1)


class TestRecordDataStaleness:
    """Served-data staleness lands in the labelled histogram by data_type."""

    def test_bar_staleness_observed(self) -> None:
        before = _sample(
            _exposition(),
            "llamatrade_marketdata_data_staleness_seconds_count",
            data_type="bars",
        )
        record_bar_staleness([_bar(datetime.now(UTC) - timedelta(seconds=10))])
        after = _sample(
            _exposition(),
            "llamatrade_marketdata_data_staleness_seconds_count",
            data_type="bars",
        )
        assert after == (before or 0.0) + 1.0

    def test_bar_staleness_uses_freshest_bar(self) -> None:
        now = datetime.now(UTC)
        bars = [_bar(now - timedelta(seconds=300)), _bar(now - timedelta(seconds=2))]
        before = _sample(
            _exposition(), "llamatrade_marketdata_data_staleness_seconds_sum", data_type="bars"
        )
        record_bar_staleness(bars)
        after = _sample(
            _exposition(), "llamatrade_marketdata_data_staleness_seconds_sum", data_type="bars"
        )
        # The freshest (≈2s) bar drives staleness, not the 300s-old one.
        assert (after or 0.0) - (before or 0.0) < 60.0

    def test_empty_series_is_noop(self) -> None:
        before = _sample(
            _exposition(),
            "llamatrade_marketdata_data_staleness_seconds_count",
            data_type="bars",
        )
        record_bar_staleness([])
        after = _sample(
            _exposition(),
            "llamatrade_marketdata_data_staleness_seconds_count",
            data_type="bars",
        )
        assert after == before

    def test_quote_and_trade_staleness(self) -> None:
        now = datetime.now(UTC)
        record_quote_staleness((now - timedelta(seconds=3)).isoformat())
        record_trade_staleness(now - timedelta(seconds=4))
        text = _exposition()
        assert (
            _sample(text, "llamatrade_marketdata_data_staleness_seconds_count", data_type="quotes")
            is not None
        )
        assert (
            _sample(text, "llamatrade_marketdata_data_staleness_seconds_count", data_type="trades")
            is not None
        )

    def test_future_timestamp_clamped_to_zero(self) -> None:
        before = _sample(
            _exposition(), "llamatrade_marketdata_data_staleness_seconds_sum", data_type="bars"
        )
        record_bar_staleness([_bar(datetime.now(UTC) + timedelta(seconds=30))])
        after = _sample(
            _exposition(), "llamatrade_marketdata_data_staleness_seconds_sum", data_type="bars"
        )
        # A future timestamp must not push the sum below its prior value.
        assert (after or 0.0) >= (before or 0.0)


class TestRecordStreamMessageLag:
    """Stream-message lag lands in the no-label histogram."""

    def test_lag_observed(self) -> None:
        before = _sample(_exposition(), "llamatrade_marketdata_stream_message_lag_seconds_count")
        record_stream_message_lag((datetime.now(UTC) - timedelta(seconds=1)).isoformat())
        after = _sample(_exposition(), "llamatrade_marketdata_stream_message_lag_seconds_count")
        assert after == (before or 0.0) + 1.0

    def test_accepts_datetime_and_string(self) -> None:
        before = _sample(_exposition(), "llamatrade_marketdata_stream_message_lag_seconds_count")
        record_stream_message_lag(datetime.now(UTC) - timedelta(seconds=2))
        record_stream_message_lag((datetime.now(UTC) - timedelta(seconds=2)).isoformat())
        after = _sample(_exposition(), "llamatrade_marketdata_stream_message_lag_seconds_count")
        assert after == (before or 0.0) + 2.0

    def test_naive_timestamp_treated_as_utc(self) -> None:
        # A naive ISO string (no tz) must not raise on subtraction.
        naive = datetime.now(UTC).replace(tzinfo=None).isoformat()
        record_stream_message_lag(naive)
        assert (
            _sample(_exposition(), "llamatrade_marketdata_stream_message_lag_seconds_count")
            is not None
        )


class TestRecordBarSeriesGaps:
    """Interior holes in an intraday series increment the gap counter."""

    def test_intraday_hole_counts_one_gap(self) -> None:
        now = datetime.now(UTC)
        before = _sample(_exposition(), "llamatrade_marketdata_data_gaps_detected_total")
        # 1Min series with a single missing bar (3-min then 1-min cadence).
        bars = [_bar(now - timedelta(minutes=3)), _bar(now - timedelta(minutes=1))]
        record_bar_series_gaps("1Min", bars)
        after = _sample(_exposition(), "llamatrade_marketdata_data_gaps_detected_total")
        assert after == (before or 0.0) + 1.0

    def test_contiguous_series_has_no_gap(self) -> None:
        now = datetime.now(UTC)
        before = _sample(_exposition(), "llamatrade_marketdata_data_gaps_detected_total")
        bars = [_bar(now - timedelta(minutes=2)), _bar(now - timedelta(minutes=1))]
        record_bar_series_gaps("1Min", bars)
        after = _sample(_exposition(), "llamatrade_marketdata_data_gaps_detected_total")
        assert after == before

    def test_session_boundary_jump_not_counted(self) -> None:
        now = datetime.now(UTC)
        before = _sample(_exposition(), "llamatrade_marketdata_data_gaps_detected_total")
        # A 10-minute jump on a 1Min series exceeds the session-boundary bound.
        bars = [_bar(now - timedelta(minutes=11)), _bar(now - timedelta(minutes=1))]
        record_bar_series_gaps("1Min", bars)
        after = _sample(_exposition(), "llamatrade_marketdata_data_gaps_detected_total")
        assert after == before

    def test_daily_series_is_skipped(self) -> None:
        now = datetime.now(UTC)
        before = _sample(_exposition(), "llamatrade_marketdata_data_gaps_detected_total")
        # Daily+ series are skipped (no trading calendar to distinguish weekends).
        bars = [_bar(now - timedelta(days=5)), _bar(now - timedelta(days=1))]
        record_bar_series_gaps("1Day", bars)
        after = _sample(_exposition(), "llamatrade_marketdata_data_gaps_detected_total")
        assert after == before


class TestRecordMissingSymbol:
    """Missing-symbol requests increment the error counter."""

    def test_increments(self) -> None:
        before = _sample(_exposition(), "llamatrade_marketdata_missing_symbol_errors_total")
        record_missing_symbol()
        after = _sample(_exposition(), "llamatrade_marketdata_missing_symbol_errors_total")
        assert after == (before or 0.0) + 1.0


class TestIngestUniverseMetrics:
    """The derived ingest universe exposes its size and its refresh failures."""

    def test_size_gauge_is_set_per_kind(self) -> None:
        record_ingest_universe_size(baseline=3, live=5, total=7)
        text = _exposition()
        assert _sample(text, "llamatrade_marketdata_ingest_universe_symbols", kind="baseline") == 3
        assert _sample(text, "llamatrade_marketdata_ingest_universe_symbols", kind="live") == 5
        assert _sample(text, "llamatrade_marketdata_ingest_universe_symbols", kind="total") == 7

    def test_size_gauge_follows_the_latest_value(self) -> None:
        record_ingest_universe_size(baseline=1, live=1, total=2)
        record_ingest_universe_size(baseline=1, live=0, total=1)
        text = _exposition()
        assert _sample(text, "llamatrade_marketdata_ingest_universe_symbols", kind="live") == 0
        assert _sample(text, "llamatrade_marketdata_ingest_universe_symbols", kind="total") == 1

    def test_refresh_failures_counted_per_reason(self) -> None:
        name = "llamatrade_marketdata_ingest_universe_refresh_failures_total"
        before = _sample(_exposition(), name, reason="query")
        record_ingest_universe_refresh_failure("query")
        record_ingest_universe_refresh_failure("subscribe")
        text = _exposition()
        assert _sample(text, name, reason="query") == (before or 0.0) + 1.0
        assert _sample(text, name, reason="subscribe") is not None
