"""Strategy Service - FastAPI with Connect protocol.

This service manages trading strategies for LlamaTrade.
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

# Configuration
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:8800,http://localhost:3000,http://localhost:47333"
).split(",")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan handler."""
    # Mount Connect ASGI app
    try:
        from llamatrade_proto.generated.strategy_connect import (
            StrategyService,
            StrategyServiceASGIApplication,
        )

        from src.grpc.servicer import StrategyServicer

        servicer = StrategyServicer()
        connect_app = StrategyServiceASGIApplication(cast(StrategyService, servicer))
        app.mount("/", cast(ASGIApp, connect_app))
        logger.info("Connect ASGI application mounted successfully")
    except ImportError as e:
        logger.warning("Connect dependencies not available: %s", e)

    # Periodically release sleeves stranded by a failed ledger close (must never
    # block startup; a single pod runs the sweep via an advisory lock).
    stop_event = asyncio.Event()
    sweep_task: asyncio.Task[None] | None = None
    try:
        from src.tasks import stranded_sleeve_loop

        sweep_task = asyncio.create_task(stranded_sleeve_loop(stop_event))
        logger.info("Started stranded-sleeve sweep loop")
    except Exception:
        logger.exception("Failed to start stranded-sleeve sweep loop")

    yield

    # Shutdown - stop the sweep, dispose the DB connection pool.
    stop_event.set()
    if sweep_task is not None:
        sweep_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sweep_task
    await close_db()


app = FastAPI(
    title="LlamaTrade Strategy Service",
    description="Strategy management service for LlamaTrade (Connect protocol)",
    version="0.1.0",
    lifespan=lifespan,
)

# Authentication (fail-closed); added before CORS so CORS stays outermost.
# Exempt the public template endpoints from auth (the modal loads them without a session).
app.add_middleware(
    AuthMiddleware,
    public_suffixes=["/ListTemplates", "/GetTemplate"],
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Export DB connection-pool stats on /metrics
init_telemetry(app, service="strategy", pool_stats_provider=get_pool_stats)


app.include_router(HealthChecker("strategy", "0.1.0").create_router())
