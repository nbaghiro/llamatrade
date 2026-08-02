"""Billing Service - FastAPI with Connect protocol.

This service handles subscription and billing management with Stripe.
It exposes endpoints via Connect protocol for direct browser access.
Note: Stripe webhooks are still handled via HTTP endpoints.
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

from src.routers import webhooks

logger = logging.getLogger(__name__)

# Configuration
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:8800,http://localhost:47333,http://localhost:3000"
).split(",")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan handler."""
    # Fail closed (prod/staging) if the DB role can bypass RLS.
    await verify_rls_enforcement()

    # Mount Connect ASGI app (mandatory: an import failure must fail startup).
    from llamatrade_proto.generated.billing_connect import (
        BillingService,
        BillingServiceASGIApplication,
    )

    from src.grpc.servicer import BillingServicer

    servicer = BillingServicer()
    # Decorated handlers return Coroutine, not the CoroutineType the protocol declares.
    connect_app = BillingServiceASGIApplication(cast(BillingService, servicer))
    app.mount("/", cast(ASGIApp, connect_app))
    logger.info("Connect ASGI application mounted successfully")

    yield

    # Shutdown
    await close_db()


app = FastAPI(
    title="LlamaTrade Billing Service",
    description="Subscription and billing management with Stripe (Connect protocol)",
    version="0.1.0",
    lifespan=lifespan,
)

# Authentication (fail-closed); added before CORS so CORS stays outermost. The
# Stripe webhook carries a Stripe signature, not a bearer token, so its path is
# public to this middleware — signature verification in the router is its auth.
app.add_middleware(AuthMiddleware, public_suffixes=["/webhooks/stripe"])

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


_check_database = cached_engine_check(get_engine)

_health = HealthChecker("billing", "0.1.0")
_health.add_check("database", lambda: _check_database())
app.include_router(_health.create_router())
