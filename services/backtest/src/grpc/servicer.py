"""Backtest gRPC servicer implementation."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import grpc.aio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_db import get_session_maker
from llamatrade_proto.generated import backtest_pb2

from src.models import BacktestResponse
from src.services.backtest_service import BacktestService

logger = logging.getLogger(__name__)


class BacktestServicer:
    """gRPC servicer for the Backtest service.

    Implements the BacktestService defined in backtest.proto.
    """

    def __init__(self) -> None:
        """Initialize the servicer."""
        self._session_maker: async_sessionmaker[AsyncSession] | None = None

    @asynccontextmanager
    async def _get_db(self) -> AsyncIterator[AsyncSession]:
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

                    return backtest_pb2.GetBacktestResponse(
                        backtest=self._to_proto_backtest(backtest),
                    )

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

        from src.models import (
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
            # First check if the backtest exists and get initial status
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

                    # Send initial status (backtest.status is already proto int)
                    yield backtest_pb2.BacktestProgressUpdate(
                        backtest_id=backtest_id,
                        status=backtest.status,
                        progress_percent=int(backtest.progress),
                        message=backtest.error_message or "Connected to progress stream",
                        timestamp=common_pb2.Timestamp(seconds=int(datetime.now(UTC).timestamp())),
                    )

                    # If already completed, stop streaming
                    if backtest.status in terminal_statuses:
                        return

            # Subscribe to Redis pub/sub for real-time updates
            async for update in subscriber.subscribe(backtest_id):
                if context.cancelled():
                    break

                # Determine status from progress
                if update.progress >= 100:
                    status = backtest_pb2.BACKTEST_STATUS_COMPLETED
                elif update.progress > 0:
                    status = backtest_pb2.BACKTEST_STATUS_RUNNING
                else:
                    status = backtest_pb2.BACKTEST_STATUS_PENDING

                yield backtest_pb2.BacktestProgressUpdate(
                    backtest_id=backtest_id,
                    status=status,
                    progress_percent=int(update.progress),
                    message=update.message,
                    timestamp=common_pb2.Timestamp(seconds=int(datetime.now(UTC).timestamp())),
                )

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
                    for bid in backtest_ids:
                        backtest = await service.get_backtest(
                            backtest_id=bid,
                            tenant_id=tenant_id,
                        )
                        if backtest:
                            backtests.append(backtest)

                    proto_backtests = [self._to_proto_backtest(b) for b in backtests]

                    return backtest_pb2.CompareBacktestsResponse(
                        backtests=proto_backtests,
                    )

        except Exception as e:
            logger.error("CompareBacktests error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to compare backtests: {e}",
            )

    def _to_proto_backtest(
        self,
        backtest: BacktestResponse,
    ) -> backtest_pb2.BacktestRun:
        """Convert internal backtest to proto BacktestRun."""
        from llamatrade_proto.generated import backtest_pb2, common_pb2

        # backtest.status is already a proto int
        proto = backtest_pb2.BacktestRun(
            id=str(backtest.id),
            tenant_id=str(backtest.tenant_id),
            strategy_id=str(backtest.strategy_id),
            strategy_version=backtest.strategy_version,
            status=backtest.status,
            status_message=backtest.error_message or "",
            progress_percent=int(backtest.progress),
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
