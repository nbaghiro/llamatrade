"""Portfolio Service - Main FastAPI application."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.routers import performance, portfolio, transactions


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


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

app.include_router(portfolio.router, prefix="/portfolio", tags=["Portfolio"])
app.include_router(performance.router, prefix="/performance", tags=["Performance"])
app.include_router(transactions.router, prefix="/transactions", tags=["Transactions"])


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "portfolio", "version": "0.1.0"}
