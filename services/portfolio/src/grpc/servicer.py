"""Portfolio gRPC servicer implementation."""

from __future__ import annotations

import logging
from datetime import timezone
from uuid import UUID

import grpc.aio
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db import get_session_factory

logger = logging.getLogger(__name__)


class PortfolioServicer:
    """gRPC servicer for the Portfolio service.

    Implements the PortfolioService defined in portfolio.proto.
    """

    def __init__(self) -> None:
        """Initialize the servicer."""
        self._session_factory = None

    async def _get_db(self) -> AsyncSession:
        """Get a database session."""
        if self._session_factory is None:
            self._session_factory = get_session_factory()
        return self._session_factory()

    async def GetPortfolio(
        self,
        request: portfolio_pb2.GetPortfolioRequest,
        context: grpc.aio.ServicerContext,
    ) -> portfolio_pb2.GetPortfolioResponse:
        """Get portfolio summary and positions."""
        from llamatrade.v1 import portfolio_pb2

        try:
            from src.services.portfolio_service import PortfolioService

            tenant_id = UUID(request.context.tenant_id)

            async with await self._get_db() as db:
                service = PortfolioService(db)
                summary = await service.get_summary(tenant_id)
                positions = await service.list_positions(tenant_id)

                return portfolio_pb2.GetPortfolioResponse(
                    portfolio=self._to_proto_portfolio(summary, tenant_id),
                    positions=[self._to_proto_position(p) for p in positions],
                )

        except Exception as e:
            logger.error("GetPortfolio error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to get portfolio: {e}",
            )

    async def ListPortfolios(
        self,
        request: portfolio_pb2.ListPortfoliosRequest,
        context: grpc.aio.ServicerContext,
    ) -> portfolio_pb2.ListPortfoliosResponse:
        """List portfolios for a tenant."""
        from llamatrade.v1 import common_pb2, portfolio_pb2

        try:
            from src.services.portfolio_service import PortfolioService

            tenant_id = UUID(request.context.tenant_id)

            async with await self._get_db() as db:
                service = PortfolioService(db)
                summary = await service.get_summary(tenant_id)

                # Currently we support one portfolio per tenant
                portfolios = [self._to_proto_portfolio(summary, tenant_id)]

                return portfolio_pb2.ListPortfoliosResponse(
                    portfolios=portfolios,
                    pagination=common_pb2.PaginationResponse(
                        total_items=1,
                        total_pages=1,
                        current_page=1,
                        page_size=20,
                        has_next=False,
                        has_previous=False,
                    ),
                )

        except Exception as e:
            logger.error("ListPortfolios error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to list portfolios: {e}",
            )

    async def GetPerformance(
        self,
        request: portfolio_pb2.GetPerformanceRequest,
        context: grpc.aio.ServicerContext,
    ) -> portfolio_pb2.GetPerformanceResponse:
        """Get portfolio performance metrics."""
        from llamatrade.v1 import common_pb2, portfolio_pb2

        try:
            from src.services.performance_service import PerformanceService
            from src.services.portfolio_service import PortfolioService

            tenant_id = UUID(request.context.tenant_id)

            async with await self._get_db() as db:
                portfolio_service = PortfolioService(db)
                perf_service = PerformanceService(db)

                # Get portfolio summary for basic metrics
                summary = await portfolio_service.get_summary(tenant_id)

                # Convert time range if provided
                start_date = None
                end_date = None
                if request.HasField("time_range"):
                    from datetime import datetime

                    if request.time_range.start.seconds > 0:
                        start_date = datetime.fromtimestamp(
                            request.time_range.start.seconds, tz=timezone.utc
                        )
                    if request.time_range.end.seconds > 0:
                        end_date = datetime.fromtimestamp(
                            request.time_range.end.seconds, tz=timezone.utc
                        )

                # Get performance metrics
                metrics = await perf_service.get_metrics(
                    tenant_id=tenant_id,
                    start_date=start_date,
                    end_date=end_date,
                )

                # Build response
                proto_metrics = portfolio_pb2.PerformanceMetrics(
                    total_return=common_pb2.Decimal(value=str(metrics.total_return)),
                    ytd_return=common_pb2.Decimal(value=str(metrics.ytd_return)),
                    mtd_return=common_pb2.Decimal(value=str(metrics.mtd_return)),
                    wtd_return=common_pb2.Decimal(value=str(metrics.wtd_return)),
                    volatility=common_pb2.Decimal(value=str(metrics.volatility)),
                    sharpe_ratio=common_pb2.Decimal(value=str(metrics.sharpe_ratio)),
                    max_drawdown=common_pb2.Decimal(value=str(metrics.max_drawdown)),
                    beta=common_pb2.Decimal(value=str(metrics.beta)),
                    benchmark_return=common_pb2.Decimal(value=str(metrics.benchmark_return)),
                    alpha=common_pb2.Decimal(value=str(metrics.alpha)),
                    total_positions=summary.positions_count,
                )

                return portfolio_pb2.GetPerformanceResponse(metrics=proto_metrics)

        except Exception as e:
            logger.error("GetPerformance error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to get performance: {e}",
            )

    async def GetAssetAllocation(
        self,
        request: portfolio_pb2.GetAssetAllocationRequest,
        context: grpc.aio.ServicerContext,
    ) -> portfolio_pb2.GetAssetAllocationResponse:
        """Get asset allocation breakdown."""
        from llamatrade.v1 import common_pb2, portfolio_pb2

        try:
            from src.services.portfolio_service import PortfolioService

            tenant_id = UUID(request.context.tenant_id)

            async with await self._get_db() as db:
                service = PortfolioService(db)
                positions = await service.list_positions(tenant_id)

                # Calculate allocation by grouping
                # For simplicity, treat all as "Stocks" category
                total_value = sum(p.market_value for p in positions)

                allocations = []
                if total_value > 0:
                    items = []
                    for pos in positions:
                        pct = (pos.market_value / total_value) * 100 if total_value > 0 else 0
                        items.append(
                            portfolio_pb2.AllocationItem(
                                symbol=pos.symbol,
                                name=pos.symbol,  # Would need company name lookup
                                value=common_pb2.Decimal(value=str(pos.market_value)),
                                percentage=common_pb2.Decimal(value=str(pct)),
                                return_percent=common_pb2.Decimal(
                                    value=str(pos.unrealized_pnl_percent)
                                ),
                            )
                        )

                    allocations.append(
                        portfolio_pb2.AssetAllocation(
                            category="Stocks",
                            value=common_pb2.Decimal(value=str(total_value)),
                            percentage=common_pb2.Decimal(value="100.0"),
                            items=items,
                        )
                    )

                return portfolio_pb2.GetAssetAllocationResponse(allocations=allocations)

        except Exception as e:
            logger.error("GetAssetAllocation error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to get asset allocation: {e}",
            )

    async def GetPositions(
        self,
        request: portfolio_pb2.GetPositionsRequest,
        context: grpc.aio.ServicerContext,
    ) -> portfolio_pb2.GetPositionsResponse:
        """Get all positions."""
        from llamatrade.v1 import portfolio_pb2, trading_pb2

        try:
            from src.services.portfolio_service import PortfolioService

            tenant_id = UUID(request.context.tenant_id)

            async with await self._get_db() as db:
                service = PortfolioService(db)
                positions = await service.list_positions(tenant_id)

                return portfolio_pb2.GetPositionsResponse(
                    positions=[self._to_proto_position(p) for p in positions],
                )

        except Exception as e:
            logger.error("GetPositions error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to get positions: {e}",
            )

    async def ListTransactions(
        self,
        request: portfolio_pb2.ListTransactionsRequest,
        context: grpc.aio.ServicerContext,
    ) -> portfolio_pb2.ListTransactionsResponse:
        """List portfolio transactions."""
        from llamatrade.v1 import common_pb2, portfolio_pb2

        try:
            from src.services.transaction_service import TransactionService

            tenant_id = UUID(request.context.tenant_id)
            page = request.pagination.page if request.HasField("pagination") else 1
            page_size = request.pagination.page_size if request.HasField("pagination") else 20

            async with await self._get_db() as db:
                service = TransactionService(db)
                transactions, total = await service.list_transactions(
                    tenant_id=tenant_id,
                    page=page,
                    page_size=page_size,
                )

                total_pages = (total + page_size - 1) // page_size if total > 0 else 1

                return portfolio_pb2.ListTransactionsResponse(
                    transactions=[self._to_proto_transaction(t) for t in transactions],
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
            logger.error("ListTransactions error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to list transactions: {e}",
            )

    async def RecordTransaction(
        self,
        request: portfolio_pb2.RecordTransactionRequest,
        context: grpc.aio.ServicerContext,
    ) -> portfolio_pb2.RecordTransactionResponse:
        """Record a new transaction."""
        from llamatrade.v1 import portfolio_pb2

        try:
            from decimal import Decimal

            from src.models import TransactionCreate, TransactionType
            from src.services.transaction_service import TransactionService

            tenant_id = UUID(request.context.tenant_id)
            txn_type = self._from_proto_transaction_type(request.type)

            create_data = TransactionCreate(
                type=txn_type,
                symbol=request.symbol if request.symbol else None,
                quantity=Decimal(request.quantity.value) if request.HasField("quantity") else None,
                price=Decimal(request.price.value) if request.HasField("price") else None,
                fees=Decimal(request.fees.value) if request.HasField("fees") else Decimal("0"),
                description=request.description if request.description else None,
                reference_id=request.reference_id if request.reference_id else None,
            )

            async with await self._get_db() as db:
                service = TransactionService(db)
                transaction = await service.create_transaction(
                    tenant_id=tenant_id,
                    data=create_data,
                )

                return portfolio_pb2.RecordTransactionResponse(
                    transaction=self._to_proto_transaction(transaction),
                )

        except ValueError as e:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                str(e),
            )
        except grpc.aio.AioRpcError:
            raise
        except Exception as e:
            logger.error("RecordTransaction error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to record transaction: {e}",
            )

    async def SyncPortfolio(
        self,
        request: portfolio_pb2.SyncPortfolioRequest,
        context: grpc.aio.ServicerContext,
    ) -> portfolio_pb2.SyncPortfolioResponse:
        """Sync portfolio with trading session."""
        from llamatrade.v1 import portfolio_pb2

        try:
            from src.services.portfolio_service import PortfolioService

            tenant_id = UUID(request.context.tenant_id)

            # This would call the trading service to get current positions
            # and sync them to the portfolio
            async with await self._get_db() as db:
                service = PortfolioService(db)
                summary = await service.get_summary(tenant_id)
                positions = await service.list_positions(tenant_id)

                return portfolio_pb2.SyncPortfolioResponse(
                    portfolio=self._to_proto_portfolio(summary, tenant_id),
                    positions_synced=len(positions),
                    transactions_recorded=0,
                )

        except Exception as e:
            logger.error("SyncPortfolio error: %s", e, exc_info=True)
            await context.abort(
                grpc.StatusCode.INTERNAL,
                f"Failed to sync portfolio: {e}",
            )

    # ===================
    # Helper methods
    # ===================

    def _to_proto_portfolio(
        self, summary: PortfolioSummary, tenant_id: UUID
    ) -> portfolio_pb2.Portfolio:
        """Convert internal portfolio summary to proto Portfolio."""
        from llamatrade.v1 import common_pb2, portfolio_pb2

        return portfolio_pb2.Portfolio(
            id=str(tenant_id),  # Using tenant_id as portfolio ID for now
            tenant_id=str(tenant_id),
            user_id="",
            name="Main Portfolio",
            total_value=common_pb2.Decimal(value=str(summary.total_equity)),
            cash_balance=common_pb2.Decimal(value=str(summary.cash)),
            positions_value=common_pb2.Decimal(value=str(summary.market_value)),
            total_return=common_pb2.Decimal(
                value=str(summary.total_unrealized_pnl + summary.total_realized_pnl)
            ),
            total_return_percent=common_pb2.Decimal(value=str(summary.total_pnl_percent)),
            day_return=common_pb2.Decimal(value=str(summary.day_pnl)),
            day_return_percent=common_pb2.Decimal(value=str(summary.day_pnl_percent)),
            updated_at=common_pb2.Timestamp(seconds=int(summary.updated_at.timestamp())),
        )

    def _to_proto_position(self, pos: PositionResponse) -> trading_pb2.Position:
        """Convert internal position to proto Position."""
        from llamatrade.v1 import common_pb2, trading_pb2

        side = (
            trading_pb2.POSITION_SIDE_LONG if pos.side == "long" else trading_pb2.POSITION_SIDE_SHORT
        )

        return trading_pb2.Position(
            id="",
            symbol=pos.symbol,
            side=side,
            quantity=common_pb2.Decimal(value=str(pos.qty)),
            cost_basis=common_pb2.Decimal(value=str(pos.cost_basis)),
            average_entry_price=common_pb2.Decimal(value=str(pos.avg_entry_price)),
            current_price=common_pb2.Decimal(value=str(pos.current_price)),
            market_value=common_pb2.Decimal(value=str(pos.market_value)),
            unrealized_pnl=common_pb2.Decimal(value=str(pos.unrealized_pnl)),
        )

    def _to_proto_transaction(self, txn: TransactionResponse) -> portfolio_pb2.Transaction:
        """Convert internal transaction to proto Transaction."""
        from llamatrade.v1 import common_pb2, portfolio_pb2

        return portfolio_pb2.Transaction(
            id=str(txn.id),
            portfolio_id=str(txn.tenant_id),
            type=self._to_proto_transaction_type(txn.type),
            symbol=txn.symbol or "",
            quantity=common_pb2.Decimal(value=str(txn.quantity or 0)),
            price=common_pb2.Decimal(value=str(txn.price or 0)),
            amount=common_pb2.Decimal(value=str(txn.amount)),
            fees=common_pb2.Decimal(value=str(txn.fees or 0)),
            description=txn.description or "",
            reference_id=txn.reference_id or "",
            timestamp=common_pb2.Timestamp(seconds=int(txn.created_at.timestamp())),
        )

    def _to_proto_transaction_type(self, txn_type: TransactionType) -> int:
        """Convert internal transaction type to proto enum value."""
        from llamatrade.v1 import portfolio_pb2

        from src.models import TransactionType

        type_map = {
            TransactionType.DEPOSIT: portfolio_pb2.TRANSACTION_TYPE_DEPOSIT,
            TransactionType.WITHDRAWAL: portfolio_pb2.TRANSACTION_TYPE_WITHDRAWAL,
            TransactionType.BUY: portfolio_pb2.TRANSACTION_TYPE_BUY,
            TransactionType.SELL: portfolio_pb2.TRANSACTION_TYPE_SELL,
            TransactionType.DIVIDEND: portfolio_pb2.TRANSACTION_TYPE_DIVIDEND,
            TransactionType.INTEREST: portfolio_pb2.TRANSACTION_TYPE_INTEREST,
            TransactionType.FEE: portfolio_pb2.TRANSACTION_TYPE_FEE,
        }
        return type_map.get(txn_type, portfolio_pb2.TRANSACTION_TYPE_UNSPECIFIED)

    def _from_proto_transaction_type(self, txn_type: int) -> TransactionType:
        """Convert proto transaction type to internal type."""
        from llamatrade.v1 import portfolio_pb2

        from src.models import TransactionType

        type_map = {
            portfolio_pb2.TRANSACTION_TYPE_DEPOSIT: TransactionType.DEPOSIT,
            portfolio_pb2.TRANSACTION_TYPE_WITHDRAWAL: TransactionType.WITHDRAWAL,
            portfolio_pb2.TRANSACTION_TYPE_BUY: TransactionType.BUY,
            portfolio_pb2.TRANSACTION_TYPE_SELL: TransactionType.SELL,
            portfolio_pb2.TRANSACTION_TYPE_DIVIDEND: TransactionType.DIVIDEND,
            portfolio_pb2.TRANSACTION_TYPE_INTEREST: TransactionType.INTEREST,
            portfolio_pb2.TRANSACTION_TYPE_FEE: TransactionType.FEE,
        }
        return type_map.get(txn_type, TransactionType.DEPOSIT)


# Type aliases for method signatures (imported lazily)
from src.models import PortfolioSummary, PositionResponse, TransactionResponse, TransactionType
from llamatrade.v1 import portfolio_pb2, trading_pb2
