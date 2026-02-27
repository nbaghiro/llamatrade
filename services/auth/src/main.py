"""Auth Service - FastAPI with Connect protocol.

This service handles authentication and authorization for LlamaTrade.
It exposes endpoints via Connect protocol for direct browser access.
"""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.services.database import close_db, init_db

logger = logging.getLogger(__name__)

# Configuration
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:8800,http://localhost:3000,http://localhost:47333"
).split(",")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler."""
    # Startup
    try:
        await init_db()
    except Exception as e:
        # Log but don't fail - allows testing without database
        logger.warning("Database initialization failed (non-critical): %s", e)

    # Mount Connect ASGI app
    try:
        from llamatrade.v1.auth_connect import AuthServiceASGIApplication
        from src.grpc.servicer import AuthServicer

        servicer = AuthServicer()
        connect_app = AuthServiceASGIApplication(servicer)
        app.mount("/", connect_app)
        logger.info("Connect ASGI application mounted successfully")
    except ImportError as e:
        logger.warning("Connect dependencies not available: %s", e)

    yield

    # Shutdown
    await close_db()


app = FastAPI(
    title="LlamaTrade Auth Service",
    description="Authentication and authorization service for LlamaTrade (Connect protocol)",
    version="0.1.0",
    lifespan=lifespan,
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


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "auth",
        "version": "0.1.0",
    }
