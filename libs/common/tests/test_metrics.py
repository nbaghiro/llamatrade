"""Tests for the llamatrade_common.metrics back-compat shim.

The metrics implementation now lives in ``llamatrade_telemetry`` (with its own
test suite); these tests verify the shim re-exports and delegates correctly.
"""

from __future__ import annotations

from llamatrade_common.metrics import (
    PoolStatsLike,
    get_metrics,
    init_service_info,
    register_db_pool_observer,
)


class _Stats:
    checked_out = 2
    checked_in = 8
    max_connections = 10


def test_get_metrics_returns_prometheus_bytes() -> None:
    out = get_metrics()
    assert isinstance(out, bytes)
    assert b"python_info" in out


def test_init_service_info_is_noop() -> None:
    assert init_service_info("svc", "1.0.0", "test") is None


def test_register_db_pool_observer_exports_gauge() -> None:
    register_db_pool_observer("common-test", lambda: _Stats())
    out = get_metrics().decode()
    assert 'llamatrade_db_connections{state="active"} 2.0' in out
    assert 'llamatrade_db_connections{state="idle"} 8.0' in out
    assert 'llamatrade_db_connections{state="max"} 10.0' in out


def test_pool_stats_like_is_exported() -> None:
    assert PoolStatsLike is not None
