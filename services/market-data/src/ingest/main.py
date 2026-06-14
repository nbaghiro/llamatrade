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
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from llamatrade_alpaca import (
    close_all_clients,
    close_market_data_stream,
    get_market_data_client_async,
    init_market_data_stream,
)
from llamatrade_common.events import EventBus

from src.ingest.backfill import BackfillController
from src.ingest.config import BACKFILL_TIMEFRAMES, IngestConfig, get_universe
from src.ingest.corporate_actions import CorporateActionRefresher
from src.ingest.gaps import GapRepairer
from src.ingest.stream import BarIngestor
from src.store.config import close_engine
from src.store.repository import BarStore

logger = logging.getLogger(__name__)


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


async def run() -> None:
    config = IngestConfig.from_env()
    universe = get_universe()
    if not universe:
        logger.warning(
            "MARKET_DATA_UNIVERSE is empty — ingestor has nothing to sync. "
            "Set it to a comma-separated symbol list."
        )

    store = BarStore()
    alpaca = await get_market_data_client_async()
    bus = EventBus(os.getenv("REDIS_URL"))

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

    stop = asyncio.Event()
    _install_signal_handlers(stop)

    tasks: list[asyncio.Task[None]] = []

    # 1. Initial backfill so the store is useful immediately.
    if universe:
        logger.info("Initial backfill of %d symbols", len(universe))
        await controller.run(universe, _now())

    # 2. Real-time stream write-through (minute bars).
    stream = await init_market_data_stream()
    if stream is not None and universe:
        ingestor.attach(stream)
        await stream.subscribe(bars=universe)
        tasks.append(asyncio.create_task(stream.run()))
        tasks.append(asyncio.create_task(ingestor.run_flush_loop(stop_event=stop)))
        logger.info("Streaming minute bars for %d symbols", len(universe))
    else:
        logger.warning("Alpaca stream unavailable — running backfill/repair loops only")

    # 3. Periodic maintenance loops.
    tasks.append(
        asyncio.create_task(
            _periodic(
                "backfill",
                lambda: controller.run(universe, _now()),
                config.backfill_interval_s,
                stop,
            )
        )
    )
    tasks.append(
        asyncio.create_task(
            _periodic(
                "gap-repair",
                lambda: gap_repairer.repair(universe, "1Min", _now()),
                config.gap_repair_interval_s,
                stop,
            )
        )
    )
    tasks.append(
        asyncio.create_task(
            _periodic(
                "corporate-actions",
                lambda: refresher.refresh(universe, _now()),
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
    await close_market_data_stream()
    await close_all_clients()
    await bus.close()
    await close_engine()


def _install_signal_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # e.g. Windows
            pass


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    asyncio.run(run())


if __name__ == "__main__":
    main()
