"""Backtest gRPC servicer implementation."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from connectrpc.request import RequestContext
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_common import pagination_response, resolve_pagination
from llamatrade_common.connect import handle_service_errors, resolve_identity_connect
from llamatrade_db import get_session_maker, tenant_session
from llamatrade_db.models.backtest import Backtest
from llamatrade_db.plan_limits import PlanLimitExceededError, enforce_plan_limit
from llamatrade_events.catalog.notifications import (
    NotificationEvent,
    shared_notification_events,
)
from llamatrade_proto.generated import backtest_pb2, events_pb2
from llamatrade_proto.timestamps import date_from_proto_timestamp, to_proto_timestamp
from llamatrade_telemetry import metrics

from src import proto_mappers
from src.services.backtest_service import MAX_TRADES_PAGE_SIZE, BacktestService

logger = logging.getLogger(__name__)

# Connect handlers get a RequestContext (no .abort()); errors raise ConnectError.
type AnyContext = RequestContext[object, object]

# GetBacktest returns at most this many trades inline; the full log is paged via
# GetBacktestTrades so a pathological trade count never bloats one response.
_GET_BACKTEST_TRADES_PREVIEW = int(os.getenv("BACKTEST_TRADES_PREVIEW", "500"))


def _reject_unsupported_config(config: backtest_pb2.BacktestConfig) -> None:
    """Reject config fields the engine cannot honor — fail loud, never mislead.

    Daily bars are split-adjusted, so ``use_adjusted_prices`` is honored;
    ``allow_shorting``, ``max_position_size``, and strategy ``parameters``
    remain unsupported.
    """
    unsupported: list[str] = []
    if config.allow_shorting:
        unsupported.append("allow_shorting (engine is long-only)")
    if config.HasField("max_position_size"):
        raw = config.max_position_size.value
        try:
            capped = Decimal(raw) if raw else Decimal(0)
        except ArithmeticError, ValueError:
            capped = Decimal(0)
        if capped > 0:
            unsupported.append("max_position_size (per-position cap not yet enforced)")
    if len(config.parameters) > 0:
        unsupported.append("parameters (strategy parameter override not supported)")
    if unsupported:
        raise ValueError("Unsupported backtest config field(s) set: " + "; ".join(unsupported))


async def _enforce_backtest_quota(db: AsyncSession, tenant_id: UUID) -> None:
    """Reject when the tenant has used its plan's monthly backtest quota."""
    now = datetime.now(UTC)
    month_start = datetime(now.year, now.month, 1, tzinfo=UTC)
    used = (
        await db.scalar(
            select(func.count())
            .select_from(Backtest)
            .where(Backtest.tenant_id == tenant_id, Backtest.created_at >= month_start)
        )
        or 0
    )
    try:
        await enforce_plan_limit(db, tenant_id, "backtests_per_month", used)
    except PlanLimitExceededError as e:
        metrics.billing.plan_limit_exceeded(limit="backtests_monthly")
        await shared_notification_events().publish_safe(
            NotificationEvent(
                category=events_pb2.NOTIFICATION_CATEGORY_PLAN_LIMIT_REACHED,
                reason=f"{e.limit} backtests this month",
            ),
            tenant_id=str(tenant_id),
            dedup_parts=("backtests_monthly", str(e.limit)),
        )
        raise ConnectError(
            Code.RESOURCE_EXHAUSTED,
            f"Plan limit reached: {e.limit} backtests this month; upgrade to run more.",
        ) from e


class BacktestServicer:
    """gRPC servicer for the Backtest service.

    Implements the BacktestService defined in backtest.proto.
    """

    def __init__(self) -> None:
        """Initialize the servicer."""
        self._session_maker: async_sessionmaker[AsyncSession] | None = None

    def _maker(self) -> async_sessionmaker[AsyncSession]:
        """The session factory (lazily created; tests inject a test-DB factory).

        Request handlers wrap this in ``tenant_session(tenant_id, self._maker())``
        so every query is RLS-scoped to the caller's verified tenant. BacktestService
        commits its own writes, so the session context need not auto-commit.
        """
        if self._session_maker is None:
            self._session_maker = get_session_maker()
        return self._session_maker

    @handle_service_errors
    async def run_backtest(
        self,
        request: backtest_pb2.RunBacktestRequest,
        context: AnyContext,
    ) -> backtest_pb2.RunBacktestResponse:
        """Start a new backtest run."""
        tenant_id, user_id = resolve_identity_connect(request.context)

        config = request.config

        # Fail fast on config the engine can't honor, before touching the DB.
        _reject_unsupported_config(config)

        # Create the backtest
        async with tenant_session(tenant_id, self._maker()) as db:
            await _enforce_backtest_quota(db, tenant_id)
            async with BacktestService(db) as service:
                backtest = await service.create_backtest(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    strategy_id=UUID(config.strategy_id),
                    strategy_version=config.strategy_version if config.strategy_version else None,
                    name=f"Backtest {config.strategy_id[:8]}",
                    start_date=date_from_proto_timestamp(config.start_date),
                    end_date=date_from_proto_timestamp(config.end_date),
                    initial_capital=float(Decimal(config.initial_capital.value)),
                    symbols=list(config.symbols) if config.symbols else None,
                    commission=float(Decimal(config.commission.value))
                    if config.HasField("commission")
                    else 0.0,
                    slippage=float(Decimal(config.slippage_percent.value))
                    if config.HasField("slippage_percent")
                    else 0.0,
                    # Timeframe and benchmark configuration
                    timeframe=config.timeframe if config.timeframe else None,
                    benchmark_symbol=config.benchmark_symbol if config.benchmark_symbol else "SPY",
                    include_benchmark=config.include_benchmark,
                    # Sizing overrides (unset -> engine defaults at run time).
                    sizing_mode=config.sizing_mode,
                    drift_tolerance=float(Decimal(config.drift_tolerance.value))
                    if config.HasField("drift_tolerance")
                    else None,
                    min_order_notional=float(Decimal(config.min_order_notional.value))
                    if config.HasField("min_order_notional")
                    else None,
                )

                # Queue execution — the Celery worker is the only
                # execution path; nothing runs in the API process.
                try:
                    await service.queue_backtest(
                        backtest_id=backtest.id,
                        tenant_id=tenant_id,
                    )
                except Exception as enqueue_error:
                    # Compensating action: the PENDING row was already
                    # committed, so a failed enqueue would strand it. Mark it
                    # FAILED so the DB matches the error the caller gets.
                    logger.error(
                        "Failed to enqueue backtest %s; marking FAILED: %s",
                        backtest.id,
                        enqueue_error,
                        exc_info=True,
                    )
                    await service.fail_backtest(
                        backtest.id,
                        tenant_id,
                        f"Failed to enqueue backtest: {enqueue_error}",
                    )
                    raise

                return backtest_pb2.RunBacktestResponse(
                    backtest=proto_mappers.backtest_run_to_proto(backtest),
                )

    @handle_service_errors
    async def get_backtest(
        self,
        request: backtest_pb2.GetBacktestRequest,
        context: AnyContext,
    ) -> backtest_pb2.GetBacktestResponse:
        """Get a backtest by ID."""
        from llamatrade_proto.generated import backtest_pb2

        tenant_id, _ = resolve_identity_connect(request.context)
        backtest_id = UUID(request.backtest_id)

        async with tenant_session(tenant_id, self._maker()) as db:
            async with BacktestService(db) as service:
                backtest = await service.get_backtest(
                    backtest_id=backtest_id,
                    tenant_id=tenant_id,
                )

                if not backtest:
                    raise ConnectError(Code.NOT_FOUND, f"Backtest not found: {request.backtest_id}")

                proto_backtest = proto_mappers.backtest_run_to_proto(backtest)

                # Attach full results on single-get only — list responses
                # must stay slim
                if backtest.status == backtest_pb2.BACKTEST_STATUS_COMPLETED:
                    rows = await service.get_result_rows(
                        backtest_id=backtest_id,
                        tenant_id=tenant_id,
                    )
                    if rows:
                        proto_backtest.results.CopyFrom(
                            proto_mappers.backtest_results_to_proto(
                                rows[0], rows[1], trades_preview=_GET_BACKTEST_TRADES_PREVIEW
                            )
                        )

                return backtest_pb2.GetBacktestResponse(backtest=proto_backtest)

    @handle_service_errors
    async def list_backtests(
        self,
        request: backtest_pb2.ListBacktestsRequest,
        context: AnyContext,
    ) -> backtest_pb2.ListBacktestsResponse:
        """List backtests for a tenant."""
        from llamatrade_proto.generated import backtest_pb2, common_pb2

        tenant_id, _ = resolve_identity_connect(request.context)
        strategy_id = UUID(request.strategy_id) if request.strategy_id else None

        # Status filter - proto constants are used directly throughout
        status = None
        if request.statuses:
            # Use first status filter if provided (proto int used directly)
            status = request.statuses[0]

        page, page_size = resolve_pagination(
            request.pagination if request.HasField("pagination") else None
        )

        async with tenant_session(tenant_id, self._maker()) as db:
            async with BacktestService(db) as service:
                backtests, total = await service.list_backtests(
                    tenant_id=tenant_id,
                    strategy_id=strategy_id,
                    status=status,
                    page=page,
                    page_size=page_size,
                )

                proto_backtests = [proto_mappers.backtest_run_to_proto(b) for b in backtests]

                return backtest_pb2.ListBacktestsResponse(
                    backtests=proto_backtests,
                    pagination=common_pb2.PaginationResponse(
                        **pagination_response(total, page, page_size)
                    ),
                )

    @handle_service_errors
    async def cancel_backtest(
        self,
        request: backtest_pb2.CancelBacktestRequest,
        context: AnyContext,
    ) -> backtest_pb2.CancelBacktestResponse:
        """Cancel a running backtest."""
        from llamatrade_proto.generated import backtest_pb2

        tenant_id, _ = resolve_identity_connect(request.context)
        backtest_id = UUID(request.backtest_id)

        async with tenant_session(tenant_id, self._maker()) as db:
            async with BacktestService(db) as service:
                # AUTHORIZATION: the cancel flag is keyed by backtest_id
                # only. cancel_backtest is tenant-scoped and returns False for
                # a backtest the caller's tenant does not own, so a cross-tenant
                # cancel cannot set the flag.
                success = await service.cancel_backtest(
                    backtest_id=backtest_id,
                    tenant_id=tenant_id,
                )

                if not success:
                    raise ConnectError(Code.FAILED_PRECONDITION, "Cannot cancel backtest")

                backtest = await service.get_backtest(
                    backtest_id=backtest_id,
                    tenant_id=tenant_id,
                )

                if not backtest:
                    raise ConnectError(Code.NOT_FOUND, f"Backtest not found: {backtest_id}")

                return backtest_pb2.CancelBacktestResponse(
                    backtest=proto_mappers.backtest_run_to_proto(backtest),
                )

    async def stream_backtest_progress(
        self,
        request: backtest_pb2.StreamBacktestProgressRequest,
        context: AnyContext,
    ) -> AsyncIterator[backtest_pb2.BacktestProgressUpdate]:
        """Stream backtest progress updates via Redis pub/sub."""
        from llamatrade_proto.generated import backtest_pb2
        from llamatrade_proto.generated.backtest_pb2 import (
            BACKTEST_STATUS_CANCELLED,
            BACKTEST_STATUS_COMPLETED,
            BACKTEST_STATUS_FAILED,
        )

        from src.progress import ProgressSubscriber

        tenant_id, _ = resolve_identity_connect(request.context)
        backtest_id = request.backtest_id
        logger.info("Starting progress stream for backtest: %s", backtest_id)

        # Terminal statuses where backtest is complete
        terminal_statuses = {
            BACKTEST_STATUS_COMPLETED,
            BACKTEST_STATUS_FAILED,
            BACKTEST_STATUS_CANCELLED,
        }

        subscriber = ProgressSubscriber()

        try:
            # AUTHORIZATION: the progress stream below is keyed by
            # backtest_id only and carries no tenant scope of its own. This
            # tenant-scoped ownership lookup is the gate — a caller from another
            # tenant gets NOT_FOUND and never reaches subscriber.tail().
            async with tenant_session(tenant_id, self._maker()) as db:
                async with BacktestService(db) as service:
                    backtest = await service.get_backtest(
                        backtest_id=UUID(backtest_id),
                        tenant_id=tenant_id,
                    )

                    if not backtest:
                        raise ConnectError(Code.NOT_FOUND, f"Backtest not found: {backtest_id}")

                    # Send initial status (backtest.status is already proto ValueType).
                    # Progress is derivable from status (terminal=100 if completed),
                    # so a late joiner to a finished run sees the right percentage.
                    initial_pct = (
                        100 if backtest.status == backtest_pb2.BACKTEST_STATUS_COMPLETED else 0
                    )
                    yield backtest_pb2.BacktestProgressUpdate(
                        backtest_id=backtest_id,
                        status=backtest.status,
                        progress_percent=initial_pct,
                        message=backtest.error_message or "Connected to progress stream",
                        timestamp=to_proto_timestamp(datetime.now(UTC)),
                    )

                    # If already completed, stop streaming
                    if backtest.status in terminal_statuses:
                        return

            # Tail the bounded stream from the start so a client connecting
            # mid-run replays prior updates and catches up immediately. The
            # subscriber yields the BacktestProgressUpdate proto directly, with
            # an EXPLICIT status set by the publisher — inferring status from the
            # progress number is wrong: failed runs also publish progress=100 and
            # would be reported as COMPLETED.
            async for update in subscriber.tail(backtest_id):
                if update.status == backtest_pb2.BACKTEST_STATUS_UNSPECIFIED:
                    update.status = backtest_pb2.BACKTEST_STATUS_RUNNING

                yield update

                if update.status in terminal_statuses:
                    break

        except asyncio.CancelledError:
            logger.info("Progress stream cancelled for backtest: %s", backtest_id)
        finally:
            await subscriber.close()

    @handle_service_errors
    async def compare_backtests(
        self,
        request: backtest_pb2.CompareBacktestsRequest,
        context: AnyContext,
    ) -> backtest_pb2.CompareBacktestsResponse:
        """Compare multiple backtests."""
        from llamatrade_proto.generated import backtest_pb2

        tenant_id, _ = resolve_identity_connect(request.context)
        backtest_ids = [UUID(bid) for bid in request.backtest_ids]

        async with tenant_session(tenant_id, self._maker()) as db:
            async with BacktestService(db) as service:
                backtests: list[Backtest] = []
                metrics_by_id: dict[str, backtest_pb2.BacktestMetrics] = {}
                for bid in backtest_ids:
                    backtest = await service.get_backtest(
                        backtest_id=bid,
                        tenant_id=tenant_id,
                    )
                    if not backtest:
                        continue
                    backtests.append(backtest)

                    if backtest.status == backtest_pb2.BACKTEST_STATUS_COMPLETED:
                        rows = await service.get_result_rows(
                            backtest_id=bid,
                            tenant_id=tenant_id,
                        )
                        if rows:
                            metrics_by_id[str(bid)] = proto_mappers.backtest_results_to_proto(
                                rows[0], rows[1], trades_preview=0
                            ).metrics

                proto_backtests = [proto_mappers.backtest_run_to_proto(b) for b in backtests]

                return backtest_pb2.CompareBacktestsResponse(
                    backtests=proto_backtests,
                    metrics_by_id=metrics_by_id,
                )

    @handle_service_errors
    async def get_backtest_trades(
        self,
        request: backtest_pb2.GetBacktestTradesRequest,
        context: AnyContext,
    ) -> backtest_pb2.GetBacktestTradesResponse:
        """Return a page of a completed backtest's trades."""
        from llamatrade_proto.generated import backtest_pb2, common_pb2

        tenant_id, _ = resolve_identity_connect(request.context)
        backtest_id = UUID(request.backtest_id)
        page, page_size = resolve_pagination(
            request.pagination if request.HasField("pagination") else None,
            default_page_size=50,
            max_page_size=MAX_TRADES_PAGE_SIZE,
        )

        async with tenant_session(tenant_id, self._maker()) as db:
            async with BacktestService(db) as service:
                # Tenant-scoped: get_backtest_trades resolves the backtest by
                # (id, tenant), so a foreign tenant gets an empty page.
                trades, total = await service.get_backtest_trades(
                    backtest_id=backtest_id,
                    tenant_id=tenant_id,
                    page=page,
                    page_size=page_size,
                )

        return backtest_pb2.GetBacktestTradesResponse(
            trades=[proto_mappers.backtest_trade_to_proto(t) for t in trades],
            pagination=common_pb2.PaginationResponse(**pagination_response(total, page, page_size)),
        )
