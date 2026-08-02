"""Ingest supervisor — the writer entrypoint (``python -m src.ingest.main``).

Composition root for the ingest role: wires the store, Alpaca client/stream, and
the internal bus, then runs the initial backfill, the real-time stream
write-through, and the periodic gap-repair / corporate-action / backfill loops
until terminated. This is the singleton writer workload (see the two-role plan).
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from llamatrade_alpaca import (
    MarketDataStreamClient,
    close_all_clients,
    close_market_data_stream,
    get_market_data_client_async,
    init_market_data_stream,
)
from llamatrade_events import EventBus, get_default_transport
from llamatrade_telemetry import init_telemetry

from src.ingest.backfill import BackfillController, TargetedBackfill
from src.ingest.config import BACKFILL_TIMEFRAMES, IngestConfig, get_universe
from src.ingest.corporate_actions import CorporateActionRefresher
from src.ingest.gaps import GapRepairer
from src.ingest.stream import BarIngestor
from src.ingest.universe import IngestUniverse
from src.metrics import record_stream_reconnect
from src.store.config import close_engine
from src.store.repository import BarStore

logger = logging.getLogger(__name__)

SERVICE_NAME = "market-data-ingest"
SERVICE_VERSION = "0.1.0"
DEFAULT_ADMIN_PORT = 8841


def _now() -> datetime:
    return datetime.now(UTC)


async def _periodic(
    name: str, fn: Callable[[], Awaitable[object]], interval_s: float, stop: asyncio.Event
) -> None:
    """Run ``fn`` every ``interval_s`` seconds until ``stop`` is set."""
    while not stop.is_set():
        try:
            await fn()
        except Exception:
            logger.exception("%s loop iteration failed", name)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_s)
        except TimeoutError:
            pass


def _build_admin_app(loops_alive: Callable[[], bool]) -> Starlette:
    """Ops surface for the ingest process; ``init_telemetry`` adds ``/metrics``.

    Args:
        loops_alive: reports whether the supervised ingest loop tasks are alive.
    """

    async def health(request: Request) -> JSONResponse:
        alive = loops_alive()
        return JSONResponse(
            {
                "status": "healthy" if alive else "unhealthy",
                "timestamp": _now().isoformat(),
                "service": SERVICE_NAME,
                "version": SERVICE_VERSION,
                "checks": {"ingest_loops": {"healthy": alive, "critical": True}},
            },
            status_code=200 if alive else 503,
        )

    return Starlette(routes=[Route("/health", health, methods=["GET"])])


class _AdminServer(uvicorn.Server):
    """Uvicorn server that leaves signal handling to the supervisor's handlers."""

    @contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield


def _build_admin_server(app: Starlette) -> uvicorn.Server:
    port = int(os.getenv("MARKET_DATA_INGEST_PORT", str(DEFAULT_ADMIN_PORT)))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning", lifespan="off")
    return _AdminServer(config)


async def _serve_admin(server: uvicorn.Server, stop: asyncio.Event) -> None:
    """Serve ``/metrics`` + ``/health`` until ``stop`` is set, then exit cleanly."""

    async def _stopper() -> None:
        await stop.wait()
        server.should_exit = True

    stopper = asyncio.create_task(_stopper())
    try:
        await server.serve()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Ingest admin server failed; /metrics and /health are down")
    finally:
        stopper.cancel()
        await asyncio.gather(stopper, return_exceptions=True)


def _install_reconnect_hook(stream: MarketDataStreamClient) -> None:
    """Install the reconnect-metric hook on the shared stream client (13A); the
    singleton factory takes no hook arguments."""
    setattr(stream, "_on_reconnect", record_stream_reconnect)


async def run() -> None:
    stop = asyncio.Event()
    _install_signal_handlers(stop)
    tasks: list[asyncio.Task[None]] = []

    # Telemetry + the admin port come up first so /metrics and /health cover the
    # initial backfill too. A task that ends before stop is set has crashed.
    admin_app = _build_admin_app(lambda: all(not t.done() for t in tasks))
    init_telemetry(admin_app, service=SERVICE_NAME, version=SERVICE_VERSION)
    admin_task = asyncio.create_task(_serve_admin(_build_admin_server(admin_app), stop))

    config = IngestConfig.from_env()
    universe = IngestUniverse(get_universe())
    # Derive the live symbols before the first backfill so new sessions are covered
    # by history too, not only by the stream.
    await universe.refresh()
    if not universe.symbols:
        logger.warning(
            "Ingest universe is empty — no MARKET_DATA_UNIVERSE baseline and no live "
            "sessions. Set MARKET_DATA_UNIVERSE to a comma-separated symbol list."
        )

    store = BarStore()
    alpaca = await get_market_data_client_async()
    bus = EventBus(get_default_transport())

    controller = BackfillController(
        store,
        alpaca,
        timeframes=BACKFILL_TIMEFRAMES,
        lookback_for={
            "1Day": config.daily_lookback_days,
            "1Min": config.minute_lookback_days,
        },
        max_concurrency=config.max_concurrency,
        fetch_limit=config.fetch_limit,
    )
    gap_repairer = GapRepairer(
        controller,
        step=timedelta(minutes=1),
        max_gap=timedelta(hours=4),
        recent_lookback_days=2,
    )
    refresher = CorporateActionRefresher(
        store, alpaca, window_days=config.corporate_action_window_days
    )
    ingestor = BarIngestor(store, bus)
    targeted = TargetedBackfill(controller, _now)

    # 1. Initial backfill so the store is useful immediately.
    if universe.symbols:
        logger.info("Initial backfill of %d symbols", len(universe.symbols))
        await controller.run(list(universe.symbols), _now())

    # 2. Real-time stream write-through (minute bars).
    stream = await init_market_data_stream()
    if stream is not None:
        _install_reconnect_hook(stream)
        ingestor.attach(stream)
        universe.attach(stream)
        if universe.symbols:
            await stream.subscribe(bars=list(universe.symbols))

        async def _supervise_stream(md_stream: MarketDataStreamClient | None) -> None:
            """Keep the singleton Alpaca stream alive: ``run()`` returns when the
            client exhausts its reconnect attempts, which would otherwise silently
            end all real-time write-through until a manual restart. Re-establish a
            fresh connection and re-subscribe instead."""
            restart_delay_s = 15.0
            while not stop.is_set():
                if md_stream is None:
                    await asyncio.sleep(restart_delay_s)
                    md_stream = await init_market_data_stream()
                    if md_stream is None:
                        logger.warning("market-data stream re-init failed; retrying")
                        continue
                    _install_reconnect_hook(md_stream)
                    ingestor.attach(md_stream)
                    universe.attach(md_stream)
                    if universe.symbols:
                        await md_stream.subscribe(bars=list(universe.symbols))
                    logger.info("market-data stream re-established")
                try:
                    await md_stream.run()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("market-data stream loop crashed")
                if stop.is_set():
                    break
                logger.error("market-data stream ended (reconnects exhausted); re-establishing")
                await close_market_data_stream()
                universe.attach(None)
                md_stream = None

        tasks.append(asyncio.create_task(_supervise_stream(stream)))
        tasks.append(asyncio.create_task(ingestor.run_flush_loop(stop_event=stop)))
        logger.info("Streaming minute bars for %d symbols", len(universe.symbols))
    else:
        logger.warning("Alpaca stream unavailable — running backfill/repair loops only")

    # 3. Periodic maintenance loops. Each reads the universe at call time, so a
    # session started since the last pass is picked up without a restart.
    async def _refresh_universe() -> None:
        change = await universe.refresh()
        targeted.schedule(change.added)

    tasks.append(
        asyncio.create_task(
            _periodic(
                "universe-refresh",
                _refresh_universe,
                config.universe_refresh_interval_s,
                stop,
            )
        )
    )
    tasks.append(
        asyncio.create_task(
            _periodic(
                "backfill",
                lambda: controller.run(list(universe.symbols), _now()),
                config.backfill_interval_s,
                stop,
            )
        )
    )
    tasks.append(
        asyncio.create_task(
            _periodic(
                "gap-repair",
                lambda: gap_repairer.repair(list(universe.symbols), "1Min", _now()),
                config.gap_repair_interval_s,
                stop,
            )
        )
    )
    tasks.append(
        asyncio.create_task(
            _periodic(
                "corporate-actions",
                lambda: refresher.refresh(list(universe.symbols), _now()),
                config.corporate_action_interval_s,
                stop,
            )
        )
    )

    logger.info("Ingestor running; awaiting shutdown signal")
    await stop.wait()

    logger.info("Shutting down ingestor")
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await targeted.aclose()
    await close_market_data_stream()
    await close_all_clients()
    await bus.close()
    await close_engine()
    try:
        await asyncio.wait_for(admin_task, timeout=5.0)
    except TimeoutError:
        admin_task.cancel()
        await asyncio.gather(admin_task, return_exceptions=True)


def _install_signal_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # e.g. Windows
            pass


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
