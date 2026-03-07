"""Portfolio Connect servicer implementation."""

from __future__ import annotations

import logging
from datetime import UTC
from typing import TYPE_CHECKING
from uuid import UUID

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from connectrpc.request import RequestContext
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Type alias for generic request context (accepts any request/response types)
type AnyContext = RequestContext[object, object]

from llamatrade_db import get_session_maker

if TYPE_CHECKING:
    from llamatrade_proto.generated import portfolio_pb2

logger = logging.getLogger(__name__)


class PortfolioServicer:
    """Connect servicer for the Portfolio service.

    Implements the PortfolioService Protocol defined in portfolio_connect.py.
    """

    def __init__(self) -> None:
        """Initialize the servicer."""
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    async def _get_db(self) -> AsyncSession:
        """Get a database session."""
        if self._session_factory is None:
            self._session_factory = get_session_maker()
        assert self._session_factory is not None
        return self._session_factory()

    async def get_portfolio(
        self,
        request: portfolio_pb2.GetPortfolioRequest,
        ctx: AnyContext,
    ) -> portfolio_pb2.GetPortfolioResponse:
        """Get portfolio summary and positions."""
        from llamatrade_proto.generated import portfolio_pb2

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
            logger.error("get_portfolio error: %s", e, exc_info=True)
            raise ConnectError(
                Code.INTERNAL,
                f"Failed to get portfolio: {e}",
            ) from e

    async def list_portfolios(
        self,
        request: portfolio_pb2.ListPortfoliosRequest,
        ctx: AnyContext,
    ) -> portfolio_pb2.ListPortfoliosResponse:
        """List portfolios for a tenant."""
        from llamatrade_proto.generated import common_pb2, portfolio_pb2

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
            logger.error("list_portfolios error: %s", e, exc_info=True)
            raise ConnectError(
                Code.INTERNAL,
                f"Failed to list portfolios: {e}",
            ) from e

    async def get_performance(
        self,
        request: portfolio_pb2.GetPerformanceRequest,
        ctx: AnyContext,
    ) -> portfolio_pb2.GetPerformanceResponse:
        """Get portfolio performance metrics."""
        from llamatrade_proto.generated import common_pb2, portfolio_pb2

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
                            request.time_range.start.seconds, tz=UTC
                        )
                    if request.time_range.end.seconds > 0:
                        end_date = datetime.fromtimestamp(request.time_range.end.seconds, tz=UTC)

                # Convert date range to period string for metrics API
                # Default to 1M if no time range provided
                period = "1M"
                if start_date and end_date:
                    delta = end_date - start_date
                    if delta.days <= 1:
                        period = "1D"
                    elif delta.days <= 7:
                        period = "1W"
                    elif delta.days <= 30:
                        period = "1M"
                    elif delta.days <= 90:
                        period = "3M"
                    elif delta.days <= 180:
                        period = "6M"
                    elif delta.days <= 365:
                        period = "1Y"
                    else:
                        period = "ALL"

                # Get performance metrics
                metrics = await perf_service.get_metrics(
                    tenant_id=tenant_id,
                    period=period,
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
            logger.error("get_performance error: %s", e, exc_info=True)
            raise ConnectError(
                Code.INTERNAL,
                f"Failed to get performance: {e}",
            ) from e

    async def get_asset_allocation(
        self,
        request: portfolio_pb2.GetAssetAllocationRequest,
        ctx: AnyContext,
    ) -> portfolio_pb2.GetAssetAllocationResponse:
        """Get asset allocation breakdown."""
        from llamatrade_proto.generated import common_pb2, portfolio_pb2

        try:
            from src.services.portfolio_service import PortfolioService

            tenant_id = UUID(request.context.tenant_id)

            async with await self._get_db() as db:
                service = PortfolioService(db)
                positions = await service.list_positions(tenant_id)

                # Calculate allocation by grouping
                # For simplicity, treat all as "Stocks" category
                total_value = sum(p.market_value for p in positions)

                allocations: list[portfolio_pb2.AssetAllocation] = []
                if total_value > 0:
                    items: list[portfolio_pb2.AllocationItem] = []
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
            logger.error("get_asset_allocation error: %s", e, exc_info=True)
            raise ConnectError(
                Code.INTERNAL,
                f"Failed to get asset allocation: {e}",
            ) from e

    async def get_positions(
        self,
        request: portfolio_pb2.GetPositionsRequest,
        ctx: AnyContext,
    ) -> portfolio_pb2.GetPositionsResponse:
        """Get all positions."""
        from llamatrade_proto.generated import portfolio_pb2

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
            logger.error("get_positions error: %s", e, exc_info=True)
            raise ConnectError(
                Code.INTERNAL,
                f"Failed to get positions: {e}",
            ) from e

    async def list_transactions(
        self,
        request: portfolio_pb2.ListTransactionsRequest,
        ctx: AnyContext,
    ) -> portfolio_pb2.ListTransactionsResponse:
        """List portfolio transactions."""
        from llamatrade_proto.generated import common_pb2, portfolio_pb2

        try:
            from src.services.transaction_service import TransactionService

            tenant_id = UUID(request.context.tenant_id)
            page = request.pagination.page if request.HasField("pagination") else 1
            page_size = request.pagination.page_size if request.HasField("pagination") else 20

            async with await self._get_db() as db:
                service = TransactionService(db)
                transactions, total = await service.list_transactions(
                    tenant_id=tenant_id,
                    type=None,
                    symbol=None,
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
            logger.error("list_transactions error: %s", e, exc_info=True)
            raise ConnectError(
                Code.INTERNAL,
                f"Failed to list transactions: {e}",
            ) from e

    async def record_transaction(
        self,
        request: portfolio_pb2.RecordTransactionRequest,
        ctx: AnyContext,
    ) -> portfolio_pb2.RecordTransactionResponse:
        """Record a new transaction."""
        from llamatrade_proto.generated import portfolio_pb2

        try:
            from decimal import Decimal

            from src.models import TransactionCreate
            from src.services.transaction_service import TransactionService

            tenant_id = UUID(request.context.tenant_id)
            txn_type = self._from_proto_transaction_type(request.type)

            # Calculate amount from quantity * price, or use explicit amount if provided
            qty = Decimal(request.quantity.value) if request.HasField("quantity") else None
            price = Decimal(request.price.value) if request.HasField("price") else None
            amount = Decimal("0")
            if qty is not None and price is not None:
                amount = qty * price

            create_data = TransactionCreate(
                type=txn_type,
                symbol=request.symbol if request.symbol else None,
                qty=float(qty) if qty is not None else None,
                price=float(price) if price is not None else None,
                amount=float(amount),
                commission=float(Decimal(request.fees.value)) if request.HasField("fees") else 0,
                description=request.description if request.description else None,
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
            raise ConnectError(
                Code.INVALID_ARGUMENT,
                str(e),
            ) from e
        except ConnectError:
            raise
        except Exception as e:
            logger.error("record_transaction error: %s", e, exc_info=True)
            raise ConnectError(
                Code.INTERNAL,
                f"Failed to record transaction: {e}",
            ) from e

    async def sync_portfolio(
        self,
        request: portfolio_pb2.SyncPortfolioRequest,
        ctx: AnyContext,
    ) -> portfolio_pb2.SyncPortfolioResponse:
        """Sync portfolio with trading session."""
        from llamatrade_proto.generated import portfolio_pb2

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
            logger.error("sync_portfolio error: %s", e, exc_info=True)
            raise ConnectError(
                Code.INTERNAL,
                f"Failed to sync portfolio: {e}",
            ) from e

    # ===================
    # Strategy Performance Methods
    # ===================

    async def list_strategy_performance(
        self,
        request: portfolio_pb2.ListStrategyPerformanceRequest,
        ctx: AnyContext,
    ) -> portfolio_pb2.ListStrategyPerformanceResponse:
        """List all deployed strategies with performance summaries."""
        from llamatrade_proto.generated import common_pb2, portfolio_pb2

        try:
            from src.services.strategy_performance_service import (
                ListPerformanceFilters,
                StrategyPerformanceService,
            )

            tenant_id = UUID(request.context.tenant_id)
            page = request.pagination.page if request.HasField("pagination") else 1
            page_size = request.pagination.page_size if request.HasField("pagination") else 20

            # Build filters - proto enum values are passed directly as ints
            filters = ListPerformanceFilters()
            if request.mode != portfolio_pb2.EXECUTION_MODE_UNSPECIFIED:
                filters.mode = request.mode
            if request.status != portfolio_pb2.EXECUTION_STATUS_UNSPECIFIED:
                filters.status = request.status

            async with await self._get_db() as db:
                service = StrategyPerformanceService(db)
                result = await service.list_strategy_performance(
                    tenant_id=tenant_id,
                    filters=filters,
                    page=page,
                    page_size=page_size,
                )

                total_pages = (result.total + page_size - 1) // page_size if result.total > 0 else 1

                return portfolio_pb2.ListStrategyPerformanceResponse(
                    strategies=[self._to_proto_strategy_summary(s) for s in result.strategies],
                    total_allocated=common_pb2.Decimal(value=str(result.total_allocated)),
                    total_current_value=common_pb2.Decimal(value=str(result.total_current_value)),
                    combined_return=common_pb2.Decimal(
                        value=str(result.combined_return) if result.combined_return else "0"
                    ),
                    pagination=common_pb2.PaginationResponse(
                        total_items=result.total,
                        total_pages=total_pages,
                        current_page=page,
                        page_size=page_size,
                        has_next=page < total_pages,
                        has_previous=page > 1,
                    ),
                )

        except Exception as e:
            logger.error("list_strategy_performance error: %s", e, exc_info=True)
            raise ConnectError(
                Code.INTERNAL,
                f"Failed to list strategy performance: {e}",
            ) from e

    async def get_strategy_performance(
        self,
        request: portfolio_pb2.GetStrategyPerformanceRequest,
        ctx: AnyContext,
    ) -> portfolio_pb2.GetStrategyPerformanceResponse:
        """Get detailed performance for a single strategy."""
        from llamatrade_proto.generated import portfolio_pb2

        try:
            from src.services.strategy_performance_service import StrategyPerformanceService

            tenant_id = UUID(request.context.tenant_id)
            execution_id = UUID(request.execution_id)

            async with await self._get_db() as db:
                service = StrategyPerformanceService(db)
                detail = await service.get_strategy_performance(
                    tenant_id=tenant_id,
                    execution_id=execution_id,
                )

                if not detail:
                    raise ConnectError(
                        Code.NOT_FOUND,
                        f"Strategy execution {execution_id} not found",
                    )

                return portfolio_pb2.GetStrategyPerformanceResponse(
                    summary=self._to_proto_strategy_summary(detail.summary),
                    metrics=self._to_proto_live_metrics(detail.metrics),
                    positions=[],  # Positions handled separately
                )

        except ConnectError:
            raise
        except Exception as e:
            logger.error("get_strategy_performance error: %s", e, exc_info=True)
            raise ConnectError(
                Code.INTERNAL,
                f"Failed to get strategy performance: {e}",
            ) from e

    async def get_strategy_equity_curve(
        self,
        request: portfolio_pb2.GetStrategyEquityCurveRequest,
        ctx: AnyContext,
    ) -> portfolio_pb2.GetStrategyEquityCurveResponse:
        """Get equity curve time series for a strategy."""
        from datetime import datetime

        from llamatrade_proto.generated import common_pb2, portfolio_pb2

        try:
            from src.services.strategy_performance_service import StrategyPerformanceService

            tenant_id = UUID(request.context.tenant_id)
            execution_id = UUID(request.execution_id)

            # Parse time range
            start_time = None
            end_time = None
            if request.HasField("time_range"):
                if request.time_range.start.seconds > 0:
                    start_time = datetime.fromtimestamp(request.time_range.start.seconds, tz=UTC)
                if request.time_range.end.seconds > 0:
                    end_time = datetime.fromtimestamp(request.time_range.end.seconds, tz=UTC)

            async with await self._get_db() as db:
                service = StrategyPerformanceService(db)
                result = await service.get_strategy_equity_curve(
                    tenant_id=tenant_id,
                    execution_id=execution_id,
                    start_time=start_time,
                    end_time=end_time,
                    sample_interval_minutes=request.sample_interval_minutes,
                )

                if not result:
                    raise ConnectError(
                        Code.NOT_FOUND,
                        f"Strategy execution {execution_id} not found",
                    )

                return portfolio_pb2.GetStrategyEquityCurveResponse(
                    equity_curve=[
                        portfolio_pb2.StrategyEquityPoint(
                            timestamp=common_pb2.Timestamp(seconds=int(p.timestamp.timestamp())),
                            equity=common_pb2.Decimal(value=str(p.equity)),
                            return_percent=common_pb2.Decimal(
                                value=str(p.return_percent) if p.return_percent else "0"
                            ),
                            drawdown=common_pb2.Decimal(
                                value=str(p.drawdown) if p.drawdown else "0"
                            ),
                        )
                        for p in result.equity_curve
                    ],
                    period_returns=self._to_proto_period_returns(result.period_returns),
                )

        except ConnectError:
            raise
        except Exception as e:
            logger.error("get_strategy_equity_curve error: %s", e, exc_info=True)
            raise ConnectError(
                Code.INTERNAL,
                f"Failed to get equity curve: {e}",
            ) from e

    # ===================
    # Helper methods
    # ===================

    def _to_proto_portfolio(
        self, summary: PortfolioSummary, tenant_id: UUID
    ) -> portfolio_pb2.Portfolio:
        """Convert internal portfolio summary to proto Portfolio."""
        from llamatrade_proto.generated import common_pb2, portfolio_pb2

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
        from llamatrade_proto.generated import common_pb2, trading_pb2

        side = (
            trading_pb2.POSITION_SIDE_LONG
            if pos.side == "long"
            else trading_pb2.POSITION_SIDE_SHORT
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
        from llamatrade_proto.generated import common_pb2, portfolio_pb2

        txn_type = portfolio_pb2.TransactionType.ValueType(
            self._to_proto_transaction_type(txn.type)
        )
        return portfolio_pb2.Transaction(
            id=str(txn.id),
            portfolio_id=str(txn.tenant_id),
            type=txn_type,
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
        from llamatrade_proto.generated import portfolio_pb2

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
        from llamatrade_proto.generated import portfolio_pb2

        from src.models import TransactionType

        type_map: dict[int, TransactionType] = {
            portfolio_pb2.TRANSACTION_TYPE_DEPOSIT: TransactionType.DEPOSIT,
            portfolio_pb2.TRANSACTION_TYPE_WITHDRAWAL: TransactionType.WITHDRAWAL,
            portfolio_pb2.TRANSACTION_TYPE_BUY: TransactionType.BUY,
            portfolio_pb2.TRANSACTION_TYPE_SELL: TransactionType.SELL,
            portfolio_pb2.TRANSACTION_TYPE_DIVIDEND: TransactionType.DIVIDEND,
            portfolio_pb2.TRANSACTION_TYPE_INTEREST: TransactionType.INTEREST,
            portfolio_pb2.TRANSACTION_TYPE_FEE: TransactionType.FEE,
        }
        return type_map.get(txn_type, TransactionType.DEPOSIT)

    def _to_proto_strategy_summary(
        self, summary: StrategyPerformanceSummary
    ) -> portfolio_pb2.StrategyPerformanceSummary:
        """Convert internal strategy summary to proto."""
        from llamatrade_proto.generated import common_pb2, portfolio_pb2

        mode_map = {
            "paper": portfolio_pb2.EXECUTION_MODE_PAPER,
            "live": portfolio_pb2.EXECUTION_MODE_LIVE,
        }
        status_map = {
            "pending": portfolio_pb2.EXECUTION_STATUS_UNSPECIFIED,
            "running": portfolio_pb2.EXECUTION_STATUS_RUNNING,
            "paused": portfolio_pb2.EXECUTION_STATUS_PAUSED,
            "stopped": portfolio_pb2.EXECUTION_STATUS_STOPPED,
            "error": portfolio_pb2.EXECUTION_STATUS_ERROR,
        }

        return portfolio_pb2.StrategyPerformanceSummary(
            execution_id=str(summary.execution_id),
            strategy_id=str(summary.strategy_id),
            strategy_name=summary.strategy_name,
            mode=mode_map.get(summary.mode, portfolio_pb2.EXECUTION_MODE_UNSPECIFIED),
            status=status_map.get(summary.status, portfolio_pb2.EXECUTION_STATUS_UNSPECIFIED),
            color=summary.color or "",
            allocated_capital=common_pb2.Decimal(
                value=str(summary.allocated_capital) if summary.allocated_capital else "0"
            ),
            current_value=common_pb2.Decimal(
                value=str(summary.current_value) if summary.current_value else "0"
            ),
            positions_count=summary.positions_count,
            returns=self._to_proto_period_returns(summary.returns),
            started_at=common_pb2.Timestamp(
                seconds=int(summary.started_at.timestamp()) if summary.started_at else 0
            ),
            updated_at=common_pb2.Timestamp(seconds=int(summary.updated_at.timestamp())),
        )

    def _to_proto_period_returns(
        self, returns: PeriodReturns
    ) -> portfolio_pb2.StrategyPeriodReturns:
        """Convert internal period returns to proto."""
        from llamatrade_proto.generated import common_pb2, portfolio_pb2

        return portfolio_pb2.StrategyPeriodReturns(
            return_1d=common_pb2.Decimal(
                value=str(returns.return_1d) if returns.return_1d else "0"
            ),
            return_1w=common_pb2.Decimal(
                value=str(returns.return_1w) if returns.return_1w else "0"
            ),
            return_1m=common_pb2.Decimal(
                value=str(returns.return_1m) if returns.return_1m else "0"
            ),
            return_3m=common_pb2.Decimal(
                value=str(returns.return_3m) if returns.return_3m else "0"
            ),
            return_6m=common_pb2.Decimal(
                value=str(returns.return_6m) if returns.return_6m else "0"
            ),
            return_1y=common_pb2.Decimal(
                value=str(returns.return_1y) if returns.return_1y else "0"
            ),
            return_ytd=common_pb2.Decimal(
                value=str(returns.return_ytd) if returns.return_ytd else "0"
            ),
            return_all=common_pb2.Decimal(
                value=str(returns.return_all) if returns.return_all else "0"
            ),
        )

    def _to_proto_live_metrics(self, metrics: LiveMetrics) -> portfolio_pb2.StrategyLiveMetrics:
        """Convert internal live metrics to proto."""
        from decimal import Decimal

        from llamatrade_proto.generated import common_pb2, portfolio_pb2

        def dec(val: Decimal | None) -> common_pb2.Decimal:
            return common_pb2.Decimal(value=str(val) if val is not None else "0")

        return portfolio_pb2.StrategyLiveMetrics(
            sharpe_ratio=dec(metrics.sharpe_ratio),
            sortino_ratio=dec(metrics.sortino_ratio),
            calmar_ratio=dec(metrics.calmar_ratio),
            max_drawdown=dec(metrics.max_drawdown),
            current_drawdown=dec(metrics.current_drawdown),
            volatility=dec(metrics.volatility),
            total_trades=metrics.total_trades,
            winning_trades=metrics.winning_trades,
            losing_trades=metrics.losing_trades,
            win_rate=dec(metrics.win_rate),
            profit_factor=dec(metrics.profit_factor),
            average_win=dec(metrics.average_win),
            average_loss=dec(metrics.average_loss),
            starting_capital=dec(metrics.starting_capital),
            current_equity=dec(metrics.current_equity),
            peak_equity=dec(metrics.peak_equity),
            total_pnl=dec(metrics.total_pnl),
            benchmark_symbol=metrics.benchmark_symbol or "",
            alpha=dec(metrics.alpha),
            beta=dec(metrics.beta),
            correlation=dec(metrics.correlation),
            calculated_at=common_pb2.Timestamp(
                seconds=int(metrics.calculated_at.timestamp()) if metrics.calculated_at else 0
            ),
        )


# Type aliases for method signatures (imported lazily)
from llamatrade_proto.generated import portfolio_pb2, trading_pb2

from src.models import PortfolioSummary, PositionResponse, TransactionResponse, TransactionType
from src.services.strategy_performance_service import (
    LiveMetrics,
    PeriodReturns,
    StrategyPerformanceSummary,
)
