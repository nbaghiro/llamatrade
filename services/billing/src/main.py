"""Billing Service - Main FastAPI application."""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TypedDict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from llamatrade_common.middleware import TenantMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from src.routers import payment_methods, subscriptions, usage, webhooks
from src.services.database import close_db, init_db

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    # Startup
    await init_db()
    yield
    # Shutdown
    await close_db()


app = FastAPI(
    title="LlamaTrade Billing Service",
    description="Subscription and billing management with Stripe",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:47333,http://localhost:3000").split(
        ","
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tenant context middleware (extracts JWT claims)
app.add_middleware(
    BaseHTTPMiddleware,
    dispatch=TenantMiddleware(
        jwt_secret=JWT_SECRET,
        jwt_algorithm=JWT_ALGORITHM,
        public_paths=[
            "/health",
            "/docs",
            "/openapi.json",
            "/webhooks/stripe",
            "/api/webhooks/stripe",
            "/subscriptions/plans",
            "/api/subscriptions/plans",
        ],
    ),
)

# Mount routers to handle both direct and gateway-routed requests
# Gateway routes /api/subscriptions/* and /api/billing/* to this service
app.include_router(subscriptions.router, prefix="/subscriptions", tags=["Subscriptions"])
app.include_router(subscriptions.router, prefix="/api/subscriptions", tags=["Subscriptions"])
app.include_router(payment_methods.router, prefix="/payment-methods", tags=["Payment Methods"])
app.include_router(
    payment_methods.router, prefix="/api/billing/payment-methods", tags=["Payment Methods"]
)
app.include_router(usage.router, prefix="/usage", tags=["Usage"])
app.include_router(usage.router, prefix="/api/usage", tags=["Usage"])
app.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
app.include_router(webhooks.router, prefix="/api/webhooks", tags=["Webhooks"])


class HealthResponse(TypedDict):
    """Health check response."""

    status: str
    service: str
    version: str


@app.get("/health")
async def health_check() -> HealthResponse:
    return {"status": "healthy", "service": "billing", "version": "0.1.0"}
