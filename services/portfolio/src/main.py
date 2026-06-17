"""Portfolio Service - FastAPI with Connect protocol.

This service handles portfolio tracking and performance analytics.
It exposes endpoints via Connect protocol for direct browser access.
"""

import asyncio
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TypedDict, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

from llamatrade_db import close_db, get_pool_stats, get_session_maker, init_db
from llamatrade_telemetry import init_telemetry

logger = logging.getLogger(__name__)

# Configuration
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:8800,http://localhost:3000,http://localhost:47333"
).split(",")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
RECONCILIATION_INTERVAL_SECONDS = float(os.getenv("LEDGER_RECONCILE_INTERVAL_SECONDS", "300"))
SNAPSHOT_INTERVAL_SECONDS = float(os.getenv("LEDGER_SNAPSHOT_INTERVAL_SECONDS", "3600"))
# Grace period for shadow tasks to drain on shutdown before force-cancel.
SHUTDOWN_GRACE_SECONDS = 5.0


class HealthResponse(TypedDict):
    status: str
    service: str
    version: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan handler."""
    # Startup
    try:
        await init_db()
    except Exception as e:
        logger.warning("Database initialization failed (non-critical): %s", e)

    # Mount Connect ASGI apps. The LedgerService is hosted by this same process
    # (it projects from the event log this service owns). Mount it at its own
    # service path FIRST, then the PortfolioService as the catch-all at "/".
    try:
        from llamatrade_proto.generated.ledger_connect import LedgerServiceASGIApplication
        from llamatrade_proto.generated.portfolio_connect import PortfolioServiceASGIApplication

        from src.grpc.ledger_servicer import LedgerServicer
        from src.grpc.servicer import PortfolioServicer

        ledger_app = LedgerServiceASGIApplication(LedgerServicer())
        app.mount(ledger_app.path, cast(ASGIApp, ledger_app))

        connect_app = PortfolioServiceASGIApplication(PortfolioServicer())
        app.mount("/", cast(ASGIApp, connect_app))
        logger.info("Connect ASGI applications mounted (portfolio + ledger)")
    except ImportError as e:
        logger.warning("Connect dependencies not available: %s", e)

    # Ledger runtime (the ledger is the book of record): ingest fills, reconcile
    # against broker truth, and materialize the read-side equity-curve snapshots.
    ledger_tasks: list[asyncio.Task[None]] = []
    stop_event = asyncio.Event()
    fills = None
    try:
        from llamatrade_events import EventBus, FillEvents, RedisStreamsTransport

        from src.clients.market_data import get_market_data_client
        from src.tasks.equity_snapshot import snapshot_loop
        from src.tasks.fill_ingestion import (
            consume_fill_stream,
            make_fill_handler,
            monitor_stream_lag,
        )
        from src.tasks.reconciliation import reconciliation_loop

        session_factory = get_session_maker()
        fill_handler = make_fill_handler(session_factory)

        # Durable fill ingestion via the Redis Streams consumer group: a dead
        # pod's pending entries are reclaimed via XAUTOCLAIM; the writer's
        # event_id dedupe makes redelivery a no-op. Trading publishes proto
        # LedgerFill/LedgerReservation onto lt:ledger:fills (CONTRACTS.md §1/§4).
        fills = FillEvents(bus=EventBus(RedisStreamsTransport(REDIS_URL)))
        ledger_tasks.append(
            asyncio.create_task(
                consume_fill_stream(
                    fills,
                    fill_handler,
                    consumer_name=os.getenv("HOSTNAME", "portfolio-0"),
                )
            )
        )
        ledger_tasks.append(
            asyncio.create_task(monitor_stream_lag(fills.bus, stop_event=stop_event))
        )
        ledger_tasks.append(
            asyncio.create_task(
                reconciliation_loop(
                    session_factory,
                    interval_seconds=RECONCILIATION_INTERVAL_SECONDS,
                    stop_event=stop_event,
                )
            )
        )
        ledger_tasks.append(
            asyncio.create_task(
                snapshot_loop(
                    session_factory,
                    get_market_data_client(),
                    stop_event=stop_event,
                    interval_seconds=SNAPSHOT_INTERVAL_SECONDS,
                )
            )
        )

        logger.info("Ledger runtime started: fill stream consumer + reconciliation + snapshots")
    except Exception as e:  # the ledger runtime must never block startup
        logger.warning("Failed to start ledger runtime: %s", e)

    yield

    # Shutdown: signal the ledger tasks to stop and let them drain gracefully
    # (they wake within ~1s of stop_event). Only force-cancel stragglers, so
    # the Redis cleanup in their `finally` blocks runs to completion.
    stop_event.set()
    if ledger_tasks:
        _done, pending = await asyncio.wait(ledger_tasks, timeout=SHUTDOWN_GRACE_SECONDS)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    if fills is not None:
        await fills.close()

    await close_db()


app = FastAPI(
    title="LlamaTrade Portfolio Service",
    description="Portfolio tracking and performance analytics (Connect protocol)",
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

# Export DB connection-pool stats on /metrics
init_telemetry(app, service="portfolio", pool_stats_provider=get_pool_stats)


@app.get("/health")
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return {"status": "healthy", "service": "portfolio", "version": "0.1.0"}
