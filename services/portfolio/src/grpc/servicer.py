"""Portfolio Connect servicer implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from connectrpc.request import RequestContext
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Type alias for generic request context (accepts any request/response types)
type AnyContext = RequestContext[object, object]

from llamatrade_common import pagination_response, resolve_pagination
from llamatrade_common.connect import (
    handle_service_errors,
    parse_uuid,
    resolve_identity_connect,
)
from llamatrade_db import get_session_maker, tenant_session

from src.clients.market_data import get_market_data_client
from src.ledger.projector import LedgerProjector
from src.proto_mappers import position_view_to_proto, summary_view_to_proto
from src.services.read_context import AccountProjectionCache, PriceCache

if TYPE_CHECKING:
    from llamatrade_proto.generated import portfolio_pb2

    from src.services.portfolio_read_service import PortfolioReadService
    from src.services.strategy_performance_read_service import StrategyPerformanceReadService


class PortfolioServicer:
    """Connect servicer for the Portfolio service.

    Implements the PortfolioService Protocol defined in portfolio_connect.py.
    """

    def __init__(self) -> None:
        """Initialize the servicer."""
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    def _maker(self) -> async_sessionmaker[AsyncSession]:
        """The session factory (lazily created; tests inject a test-DB factory)."""
        if self._session_factory is None:
            self._session_factory = get_session_maker()
        return self._session_factory

    # All portfolio/strategy reads derive from the ledger projection — the single source of truth.

    def _read_caches(self, db: AsyncSession) -> tuple[AccountProjectionCache, PriceCache]:
        """Per-request fold-once + price-once caches, shared across both readers."""
        return (
            AccountProjectionCache(LedgerProjector(db)),
            PriceCache(get_market_data_client()),
        )

    def _reader(
        self,
        db: AsyncSession,
        projections: AccountProjectionCache | None = None,
        prices: PriceCache | None = None,
    ) -> PortfolioReadService:
        """Ledger-backed reader for summary / positions / performance / transactions."""
        from src.services.portfolio_read_service import PortfolioReadService

        return PortfolioReadService(
            db, market_data=get_market_data_client(), projections=projections, prices=prices
        )

    def _strategy_perf_reader(
        self,
        db: AsyncSession,
        projections: AccountProjectionCache | None = None,
        prices: PriceCache | None = None,
    ) -> StrategyPerformanceReadService:
        """Ledger-backed strategy-performance reader (list/get/equity-curve)."""
        from src.services.strategy_performance_read_service import (
            StrategyPerformanceReadService,
        )

        return StrategyPerformanceReadService(
            db, market_data=get_market_data_client(), projections=projections, prices=prices
        )

    @handle_service_errors
    async def get_portfolio(
        self,
        request: portfolio_pb2.GetPortfolioRequest,
        ctx: AnyContext,
    ) -> portfolio_pb2.GetPortfolioResponse:
        """Get portfolio summary and positions."""
        from llamatrade_proto.generated import portfolio_pb2

        tenant_id, _ = resolve_identity_connect(request.context)

        async with tenant_session(tenant_id, self._maker()) as db:
            projections, prices = self._read_caches(db)
            service = self._reader(db, projections, prices)
            summary = await service.get_summary(tenant_id)
            positions = await service.list_positions(tenant_id)
            book = await self._strategy_perf_reader(db, projections, prices).book_totals(tenant_id)

            return portfolio_pb2.GetPortfolioResponse(
                portfolio=summary_view_to_proto(summary, tenant_id, book),
                positions=[position_view_to_proto(p) for p in positions],
            )

    @handle_service_errors
    async def list_portfolios(
        self,
        request: portfolio_pb2.ListPortfoliosRequest,
        ctx: AnyContext,
    ) -> portfolio_pb2.ListPortfoliosResponse:
        """List portfolios for a tenant."""
        from llamatrade_proto.generated import common_pb2, portfolio_pb2

        tenant_id, _ = resolve_identity_connect(request.context)

        async with tenant_session(tenant_id, self._maker()) as db:
            projections, prices = self._read_caches(db)
            service = self._reader(db, projections, prices)
            summary = await service.get_summary(tenant_id)
            book = await self._strategy_perf_reader(db, projections, prices).book_totals(tenant_id)

            # Currently we support one portfolio per tenant
            portfolios = [summary_view_to_proto(summary, tenant_id, book)]

            return portfolio_pb2.ListPortfoliosResponse(
                portfolios=portfolios,
                pagination=common_pb2.PaginationResponse(**pagination_response(1, 1, 20)),
            )

    @handle_service_errors
    async def get_performance(
        self,
        request: portfolio_pb2.GetPerformanceRequest,
        ctx: AnyContext,
    ) -> portfolio_pb2.GetPerformanceResponse:
        """Get portfolio performance metrics."""
        from llamatrade_proto.generated import portfolio_pb2

        tenant_id, _ = resolve_identity_connect(request.context)

        async with tenant_session(tenant_id, self._maker()) as db:
            service = self._reader(db)

            summary = await service.get_summary(tenant_id)

            # Convert time range if provided
            start_date = None
            end_date = None
            if request.HasField("time_range"):
                from llamatrade_proto.timestamps import from_proto_timestamp

                if request.time_range.start.seconds > 0:
                    start_date = from_proto_timestamp(request.time_range.start)
                if request.time_range.end.seconds > 0:
                    end_date = from_proto_timestamp(request.time_range.end)

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

            proto_metrics = await service.get_metrics(
                tenant_id=tenant_id,
                period=period,
            )
            proto_metrics.total_positions = summary.positions_count

            return portfolio_pb2.GetPerformanceResponse(metrics=proto_metrics)

    @handle_service_errors
    async def get_asset_allocation(
        self,
        request: portfolio_pb2.GetAssetAllocationRequest,
        ctx: AnyContext,
    ) -> portfolio_pb2.GetAssetAllocationResponse:
        """Get asset allocation breakdown."""
        from llamatrade_proto.generated import common_pb2, portfolio_pb2

        tenant_id, _ = resolve_identity_connect(request.context)

        async with tenant_session(tenant_id, self._maker()) as db:
            service = self._reader(db)
            positions = await service.list_positions(tenant_id)
            summary = await service.get_summary(tenant_id)

            positions_value = sum(p.market_value for p in positions)
            cash = summary.cash
            total = positions_value + cash

            allocations: list[portfolio_pb2.AssetAllocation] = []
            if total > 0:
                # Per-symbol weights are over the WHOLE portfolio (incl. cash), so symbol weights and the cash weight sum to 100%.
                items = [
                    portfolio_pb2.AllocationItem(
                        symbol=pos.symbol,
                        name=pos.symbol,  # company-name lookup is a follow-up
                        value=common_pb2.Decimal(value=str(pos.market_value)),
                        percentage=common_pb2.Decimal(value=str(pos.market_value / total * 100)),
                        return_percent=common_pb2.Decimal(value=str(pos.unrealized_pnl_percent)),
                    )
                    for pos in positions
                ]
                if items:
                    allocations.append(
                        portfolio_pb2.AssetAllocation(
                            category="Stocks",
                            value=common_pb2.Decimal(value=str(positions_value)),
                            percentage=common_pb2.Decimal(value=str(positions_value / total * 100)),
                            items=items,
                        )
                    )
                if cash > 0:
                    allocations.append(
                        portfolio_pb2.AssetAllocation(
                            category="Cash",
                            value=common_pb2.Decimal(value=str(cash)),
                            percentage=common_pb2.Decimal(value=str(cash / total * 100)),
                            items=[],
                        )
                    )

            return portfolio_pb2.GetAssetAllocationResponse(allocations=allocations)

    @handle_service_errors
    async def get_positions(
        self,
        request: portfolio_pb2.GetPositionsRequest,
        ctx: AnyContext,
    ) -> portfolio_pb2.GetPositionsResponse:
        """Get all positions."""
        from llamatrade_proto.generated import portfolio_pb2

        tenant_id, _ = resolve_identity_connect(request.context)

        async with tenant_session(tenant_id, self._maker()) as db:
            service = self._reader(db)
            positions = await service.list_positions(tenant_id)

            return portfolio_pb2.GetPositionsResponse(
                positions=[position_view_to_proto(p) for p in positions],
            )

    @handle_service_errors
    async def list_transactions(
        self,
        request: portfolio_pb2.ListTransactionsRequest,
        ctx: AnyContext,
    ) -> portfolio_pb2.ListTransactionsResponse:
        """List portfolio transactions."""
        from llamatrade_proto.generated import common_pb2, portfolio_pb2

        tenant_id, _ = resolve_identity_connect(request.context)
        page, page_size = resolve_pagination(
            request.pagination if request.HasField("pagination") else None
        )

        async with tenant_session(tenant_id, self._maker()) as db:
            service = self._reader(db)
            transactions, total = await service.list_transactions(
                tenant_id=tenant_id,
                type=None,
                symbol=None,
                page=page,
                page_size=page_size,
            )

            return portfolio_pb2.ListTransactionsResponse(
                transactions=list(transactions),
                pagination=common_pb2.PaginationResponse(
                    **pagination_response(total, page, page_size)
                ),
            )

    @handle_service_errors
    async def sync_portfolio(
        self,
        request: portfolio_pb2.SyncPortfolioRequest,
        ctx: AnyContext,
    ) -> portfolio_pb2.SyncPortfolioResponse:
        """Reconcile the tenant's accounts against broker truth, then return the
        freshly reconciled portfolio.

        For an event-sourced ledger the "sync" IS a reconciliation pass: it reads
        broker positions, adopts external trades into Unmanaged, and flags
        material drift (the same path the background loop runs, idempotent).
        ``transactions_recorded`` is the number of drifts the pass surfaced.
        """
        from sqlalchemy import select

        from llamatrade_db.models.ledger import Account
        from llamatrade_proto.generated import portfolio_pb2

        from src.tasks.reconciliation import reconcile_accounts_once

        tenant_id, _ = resolve_identity_connect(request.context)
        maker = self._maker()

        async with tenant_session(tenant_id, maker) as db:
            accounts = list(await db.scalars(select(Account).where(Account.tenant_id == tenant_id)))
        transactions_recorded = 0
        if accounts:
            results = await reconcile_accounts_once(maker, accounts)
            transactions_recorded = sum(len(r.drifts) for r in results)

        async with tenant_session(tenant_id, maker) as db:
            projections, prices = self._read_caches(db)
            service = self._reader(db, projections, prices)
            summary = await service.get_summary(tenant_id)
            positions = await service.list_positions(tenant_id)
            book = await self._strategy_perf_reader(db, projections, prices).book_totals(tenant_id)

            return portfolio_pb2.SyncPortfolioResponse(
                portfolio=summary_view_to_proto(summary, tenant_id, book),
                positions_synced=len(positions),
                transactions_recorded=transactions_recorded,
            )

    @handle_service_errors
    async def list_strategy_performance(
        self,
        request: portfolio_pb2.ListStrategyPerformanceRequest,
        ctx: AnyContext,
    ) -> portfolio_pb2.ListStrategyPerformanceResponse:
        """List all deployed strategies with performance summaries."""
        from llamatrade_proto.generated import common_pb2, portfolio_pb2

        from src.services.strategy_performance_service import ListPerformanceFilters

        tenant_id, _ = resolve_identity_connect(request.context)
        page, page_size = resolve_pagination(
            request.pagination if request.HasField("pagination") else None
        )

        # Build filters - proto enum values are passed directly as ints
        filters = ListPerformanceFilters()
        if request.mode != common_pb2.EXECUTION_MODE_UNSPECIFIED:
            filters.mode = request.mode
        if request.status != common_pb2.EXECUTION_STATUS_UNSPECIFIED:
            filters.status = request.status

        async with tenant_session(tenant_id, self._maker()) as db:
            service = self._strategy_perf_reader(db)
            result = await service.list_strategy_performance(
                tenant_id=tenant_id,
                filters=filters,
                page=page,
                page_size=page_size,
            )

            return portfolio_pb2.ListStrategyPerformanceResponse(
                strategies=list(result.strategies),
                total_allocated=common_pb2.Decimal(value=str(result.total_allocated)),
                total_current_value=common_pb2.Decimal(value=str(result.total_current_value)),
                combined_return=common_pb2.Decimal(
                    value=str(result.combined_return) if result.combined_return else "0"
                ),
                pagination=common_pb2.PaginationResponse(
                    **pagination_response(result.total, page, page_size)
                ),
            )

    @handle_service_errors
    async def get_strategy_performance(
        self,
        request: portfolio_pb2.GetStrategyPerformanceRequest,
        ctx: AnyContext,
    ) -> portfolio_pb2.GetStrategyPerformanceResponse:
        """Get detailed performance for a single strategy."""
        from llamatrade_proto.generated import portfolio_pb2

        tenant_id, _ = resolve_identity_connect(request.context)
        execution_id = parse_uuid(request.execution_id, "execution_id")

        async with tenant_session(tenant_id, self._maker()) as db:
            service = self._strategy_perf_reader(db)
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
                summary=detail.summary,
                metrics=detail.metrics,
                positions=[position_view_to_proto(p) for p in detail.positions],
            )

    @handle_service_errors
    async def get_strategy_equity_curve(
        self,
        request: portfolio_pb2.GetStrategyEquityCurveRequest,
        ctx: AnyContext,
    ) -> portfolio_pb2.GetStrategyEquityCurveResponse:
        """Get equity curve time series for a strategy."""
        from llamatrade_proto.generated import portfolio_pb2
        from llamatrade_proto.timestamps import from_proto_timestamp

        tenant_id, _ = resolve_identity_connect(request.context)
        execution_id = parse_uuid(request.execution_id, "execution_id")

        # Parse time range
        start_time = None
        end_time = None
        if request.HasField("time_range"):
            if request.time_range.start.seconds > 0:
                start_time = from_proto_timestamp(request.time_range.start)
            if request.time_range.end.seconds > 0:
                end_time = from_proto_timestamp(request.time_range.end)

        async with tenant_session(tenant_id, self._maker()) as db:
            service = self._strategy_perf_reader(db)
            result = await service.get_strategy_equity_curve(
                tenant_id=tenant_id,
                execution_id=execution_id,
                start_time=start_time,
                end_time=end_time,
                sample_interval_minutes=request.sample_interval_minutes,
                benchmark_symbol=request.benchmark_symbol,
            )

            if not result:
                raise ConnectError(
                    Code.NOT_FOUND,
                    f"Strategy execution {execution_id} not found",
                )

            return portfolio_pb2.GetStrategyEquityCurveResponse(
                equity_curve=list(result.equity_curve),
                benchmark=result.benchmark,
                period_returns=result.period_returns,
            )
