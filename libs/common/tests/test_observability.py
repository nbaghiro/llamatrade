"""Tests for the llamatrade_common.observability back-compat shim.

``setup_observability`` / ``enable_db_pool_metrics`` now delegate to
``llamatrade_telemetry.init_telemetry``; these tests verify the shim wires a
working app (RED middleware + ``/metrics`` + request id).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from llamatrade_common.observability import (
    ObservabilityMiddleware,
    enable_db_pool_metrics,
    setup_observability,
)


class _Stats:
    checked_out = 1
    checked_in = 9
    max_connections = 10


def test_observability_middleware_is_telemetry_middleware() -> None:
    # Back-compat alias for the unified telemetry middleware.
    assert ObservabilityMiddleware.__name__ == "TelemetryMiddleware"


def test_setup_observability_adds_metrics_and_request_id() -> None:
    app = FastAPI()

    @app.get("/test")
    async def endpoint() -> dict[str, str]:
        return {"message": "ok"}

    setup_observability(app, service_name="obs-test", version="1.0.0")
    client = TestClient(app)

    resp = client.get("/test")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "llamatrade_http_requests_total" in metrics.text


def test_enable_db_pool_metrics_exports_pool_gauge() -> None:
    app = FastAPI()

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    enable_db_pool_metrics(app, "obs-pool-test", lambda: _Stats())
    client = TestClient(app)
    client.get("/ping")

    out = client.get("/metrics").text
    assert 'llamatrade_db_connections{state="max"} 10.0' in out
