"""Ledger-backed portfolio reads.

Reads derive from folding the event log (a tenant may own several accounts, one
per broker credential set; every read aggregates across all of them) and map the
read-model views straight to proto (``src.proto_mappers``) — proto is the
canonical read shape and money stays ``Decimal`` end-to-end. Balances/
positions come from the projection; the performance curve from ``SleeveSnapshot``
rows.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models.ledger import Account, Sleeve, SleeveSnapshot
from llamatrade_proto.generated import common_pb2, portfolio_pb2

from src.ledger import read_model
from src.ledger.analytics import benchmark_metrics, equity_metrics
from src.ledger.projection import AccountProjection
from src.ledger.projector import LedgerProjector
from src.metrics import record_projection_read
from src.ports import PriceProvider
from src.proto_mappers import TXN_TYPE_TO_PROTO, transaction_view_to_proto
from src.services.read_context import AccountProjectionCache, LedgerReadBase, PriceCache


def _dec(value: Decimal | float | int) -> common_pb2.Decimal:
    return common_pb2.Decimal(value=str(value))


def _performance_metrics_proto(
    *,
    total_return: float = 0.0,
    ytd: float = 0.0,
    mtd: float = 0.0,
    wtd: float = 0.0,
    volatility: float = 0.0,
    sharpe: float = 0.0,
    max_drawdown: float = 0.0,
    beta: float = 0.0,
    benchmark_return: float = 0.0,
    alpha: float = 0.0,
) -> portfolio_pb2.PerformanceMetrics:
    """Assemble the proto metrics; ``total_positions`` is filled by the servicer."""
    return portfolio_pb2.PerformanceMetrics(
        total_return=_dec(total_return),
        ytd_return=_dec(ytd),
        mtd_return=_dec(mtd),
        wtd_return=_dec(wtd),
        volatility=_dec(volatility),
        sharpe_ratio=_dec(sharpe),
        max_drawdown=_dec(max_drawdown),
        beta=_dec(beta),
        benchmark_return=_dec(benchmark_return),
        alpha=_dec(alpha),
    )


class PortfolioReadService(LedgerReadBase):
    """Portfolio/performance/transaction reads derived from the ledger."""

    def __init__(
        self,
        db: AsyncSession,
        market_data: PriceProvider | None = None,
        benchmark_symbol: str = "SPY",
        projections: AccountProjectionCache | None = None,
        prices: PriceCache | None = None,
    ) -> None:
        super().__init__(LedgerProjector(db), projections)
        self.db = db
        self.market_data = market_data
        self._benchmark_symbol = benchmark_symbol
        self._price_cache = prices or PriceCache(market_data)

    async def get_summary(self, tenant_id: UUID) -> read_model.SummaryView:
        projections = await self._projections(tenant_id)
        prices = await self._prices(projections)
        prior = await self._prior_equity(tenant_id)
        return read_model.portfolio_summary(projections, prices, prior_equity=prior)

    async def list_positions(self, tenant_id: UUID) -> list[read_model.PositionView]:
        projections = await self._projections(tenant_id)
        prices = await self._prices(projections)
        return read_model.aggregate_positions(projections, prices)

    async def get_position(self, tenant_id: UUID, symbol: str) -> read_model.PositionView | None:
        symbol_upper = symbol.upper()
        for pos in await self.list_positions(tenant_id):
            if pos.symbol == symbol_upper:
                return pos
        return None

    async def list_transactions(
        self,
        tenant_id: UUID,
        type: int | None,
        symbol: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[portfolio_pb2.Transaction], int]:
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
            views = [v for v in views if TXN_TYPE_TO_PROTO.get(v.type) == type]

        total = len(views)
        start = (page - 1) * page_size
        page_views = views[start : start + page_size]
        sleeve_names = await self._sleeve_names({v.sleeve_id for v in page_views if v.sleeve_id})
        transactions = [
            transaction_view_to_proto(
                v,
                tenant_id=tenant_id,
                description=sleeve_names.get(v.sleeve_id, "") if v.sleeve_id else "",
            )
            for v in page_views
        ]
        return transactions, total

    async def _sleeve_names(self, sleeve_ids: set[str]) -> dict[str, str]:
        """Map sleeve id -> human name, so allocation rows can name their strategy."""
        if not sleeve_ids:
            return {}
        rows = await self.db.execute(
            select(Sleeve.id, Sleeve.name).where(Sleeve.id.in_({UUID(s) for s in sleeve_ids}))
        )
        return {str(sid): name for sid, name in rows.all()}

    async def get_metrics(self, tenant_id: UUID, period: str) -> portfolio_pb2.PerformanceMetrics:
        start_date, end_date = _period_dates(period)
        series = await self._daily_equity_series(tenant_id, start_date, end_date)
        if len(series) < 2:
            return _performance_metrics_proto()

        dates = [d for d, _ in series]
        equities = np.array([e for _, e in series], dtype=np.float64)
        # Numpy is CPU-bound; keep it off the event loop so concurrent reads don't stall on a large series.
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

        ytd, mtd, wtd = await self._period_returns(tenant_id)
        return _performance_metrics_proto(
            total_return=m.total_return,
            ytd=ytd,
            mtd=mtd,
            wtd=wtd,
            volatility=m.volatility,
            sharpe=m.sharpe_ratio,
            max_drawdown=m.max_drawdown,
            beta=beta,
            benchmark_return=benchmark_return,
            alpha=alpha,
        )

    async def _period_returns(self, tenant_id: UUID) -> tuple[float, float, float]:
        """YTD / MTD / WTD account returns (%) from the daily equity series.

        Each baseline is the first equity point on or after the period boundary;
        return = (latest - baseline) / baseline * 100.
        """
        today = datetime.now(UTC).date()
        year_start = today.replace(month=1, day=1)
        month_start = today.replace(day=1)
        week_start = today - timedelta(days=today.weekday())
        series = await self._daily_equity_series(tenant_id, year_start, today)
        if len(series) < 2:
            return 0.0, 0.0, 0.0
        latest = series[-1][1]

        def _ret(boundary: date) -> float:
            base = next((eq for d, eq in series if d >= boundary), None)
            if not base:
                return 0.0
            return float((latest - base) / base * 100)  # feeds the numpy analytics model

        return _ret(year_start), _ret(month_start), _ret(week_start)

    async def _accounts(self, tenant_id: UUID) -> list[Account]:
        result = await self.db.scalars(select(Account).where(Account.tenant_id == tenant_id))
        return list(result.all())

    async def _projections(self, tenant_id: UUID) -> list[AccountProjection]:
        projections: list[AccountProjection] = []
        for account in await self._accounts(tenant_id):
            projection = await self._project(tenant_id, account.id)
            # Degraded (poison-skipped) projections are served, never silently.
            record_projection_read(account.id, projection.poison_events)
            projections.append(projection)
        return projections

    async def _prices(self, projections: list[AccountProjection]) -> dict[str, Decimal]:
        symbols = sorted(
            {sym for proj in projections for s in proj.sleeves.values() for sym in s.positions}
        )
        if not symbols:
            return {}
        return await self._price_cache.get(symbols)

    async def _daily_equity_series(
        self, tenant_id: UUID, start_date: date, end_date: date
    ) -> list[tuple[date, Decimal]]:
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
            (d, sum((eq for _, eq in sleeves.values()), Decimal("0")))
            for d, sleeves in sorted(by_day.items())
        ]

    async def _prior_equity(self, tenant_id: UUID) -> Decimal | None:
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
