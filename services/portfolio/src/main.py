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

from llamatrade_common.eventbus import streams_ledger_fills_enabled
from llamatrade_common.observability import enable_db_pool_metrics
from llamatrade_db import close_db, get_pool_stats, get_session_maker, init_db

from src.ledger.settings import shadow_mode_enabled

logger = logging.getLogger(__name__)

# Configuration
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:8800,http://localhost:3000,http://localhost:47333"
).split(",")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
RECONCILIATION_INTERVAL_SECONDS = float(os.getenv("LEDGER_RECONCILE_INTERVAL_SECONDS", "300"))
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

    # Shadow-mode ledger runtime: ingest fills + reconcile against broker truth.
    # Read-only — drives nothing — and fully gated behind LEDGER_SHADOW_MODE.
    shadow_tasks: list[asyncio.Task[None]] = []
    stop_event = asyncio.Event()
    redis_client = None
    event_bus = None
    if shadow_mode_enabled():
        try:
            import redis.asyncio as aioredis

            from src.tasks.fill_ingestion import consume_fills, make_fill_handler
            from src.tasks.reconciliation import reconciliation_loop

            session_factory = get_session_maker()
            redis_client = aioredis.from_url(REDIS_URL)
            fill_handler = make_fill_handler(session_factory)
            shadow_tasks.append(
                asyncio.create_task(
                    consume_fills(
                        redis_client,
                        fill_handler,
                        stop_event=stop_event,
                    )
                )
            )
            shadow_tasks.append(
                asyncio.create_task(
                    reconciliation_loop(
                        session_factory,
                        interval_seconds=RECONCILIATION_INTERVAL_SECONDS,
                        stop_event=stop_event,
                    )
                )
            )

            # Durable Streams consumer (dual-read during the soak — the
            # writer's event_id dedupe makes consuming both paths a no-op on
            # the second delivery). Stops via task cancellation on shutdown.
            if streams_ledger_fills_enabled():
                from llamatrade_common.eventbus import EventBus

                from src.tasks.fill_ingestion import consume_fill_stream, monitor_stream_lag

                event_bus = EventBus(REDIS_URL)
                shadow_tasks.append(
                    asyncio.create_task(
                        consume_fill_stream(
                            event_bus,
                            fill_handler,
                            consumer_name=os.getenv("HOSTNAME", "portfolio-0"),
                        )
                    )
                )
                shadow_tasks.append(
                    asyncio.create_task(monitor_stream_lag(event_bus, stop_event=stop_event))
                )
                logger.info("Ledger fills stream consumer started (consumer group)")

            logger.info("Ledger shadow mode enabled: fill ingestion + reconciliation started")
        except Exception as e:  # shadow runtime must never block startup
            logger.warning("Failed to start ledger shadow runtime: %s", e)

    yield

    # Shutdown: signal the shadow tasks to stop and let them drain gracefully
    # (both wake within ~1s of stop_event). Only force-cancel stragglers, so
    # the Redis unsubscribe/cleanup in their `finally` blocks runs to completion.
    stop_event.set()
    if shadow_tasks:
        _done, pending = await asyncio.wait(shadow_tasks, timeout=SHUTDOWN_GRACE_SECONDS)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
    if redis_client is not None:
        await redis_client.aclose()
    if event_bus is not None:
        await event_bus.close()

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
enable_db_pool_metrics(app, "portfolio", get_pool_stats)


@app.get("/health")
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return {"status": "healthy", "service": "portfolio", "version": "0.1.0"}
