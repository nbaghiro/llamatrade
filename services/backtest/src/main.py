"""Backtest Service - FastAPI with Connect protocol.

This service handles historical backtesting for trading strategies.
It exposes endpoints via Connect protocol for direct browser access.
"""

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

from llamatrade_common import AuthMiddleware, HealthChecker, check_redis
from llamatrade_common.health import cached_engine_check
from llamatrade_db import close_db, get_engine, get_pool_stats
from llamatrade_db.session import verify_rls_enforcement
from llamatrade_telemetry import init_telemetry

from src.celery_app import REDIS_URL
from src.queue_metrics import QueueDepthSampler

logger = logging.getLogger(__name__)

queue_depth_sampler = QueueDepthSampler()

# Configuration
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:8800,http://localhost:3000,http://localhost:47333"
).split(",")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan handler."""
    # Fail closed (prod/staging) if the DB role can bypass RLS.
    await verify_rls_enforcement()

    # Mount the Connect ASGI app. This is mandatory: the service exists to serve
    # these RPCs, so a missing generated module must crash startup rather than
    # leave a process that boots healthy but answers nothing.
    from llamatrade_proto.generated.backtest_connect import (
        BacktestService,
        BacktestServiceASGIApplication,
    )

    from src.grpc.servicer import BacktestServicer

    servicer = BacktestServicer()
    # gRPC ServicerContext and Connect RequestContext are compatible at runtime
    # but have different type signatures. Cast to the protocol type.
    connect_app = BacktestServiceASGIApplication(cast(BacktestService, servicer))
    app.mount("/", cast(ASGIApp, connect_app))
    logger.info("Connect ASGI application mounted successfully")

    await queue_depth_sampler.start()

    yield

    await queue_depth_sampler.stop()

    # Shutdown - dispose the DB connection pool
    await close_db()


app = FastAPI(
    title="LlamaTrade Backtest Service",
    description="Historical backtesting service for trading strategies (Connect protocol)",
    version="0.1.0",
    lifespan=lifespan,
)

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

# Export DB connection-pool stats on /metrics
init_telemetry(app, service="backtest", pool_stats_provider=get_pool_stats)


_check_database = cached_engine_check(get_engine)

_health = HealthChecker("backtest", "0.1.0")
_health.add_check("database", lambda: _check_database())
# Redis is the Celery broker/result backend; backtests cannot enqueue without it.
_health.add_check("redis", lambda: check_redis(REDIS_URL))
app.include_router(_health.create_router())
