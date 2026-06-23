"""Tests for trading-service metrics via telemetry exposition.

These assert against the Prometheus exposition produced by
``llamatrade_telemetry.get_metrics`` (the real ``/metrics`` payload) rather
than poking at prometheus_client internals.
"""

import re

import pytest

from llamatrade_telemetry import get_metrics

from src.metrics import (
    record_bar_latency,
    record_bar_processed,
    record_bar_stream_reconnect,
    record_bracket_order_submitted,
    record_bracket_order_triggered,
    record_fill_processed,
    record_order_submission,
    record_position_reconciliation,
    record_risk_check,
    record_signal,
    record_strategy_error,
    record_trade_stream_event,
    set_bar_stream_connected,
    update_runner_gauge,
)


def _exposition() -> str:
    """Return the current Prometheus exposition text."""
    return get_metrics().decode()


def _sample(text: str, metric: str, **labels: str) -> float:
    """Return the value of a single exposition sample, or 0.0 if absent.

    Matches a line like ``metric{a="b",c="d"} 3.0`` regardless of label order.
    """
    for line in text.splitlines():
        if line.startswith("#") or not line.startswith(metric):
            continue
        match = re.match(
            rf"{re.escape(metric)}(?:\{{(?P<labels>[^}}]*)\}})?\s+(?P<value>\S+)$", line
        )
        if not match:
            continue
        present = dict(re.findall(r'(\w+)="([^"]*)"', match.group("labels") or ""))
        if all(present.get(k) == v for k, v in labels.items()):
            return float(match.group("value"))
    return 0.0


class TestOrderMetrics:
    """Order submission metrics route through the trading domain namespace."""

    def test_record_order_submission_success(self):
        metric = "llamatrade_trading_order_submissions_total"
        before = _sample(_exposition(), metric, side="buy", type="market", status="success")

        record_order_submission(side="buy", order_type="market", status="success", duration=0.5)

        after = _sample(_exposition(), metric, side="buy", type="market", status="success")
        assert after == before + 1

    def test_record_order_submission_rejected(self):
        metric = "llamatrade_trading_order_submissions_total"
        before = _sample(_exposition(), metric, side="sell", type="limit", status="rejected_risk")

        record_order_submission(
            side="sell", order_type="limit", status="rejected_risk", duration=0.1
        )

        after = _sample(_exposition(), metric, side="sell", type="limit", status="rejected_risk")
        assert after == before + 1

    def test_order_submission_latency_observed(self):
        metric = "llamatrade_trading_order_submission_latency_seconds_count"
        before = _sample(_exposition(), metric)

        record_order_submission(side="buy", order_type="market", status="success", duration=0.3)

        assert _sample(_exposition(), metric) == before + 1


class TestBracketOrderMetrics:
    """Bracket-order counters are trading-service-local."""

    def test_record_bracket_order_submitted(self):
        metric = "llamatrade_trading_bracket_orders_submitted_total"
        before_sl = _sample(_exposition(), metric, bracket_type="stop_loss")
        before_tp = _sample(_exposition(), metric, bracket_type="take_profit")

        record_bracket_order_submitted("stop_loss")
        record_bracket_order_submitted("take_profit")

        text = _exposition()
        assert _sample(text, metric, bracket_type="stop_loss") == before_sl + 1
        assert _sample(text, metric, bracket_type="take_profit") == before_tp + 1

    def test_record_bracket_order_triggered(self):
        metric = "llamatrade_trading_bracket_orders_triggered_total"
        before = _sample(_exposition(), metric, bracket_type="stop_loss")

        record_bracket_order_triggered("stop_loss")

        assert _sample(_exposition(), metric, bracket_type="stop_loss") == before + 1


class TestRiskMetrics:
    """Risk checks and violation classification."""

    def test_record_risk_check_passed(self):
        metric = "llamatrade_trading_risk_checks_total"
        before = _sample(_exposition(), metric, result="passed")

        record_risk_check(passed=True, violations=[], duration=0.01)

        assert _sample(_exposition(), metric, result="passed") == before + 1

    def test_record_risk_check_failed_with_violations(self):
        checks = "llamatrade_trading_risk_checks_total"
        violations = "llamatrade_trading_risk_violations_total"
        text = _exposition()
        before_failed = _sample(text, checks, result="failed")
        before_order = _sample(text, violations, violation_type="max_order_value")
        before_daily = _sample(text, violations, violation_type="daily_loss")

        record_risk_check(
            passed=False,
            violations=[
                "Order value $10000 exceeds limit $5000",
                "Daily loss limit exceeded",
            ],
            duration=0.02,
        )

        text = _exposition()
        assert _sample(text, checks, result="failed") == before_failed + 1
        assert _sample(text, violations, violation_type="max_order_value") == before_order + 1
        assert _sample(text, violations, violation_type="daily_loss") == before_daily + 1

    def test_record_risk_check_position_violation(self):
        violations = "llamatrade_trading_risk_violations_total"
        before = _sample(_exposition(), violations, violation_type="max_position_size")

        record_risk_check(
            passed=False,
            violations=["Position would exceed max size"],
            duration=0.01,
        )

        assert _sample(_exposition(), violations, violation_type="max_position_size") == before + 1


class TestStrategyMetrics:
    """Signal, bar-processing, strategy-error, and runner-gauge metrics."""

    def test_record_signal(self):
        metric = "llamatrade_trading_signals_generated_total"
        text = _exposition()
        before_buy = _sample(text, metric, signal_type="buy")
        before_sell = _sample(text, metric, signal_type="sell")

        record_signal("buy")
        record_signal("sell")
        record_signal("buy")

        text = _exposition()
        assert _sample(text, metric, signal_type="buy") == before_buy + 2
        assert _sample(text, metric, signal_type="sell") == before_sell + 1

    def test_record_bar_processed(self):
        count = "llamatrade_trading_bars_processed_total"
        duration = "llamatrade_trading_bar_processing_duration_seconds_count"
        text = _exposition()
        before_count = _sample(text, count)
        before_duration = _sample(text, duration)

        record_bar_processed(duration=0.005)

        text = _exposition()
        assert _sample(text, count) == before_count + 1
        assert _sample(text, duration) == before_duration + 1

    def test_record_strategy_error(self):
        metric = "llamatrade_trading_strategy_errors_total"
        before = _sample(_exposition(), metric, error_type="signal_generation")

        record_strategy_error("signal_generation")

        assert _sample(_exposition(), metric, error_type="signal_generation") == before + 1

    def test_update_runner_gauge(self):
        metric = "llamatrade_trading_active_runners"

        update_runner_gauge(5)
        assert _sample(_exposition(), metric) == 5

        update_runner_gauge(3)
        assert _sample(_exposition(), metric) == 3


class TestStreamMetrics:
    """Bar/trade stream connection and reconnect metrics."""

    def test_record_bar_latency(self):
        metric = "llamatrade_trading_bar_stream_latency_seconds_count"
        before = _sample(_exposition(), metric)

        record_bar_latency(0.5)
        record_bar_latency(1.2)

        assert _sample(_exposition(), metric) == before + 2

    def test_record_bar_stream_reconnect(self):
        metric = "llamatrade_trading_bar_stream_reconnects_total"
        before = _sample(_exposition(), metric)

        record_bar_stream_reconnect()

        assert _sample(_exposition(), metric) == before + 1

    def test_set_bar_stream_connected(self):
        metric = "llamatrade_trading_bar_stream_connected"

        set_bar_stream_connected(True)
        assert _sample(_exposition(), metric) == 1

        set_bar_stream_connected(False)
        assert _sample(_exposition(), metric) == 0

    def test_record_trade_stream_event(self):
        metric = "llamatrade_trading_trade_stream_events_total"
        before = _sample(_exposition(), metric, event_type="fill")

        record_trade_stream_event("fill")

        assert _sample(_exposition(), metric, event_type="fill") == before + 1


class TestFillMetrics:
    """Fill processing counters and duration."""

    def test_record_fill_processed(self):
        count = "llamatrade_trading_fills_total"
        duration = "llamatrade_trading_fill_processing_duration_seconds_count"
        text = _exposition()
        before_count = _sample(text, count, side="buy", fill_type="full")
        before_duration = _sample(text, duration)

        record_fill_processed(side="buy", fill_type="full", duration=0.01)

        text = _exposition()
        assert _sample(text, count, side="buy", fill_type="full") == before_count + 1
        assert _sample(text, duration) == before_duration + 1


class TestReconciliationMetrics:
    """Position reconciliation, drift, and drift-magnitude metrics."""

    def test_record_position_reconciliation_match(self):
        metric = "llamatrade_trading_position_reconciliation_total"
        duration = "llamatrade_trading_position_reconciliation_duration_seconds_count"
        text = _exposition()
        before = _sample(text, metric, result="match")
        before_duration = _sample(text, duration)

        record_position_reconciliation(result="match", duration=0.1)

        text = _exposition()
        assert _sample(text, metric, result="match") == before + 1
        assert _sample(text, duration) == before_duration + 1

    def test_record_position_reconciliation_drift(self):
        recon = "llamatrade_trading_position_reconciliation_total"
        drift = "llamatrade_trading_position_drift_detected_total"
        pct = "llamatrade_trading_position_drift_quantity_pct_count"
        text = _exposition()
        before_recon = _sample(text, recon, result="drift_alerted")
        before_drift = _sample(text, drift, drift_type="quantity_mismatch")
        before_pct = _sample(text, pct)

        record_position_reconciliation(
            result="drift_alerted",
            duration=0.2,
            drift_type="quantity_mismatch",
            drift_percent=12.5,
        )

        text = _exposition()
        assert _sample(text, recon, result="drift_alerted") == before_recon + 1
        assert _sample(text, drift, drift_type="quantity_mismatch") == before_drift + 1
        assert _sample(text, pct) == before_pct + 1


class TestExpositionShape:
    """Forbidden per-session labels must not appear in the exposition."""

    @pytest.mark.parametrize(
        "forbidden",
        [
            "tenant_id=",
            "session_id=",
            "trading_daily_pnl_dollars",
            "trading_current_drawdown_percent",
            "trading_position_value_dollars",
            "trading_alpaca_api_calls_total",
        ],
    )
    def test_no_forbidden_labels_or_dropped_metrics(self, forbidden):
        # Emit a representative signal so the trading metrics exist in output.
        record_order_submission(side="buy", order_type="market", status="success", duration=0.1)
        assert forbidden not in _exposition()


class TestDegradedEvalsMetric:
    """record_degraded_evals — strategy conditions that couldn't be evaluated (Issue 5A)."""

    def test_increments_by_count(self) -> None:
        from src.metrics import record_degraded_evals

        metric = "llamatrade_trading_strategy_degraded_evals_total"
        before = _sample(_exposition(), metric)
        record_degraded_evals(3)
        assert _sample(_exposition(), metric) == before + 3

    def test_nonpositive_is_noop(self) -> None:
        from src.metrics import record_degraded_evals

        metric = "llamatrade_trading_strategy_degraded_evals_total"
        before = _sample(_exposition(), metric)
        record_degraded_evals(0)
        assert _sample(_exposition(), metric) == before
