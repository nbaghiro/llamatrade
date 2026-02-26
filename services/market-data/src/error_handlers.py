"""Global FastAPI exception handlers for market data service.

Maps Alpaca API errors and resilience errors to appropriate HTTP responses.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.models import (
    AlpacaError,
    AlpacaRateLimitError,
    AlpacaServerError,
    CircuitOpenError,
    InvalidRequestError,
    SymbolNotFoundError,
)

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    """Register all error handlers with the FastAPI app.

    Args:
        app: FastAPI application instance
    """

    @app.exception_handler(SymbolNotFoundError)
    async def symbol_not_found_handler(request: Request, exc: SymbolNotFoundError) -> JSONResponse:
        """Handle symbol not found errors (404)."""
        logger.warning(
            f"Symbol not found: {exc.symbol}",
            extra={"symbol": exc.symbol, "path": request.url.path},
        )
        return JSONResponse(
            status_code=404,
            content={
                "error": "symbol_not_found",
                "message": str(exc),
                "symbol": exc.symbol,
            },
        )

    @app.exception_handler(InvalidRequestError)
    async def invalid_request_handler(request: Request, exc: InvalidRequestError) -> JSONResponse:
        """Handle invalid request errors (400)."""
        logger.warning(
            f"Invalid request: {exc.message}",
            extra={"path": request.url.path},
        )
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_request",
                "message": exc.message,
            },
        )

    @app.exception_handler(AlpacaRateLimitError)
    async def rate_limit_handler(request: Request, exc: AlpacaRateLimitError) -> JSONResponse:
        """Handle rate limit errors (503 with Retry-After).

        We return 503 (Service Unavailable) instead of 429 because:
        1. The rate limit is with our upstream provider (Alpaca), not with the client
        2. 503 better indicates the service is temporarily unavailable
        3. We include Retry-After header for proper client backoff
        """
        logger.warning(
            "Alpaca rate limit exceeded",
            extra={"retry_after": exc.retry_after, "path": request.url.path},
        )

        headers = {}
        if exc.retry_after:
            headers["Retry-After"] = str(exc.retry_after)

        return JSONResponse(
            status_code=503,
            content={
                "error": "rate_limited",
                "message": "Market data service temporarily unavailable due to rate limiting",
                "retry_after": exc.retry_after,
            },
            headers=headers,
        )

    @app.exception_handler(AlpacaServerError)
    async def alpaca_server_error_handler(request: Request, exc: AlpacaServerError) -> JSONResponse:
        """Handle Alpaca server errors (502 Bad Gateway)."""
        logger.error(
            f"Alpaca server error: {exc.message}",
            extra={"status_code": exc.status_code, "path": request.url.path},
        )
        return JSONResponse(
            status_code=502,
            content={
                "error": "upstream_error",
                "message": "Market data provider returned an error",
            },
        )

    @app.exception_handler(CircuitOpenError)
    async def circuit_open_handler(request: Request, exc: CircuitOpenError) -> JSONResponse:
        """Handle circuit breaker open errors (503)."""
        logger.warning(
            "Circuit breaker open",
            extra={"path": request.url.path},
        )
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "60"},
            content={
                "error": "service_unavailable",
                "message": "Market data service temporarily unavailable",
                "retry_after": 60,
            },
        )

    @app.exception_handler(AlpacaError)
    async def alpaca_error_handler(request: Request, exc: AlpacaError) -> JSONResponse:
        """Catch-all handler for any other Alpaca errors."""
        logger.error(
            f"Alpaca error: {exc.message}",
            extra={"status_code": exc.status_code, "path": request.url.path},
        )
        return JSONResponse(
            status_code=exc.status_code or 500,
            content={
                "error": "market_data_error",
                "message": exc.message,
            },
        )
