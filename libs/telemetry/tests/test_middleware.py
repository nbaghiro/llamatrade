from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from httpx import ASGITransport, AsyncClient

from llamatrade_telemetry import init_telemetry
from tests.conftest import scrape


@pytest.fixture
def app() -> FastAPI:
    application = FastAPI()

    @application.get("/ok")
    async def ok() -> dict[str, bool]:
        return {"ok": True}

    @application.get("/boom")
    async def boom() -> dict[str, bool]:
        raise ValueError("kaboom")

    @application.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @application.get("/stream")
    async def stream() -> StreamingResponse:
        async def gen() -> AsyncIterator[bytes]:
            for i in range(3):
                yield f"chunk{i}".encode()

        return StreamingResponse(gen(), media_type="text/plain")

    init_telemetry(application, service="mw", version="0.0.0")
    return application


async def test_red_metrics_and_request_id(app: FastAPI) -> None:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        r = await client.get("/ok")
        assert r.status_code == 200
        assert "X-Request-ID" in r.headers
        assert "X-Response-Time" in r.headers

    out = scrape()
    assert (
        'llamatrade_http_requests_total{method="GET",route="/ok",'
        'status_class="2xx",status_code="200",transport="http"} 1.0' in out
    )
    assert 'llamatrade_http_request_duration_seconds_count{method="GET",route="/ok"' in out


async def test_server_error_recorded_as_5xx(app: FastAPI) -> None:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        r = await client.get("/boom")
        assert r.status_code == 500

    out = scrape()
    assert 'route="/boom"' in out
    assert 'status_class="5xx"' in out


async def test_metrics_endpoint_served(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        r = await client.get("/metrics")
        assert r.status_code == 200
        assert "llamatrade_http_requests_total" in r.text


async def test_inbound_request_id_propagated(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        r = await client.get("/ok", headers={"X-Request-ID": "fixed-id"})
        assert r.headers["X-Request-ID"] == "fixed-id"


async def test_operational_routes_excluded_from_red(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        assert (await client.get("/health")).status_code == 200
        assert (await client.get("/metrics")).status_code == 200
    out = scrape()
    # /health and /metrics are served but never counted (self-noise).
    assert 'route="/health"' not in out
    assert 'route="/metrics"' not in out


async def test_streaming_skips_duration_histogram(app: FastAPI) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        r = await client.get("/stream")
        assert r.status_code == 200
        assert r.text == "chunk0chunk1chunk2"
    out = scrape()
    # The request is counted...
    assert 'llamatrade_http_requests_total{method="GET",route="/stream"' in out
    # ...but its (unbounded) duration is NOT in the latency histogram.
    assert 'llamatrade_http_request_duration_seconds_count{method="GET",route="/stream"' not in out
