"""Strategy Service - FastAPI with Connect protocol.

This service manages trading strategies for LlamaTrade.
It exposes endpoints via Connect protocol for direct browser access.
"""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

# Configuration
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:8800,http://localhost:3000,http://localhost:47333"
).split(",")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler."""
    # Mount Connect ASGI app
    try:
        from llamatrade.v1.strategy_connect import StrategyServiceASGIApplication
        from src.grpc.servicer import StrategyServicer

        servicer = StrategyServicer()
        connect_app = StrategyServiceASGIApplication(servicer)
        app.mount("/", connect_app)
        logger.info("Connect ASGI application mounted successfully")
    except ImportError as e:
        logger.warning("Connect dependencies not available: %s", e)

    yield


app = FastAPI(
    title="LlamaTrade Strategy Service",
    description="Strategy management service for LlamaTrade (Connect protocol)",
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
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "strategy",
        "version": "0.1.0",
    }
