"""Celery tasks for backtest execution.

The Celery worker is the ONLY execution path for backtests: the RunBacktest
RPC enqueues run_backtest_task, which delegates to BacktestService.run_backtest.
All simulation, persistence, and progress logic lives in the service — this
module only owns task lifecycle (sessions, retries).
"""

import asyncio
import concurrent.futures
import logging
import os
from collections.abc import AsyncGenerator, Coroutine
from contextlib import asynccontextmanager
from uuid import UUID

from celery import shared_task
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llamatrade_db.models.backtest import Backtest
from llamatrade_proto.generated.backtest_pb2 import (
    BACKTEST_STATUS_FAILED,
    BACKTEST_STATUS_PENDING,
)

from src.services.backtest_service import (
    BacktestService,
    MarketDataError,
    MarketDataFetcher,
    get_market_data_client,
)

logger = logging.getLogger(__name__)


def _run_async[T](coro: Coroutine[object, object, T]) -> T:
    """Run a coroutine to completion from synchronous task code.

    In a real Celery worker there is no running event loop and this is just
    asyncio.run(). Under eager mode (tests) the task executes inside the
    caller's event loop, so the coroutine runs in a fresh thread instead.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coro).result()


# Database configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://llamatrade:llamatrade@localhost:5432/llamatrade",
)


def _create_market_data_client() -> MarketDataFetcher:
    """Market data client factory (patchable in tests)."""
    return get_market_data_client()


@asynccontextmanager
async def _session_scope() -> AsyncGenerator[AsyncSession]:
    """Provide a database session with engine lifecycle management."""
    engine = create_async_engine(DATABASE_URL)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


async def _execute_backtest(backtest_id: str, tenant_id: str) -> dict[str, str | float | int]:
    """Run a backtest through the service layer."""
    async with _session_scope() as db:
        async with BacktestService(db, market_data_client=_create_market_data_client()) as service:
            result = await service.run_backtest(UUID(backtest_id), UUID(tenant_id))
            return {
                "status": "completed",
                "backtest_id": backtest_id,
                "total_return": result.metrics.total_return,
                "total_trades": result.metrics.total_trades,
            }


async def _reap_stale_backtests() -> dict[str, int]:
    """Run one reaper pass through the service layer."""
    async with _session_scope() as db:
        async with BacktestService(db, market_data_client=_create_market_data_client()) as service:
            return await service.reap_stale_backtests()


async def _reset_to_pending(backtest_id: str, tenant_id: str) -> None:
    """Reset a FAILED backtest to PENDING so a retry attempt can run.

    The service marks the row FAILED before a MarketDataError propagates;
    without this reset, run_backtest would refuse the retry with "cannot run".
    """
    async with _session_scope() as db:
        await db.execute(
            update(Backtest)
            .where(
                Backtest.id == UUID(backtest_id),
                Backtest.tenant_id == UUID(tenant_id),
                Backtest.status == BACKTEST_STATUS_FAILED,
            )
            .values(status=BACKTEST_STATUS_PENDING, error_message=None)
        )
        await db.commit()


@shared_task(bind=True, max_retries=3, default_retry_delay=60, retry_backoff=True)
def run_backtest_task(
    self: object, backtest_id: str, tenant_id: str
) -> dict[str, str | float | int]:
    """Execute a backtest as a Celery task.

    Transient market-data failures are retried (with the row reset to
    PENDING between attempts); other failures are terminal and the row
    stays FAILED with its error message.

    Args:
        backtest_id: UUID of the backtest to run
        tenant_id: UUID of the tenant

    Returns:
        Dictionary with status and results
    """
    logger.info(f"Starting backtest task: {backtest_id}")

    try:
        result = _run_async(_execute_backtest(backtest_id, tenant_id))
        logger.info(f"Backtest completed: {backtest_id}")
        return result
    except MarketDataError as e:
        # Celery task protocol attributes exist at runtime; stubs are incomplete
        request = getattr(self, "request", None)
        max_retries = getattr(self, "max_retries", 0) or 0
        retries_so_far = getattr(request, "retries", 0) if request is not None else 0

        if retries_so_far < max_retries:
            logger.warning(
                f"Backtest {backtest_id} hit a market data error "
                f"(attempt {retries_so_far + 1}/{max_retries + 1}), retrying: {e}"
            )
            _run_async(_reset_to_pending(backtest_id, tenant_id))
            retry = getattr(self, "retry")
            raise retry(exc=e) from e

        logger.error(f"Backtest failed after retries: {backtest_id} - {e}")
        raise
    except Exception as e:
        logger.error(f"Backtest failed: {backtest_id} - {e}")
        raise


@shared_task
def reap_stale_backtests_task() -> dict[str, int]:
    """Periodic reaper for orphaned RUNNING/PENDING backtests (1A).

    Scheduled via Celery beat and routed to the maintenance queue so it is not
    starved behind long-running backtests on the main queue. Returns recovery
    counts for observability.
    """
    counts = _run_async(_reap_stale_backtests())
    logger.info(f"Reaper pass complete: {counts}")
    return counts
