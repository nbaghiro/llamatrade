"""Agent Service - FastAPI with Connect protocol.

This service provides the AI Strategy Agent (Copilot) for LlamaTrade.
It enables users to generate, edit, and optimize trading strategies
through natural language conversation.

Port: 8890
"""

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

from llamatrade_common import AuthMiddleware, HealthChecker
from llamatrade_common.health import cached_engine_check
from llamatrade_db import close_db, get_engine, get_pool_stats
from llamatrade_db.session import verify_rls_enforcement
from llamatrade_telemetry import init_telemetry

logger = logging.getLogger(__name__)

# Configuration
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:8800,http://localhost:3000,http://localhost:47333"
).split(",")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan handler."""
    # Fail closed (prod/staging) if the DB role can bypass RLS.
    await verify_rls_enforcement()

    # Mount Connect ASGI app (mandatory: a missing servicer is a boot failure).
    from llamatrade_proto.generated.agent_connect import (
        AgentService,
        AgentServiceASGIApplication,
    )

    from src.grpc.servicer import AgentServicer

    servicer = AgentServicer()
    connect_app = AgentServiceASGIApplication(cast(AgentService, servicer))
    app.mount("/", cast(ASGIApp, connect_app))
    logger.info("Connect ASGI application mounted successfully")

    yield

    await close_db()


app = FastAPI(
    title="LlamaTrade Agent Service",
    description="AI Strategy Agent (Copilot) service for LlamaTrade (Connect protocol)",
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
init_telemetry(app, service="agent", pool_stats_provider=get_pool_stats)

_check_database = cached_engine_check(get_engine)

# LLM reachability is deliberately not probed: an upstream outage must not
# recycle pods that still serve conversation history from the database.
_health = HealthChecker("agent", "0.1.0")
_health.add_check("database", lambda: _check_database())
app.include_router(_health.create_router())
