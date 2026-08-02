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

from llamatrade_common import AuthMiddleware, HealthChecker, check_redis
from llamatrade_common.health import cached_engine_check
from llamatrade_db import close_db, get_engine, get_pool_stats
from llamatrade_db.session import verify_rls_enforcement
from llamatrade_telemetry import init_telemetry

from src.redis_client import get_redis
from src.routers.oauth import router as oauth_router

logger = logging.getLogger(__name__)

CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:8800,http://localhost:3000,http://localhost:47333"
).split(",")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan handler."""
    # Fail closed (prod/staging) if the DB role can bypass RLS.
    await verify_rls_enforcement()

    # Auth is the JWKS issuer; a missing Connect dependency must fail startup
    # rather than silently serve no RPCs.
    from llamatrade_proto.generated.auth_connect import AuthServiceASGIApplication

    from src.grpc.servicer import AuthServicer

    servicer = AuthServicer()
    connect_app = AuthServiceASGIApplication(servicer)
    app.mount("/", cast(ASGIApp, connect_app))
    logger.info("Connect ASGI application mounted successfully")

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
# redis_client enables revocation checking (fails open if Redis is down).
app.add_middleware(
    AuthMiddleware,
    redis_client=get_redis(),
    public_suffixes=[
        "/Login",
        "/Register",
        "/RefreshToken",
        "/RequestPasswordReset",
        "/ResetPassword",
        "/VerifyEmail",
        "/ResendVerification",
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


_check_database = cached_engine_check(get_engine)


async def _check_revocation_redis() -> bool:
    """Revocation/rate-limit store; healthy-by-absence when REDIS_URL is unset."""
    url = os.getenv("REDIS_URL", "")
    if not url:
        return True
    return await check_redis(url)


_health = HealthChecker("auth", "0.1.0")
_health.add_check("database", lambda: _check_database())
# Redis only backs revocation/rate limits and auth fails open without it.
_health.add_check("redis", lambda: _check_revocation_redis(), critical=False)
app.include_router(_health.create_router())
