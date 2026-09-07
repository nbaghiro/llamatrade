"""Tests for the global FastAPI error handlers (Alpaca/resilience -> HTTP)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.error_handlers import register_error_handlers
from src.models import (
    AlpacaError,
    AlpacaRateLimitError,
    AlpacaServerError,
    CircuitOpenError,
    InvalidRequestError,
    SymbolNotFoundError,
)

_ERRORS: dict[str, Exception] = {
    "symbol-not-found": SymbolNotFoundError("MISSING"),
    "invalid-request": InvalidRequestError("Missing required parameter: symbol"),
    "rate-limit": AlpacaRateLimitError(retry_after=5),
    "rate-limit-no-hint": AlpacaRateLimitError(),
    "server-error": AlpacaServerError("bad gateway", status_code=502),
    "circuit-open": CircuitOpenError(),
    "alpaca-with-status": AlpacaError("teapot", status_code=418),
    "alpaca-no-status": AlpacaError("mystery failure"),
}


@pytest.fixture
async def handler_client() -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom/{kind}")
    async def boom(kind: str) -> dict[str, str]:
        raise _ERRORS[kind]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class TestErrorHandlers:
    async def test_symbol_not_found_maps_to_404(self, handler_client: AsyncClient) -> None:
        response = await handler_client.get("/boom/symbol-not-found")
        assert response.status_code == 404
        body = response.json()
        assert body["error"] == "symbol_not_found"
        assert body["symbol"] == "MISSING"
        assert "MISSING" in body["message"]

    async def test_invalid_request_maps_to_400(self, handler_client: AsyncClient) -> None:
        response = await handler_client.get("/boom/invalid-request")
        assert response.status_code == 400
        body = response.json()
        assert body["error"] == "invalid_request"
        assert body["message"] == "Missing required parameter: symbol"

    async def test_rate_limit_maps_to_503_with_retry_after(
        self, handler_client: AsyncClient
    ) -> None:
        response = await handler_client.get("/boom/rate-limit")
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "5"
        body = response.json()
        assert body["error"] == "rate_limited"
        assert body["retry_after"] == 5

    async def test_rate_limit_without_hint_omits_retry_after_header(
        self, handler_client: AsyncClient
    ) -> None:
        response = await handler_client.get("/boom/rate-limit-no-hint")
        assert response.status_code == 503
        assert "Retry-After" not in response.headers
        assert response.json()["retry_after"] is None

    async def test_alpaca_server_error_maps_to_502(self, handler_client: AsyncClient) -> None:
        response = await handler_client.get("/boom/server-error")
        assert response.status_code == 502
        body = response.json()
        assert body["error"] == "upstream_error"
        assert "bad gateway" not in body["message"]  # upstream detail not leaked

    async def test_circuit_open_maps_to_503_with_fixed_retry(
        self, handler_client: AsyncClient
    ) -> None:
        response = await handler_client.get("/boom/circuit-open")
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "60"
        body = response.json()
        assert body["error"] == "service_unavailable"
        assert body["retry_after"] == 60

    async def test_generic_alpaca_error_uses_its_status_code(
        self, handler_client: AsyncClient
    ) -> None:
        response = await handler_client.get("/boom/alpaca-with-status")
        assert response.status_code == 418
        body = response.json()
        assert body["error"] == "market_data_error"
        assert body["message"] == "teapot"

    async def test_generic_alpaca_error_defaults_to_500(self, handler_client: AsyncClient) -> None:
        response = await handler_client.get("/boom/alpaca-no-status")
        assert response.status_code == 500
        assert response.json()["error"] == "market_data_error"
