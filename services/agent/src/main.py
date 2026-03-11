"""Agent Service - FastAPI with Connect protocol.

This service provides the AI Strategy Agent (Copilot) for LlamaTrade.
It enables users to generate, edit, and optimize trading strategies
through natural language conversation.

Port: 8890
"""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# Configuration
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:8800,http://localhost:3000,http://localhost:47333"
).split(",")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler."""
    # Initialize database (non-critical - may fail if DB not available)
    try:
        from src.services.database import init_db

        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.warning("Database initialization failed (non-critical): %s", e)

    # Mount Connect ASGI app
    try:
        from llamatrade_proto.generated.agent_connect import (
            AgentService,
            AgentServiceASGIApplication,
        )

        from src.grpc.servicer import AgentServicer

        servicer = AgentServicer()
        connect_app = AgentServiceASGIApplication(cast(AgentService, servicer))
        app.mount("/", cast(ASGIApp, connect_app))
        logger.info("Connect ASGI application mounted successfully")
    except ImportError as e:
        logger.warning("Connect dependencies not available: %s", e)

    yield

    # Cleanup
    try:
        from src.services.database import close_db

        await close_db()
    except Exception as e:
        logger.warning("Database cleanup failed: %s", e)


app = FastAPI(
    title="LlamaTrade Agent Service",
    description="AI Strategy Agent (Copilot) service for LlamaTrade (Connect protocol)",
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
        "service": "agent",
        "version": "0.1.0",
    }
