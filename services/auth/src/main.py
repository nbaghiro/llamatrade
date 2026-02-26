"""Auth Service - Main FastAPI application."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from llamatrade_common.middleware import TenantMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from src.routers import api_keys, auth, tenants, users
from src.services.database import close_db, init_db

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler."""
    # Startup
    await init_db()
    yield
    # Shutdown
    await close_db()


app = FastAPI(
    title="LlamaTrade Auth Service",
    description="Authentication and authorization service for LlamaTrade",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
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
            "/auth/register",
            "/auth/login",
            "/auth/refresh",
        ],
    ),
)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(tenants.router, prefix="/tenants", tags=["Tenants"])
app.include_router(api_keys.router, prefix="/api-keys", tags=["API Keys"])


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "auth",
        "version": "0.1.0",
    }
