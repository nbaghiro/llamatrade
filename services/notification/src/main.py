"""Notification Service - Main FastAPI application."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.routers import alerts, channels, notifications


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield


app = FastAPI(
    title="LlamaTrade Notification Service",
    description="Alerts, webhooks, email/SMS notifications",
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

app.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
app.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
app.include_router(channels.router, prefix="/channels", tags=["Channels"])


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy", "service": "notification", "version": "0.1.0"}
