"""Backtest gRPC servicer implementation."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import grpc.aio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_db import get_session_maker
from llamatrade_proto.generated import backtest_pb2

from src.models import BacktestMetrics, BacktestResponse, BacktestResultResponse, TradeRecord
from src.services.backtest_service import BacktestService

logger = logging.getLogger(__name__)

# GetBacktest returns at most this many trades inline; the full log is paged via
# GetBacktestTrades so a pathological trade count never bloats one response (14B).
_GET_BACKTEST_TRADES_PREVIEW = int(os.getenv("BACKTEST_TRADES_PREVIEW", "500"))


def _reject_unsupported_config(config: backtest_pb2.BacktestConfig) -> None:
    """Reject config fields the engine cannot honor (5A).

    These proto fields were previously accepted and silently ignored, which
    silently produces misleading results (e.g. unadjusted prices across a split,
    or an unenforced position cap). Until they are honored — enforcing
    ``max_position_size`` and applying split/dividend adjustment for
    ``use_adjusted_prices`` are tracked as fast-follow work — we fail loudly so
    a caller is never misled.
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
    if config.use_adjusted_prices:
        unsupported.append("use_adjusted_prices (split/dividend adjustment not yet applied)")
    if len(config.parameters) > 0:
        unsupported.append("parameters (strategy parameter override not supported)")
    if unsupported:
        raise ValueError("Unsupported backtest config field(s) set: " + "; ".join(unsupported))


class BacktestServicer:
    """gRPC servicer for the Backtest service.

    Implements the BacktestService defined in backtest.proto.
    """

    def __init__(self) -> None:
        """Initialize the servicer."""
        self._session_maker: async_sessionmaker[AsyncSession] | None = None

    @asynccontextmanager
    async def _get_db(self) -> AsyncGenerator[AsyncSession]:
        """Get a database session with proper lifecycle management.

        Usage:
            async with self._get_db() as db:
                service = BacktestService(db)
                # ... use service ...
            # Session is automatically closed here

        Yields:
            AsyncSession: Database session that will be properly cleaned up.
        """
        if self._session_maker is None:
            self._session_maker = get_session_maker()
        assert self._session_maker is not None
        session: AsyncSession = self._session_maker()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def RunBacktest(
        self,
        request: backtest_pb2.RunBacktestRequest,
        context: grpc.aio.ServicerContext[object, object],
    ) -> backtest_pb2.RunBacktestResponse:
        """Start a new backtest run."""
        try:
            tenant_id = UUID(request.context.tenant_id)
            user_id = UUID(request.context.user_id)

            config = request.config

            # Fail fast on config the engine can't honor, before touching the DB.
            _reject_unsupported_config(config)

            # Create the backtest
            async with self._get_db() as db:
                async with BacktestService(db) as service:
                    backtest = await service.create_backtest(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        strategy_id=UUID(config.strategy_id),
                        strategy_version=config.strategy_version
                        if config.strategy_version
                        else None,
                        name=f"Backtest {config.strategy_id[:8]}",
                        start_date=date.fromtimestamp(config.start_date.seconds),
                        end_date=date.fromtimestamp(config.end_date.seconds),
                        initial_capital=float(Decimal(config.initial_capital.value)),
                        symbols=list(config.symbols) if config.symbols else None,
                        commission=float(Decimal(config.commission.value))
                        if config.HasField("commission")
                        else 0.0,
                        slippage=float(Decimal(config.slippage_percent.value))
                        if config.HasField("slippage_percent")
                        else 0.0,
                        # Phase 1 & 2: Timeframe and benchmark configuration
                        timeframe=config.timeframe if config.timeframe else None,
                        benchmark_symbol=config.benchmark_symbol
                        if config.benchmark_symbol
                        else "SPY",
                        include_benchmark=config.include_benchmark,
                    )

                    # Queue execution — the Celery worker is the only
                    # execution path; nothing runs in the API process.
                    try:
                        await service.queue_backtest(
                            backtest_id=backtest.id,
                            tenant_id=tenant_id,
                        )
                    except Exception as enqueue_error:
                        # Compensating action (2A): the PENDING row was already
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
                        backtest=self._to_proto_backtest(backtest),
                    )

        except ValueError as e:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                str(e),
            )
        except Exception as e:
            logger.error("RunBacktest error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to run backtest: {e}",
            )

    async def GetBacktest(
        self,
        request: backtest_pb2.GetBacktestRequest,
        context: grpc.aio.ServicerContext[object, object],
    ) -> backtest_pb2.GetBacktestResponse:
        """Get a backtest by ID."""
        from llamatrade_proto.generated import backtest_pb2

        try:
            tenant_id = UUID(request.context.tenant_id)
            backtest_id = UUID(request.backtest_id)

            async with self._get_db() as db:
                async with BacktestService(db) as service:
                    backtest = await service.get_backtest(
                        backtest_id=backtest_id,
                        tenant_id=tenant_id,
                    )

                    if not backtest:
                        await context.abort(
                            grpc.StatusCode.NOT_FOUND,
                            f"Backtest not found: {request.backtest_id}",
                        )
                        return backtest_pb2.GetBacktestResponse()  # Never reached

                    proto_backtest = self._to_proto_backtest(backtest)

                    # Attach full results on single-get only — list responses
                    # must stay slim
                    if backtest.status == backtest_pb2.BACKTEST_STATUS_COMPLETED:
                        results = await service.get_results(
                            backtest_id=backtest_id,
                            tenant_id=tenant_id,
                        )
                        if results:
                            proto_backtest.results.CopyFrom(self._to_proto_results(results))

                    return backtest_pb2.GetBacktestResponse(backtest=proto_backtest)

        except grpc.aio.AioRpcError:
            raise
        except Exception as e:
            logger.error("GetBacktest error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to get backtest: {e}",
            )

    async def ListBacktests(
        self,
        request: backtest_pb2.ListBacktestsRequest,
        context: grpc.aio.ServicerContext[object, object],
    ) -> backtest_pb2.ListBacktestsResponse:
        """List backtests for a tenant."""
        from llamatrade_proto.generated import backtest_pb2, common_pb2

        try:
            tenant_id = UUID(request.context.tenant_id)
            strategy_id = UUID(request.strategy_id) if request.strategy_id else None

            # Status filter - proto constants are used directly throughout
            status = None
            if request.statuses:
                # Use first status filter if provided (proto int used directly)
                status = request.statuses[0]

            page = request.pagination.page if request.HasField("pagination") else 1
            page_size = request.pagination.page_size if request.HasField("pagination") else 20

            async with self._get_db() as db:
                async with BacktestService(db) as service:
                    backtests, total = await service.list_backtests(
                        tenant_id=tenant_id,
                        strategy_id=strategy_id,
                        status=status,
                        page=page,
                        page_size=page_size,
                    )

                    proto_backtests = [self._to_proto_backtest(b) for b in backtests]
                    total_pages = (total + page_size - 1) // page_size

                    return backtest_pb2.ListBacktestsResponse(
                        backtests=proto_backtests,
                        pagination=common_pb2.PaginationResponse(
                            total_items=total,
                            total_pages=total_pages,
                            current_page=page,
                            page_size=page_size,
                            has_next=page < total_pages,
                            has_previous=page > 1,
                        ),
                    )

        except Exception as e:
            logger.error("ListBacktests error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to list backtests: {e}",
            )

    async def CancelBacktest(
        self,
        request: backtest_pb2.CancelBacktestRequest,
        context: grpc.aio.ServicerContext[object, object],
    ) -> backtest_pb2.CancelBacktestResponse:
        """Cancel a running backtest."""
        from llamatrade_proto.generated import backtest_pb2

        try:
            tenant_id = UUID(request.context.tenant_id)
            backtest_id = UUID(request.backtest_id)

            async with self._get_db() as db:
                async with BacktestService(db) as service:
                    # AUTHORIZATION (4A): the cancel flag is keyed by backtest_id
                    # only. cancel_backtest is tenant-scoped and returns False for
                    # a backtest the caller's tenant does not own, so a cross-tenant
                    # cancel cannot set the flag.
                    success = await service.cancel_backtest(
                        backtest_id=backtest_id,
                        tenant_id=tenant_id,
                    )

                    if not success:
                        await context.abort(
                            grpc.StatusCode.FAILED_PRECONDITION,
                            "Cannot cancel backtest",
                        )
                        return backtest_pb2.CancelBacktestResponse()  # Never reached

                    backtest = await service.get_backtest(
                        backtest_id=backtest_id,
                        tenant_id=tenant_id,
                    )

                    if not backtest:
                        await context.abort(
                            grpc.StatusCode.NOT_FOUND,
                            f"Backtest not found: {backtest_id}",
                        )
                        return backtest_pb2.CancelBacktestResponse()  # Never reached

                    return backtest_pb2.CancelBacktestResponse(
                        backtest=self._to_proto_backtest(backtest),
                    )

        except grpc.aio.AioRpcError:
            raise
        except Exception as e:
            logger.error("CancelBacktest error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to cancel backtest: {e}",
            )

    async def StreamBacktestProgress(
        self,
        request: backtest_pb2.StreamBacktestProgressRequest,
        context: grpc.aio.ServicerContext[object, object],
    ) -> AsyncIterator[backtest_pb2.BacktestProgressUpdate]:
        """Stream backtest progress updates via Redis pub/sub."""
        from llamatrade_proto.generated import backtest_pb2, common_pb2
        from llamatrade_proto.generated.backtest_pb2 import (
            BACKTEST_STATUS_CANCELLED,
            BACKTEST_STATUS_COMPLETED,
            BACKTEST_STATUS_FAILED,
        )

        from src.progress import ProgressSubscriber

        tenant_id = request.context.tenant_id
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
            # AUTHORIZATION (4A): the progress stream below is keyed by
            # backtest_id only and carries no tenant scope of its own. This
            # tenant-scoped ownership lookup is the gate — a caller from another
            # tenant gets NOT_FOUND and never reaches subscriber.tail().
            async with self._get_db() as db:
                async with BacktestService(db) as service:
                    backtest = await service.get_backtest(
                        backtest_id=UUID(backtest_id),
                        tenant_id=UUID(tenant_id),
                    )

                    if not backtest:
                        await context.abort(
                            grpc.StatusCode.NOT_FOUND,
                            f"Backtest not found: {backtest_id}",
                        )
                        return

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
                        timestamp=common_pb2.Timestamp(seconds=int(datetime.now(UTC).timestamp())),
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
                if context.cancelled():
                    break

                if update.status == backtest_pb2.BACKTEST_STATUS_UNSPECIFIED:
                    update.status = backtest_pb2.BACKTEST_STATUS_RUNNING

                yield update

                if update.status in terminal_statuses:
                    break

        except asyncio.CancelledError:
            logger.info("Progress stream cancelled for backtest: %s", backtest_id)
        finally:
            await subscriber.close()

    async def CompareBacktests(
        self,
        request: backtest_pb2.CompareBacktestsRequest,
        context: grpc.aio.ServicerContext[object, object],
    ) -> backtest_pb2.CompareBacktestsResponse:
        """Compare multiple backtests."""
        from llamatrade_proto.generated import backtest_pb2

        try:
            tenant_id = UUID(request.context.tenant_id)
            backtest_ids = [UUID(bid) for bid in request.backtest_ids]

            async with self._get_db() as db:
                async with BacktestService(db) as service:
                    backtests: list[BacktestResponse] = []
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
                            results = await service.get_results(
                                backtest_id=bid,
                                tenant_id=tenant_id,
                            )
                            if results:
                                metrics_by_id[str(bid)] = self._to_proto_metrics(results.metrics)

                    proto_backtests = [self._to_proto_backtest(b) for b in backtests]

                    return backtest_pb2.CompareBacktestsResponse(
                        backtests=proto_backtests,
                        metrics_by_id=metrics_by_id,
                    )

        except Exception as e:
            logger.error("CompareBacktests error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to compare backtests: {e}",
            )

    async def GetBacktestTrades(
        self,
        request: backtest_pb2.GetBacktestTradesRequest,
        context: grpc.aio.ServicerContext[object, object],
    ) -> backtest_pb2.GetBacktestTradesResponse:
        """Return a page of a completed backtest's trades (14B)."""
        from llamatrade_proto.generated import backtest_pb2, common_pb2

        try:
            tenant_id = UUID(request.context.tenant_id)
            backtest_id = UUID(request.backtest_id)
            page = request.pagination.page if request.HasField("pagination") else 1
            page_size = request.pagination.page_size if request.HasField("pagination") else 50

            async with self._get_db() as db:
                async with BacktestService(db) as service:
                    # Tenant-scoped: get_backtest_trades resolves the backtest by
                    # (id, tenant), so a foreign tenant gets an empty page.
                    trades, total = await service.get_backtest_trades(
                        backtest_id=backtest_id,
                        tenant_id=tenant_id,
                        page=page,
                        page_size=page_size,
                    )

            effective_page = max(1, page)
            effective_size = max(1, page_size)
            total_pages = (total + effective_size - 1) // effective_size if total else 0
            return backtest_pb2.GetBacktestTradesResponse(
                trades=[self._to_proto_trade(t) for t in trades],
                pagination=common_pb2.PaginationResponse(
                    total_items=total,
                    total_pages=total_pages,
                    current_page=effective_page,
                    page_size=effective_size,
                    has_next=effective_page < total_pages,
                    has_previous=effective_page > 1,
                ),
            )

        except ValueError as e:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
        except Exception as e:
            logger.error("GetBacktestTrades error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to fetch trades: {e}",
            )

    def _to_proto_metrics(self, m: BacktestMetrics) -> backtest_pb2.BacktestMetrics:
        """Convert internal metrics to proto BacktestMetrics."""
        from llamatrade_proto.generated import backtest_pb2, common_pb2

        def dec(value: float) -> common_pb2.Decimal:
            return common_pb2.Decimal(value=str(value))

        metrics = backtest_pb2.BacktestMetrics(
            total_return=dec(m.total_return),
            annualized_return=dec(m.annual_return),
            sharpe_ratio=dec(m.sharpe_ratio),
            sortino_ratio=dec(m.sortino_ratio),
            max_drawdown=dec(m.max_drawdown),
            max_drawdown_duration_days=dec(m.max_drawdown_duration),
            total_trades=m.total_trades,
            winning_trades=m.winning_trades,
            losing_trades=m.losing_trades,
            win_rate=dec(m.win_rate),
            average_win=dec(m.avg_win),
            average_loss=dec(m.avg_loss),
            average_holding_period_days=dec(m.avg_holding_period),
        )

        # Profit factor is None when undefined (no trades or no losses):
        # leave the proto field unset rather than writing a fake 0
        if m.profit_factor is not None:
            metrics.profit_factor.CopyFrom(dec(m.profit_factor))

        # Benchmark metrics only when the comparison was actually computed
        if m.benchmark_data_available:
            metrics.benchmark_return.CopyFrom(dec(m.benchmark_return))
            metrics.alpha.CopyFrom(dec(m.alpha))
            metrics.beta.CopyFrom(dec(m.beta))
            metrics.information_ratio.CopyFrom(dec(m.information_ratio))
            metrics.excess_return.CopyFrom(dec(m.excess_return))
            metrics.benchmark_symbol = m.benchmark_symbol

        return metrics

    @staticmethod
    def _to_proto_trade(trade: TradeRecord) -> backtest_pb2.BacktestTrade:
        """Convert one internal trade record to a proto BacktestTrade."""
        from llamatrade_proto.generated import backtest_pb2, common_pb2
        from llamatrade_proto.generated.trading_pb2 import ORDER_SIDE_BUY

        def dec(value: float) -> common_pb2.Decimal:
            return common_pb2.Decimal(value=str(value))

        def ts(value: datetime) -> common_pb2.Timestamp:
            return common_pb2.Timestamp(seconds=int(value.timestamp()))

        return backtest_pb2.BacktestTrade(
            symbol=trade.symbol,
            side=ORDER_SIDE_BUY,  # engine is long-only
            quantity=dec(trade.quantity),
            entry_price=dec(trade.entry_price),
            exit_price=dec(trade.exit_price)
            if trade.exit_price is not None
            else common_pb2.Decimal(value="0"),
            entry_time=ts(trade.entry_date),
            exit_time=ts(trade.exit_date) if trade.exit_date else None,
            pnl=dec(trade.pnl),
            pnl_percent=dec(trade.pnl_percent),
            commission=dec(trade.commission),
        )

    def _to_proto_results(
        self,
        results: BacktestResultResponse,
    ) -> backtest_pb2.BacktestResults:
        """Convert internal result response to proto BacktestResults.

        Trades are capped at a preview size; the full log is paged via
        GetBacktestTrades (14B).
        """
        from llamatrade_proto.generated import backtest_pb2, common_pb2

        def dec(value: float) -> common_pb2.Decimal:
            return common_pb2.Decimal(value=str(value))

        def ts(value: datetime) -> common_pb2.Timestamp:
            return common_pb2.Timestamp(seconds=int(value.timestamp()))

        proto = backtest_pb2.BacktestResults(
            metrics=self._to_proto_metrics(results.metrics),
            equity_curve=[
                backtest_pb2.EquityPoint(
                    timestamp=ts(point.date),
                    equity=dec(point.equity),
                    drawdown=dec(point.drawdown_percent),
                )
                for point in results.equity_curve
            ],
            trades=[
                self._to_proto_trade(trade)
                for trade in results.trades[:_GET_BACKTEST_TRADES_PREVIEW]
            ],
            benchmark_equity_curve=[
                backtest_pb2.EquityPoint(
                    timestamp=ts(point.date),
                    equity=dec(point.equity),
                )
                for point in results.benchmark_equity_curve
            ],
            benchmark_symbol=results.metrics.benchmark_symbol
            if results.metrics.benchmark_data_available
            else "",
        )
        proto.monthly_returns.update(results.monthly_returns)
        return proto

    def _to_proto_backtest(
        self,
        backtest: BacktestResponse,
    ) -> backtest_pb2.BacktestRun:
        """Convert internal backtest to proto BacktestRun."""
        from llamatrade_proto.generated import backtest_pb2, common_pb2

        # backtest.status is already proto ValueType
        proto = backtest_pb2.BacktestRun(
            id=str(backtest.id),
            tenant_id=str(backtest.tenant_id),
            strategy_id=str(backtest.strategy_id),
            strategy_version=backtest.strategy_version,
            status=backtest.status,
            status_message=backtest.error_message or "",
            progress_percent=100
            if backtest.status == backtest_pb2.BACKTEST_STATUS_COMPLETED
            else 0,
            created_at=common_pb2.Timestamp(seconds=int(backtest.created_at.timestamp())),
        )

        # Set config
        proto.config.CopyFrom(
            backtest_pb2.BacktestConfig(
                strategy_id=str(backtest.strategy_id),
                strategy_version=backtest.strategy_version,
                start_date=common_pb2.Timestamp(seconds=int(backtest.start_date.timestamp())),
                end_date=common_pb2.Timestamp(seconds=int(backtest.end_date.timestamp())),
                initial_capital=common_pb2.Decimal(value=str(backtest.initial_capital)),
            )
        )

        if backtest.started_at:
            proto.started_at.CopyFrom(
                common_pb2.Timestamp(seconds=int(backtest.started_at.timestamp()))
            )
        if backtest.completed_at:
            proto.completed_at.CopyFrom(
                common_pb2.Timestamp(seconds=int(backtest.completed_at.timestamp()))
            )

        return proto

    # Connect protocol expects snake_case method names
    # These aliases provide compatibility with both gRPC and Connect
    run_backtest = RunBacktest
    get_backtest = GetBacktest
    list_backtests = ListBacktests
    cancel_backtest = CancelBacktest
    stream_backtest_progress = StreamBacktestProgress
    compare_backtests = CompareBacktests
