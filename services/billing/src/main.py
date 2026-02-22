"""Billing Service - Main FastAPI application."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.routers import subscriptions, usage, webhooks


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="LlamaTrade Billing Service",
    description="Subscription and billing management with Stripe",
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

app.include_router(subscriptions.router, prefix="/subscriptions", tags=["Subscriptions"])
app.include_router(usage.router, prefix="/usage", tags=["Usage"])
app.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "billing", "version": "0.1.0"}
