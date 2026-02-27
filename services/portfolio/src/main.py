"""Portfolio Service - FastAPI with Connect protocol.

This service handles portfolio tracking and performance analytics.
It exposes endpoints via Connect protocol for direct browser access.
"""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TypedDict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from llamatrade_db import close_db, init_db

logger = logging.getLogger(__name__)

# Configuration
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:8800,http://localhost:3000,http://localhost:47333"
).split(",")


class HealthResponse(TypedDict):
    status: str
    service: str
    version: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler."""
    # Startup
    try:
        await init_db()
    except Exception as e:
        logger.warning("Database initialization failed (non-critical): %s", e)

    # Mount Connect ASGI app
    try:
        from llamatrade.v1.portfolio_connect import PortfolioServiceASGIApplication

        from src.grpc.servicer import PortfolioServicer

        servicer = PortfolioServicer()
        connect_app = PortfolioServiceASGIApplication(servicer)
        app.mount("/", connect_app)
        logger.info("Connect ASGI application mounted successfully")
    except ImportError as e:
        logger.warning("Connect dependencies not available: %s", e)

    yield

    # Shutdown
    await close_db()


app = FastAPI(
    title="LlamaTrade Portfolio Service",
    description="Portfolio tracking and performance analytics (Connect protocol)",
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


@app.get("/health")
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return {"status": "healthy", "service": "portfolio", "version": "0.1.0"}
