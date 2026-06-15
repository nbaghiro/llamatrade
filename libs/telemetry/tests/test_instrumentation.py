from __future__ import annotations

import pytest

from llamatrade_telemetry.instrumentation import cache, celery, dependency, eventbus
from llamatrade_telemetry.instrumentation import db as dbmod
from tests.conftest import scrape


class _Stats:
    checked_out = 4
    checked_in = 6
    max_connections = 10


def test_db_pool_observer_and_query_timer() -> None:
    dbmod.register_pool_observer(lambda: _Stats())
    with dbmod.time_query("select", "users"):
        pass
    out = scrape()
    assert 'llamatrade_db_connections{state="active"} 4.0' in out
    assert 'llamatrade_db_connections{state="idle"} 6.0' in out
    assert 'llamatrade_db_connections{state="max"} 10.0' in out
    assert 'llamatrade_db_query_duration_seconds_count{operation="select",table="users"} 1.0' in out


def test_db_pool_observer_tolerates_failures() -> None:
    def bad() -> _Stats:
        raise RuntimeError("pool gone")

    dbmod.register_pool_observer(bad)
    scrape()  # must not raise


def test_cache_recorders() -> None:
    cache.record_cache_operation("bars", "get", "hit")
    with cache.time_cache_op("bars", "get"):
        pass
    out = scrape()
    assert 'llamatrade_cache_operations_total{cache="bars",op="get",result="hit"} 1.0' in out
    assert 'llamatrade_cache_op_duration_seconds_count{cache="bars",op="get"} 1.0' in out


def test_eventbus_recorders() -> None:
    eventbus.record_published("ledger:fills", "order_filled", "success")
    eventbus.record_consumed("ledger:fills", "portfolio-ledger", "success")
    eventbus.record_ack("ledger:fills", "portfolio-ledger")
    eventbus.record_nack("ledger:fills", "portfolio-ledger")
    eventbus.record_reconnect("ledger:fills", "consume")
    eventbus.record_redelivery("ledger:fills", "portfolio-ledger")
    eventbus.record_dlq("ledger:fills")
    eventbus.set_consumer_lag("ledger:fills", "portfolio-ledger", 7, 12.5)
    with eventbus.time_processing("ledger:fills", "order_filled"):
        pass
    out = scrape()
    assert (
        'llamatrade_eventbus_published_total{event_type="order_filled",result="success",stream="ledger:fills"} 1.0'
        in out
    )
    assert (
        'llamatrade_eventbus_consumer_lag_entries{group="portfolio-ledger",stream="ledger:fills"} 7.0'
        in out
    )
    assert (
        'llamatrade_eventbus_consumer_lag_seconds{group="portfolio-ledger",stream="ledger:fills"} 12.5'
        in out
    )


def test_celery_recorders() -> None:
    celery.record_task("run_backtest", "success")
    celery.observe_task_duration("run_backtest", 1.5)
    celery.observe_queue_wait("run_backtest", 0.2)
    celery.record_retry("run_backtest")
    celery.set_queue_depth("backtests", 3)
    celery.set_workers_active(2)
    out = scrape()
    assert 'llamatrade_celery_tasks_total{state="success",task="run_backtest"} 1.0' in out
    assert 'llamatrade_celery_queue_depth{queue="backtests"} 3.0' in out
    assert "llamatrade_celery_workers_active 2.0" in out


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
