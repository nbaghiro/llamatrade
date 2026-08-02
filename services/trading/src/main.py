"""Trading Service - FastAPI with Connect protocol.

This service handles live order execution and trading sessions.
It exposes endpoints via Connect protocol for direct browser access.
"""

import asyncio
import contextlib
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

from llamatrade_common import AuthMiddleware, HealthChecker
from llamatrade_common.health import cached_engine_check, check_kafka
from llamatrade_db import close_db, get_engine, get_pool_stats
from llamatrade_db.session import verify_rls_enforcement
from llamatrade_telemetry import init_telemetry

logger = logging.getLogger(__name__)

CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:8800,http://localhost:3000,http://localhost:47333"
).split(",")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan handler."""
    # Fail closed (prod/staging) if the DB role can bypass RLS.
    await verify_rls_enforcement()

    # Mount Connect ASGI app; a missing Connect dependency must crash startup (ImportError propagates) so the service never boots with no RPC surface on its money path.
    from llamatrade_proto.generated.trading_connect import (
        TradingService,
        TradingServiceASGIApplication,
    )

    from src.grpc.servicer import TradingServicer

    servicer = TradingServicer()
    # gRPC ServicerContext and Connect RequestContext are compatible at runtime
    connect_app = TradingServiceASGIApplication(cast(TradingService, servicer))
    app.mount("/", cast(ASGIApp, connect_app))
    logger.info("Connect ASGI application mounted successfully")

    # Re-attach runners to sessions left RUNNING/PAUSED by a crashed pod and keep reclaiming on an interval; a per-session advisory lock arbitrates ownership so replicas never double-run a session. Must never block startup.
    stop_event = asyncio.Event()
    rehydration_task: asyncio.Task[None] | None = None
    try:
        from src.recovery import rehydration_loop
        from src.runner.runner import get_runner_manager

        rehydration_task = asyncio.create_task(rehydration_loop(get_runner_manager(), stop_event))
        logger.info("Started live-session rehydration loop")
    except Exception:
        logger.exception("Failed to start rehydration loop")

    yield

    # Shutdown - stop rehydration, release ownership leases, dispose the pool.
    stop_event.set()
    if rehydration_task is not None:
        rehydration_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await rehydration_task
    with contextlib.suppress(Exception):
        from src.recovery import release_all_leases

        await release_all_leases()
    await close_db()


app = FastAPI(
    title="LlamaTrade Trading Service",
    description="Live order execution and trading session management (Connect protocol)",
    version="0.1.0",
    lifespan=lifespan,
)

# Authentication (fail-closed for non-public paths); added before CORS so CORS stays outermost and still handles preflight + headers on 401 responses.
app.add_middleware(AuthMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Unified telemetry: RED middleware, /metrics endpoint, JSON logging, tracing, DB connection-pool gauges.
init_telemetry(app, service="trading", version="0.1.0", pool_stats_provider=get_pool_stats)


_check_database = cached_engine_check(get_engine)


async def _check_kafka() -> bool:
    """Kafka health answered from the publisher's shared transport.

    Trading holds a live producer transport once it publishes fill/order events;
    its ``is_connected`` answers the probe so no second broker connection (which
    would fail the SASL handshake with no token provider) is opened.
    """
    from src.streaming import get_trading_event_publisher

    return await check_kafka(is_alive=get_trading_event_publisher().is_connected)


_health = HealthChecker("trading", "0.1.0")
_health.add_check("database", lambda: _check_database())
# Kafka carries fill/order events to the ledger; non-critical so session reads and order submission stay available while the backbone recovers.
_health.add_check("kafka", _check_kafka, critical=False)
app.include_router(_health.create_router())
