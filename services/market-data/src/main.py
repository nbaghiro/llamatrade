"""Market Data Service - Main FastAPI application."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.routers import bars, quotes, streaming


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup - initialize Alpaca client
    yield
    # Shutdown


app = FastAPI(
    title="LlamaTrade Market Data Service",
    description="Real-time and historical market data service for LlamaTrade",
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
app.include_router(bars.router, prefix="/bars", tags=["Bars"])
app.include_router(quotes.router, prefix="/quotes", tags=["Quotes"])
app.include_router(streaming.router, prefix="/stream", tags=["Streaming"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "market-data",
        "version": "0.1.0",
    }
