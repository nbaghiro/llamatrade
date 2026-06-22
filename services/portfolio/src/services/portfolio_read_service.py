"""Ledger-backed portfolio reads.

Drop-in replacement for the legacy ``PortfolioService`` + ``PerformanceService``
+ ``TransactionService`` read methods, returning the SAME response schemas
(``src.models``) so the Connect servicer's proto mappers are unchanged.

A tenant may own several accounts (one per broker credential set); every read
aggregates across all of them. Balances/positions derive from folding the event
log; the performance curve derives from ``SleeveSnapshot`` rows.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models.ledger import Account, SleeveSnapshot
from llamatrade_proto.generated.portfolio_pb2 import (
    TRANSACTION_TYPE_BUY,
    TRANSACTION_TYPE_DEPOSIT,
    TRANSACTION_TYPE_DIVIDEND,
    TRANSACTION_TYPE_FEE,
    TRANSACTION_TYPE_INTEREST,
    TRANSACTION_TYPE_SELL,
    TRANSACTION_TYPE_TRANSFER_IN,
    TRANSACTION_TYPE_TRANSFER_OUT,
    TRANSACTION_TYPE_WITHDRAWAL,
)

from src.ledger import read_model
from src.ledger.analytics import benchmark_metrics, equity_metrics
from src.ledger.projection import AccountProjection
from src.ledger.projector import LedgerProjector
from src.models import (
    PerformanceMetrics,
    PortfolioSummary,
    PositionResponse,
    TransactionResponse,
)
from src.ports import PriceProvider

_TXN_TYPE_TO_PROTO: dict[str, int] = {
    "buy": TRANSACTION_TYPE_BUY,
    "sell": TRANSACTION_TYPE_SELL,
    "deposit": TRANSACTION_TYPE_DEPOSIT,
    "withdrawal": TRANSACTION_TYPE_WITHDRAWAL,
    "dividend": TRANSACTION_TYPE_DIVIDEND,
    "interest": TRANSACTION_TYPE_INTEREST,
    "fee": TRANSACTION_TYPE_FEE,
    "transfer_in": TRANSACTION_TYPE_TRANSFER_IN,
    "transfer_out": TRANSACTION_TYPE_TRANSFER_OUT,
}


class PortfolioReadService:
    """Portfolio/performance/transaction reads derived from the ledger."""

    def __init__(
        self,
        db: AsyncSession,
        market_data: PriceProvider | None = None,
        benchmark_symbol: str = "SPY",
    ) -> None:
        self.db = db
        self.market_data = market_data
        self._benchmark_symbol = benchmark_symbol
        self._projector = LedgerProjector(db)

    # ----------------------------------------------------------- summary/positions

    async def get_summary(self, tenant_id: UUID) -> PortfolioSummary:
        projections = await self._projections(tenant_id)
        prices = await self._prices(projections)
        prior = await self._prior_equity(tenant_id)
        view = read_model.portfolio_summary(projections, prices, prior_equity=prior)
        return PortfolioSummary(
            total_equity=view.total_equity,
            cash=view.cash,
            market_value=view.market_value,
            total_unrealized_pnl=view.total_unrealized_pnl,
            total_realized_pnl=view.total_realized_pnl,
            day_pnl=view.day_pnl,
            day_pnl_percent=view.day_pnl_percent,
            total_pnl_percent=view.total_pnl_percent,
            positions_count=view.positions_count,
            updated_at=datetime.now(UTC),
        )

    async def list_positions(self, tenant_id: UUID) -> list[PositionResponse]:
        projections = await self._projections(tenant_id)
        prices = await self._prices(projections)
        return [
            PositionResponse(
                symbol=p.symbol,
                qty=p.qty,
                side=p.side,
                cost_basis=p.cost_basis,
                market_value=p.market_value,
                unrealized_pnl=p.unrealized_pnl,
                unrealized_pnl_percent=p.unrealized_pnl_percent,
                current_price=p.current_price,
                avg_entry_price=p.avg_entry_price,
            )
            for p in read_model.aggregate_positions(projections, prices)
        ]

    async def get_position(self, tenant_id: UUID, symbol: str) -> PositionResponse | None:
        symbol_upper = symbol.upper()
        for pos in await self.list_positions(tenant_id):
            if pos.symbol == symbol_upper:
                return pos
        return None

    # ----------------------------------------------------------------- transactions

    async def list_transactions(
        self,
        tenant_id: UUID,
        type: int | None,
        symbol: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[TransactionResponse], int]:
        accounts = await self._accounts(tenant_id)
        views: list[read_model.TransactionView] = []
        for account in accounts:
            events = await self._projector.read_events(tenant_id, account.id)
            views.extend(read_model.transactions_view(events))
        # newest-first across accounts
        views.sort(key=lambda v: (v.occurred_at is not None, v.occurred_at), reverse=True)

        if symbol:
            su = symbol.upper()
            views = [v for v in views if (v.symbol or "").upper() == su]
        if type:
            views = [v for v in views if _TXN_TYPE_TO_PROTO.get(v.type) == type]

        total = len(views)
        start = (page - 1) * page_size
        page_views = views[start : start + page_size]
        return [self._to_txn_response(tenant_id, v) for v in page_views], total

    def _to_txn_response(
        self, tenant_id: UUID, v: read_model.TransactionView
    ) -> TransactionResponse:
        created = v.occurred_at if isinstance(v.occurred_at, datetime) else datetime.now(UTC)
        try:
            txn_id = UUID(v.event_id)
        except ValueError:
            txn_id = UUID(int=0)
        return TransactionResponse(
            id=txn_id,
            tenant_id=tenant_id,
            type=_TXN_TYPE_TO_PROTO.get(v.type, TRANSACTION_TYPE_BUY),
            symbol=v.symbol,
            quantity=v.qty,
            price=v.price,
            amount=v.amount,
            fees=v.fees,
            description=None,
            reference_id=None,
            created_at=created,
        )

    # ------------------------------------------------------------------ performance

    async def get_metrics(self, tenant_id: UUID, period: str) -> PerformanceMetrics:
        start_date, end_date = _period_dates(period)
        series = await self._daily_equity_series(tenant_id, start_date, end_date)
        if len(series) < 2:
            return PerformanceMetrics(
                period=period,
                total_return=0.0,
                total_return_percent=0.0,
                annualized_return=0.0,
                volatility=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                max_drawdown=0.0,
                win_rate=0.0,
                profit_factor=0.0,
                best_day=0.0,
                worst_day=0.0,
                avg_daily_return=0.0,
            )

        dates = [d for d, _ in series]
        equities = np.array([e for _, e in series], dtype=np.float64)
        # Numpy is CPU-bound; keep it off the event loop so concurrent reads
        # don't stall on a large series.
        m = await asyncio.to_thread(equity_metrics, equities)

        beta, alpha, benchmark_return = 0.0, 0.0, 0.0
        if self.market_data is not None:
            bench_closes = await self.market_data.get_daily_closes(
                self._benchmark_symbol,
                datetime.combine(dates[0], time.min, tzinfo=UTC),
                datetime.combine(dates[-1] + timedelta(days=1), time.min, tzinfo=UTC),
            )
            beta, alpha, benchmark_return = await asyncio.to_thread(
                benchmark_metrics, dates, equities, bench_closes
            )

        return PerformanceMetrics(
            period=period,
            total_return=m.total_return,
            total_return_percent=m.total_return_percent,
            annualized_return=m.annualized_return,
            volatility=m.volatility,
            sharpe_ratio=m.sharpe_ratio,
            sortino_ratio=m.sortino_ratio,
            max_drawdown=m.max_drawdown,
            win_rate=m.win_rate,
            profit_factor=m.profit_factor,
            best_day=m.best_day,
            worst_day=m.worst_day,
            avg_daily_return=m.avg_daily_return,
            beta=beta,
            alpha=alpha,
            benchmark_return=benchmark_return,
        )

    # ----------------------------------------------------------------------- helpers

    async def _accounts(self, tenant_id: UUID) -> list[Account]:
        result = await self.db.scalars(select(Account).where(Account.tenant_id == tenant_id))
        return list(result.all())

    async def _projections(self, tenant_id: UUID) -> list[AccountProjection]:
        return [
            await self._projector.project_account(tenant_id, a.id)
            for a in await self._accounts(tenant_id)
        ]

    async def _prices(self, projections: list[AccountProjection]) -> dict[str, Decimal]:
        symbols = sorted(
            {sym for proj in projections for s in proj.sleeves.values() for sym in s.positions}
        )
        if not symbols or self.market_data is None:
            return {}
        return await self.market_data.get_prices(symbols)

    async def _daily_equity_series(
        self, tenant_id: UUID, start_date: date, end_date: date
    ) -> list[tuple[date, float]]:
        """Daily account equity from sleeve snapshots, summed across sleeves.

        For each day, take each sleeve's latest snapshot and sum them — yields
        one account-wide equity point per day (multi-account safe; SleeveSnapshot
        is tenant-scoped).
        """
        rows = await self.db.scalars(
            select(SleeveSnapshot)
            .where(SleeveSnapshot.tenant_id == tenant_id)
            .order_by(SleeveSnapshot.created_at)
        )
        # day -> sleeve_id -> (created_at, equity); last write per sleeve per day wins
        by_day: dict[date, dict[UUID, tuple[datetime, Decimal]]] = {}
        for snap in rows:
            created = snap.created_at
            d = created.date()
            if d < start_date or d > end_date:
                continue
            day = by_day.setdefault(d, {})
            prev = day.get(snap.sleeve_id)
            if prev is None or created >= prev[0]:
                day[snap.sleeve_id] = (created, snap.equity)
        return [
            (d, float(sum((eq for _, eq in sleeves.values()), Decimal("0"))))
            for d, sleeves in sorted(by_day.items())
        ]

    async def _prior_equity(self, tenant_id: UUID) -> float | None:
        """Yesterday-or-earlier account equity, for the day-P&L baseline."""
        today = datetime.now(UTC).date()
        series = await self._daily_equity_series(tenant_id, today - timedelta(days=7), today)
        prior = [eq for d, eq in series if d < today]
        return prior[-1] if prior else None


def _period_dates(period: str) -> tuple[date, date]:
    """Period string → (start_date, end_date). Mirrors the legacy mapping."""
    today = date.today()
    if period == "1D":
        return today - timedelta(days=1), today
    if period == "1W":
        return today - timedelta(weeks=1), today
    if period == "1M":
        return today - timedelta(days=30), today
    if period == "3M":
        return today - timedelta(days=90), today
    if period == "6M":
        return today - timedelta(days=180), today
    if period == "1Y":
        return today - timedelta(days=365), today
    if period == "YTD":
        return date(today.year, 1, 1), today
    return date(2000, 1, 1), today  # ALL
