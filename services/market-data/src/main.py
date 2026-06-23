"""Market Data Service - FastAPI with Connect protocol.

This service provides real-time and historical market data.
It exposes endpoints via Connect protocol for direct browser access,
while also providing WebSocket streaming via Alpaca.
"""

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

from llamatrade_alpaca import close_all_clients
from llamatrade_alpaca import (
    close_market_data_stream as close_alpaca_stream,
)
from llamatrade_alpaca import (
    get_market_data_stream as get_alpaca_stream,
)
from llamatrade_alpaca import (
    init_market_data_stream as init_alpaca_stream,
)
from llamatrade_common import AuthMiddleware
from llamatrade_db import close_db, get_pool_stats
from llamatrade_events import EventBus, RedisStreamsTransport
from llamatrade_telemetry import init_telemetry
from llamatrade_telemetry.config import TelemetrySettings

from src.cache import close_cache, get_cache, init_cache
from src.error_handlers import register_error_handlers
from src.streaming.bridge import close_stream_bridge, init_stream_bridge
from src.streaming.bus_bridge import BusBridge
from src.streaming.manager import get_stream_manager

logger = logging.getLogger(__name__)


def _bars_from_bus() -> bool:
    """Bus mode (consolidated) vs legacy direct-Alpaca, from env.

    Explicit ``MARKET_DATA_BARS_FROM_BUS`` wins; otherwise default to bus mode
    whenever Redis is configured (the deployed topology).
    """
    flag = os.getenv("MARKET_DATA_BARS_FROM_BUS")
    if flag is not None:
        return flag.strip().lower() in {"1", "true", "yes", "on"}
    return os.getenv("REDIS_URL") is not None


# Service configuration
SERVICE_NAME = "market-data"
SERVICE_VERSION = "0.1.0"
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Configuration
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:8800,http://localhost:3000,http://localhost:47333"
).split(",")

# Track streaming state for health check
_stream_connected = False

# Bus-mode fan-out handles (set in lifespan, closed on shutdown)
_event_bus: EventBus | None = None
_bus_bridge: BusBridge | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan handler."""
    global _stream_connected

    # Startup - initialize Redis cache
    cache = await init_cache()
    if cache:
        logger.info("Redis cache initialized successfully")
    else:
        logger.warning("Redis cache unavailable - service will operate without caching")

    # Startup - live bar fan-out. Two modes:
    #  - bus mode (default when REDIS_URL is set): bars come from the internal
    #    EventBus fed by the ingest role; serving holds NO Alpaca connection.
    #  - legacy mode: serving opens its own Alpaca stream directly.
    global _event_bus, _bus_bridge
    stream_manager = get_stream_manager()
    if _bars_from_bus():
        _event_bus = EventBus(RedisStreamsTransport(os.getenv("REDIS_URL")))
        _bus_bridge = BusBridge(_event_bus, stream_manager)
        await _bus_bridge.start()
        _stream_connected = True
        logger.info("Live bars sourced from internal bus (consolidated mode)")
    else:
        alpaca_stream = await init_alpaca_stream()
        if alpaca_stream:
            _stream_connected = True
            await init_stream_bridge(alpaca_stream, stream_manager)
            logger.info("Stream bridge initialized (legacy direct-Alpaca mode)")
        else:
            logger.warning(
                "Alpaca stream unavailable - real-time streaming will not work. "
                "Check ALPACA_API_KEY and ALPACA_API_SECRET environment variables."
            )
            _stream_connected = False

    # Mount Connect ASGI app
    try:
        from llamatrade_proto.generated.market_data_connect import MarketDataServiceASGIApplication

        from src.grpc.servicer import MarketDataServicer

        servicer = MarketDataServicer()
        connect_app = MarketDataServiceASGIApplication(servicer)
        app.mount("/", cast(ASGIApp, connect_app))
        logger.info("Connect ASGI application mounted successfully")
    except ImportError as e:
        logger.warning("Connect dependencies not available: %s", e)

    yield

    # Shutdown - close connections in reverse order
    if _bus_bridge is not None:
        await _bus_bridge.stop()
    if _event_bus is not None:
        await _event_bus.close()
    await close_stream_bridge()
    await close_alpaca_stream()
    await close_all_clients()
    await close_cache()
    await close_db()


app = FastAPI(
    title="LlamaTrade Market Data Service",
    description="Real-time and historical market data service (Connect protocol)",
    version=SERVICE_VERSION,
    lifespan=lifespan,
)

# Setup observability (logging, metrics, request tracing)
init_telemetry(
    app,
    service=SERVICE_NAME,
    version=SERVICE_VERSION,
    settings=TelemetrySettings(
        ENVIRONMENT=ENVIRONMENT,
        LOG_LEVEL=LOG_LEVEL,
        LOG_FORMAT="json" if ENVIRONMENT != "development" else "text",
    ),
)

# Export DB connection-pool stats (the /metrics endpoint is added above)
init_telemetry(app, service=SERVICE_NAME, pool_stats_provider=get_pool_stats)

# Register error handlers
register_error_handlers(app)

# Authentication (fail-closed); added before CORS so CORS stays outermost.
app.add_middleware(AuthMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


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
