"""Portfolio Service - FastAPI with Connect protocol.

This service handles portfolio tracking and performance analytics.
It exposes endpoints via Connect protocol for direct browser access.
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

from llamatrade_common import AuthMiddleware, HealthChecker, check_postgres
from llamatrade_common.health import check_kafka
from llamatrade_db import (
    close_db,
    get_database_url,
    get_pool_stats,
    get_session_maker,
)
from llamatrade_db.session import verify_rls_enforcement
from llamatrade_events import KafkaTransport
from llamatrade_telemetry import init_telemetry, metrics

logger = logging.getLogger(__name__)

CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:8800,http://localhost:3000,http://localhost:47333"
).split(",")
RECONCILIATION_INTERVAL_SECONDS = float(os.getenv("LEDGER_RECONCILE_INTERVAL_SECONDS", "300"))
SNAPSHOT_INTERVAL_SECONDS = float(os.getenv("LEDGER_SNAPSHOT_INTERVAL_SECONDS", "3600"))
CORPORATE_ACTIONS_INTERVAL_SECONDS = float(
    os.getenv("LEDGER_CORPORATE_ACTIONS_INTERVAL_SECONDS", "86400")
)
# Grace period for shadow tasks to drain on shutdown before force-cancel.
SHUTDOWN_GRACE_SECONDS = 5.0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan handler."""
    # Fail closed (prod/staging) if the connected DB role can bypass RLS; no DDL, migrations own the schema so startup never runs create_all.
    await verify_rls_enforcement()

    # Mount Connect ASGI apps; the LedgerService is hosted in this same process, so a missing Connect dependency must crash startup (ImportError propagates) rather than boot with no RPC surface. Mount LedgerService at its own path FIRST, then PortfolioService as the catch-all.
    from llamatrade_proto.generated.ledger_connect import (
        LedgerService,
        LedgerServiceASGIApplication,
    )
    from llamatrade_proto.generated.portfolio_connect import (
        PortfolioService,
        PortfolioServiceASGIApplication,
    )

    from src.grpc.ledger_servicer import LedgerServicer
    from src.grpc.servicer import PortfolioServicer

    ledger_app = LedgerServiceASGIApplication(cast(LedgerService, LedgerServicer()))
    app.mount(ledger_app.path, cast(ASGIApp, ledger_app))

    connect_app = PortfolioServiceASGIApplication(cast(PortfolioService, PortfolioServicer()))
    app.mount("/", cast(ASGIApp, connect_app))
    logger.info("Connect ASGI applications mounted (portfolio + ledger)")

    # Report (never merge) accounts that share a broker account within a tenant.
    try:
        from llamatrade_db import system_session

        from src.repositories import find_duplicate_broker_accounts
        from src.services.onboarding_service import report_duplicate_broker_accounts

        sweep_reason = "duplicate broker account sweep"
        async with system_session(get_session_maker(), reason=sweep_reason) as sweep_db:
            report_duplicate_broker_accounts(await find_duplicate_broker_accounts(sweep_db))
    except Exception as e:
        logger.warning("duplicate broker-account sweep failed: %s", e)

    # Ledger runtime (the ledger is the book of record): ingest fills, reconcile
    # against broker truth, and materialize the read-side equity-curve snapshots.
    ledger_tasks: list[asyncio.Task[None]] = []
    stop_event = asyncio.Event()
    fills = None
    app.state.ledger_runtime_started = False
    app.state.ledger_tasks = []
    app.state.ledger_writer_active = False
    app.state.kafka_transport = None
    try:
        from llamatrade_events import FillEvents

        from src.clients.market_data import get_market_data_client
        from src.tasks.fill_ingestion import (
            FillLagTracker,
            consume_fill_stream,
            make_fill_handler,
            monitor_stream_lag,
        )
        from src.tasks.supervisor import supervise
        from src.tasks.writer_election import ledger_writer_loop

        session_factory = get_session_maker()
        fill_handler = make_fill_handler(session_factory)
        lag_tracker = FillLagTracker()
        app.state.fill_lag_tracker = lag_tracker
        app.state.fill_consumer_active = False

        # Durable fill ingestion over Kafka: trading produces proto LedgerFill/LedgerReservation keyed by account_id; the writer's event_id dedupe makes redelivery a no-op (portfolio-ledger.md).
        fills = FillEvents()
        # The fill consumer is a durable group role, so its shared transport answers the Kafka health probe (no second broker connection).
        app.state.kafka_transport = fills.bus.transport

        # Fill ingestion runs on EVERY pod: Kafka assigns each account's partition to one group member, giving one-writer-per-account with automatic failover — no single-consumer election needed.
        metrics.ledger.fill_consumer_active.set(1.0)
        app.state.fill_consumer_active = True
        consumer_name = os.getenv("HOSTNAME", "portfolio-0")
        ledger_tasks.append(
            asyncio.create_task(
                supervise(
                    lambda: consume_fill_stream(fills, fill_handler, consumer_name=consumer_name),
                    name="fill-consumer",
                    stop_event=stop_event,
                )
            )
        )

        # The ledger WRITERS (drift events, equity snapshots, corporate-action detection) need a single active pod — replicas would double-write — so they run inside a continuous election that re-checks the advisory lock before every sweep pass.
        def _note_leadership(active: bool) -> None:
            app.state.ledger_writer_active = active

        ledger_tasks.append(
            asyncio.create_task(
                supervise(
                    lambda: ledger_writer_loop(
                        session_factory,
                        get_market_data_client(),
                        stop_event=stop_event,
                        reconcile_interval_seconds=RECONCILIATION_INTERVAL_SECONDS,
                        snapshot_interval_seconds=SNAPSHOT_INTERVAL_SECONDS,
                        corporate_actions_interval_seconds=CORPORATE_ACTIONS_INTERVAL_SECONDS,
                        on_leadership=_note_leadership,
                    ),
                    name="writer-election",
                    stop_event=stop_event,
                )
            )
        )

        # The lag monitor is read-only; every pod runs it. Supervised so a crash restarts it with backoff rather than silently halting the runtime.
        ledger_tasks.append(
            asyncio.create_task(
                supervise(
                    lambda: monitor_stream_lag(
                        fills.bus, stop_event=stop_event, tracker=lag_tracker
                    ),
                    name="lag-monitor",
                    stop_event=stop_event,
                )
            )
        )

        app.state.ledger_tasks = ledger_tasks
        app.state.ledger_runtime_started = True
        logger.info(
            "Ledger runtime started: fill consumer + reconciliation + snapshots (writers gated)"
        )
    except Exception as e:  # the ledger runtime must never block startup
        logger.warning("Failed to start ledger runtime: %s", e)

    yield

    # Shutdown: signal the ledger tasks to stop and let them drain gracefully (they wake within ~1s of stop_event); only force-cancel stragglers so their `finally` transport cleanup completes.
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

# Authentication (fail-closed); added before CORS so CORS stays outermost.
app.add_middleware(AuthMiddleware)

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


def _ledger_runtime_status() -> str:
    """Liveness of the background ledger runtime (ingest/reconcile/snapshot).

    ``down`` if it never started, ``degraded`` if a loop crashed, else ``ok``.
    Reads stay available regardless — this only surfaces background-task health.
    """
    if not getattr(app.state, "ledger_runtime_started", False):
        return "down"
    for task in getattr(app.state, "ledger_tasks", []):
        if task.done() and not task.cancelled() and task.exception() is not None:
            return "degraded"
    # A hung group member stops draining its partitions; a sustained backlog is the tell. Fail health so the liveness probe recycles this pod and Kafka reassigns its partitions.
    tracker = getattr(app.state, "fill_lag_tracker", None)
    if getattr(app.state, "fill_consumer_active", False) and tracker is not None:
        if tracker.is_backlogged:
            return "degraded"
    return "ok"


async def _check_ledger_runtime() -> bool:
    """Background ledger-runtime liveness; the tri-state surfaces as the check message."""
    status = _ledger_runtime_status()
    if status != "ok":
        raise RuntimeError(status)
    return True


async def _check_kafka() -> bool:
    """Kafka health answered from the shared fill-stream transport (no second connection).

    The fill consumer holds a live durable-group transport whose ``is_connected``
    answers the probe; before the runtime starts (or if it failed to start) fall
    back to a short authenticated probe.
    """
    transport = getattr(app.state, "kafka_transport", None)
    if isinstance(transport, KafkaTransport):
        return await check_kafka(is_alive=transport.is_connected)
    return await check_kafka()


_health = HealthChecker("portfolio", "0.1.0")
_health.add_check("database", lambda: check_postgres(get_database_url()), critical=False)
# Kafka carries the ledger fill stream; non-critical so reads stay available.
_health.add_check("kafka", _check_kafka, critical=False)
_health.add_check("ledger_runtime", _check_ledger_runtime, critical=False)
app.include_router(_health.create_router())
