from __future__ import annotations

import pytest

from llamatrade_telemetry import init_telemetry, runtime, shutdown
from llamatrade_telemetry.instrumentation import grpc
from tests.conftest import scrape


def test_init_idempotent_for_worker() -> None:
    init_telemetry(service="worker", version="0.0.0")
    init_telemetry(service="worker", version="0.0.0")
    shutdown()  # flush; must not raise


def test_grpc_recorders() -> None:
    grpc.record_grpc_request("/svc/Method", "ok")
    grpc.record_stream_message("/svc/Stream", "out")
    grpc.GRPC_STREAM_ACTIVE.labels(method="/svc/Stream").inc()
    out = scrape()
    assert 'llamatrade_grpc_requests_total{method="/svc/Method",status="ok"} 1.0' in out
    assert 'llamatrade_grpc_stream_active{method="/svc/Stream"} 1.0' in out


def test_runtime_monitor_no_loop_is_noop() -> None:
    runtime.stop_runtime_monitor()
    runtime.ensure_runtime_monitor()  # no running loop → no-op, no raise


async def test_runtime_monitor_starts_in_loop() -> None:
    runtime.ensure_runtime_monitor()
    runtime.ensure_runtime_monitor()  # idempotent
    runtime.EVENT_LOOP_LAG.observe(0.001)
    runtime.ASYNCIO_TASKS.set(1)
    runtime.stop_runtime_monitor()
    out = scrape()
    assert "llamatrade_runtime_asyncio_tasks" in out


def test_init_rejects_missing_service() -> None:
    with pytest.raises(TypeError):
        init_telemetry()  # service is keyword-only required
