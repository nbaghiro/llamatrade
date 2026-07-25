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
from llamatrade_db import close_db, get_pool_stats
from llamatrade_telemetry import init_telemetry

logger = logging.getLogger(__name__)

CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:8800,http://localhost:3000,http://localhost:47333"
).split(",")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan handler."""
    # Mount Connect ASGI app
    try:
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
    except ImportError as e:
        logger.warning("Connect dependencies not available: %s", e)

    # Re-attach runners to sessions left RUNNING/PAUSED by a crashed pod, and
    # keep reclaiming on an interval. Ownership is arbitrated by a per-session
    # advisory lock so scaled replicas never double-run a session. Must never
    # block startup.
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

# Unified telemetry: RED middleware, /metrics endpoint, JSON logging, tracing,
# and DB connection-pool gauges.
init_telemetry(app, service="trading", version="0.1.0", pool_stats_provider=get_pool_stats)

# Authentication (fail-closed for non-public paths); added before CORS so CORS
# stays outermost and still handles preflight + headers on 401 responses.
app.add_middleware(AuthMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


app.include_router(HealthChecker("trading", "0.1.0").create_router())
