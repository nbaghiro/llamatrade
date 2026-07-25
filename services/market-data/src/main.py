"""Market Data Service - FastAPI with Connect protocol.

This service provides real-time and historical market data.
It exposes endpoints via Connect protocol for direct browser access,
while also providing WebSocket streaming via Alpaca.
"""

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

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
from llamatrade_common import AuthMiddleware, HealthChecker, check_redis
from llamatrade_db import close_db, get_pool_stats
from llamatrade_events import EventBus, RedisStreamsTransport
from llamatrade_telemetry import init_telemetry
from llamatrade_telemetry.config import TelemetrySettings

from src.cache import close_cache, init_cache
from src.error_handlers import register_error_handlers
from src.streaming.bridge import close_stream_bridge, init_stream_bridge
from src.streaming.bus_bridge import BusBridge
from src.streaming.manager import get_stream_manager

logger = logging.getLogger(__name__)


def _bars_from_bus() -> bool:
    """Bus mode (serving reads live bars off the internal bus fed by the ingest
    role) vs legacy direct-Alpaca. Requires the explicit
    ``MARKET_DATA_BARS_FROM_BUS`` opt-in — inferring it from ``REDIS_URL`` (also
    the cache URL) silently put serving into bus mode with no publisher, so live
    ``stream_bars`` emitted nothing. Set it only where the ingestor runs.
    """
    return os.getenv("MARKET_DATA_BARS_FROM_BUS", "").strip().lower() in {"1", "true", "yes", "on"}


SERVICE_NAME = "market-data"
SERVICE_VERSION = "0.1.0"
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

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

    cache = await init_cache()
    if cache:
        logger.info("Redis cache initialized successfully")
    else:
        logger.warning("Redis cache unavailable - service will operate without caching")

    # Live bar fan-out: bus mode (EventBus, serving holds no Alpaca conn) or legacy direct-Alpaca.
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

register_error_handlers(app)

# Authentication (fail-closed); added before CORS so CORS stays outermost.
app.add_middleware(AuthMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


async def _check_live_bars() -> bool:
    """Live-bar fan-out health: bus-bridge state in bus mode, else the Alpaca stream."""
    if _bars_from_bus():
        return _stream_connected
    alpaca_stream = get_alpaca_stream()
    return alpaca_stream.connected if alpaca_stream else False


_health = HealthChecker(SERVICE_NAME, SERVICE_VERSION)
_health.add_check("redis", lambda: check_redis(os.getenv("REDIS_URL", "")), critical=False)
_health.add_check("live_bars", _check_live_bars, critical=False)
app.include_router(_health.create_router())
