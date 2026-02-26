"""Portfolio Service - Main FastAPI application."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TypedDict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from llamatrade_common.middleware import TenantMiddleware
from llamatrade_db import close_db, init_db
from starlette.middleware.base import BaseHTTPMiddleware

from src.routers import performance, portfolio, transactions

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")


class HealthResponse(TypedDict):
    status: str
    service: str
    version: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler."""
    await init_db()
    yield
    await close_db()


app = FastAPI(
    title="LlamaTrade Portfolio Service",
    description="Portfolio tracking and performance analytics",
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

app.add_middleware(
    BaseHTTPMiddleware,
    dispatch=TenantMiddleware(
        jwt_secret=JWT_SECRET,
        jwt_algorithm=JWT_ALGORITHM,
        public_paths=["/health", "/docs", "/openapi.json"],
    ),
)

app.include_router(portfolio.router, prefix="/portfolio", tags=["Portfolio"])
app.include_router(performance.router, prefix="/performance", tags=["Performance"])
app.include_router(transactions.router, prefix="/transactions", tags=["Transactions"])


@app.get("/health")
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return {"status": "healthy", "service": "portfolio", "version": "0.1.0"}
