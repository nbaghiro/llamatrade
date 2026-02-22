"""Strategy Service - Main FastAPI application."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.routers import indicators, strategies, templates


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="LlamaTrade Strategy Service",
    description="Strategy management and execution service for LlamaTrade",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(strategies.router, prefix="/strategies", tags=["Strategies"])
app.include_router(templates.router, prefix="/templates", tags=["Templates"])
app.include_router(indicators.router, prefix="/indicators", tags=["Indicators"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "strategy",
        "version": "0.1.0",
    }
