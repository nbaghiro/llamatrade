"""Trading Service - Main FastAPI application."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.routers import orders, positions, sessions


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    yield


app = FastAPI(
    title="LlamaTrade Trading Service",
    description="Live order execution and trading session management",
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

app.include_router(orders.router, prefix="/orders", tags=["Orders"])
app.include_router(sessions.router, prefix="/sessions", tags=["Trading Sessions"])
app.include_router(positions.router, prefix="/positions", tags=["Positions"])


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "trading", "version": "0.1.0"}
