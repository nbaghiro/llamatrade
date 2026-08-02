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
from typing import cast
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llamatrade_db import bind_tenant_guc, set_rls_bypass
from llamatrade_db.models.backtest import Backtest
from llamatrade_proto.generated.backtest_pb2 import (
    BACKTEST_STATUS_FAILED,
    BACKTEST_STATUS_PENDING,
)

from src.celery_app import celery_app
from src.dataset import RedisLike
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

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _create_market_data_client() -> MarketDataFetcher:
    """Market data client factory (patchable in tests)."""
    return get_market_data_client()


def _create_redis() -> aioredis.Redis:
    """Redis client for dataset-prepare coalescing (patchable in tests)."""
    return aioredis.from_url(REDIS_URL)


@asynccontextmanager
async def _session_scope(
    *, tenant_id: UUID | None = None, system_reason: str | None = None
) -> AsyncGenerator[AsyncSession]:
    """Provide a database session with engine lifecycle management and a bound RLS scope.

    Each task runs in its own event loop (``asyncio.run``), so a per-call engine keeps
    the connection pool owned by that loop. Exactly one RLS scope is bound before the
    session is used: a tenant GUC re-applied on every transaction for tenant-scoped work
    (``run_backtest`` commits several times, and a one-shot GUC would clear on the first
    commit), or the transaction-local system bypass for the cross-tenant reaper. Under
    the fail-closed RLS role, a write with no bound scope is rejected by the row policies.
    """
    engine = create_async_engine(DATABASE_URL)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            if tenant_id is not None:
                bind_tenant_guc(session, tenant_id)
            elif system_reason is not None:
                # The reaper reads and writes in one transaction before its single
                # commit, so the transaction-local bypass covers the whole pass.
                await set_rls_bypass(session, reason=system_reason)
            yield session
    finally:
        await engine.dispose()


async def _execute_backtest(backtest_id: str, tenant_id: str) -> dict[str, str | float | int]:
    """Run a backtest through the service layer."""
    tenant_uuid = UUID(tenant_id)
    async with _session_scope(tenant_id=tenant_uuid) as db:
        redis_client = _create_redis()
        try:
            async with BacktestService(
                db,
                market_data_client=_create_market_data_client(),
                redis=cast(RedisLike, redis_client),
            ) as service:
                result = await service.run_backtest(UUID(backtest_id), tenant_uuid)
                return {
                    "status": "completed",
                    "backtest_id": backtest_id,
                    "total_return": float(result.total_return),
                    "total_trades": result.total_trades,
                }
        finally:
            await redis_client.aclose()


async def _reap_stale_backtests() -> dict[str, int]:
    """Run one reaper pass through the service layer.

    The reaper recovers orphaned runs across every tenant, so it takes the audited
    system bypass rather than a single-tenant GUC.
    """
    async with _session_scope(system_reason="backtest reaper: cross-tenant orphan recovery") as db:
        async with BacktestService(db, market_data_client=_create_market_data_client()) as service:
            return await service.reap_stale_backtests()


async def _reset_to_pending(backtest_id: str, tenant_id: str) -> None:
    """Reset a FAILED backtest to PENDING so a retry attempt can run.

    The service marks the row FAILED before a MarketDataError propagates;
    without this reset, run_backtest would refuse the retry with "cannot run".
    """
    async with _session_scope(tenant_id=UUID(tenant_id)) as db:
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


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60, retry_backoff=True)
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


@celery_app.task
def reap_stale_backtests_task() -> dict[str, int]:
    """Periodic reaper for orphaned RUNNING/PENDING backtests.

    Scheduled via Celery beat and routed to the maintenance queue so it is not
    starved behind long-running backtests on the main queue. Returns recovery
    counts for observability.
    """
    counts = _run_async(_reap_stale_backtests())
    logger.info(f"Reaper pass complete: {counts}")
    return counts


@celery_app.task
def evict_stale_datasets_task() -> int:
    """Periodic janitor for on-disk dataset snapshots (maintenance queue).

    A raced reader rebuilds on miss, so eviction only ever costs a refetch.
    """
    from src.dataset.store import LocalDatasetStore, get_dataset_store

    store = get_dataset_store()
    if not isinstance(store, LocalDatasetStore):
        return 0
    max_age = float(os.getenv("BACKTEST_DATASET_TTL_SECONDS", str(7 * 24 * 3600)))
    removed = store.evict_stale(max_age)
    if removed:
        logger.info(f"Dataset janitor removed {removed} stale snapshots")
    return removed
