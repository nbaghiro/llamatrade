"""Backtest Service - Main FastAPI application."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.routers import backtests, websocket


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler."""
    yield


app = FastAPI(
    title="LlamaTrade Backtest Service",
    description="Historical backtesting service for trading strategies",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(backtests.router, prefix="/backtests", tags=["Backtests"])
app.include_router(websocket.router, prefix="/ws", tags=["WebSocket"])


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy", "service": "backtest", "version": "0.1.0"}
