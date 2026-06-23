"""Notification Service - FastAPI with Connect protocol.

This service handles alerts, webhooks, email/SMS notifications.
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

from llamatrade_common import AuthMiddleware
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
        from llamatrade_proto.generated.notification_connect import (
            NotificationService,
            NotificationServiceASGIApplication,
        )

        from src.grpc.servicer import NotificationServicer

        servicer = NotificationServicer()
        # gRPC ServicerContext and Connect RequestContext are compatible at runtime
        connect_app = NotificationServiceASGIApplication(cast(NotificationService, servicer))
        app.mount("/", cast(ASGIApp, connect_app))
        logger.info("Connect ASGI application mounted successfully")
    except ImportError as e:
        logger.warning("Connect dependencies not available: %s", e)

    yield

    # Shutdown - dispose the DB connection pool
    await close_db()


app = FastAPI(
    title="LlamaTrade Notification Service",
    description="Alerts, webhooks, email/SMS notifications (Connect protocol)",
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
init_telemetry(app, service="notification", pool_stats_provider=get_pool_stats)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "notification", "version": "0.1.0"}
