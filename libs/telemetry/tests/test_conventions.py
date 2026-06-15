from __future__ import annotations

import pytest

from llamatrade_telemetry import conventions as c


def test_valid_metric_name() -> None:
    c.validate_metric_name("llamatrade_trading_order_submissions")
    c.validate_metric_name("llamatrade_http_request_duration_seconds")


@pytest.mark.parametrize(
    "name",
    ["NotAllowed", "llamatrade_", "llamatrade_Trailing_", "foo_bar", "llamatrade__double"],
)
def test_invalid_metric_name(name: str) -> None:
    with pytest.raises(c.MetricNameError):
        c.validate_metric_name(name)


def test_allowed_label_keys() -> None:
    c.validate_label_keys(["service", "route", "status_code", "plan"])


@pytest.mark.parametrize("key", ["tenant_id", "session_id", "symbol", "order_id", "email"])
def test_forbidden_label_keys_rejected(key: str) -> None:
    with pytest.raises(c.LabelError):
        c.validate_label_keys([key])


def test_forbidden_allowed_when_high_cardinality_opt_in() -> None:
    # bounded top-N gauges may opt in
    c.validate_label_keys(["symbol"], allow_high_cardinality=True)


def test_unknown_label_rejected() -> None:
    with pytest.raises(c.LabelError):
        c.validate_label_keys(["totally_unbounded_dimension"])


def test_malformed_label_rejected() -> None:
    with pytest.raises(c.LabelError):
        c.validate_label_keys(["Bad-Key"])


def test_buckets_for_known_and_unknown() -> None:
    assert conventions_buckets() == c.LATENCY_RPC
    with pytest.raises(c.MetricNameError):
        c.buckets_for("llamatrade_never_declared_seconds")


def conventions_buckets() -> tuple[float, ...]:
    return c.buckets_for("llamatrade_http_request_duration_seconds")


def test_every_declared_histogram_has_valid_name() -> None:
    for name in c.HISTOGRAM_BUCKETS:
        c.validate_metric_name(name)
