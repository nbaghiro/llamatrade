from __future__ import annotations

import pytest

from llamatrade_telemetry import conventions
from llamatrade_telemetry.instrumentation import celery, dependency
from llamatrade_telemetry.instrumentation import db as dbmod
from tests.conftest import scrape


class _Stats:
    checked_out = 4
    checked_in = 6
    max_connections = 10


def test_db_pool_observer() -> None:
    dbmod.register_pool_observer(lambda: _Stats())
    out = scrape()
    assert 'llamatrade_db_connections{state="active"} 4.0' in out
    assert 'llamatrade_db_connections{state="idle"} 6.0' in out
    assert 'llamatrade_db_connections{state="max"} 10.0' in out


def test_db_rls_bypass_counter_registers_and_counts() -> None:
    dbmod.DB_RLS_BYPASS.labels(operation="set_rls_bypass").inc()
    out = scrape()
    assert 'llamatrade_db_rls_bypass_total{operation="set_rls_bypass"} 1.0' in out


def test_db_rls_bypass_counter_rejects_identifier_labels() -> None:
    """The bypass counter carries only the bounded entry point, never a tenant."""
    with pytest.raises(conventions.LabelError):
        dbmod.DB_RLS_BYPASS.labels(tenant_id="t-1")


def test_db_rls_bypass_metric_satisfies_conventions() -> None:
    conventions.validate_metric_name("llamatrade_db_rls_bypass_total")
    conventions.validate_label_keys(["operation"])


def test_db_pool_observer_tolerates_failures() -> None:
    def bad() -> _Stats:
        raise RuntimeError("pool gone")

    dbmod.register_pool_observer(bad)
    scrape()  # must not raise


def test_celery_recorders() -> None:
    celery.set_queue_depth("backtests", 3)
    out = scrape()
    assert 'llamatrade_celery_queue_depth{queue="backtests"} 3.0' in out


def test_dependency_recorders_success_and_error() -> None:
    dependency.record_dependency("alpaca", "submit_order", "success", 0.05)
    with dependency.time_dependency("alpaca", "get_bars"):
        pass
    with pytest.raises(ValueError):
        with dependency.time_dependency("alpaca", "boom"):
            raise ValueError("x")
    out = scrape()
    assert (
        'llamatrade_dependency_requests_total{operation="submit_order",status="success",target="alpaca"} 1.0'
        in out
    )
    assert (
        'llamatrade_dependency_requests_total{operation="boom",status="error",target="alpaca"} 1.0'
        in out
    )
