from __future__ import annotations

import pytest

from llamatrade_telemetry import conventions, registry
from tests.conftest import scrape


def test_counter_exposition_total_suffix() -> None:
    ctr = registry.counter("llamatrade_test_counter_total", ["result"], "test")
    ctr.labels(result="ok").inc()
    ctr.labels(result="ok").inc(2)
    out = scrape()
    assert 'llamatrade_test_counter_total{result="ok"} 3.0' in out


def test_counter_label_mismatch_raises() -> None:
    ctr = registry.counter("llamatrade_test_lblcounter", ["result"], "test")
    with pytest.raises(conventions.LabelError):
        ctr.labels(wrong="x")


def test_histogram_observe_and_time() -> None:
    h = registry.histogram("llamatrade_db_query_duration_seconds", ["operation", "table"], "d")
    h.labels(operation="select", table="orders").observe(0.02)
    with h.time(operation="insert", table="orders"):
        pass
    out = scrape()
    assert (
        'llamatrade_db_query_duration_seconds_count{operation="select",table="orders"} 1.0' in out
    )
    assert (
        'llamatrade_db_query_duration_seconds_count{operation="insert",table="orders"} 1.0' in out
    )


def test_gauge_set_with_and_without_labels() -> None:
    g = registry.gauge("llamatrade_test_gauge", ["state"], "g")
    g.labels(state="a").set(5)
    g.labels(state="a").set(8)  # last write wins
    ng = registry.gauge("llamatrade_test_plain_gauge", (), "g")
    ng.set(42)
    out = scrape()
    assert 'llamatrade_test_gauge{state="a"} 8.0' in out
    assert "llamatrade_test_plain_gauge 42.0" in out


def test_up_down_counter_inc_dec() -> None:
    u = registry.up_down_counter("llamatrade_test_inflight", ["route"], "u")
    u.labels(route="/x").inc()
    u.labels(route="/x").inc()
    u.labels(route="/x").dec()
    out = scrape()
    assert 'llamatrade_test_inflight{route="/x"} 1.0' in out


def test_factory_returns_cached_singleton() -> None:
    a = registry.counter("llamatrade_test_singleton", ["result"], "x")
    b = registry.counter("llamatrade_test_singleton", ["result"], "x")
    assert a is b


def test_no_label_counter_requires_no_labels() -> None:
    ctr = registry.counter("llamatrade_test_nolabel_total", (), "x")
    ctr.inc()
    with pytest.raises(conventions.LabelError):
        # labelled counter cannot use bare inc
        registry.counter("llamatrade_test_haslabel", ["result"], "x").inc()


def test_kill_switch_disables_recording() -> None:
    ctr = registry.counter("llamatrade_test_killswitch_total", (), "x")
    registry._enabled = False
    try:
        ctr.inc()
    finally:
        registry._enabled = True
    out = scrape()
    assert "llamatrade_test_killswitch_total" not in out


def test_observable_gauge_registration() -> None:
    from opentelemetry.metrics import CallbackOptions, Observation

    def cb(options: CallbackOptions) -> list[Observation]:
        return [Observation(11, {"state": "active"})]

    registry.observable_gauge("llamatrade_test_observable", cb, ["state"], "o")
    out = scrape()
    assert 'llamatrade_test_observable{state="active"} 11.0' in out
