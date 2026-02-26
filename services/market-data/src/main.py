"""Market Data Service - Main FastAPI application."""

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from llamatrade_common.observability import setup_observability

from src.alpaca.client import close_alpaca_client
from src.cache import close_cache, get_cache, init_cache
from src.error_handlers import register_error_handlers
from src.routers import bars, quotes, streaming
from src.streaming.alpaca_stream import (
    close_alpaca_stream,
    get_alpaca_stream,
    init_alpaca_stream,
)
from src.streaming.bridge import close_stream_bridge, init_stream_bridge
from src.streaming.manager import get_stream_manager

logger = logging.getLogger(__name__)

# Service configuration
SERVICE_NAME = "market-data"
SERVICE_VERSION = "0.1.0"
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Track streaming state for health check
_stream_connected = False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    global _stream_connected

    # Startup - initialize Redis cache
    cache = await init_cache()
    if cache:
        logger.info("Redis cache initialized successfully")
    else:
        logger.warning("Redis cache unavailable - service will operate without caching")

    # Startup - initialize Alpaca stream (non-critical)
    alpaca_stream = await init_alpaca_stream()
    if alpaca_stream:
        logger.info("Alpaca stream connected successfully")
        _stream_connected = True

        # Initialize stream bridge
        stream_manager = get_stream_manager()
        await init_stream_bridge(alpaca_stream, stream_manager)
        logger.info("Stream bridge initialized")
    else:
        logger.warning(
            "Alpaca stream unavailable - real-time streaming will not work. "
            "Check ALPACA_API_KEY and ALPACA_API_SECRET environment variables."
        )
        _stream_connected = False

    yield

    # Shutdown - close connections in reverse order
    await close_stream_bridge()
    await close_alpaca_stream()
    await close_alpaca_client()
    await close_cache()


app = FastAPI(
    title="LlamaTrade Market Data Service",
    description="Real-time and historical market data service for LlamaTrade",
    version=SERVICE_VERSION,
    lifespan=lifespan,
)

# Setup observability (logging, metrics, request tracing)
setup_observability(
    app,
    service_name=SERVICE_NAME,
    version=SERVICE_VERSION,
    environment=ENVIRONMENT,
    log_level=LOG_LEVEL,
    json_logs=ENVIRONMENT != "development",
)

# Register error handlers
register_error_handlers(app)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(bars.router, prefix="/bars", tags=["Bars"])
app.include_router(quotes.router, prefix="/quotes", tags=["Quotes"])
app.include_router(streaming.router, prefix="/stream", tags=["Streaming"])


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint."""
    cache = get_cache()
    cache_healthy = False

    if cache:
        cache_healthy = await cache.health_check()

    # Check Alpaca stream status
    alpaca_stream = get_alpaca_stream()
    stream_healthy = alpaca_stream.connected if alpaca_stream else False

    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "dependencies": {
            "redis": {
                "status": "healthy" if cache_healthy else "unavailable",
                "critical": False,
            },
            "alpaca_stream": {
                "status": "healthy" if stream_healthy else "unavailable",
                "critical": False,
            },
        },
    }
