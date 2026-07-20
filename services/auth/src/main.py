"""Auth Service - FastAPI with Connect protocol.

This service handles authentication and authorization for LlamaTrade.
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
from llamatrade_db import close_db, get_pool_stats, init_db
from llamatrade_telemetry import init_telemetry

from src.routers.oauth import router as oauth_router

logger = logging.getLogger(__name__)

CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:8800,http://localhost:3000,http://localhost:47333"
).split(",")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan handler."""
    try:
        await init_db()
    except Exception as e:
        # Log but don't fail - allows testing without database
        logger.warning("Database initialization failed (non-critical): %s", e)

    try:
        from llamatrade_proto.generated.auth_connect import AuthServiceASGIApplication

        from src.grpc.servicer import AuthServicer

        servicer = AuthServicer()
        connect_app = AuthServiceASGIApplication(servicer)
        app.mount("/", cast(ASGIApp, connect_app))
        logger.info("Connect ASGI application mounted successfully")
    except ImportError as e:
        logger.warning("Connect dependencies not available: %s", e)

    yield

    await close_db()


app = FastAPI(
    title="LlamaTrade Auth Service",
    description="Authentication and authorization service for LlamaTrade (Connect protocol)",
    version="0.1.0",
    lifespan=lifespan,
)

# Authentication (fail-closed); Login/Register/RefreshToken stay public. The
# OAuth callback is a browser redirect from Alpaca with no bearer token, so it is
# public too (its trust comes from the signed ``state``); /oauth/alpaca/start
# stays protected so the initiating tenant/user is known.
# Added before CORS so CORS remains outermost (preflight + headers on 401s).
app.add_middleware(
    AuthMiddleware,
    public_suffixes=[
        "/Login",
        "/Register",
        "/RefreshToken",
        # Alpaca OAuth entry/return for users with no session yet; /oauth/alpaca/start
        # stays protected so the linking tenant/user is known.
        "/oauth/alpaca/authorize",
        "/oauth/alpaca/callback",
        "/oauth/alpaca/exchange",
        "/oauth/alpaca/complete-signup",
    ],
)

# CORS middleware - must allow Connect protocol headers
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Export DB connection-pool stats on /metrics
init_telemetry(app, service="auth", pool_stats_provider=get_pool_stats)

# Alpaca OAuth browser-redirect routes (mounted before the Connect catch-all).
app.include_router(oauth_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "auth",
        "version": "0.1.0",
    }
