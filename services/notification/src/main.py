"""Notification Service - FastAPI with Connect protocol.

Serves the notification RPCs and runs the durable delivery consumer over the
``notifications`` stream: persist the in-app row, then deliver to email and
webhooks. Producers publish fire-and-forget; this service is the only reader.
"""

import asyncio
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

from llamatrade_common import AuthMiddleware, HealthChecker, check_postgres, supervise
from llamatrade_common.health import check_kafka
from llamatrade_db import close_db, get_database_url, get_pool_stats, get_session_maker
from llamatrade_db.session import verify_rls_enforcement
from llamatrade_events import KafkaTransport
from llamatrade_telemetry import init_telemetry

logger = logging.getLogger(__name__)

# Configuration
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:8800,http://localhost:3000,http://localhost:47333"
).split(",")

SHUTDOWN_GRACE_SECONDS = 10.0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan handler."""
    # Fail closed (prod/staging) if the DB role can bypass RLS.
    await verify_rls_enforcement()

    # Mount the Connect ASGI app. A missing dependency is fatal: the service
    # cannot serve its RPCs without it, so let the ImportError propagate rather
    # than booting a process that passes health checks but resolves no endpoint.
    from llamatrade_proto.generated.notification_connect import (
        NotificationService,
        NotificationServiceASGIApplication,
    )

    from src.grpc.servicer import NotificationServicer

    servicer = NotificationServicer()
    # gRPC ServicerContext and Connect RequestContext are compatible at runtime.
    connect_app = NotificationServiceASGIApplication(cast(NotificationService, servicer))
    app.mount("/", cast(ASGIApp, connect_app))
    logger.info("Connect ASGI application mounted successfully")

    # Durable delivery consumer over the notifications stream.
    from llamatrade_db import get_engine
    from llamatrade_events.catalog.notifications import NotificationEvents

    from src.alerts.market_loop import run_market_loop
    from src.delivery import DeliveryDispatcher
    from src.tasks.consumer import run_notification_consumer

    stop_event = asyncio.Event()
    events = NotificationEvents()
    app.state.kafka_transport = events.bus.transport
    session_factory = get_session_maker()
    consumer_task = asyncio.create_task(
        supervise(
            lambda: run_notification_consumer(events, session_factory, stop_event=stop_event),
            name="notification-consumer",
            stop_event=stop_event,
        )
    )
    # Market-driven price alerts: one leader-elected loop over the bars tail.
    market_task = asyncio.create_task(
        supervise(
            lambda: run_market_loop(
                get_engine(),
                session_factory,
                DeliveryDispatcher(session_factory),
                stop_event=stop_event,
            ),
            name="notification-market-loop",
            stop_event=stop_event,
        )
    )

    yield

    stop_event.set()
    _, pending = await asyncio.wait({consumer_task, market_task}, timeout=SHUTDOWN_GRACE_SECONDS)
    for task in pending:
        task.cancel()
    await events.close()
    await close_db()


app = FastAPI(
    title="LlamaTrade Notification Service",
    description="Alerts, webhooks, email notifications (Connect protocol)",
    version="0.1.0",
    lifespan=lifespan,
)

# Authentication (fail-closed); added before CORS so CORS stays outermost.
app.add_middleware(AuthMiddleware)

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
init_telemetry(app, service="notification", pool_stats_provider=get_pool_stats)


async def _check_kafka() -> bool:
    """Kafka health answered from the consumer's shared transport when live."""
    transport = getattr(app.state, "kafka_transport", None)
    if isinstance(transport, KafkaTransport):
        return await check_kafka(is_alive=transport.is_connected)
    return await check_kafka()


_health = HealthChecker("notification", "0.1.0")
_health.add_check("database", lambda: check_postgres(get_database_url()), critical=False)
# Kafka carries the notification stream; non-critical so reads stay available.
_health.add_check("kafka", _check_kafka, critical=False)
app.include_router(_health.create_router())
