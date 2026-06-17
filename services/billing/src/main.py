"""Billing Service - FastAPI with Connect protocol.

This service handles subscription and billing management with Stripe.
It exposes endpoints via Connect protocol for direct browser access.
Note: Stripe webhooks are still handled via HTTP endpoints.
"""

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TypedDict, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

from llamatrade_db import close_db, get_pool_stats, init_db
from llamatrade_telemetry import init_telemetry

from src.routers import webhooks

logger = logging.getLogger(__name__)

# Configuration
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:8800,http://localhost:47333,http://localhost:3000"
).split(",")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan handler."""
    # Startup
    try:
        await init_db()
    except Exception as e:
        logger.warning("Database initialization failed (non-critical): %s", e)

    # Mount Connect ASGI app
    try:
        from llamatrade_proto.generated.billing_connect import BillingServiceASGIApplication

        from src.grpc.servicer import BillingServicer

        servicer = BillingServicer()
        connect_app = BillingServiceASGIApplication(servicer)
        app.mount("/", cast(ASGIApp, connect_app))
        logger.info("Connect ASGI application mounted successfully")
    except ImportError as e:
        logger.warning("Connect dependencies not available: %s", e)

    yield

    # Shutdown
    await close_db()


app = FastAPI(
    title="LlamaTrade Billing Service",
    description="Subscription and billing management with Stripe (Connect protocol)",
    version="0.1.0",
    lifespan=lifespan,
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
init_telemetry(app, service="billing", pool_stats_provider=get_pool_stats)

# Stripe webhooks still use HTTP endpoints (not Connect)
app.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])


class HealthResponse(TypedDict):
    """Health check response."""

    status: str
    service: str
    version: str


@app.get("/health")
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return {"status": "healthy", "service": "billing", "version": "0.1.0"}
