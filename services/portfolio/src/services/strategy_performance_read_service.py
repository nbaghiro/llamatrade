"""Ledger-backed strategy performance.

Derives per-strategy performance from the strategy **sleeve** projection (current
value, positions, realized P&L) and its ``SleeveSnapshot`` equity series (returns,
risk metrics), mapping the results straight to proto (``src.proto_mappers``) —
proto is the canonical read shape and money stays ``Decimal``.

Strategy identity (name/mode/status/started_at) comes from ``StrategyExecution``;
``execution.mode``/``status`` are already proto-int (TypeDecorator) so they flow
to the proto enum fields with no string round-trip. ``execution.sleeve_id``/
``account_id`` (set when the sleeve is funded) link the execution to its ledger
sleeve.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from llamatrade_db.models.ledger import SleeveSnapshot
from llamatrade_db.models.strategy import StrategyExecution
from llamatrade_proto.generated import portfolio_pb2

from src.ledger import analytics, read_model
from src.ledger.projection import AccountProjection, SleeveProjection
from src.ledger.projector import LedgerProjector
from src.ports import PriceProvider
from src.proto_mappers import (
    benchmark_series_to_proto,
    equity_point_to_proto,
    live_metrics_to_proto,
    period_returns_to_proto,
    strategy_summary_to_proto,
)
from src.services.read_context import AccountProjectionCache, LedgerReadBase, PriceCache
from src.services.strategy_performance_service import (
    BookTotals,
    EquityCurveResult,
    ListPerformanceFilters,
    ListPerformanceResult,
    StrategyPerformanceDetail,
)

HUNDRED = Decimal("100")

ZERO = Decimal("0")

# Window (days) for each period-return key; YTD/ALL handled separately.
_PERIOD_DAYS: dict[str, int] = {
    "return_1d": 1,
    "return_1w": 7,
    "return_1m": 30,
    "return_3m": 90,
    "return_6m": 180,
    "return_1y": 365,
}


def _to_daily(series: list[tuple[datetime, Decimal]]) -> list[tuple[date, Decimal]]:
    """Collapse an intraday equity series to one point per day (last per day).

    Snapshots are taken ~hourly, but the annualized metrics use daily math
    (sqrt(252)); feeding the raw intraday series over-annualizes volatility and
    Sharpe. Collapsing to a daily grid (as the account read path does) makes the
    annualization correct.
    """
    by_day: dict[date, tuple[datetime, Decimal]] = {}
    for ts, eq in series:
        d = ts.date()
        prev = by_day.get(d)
        if prev is None or ts >= prev[0]:
            by_day[d] = (ts, eq)
    return [(d, by_day[d][1]) for d in sorted(by_day)]


class StrategyPerformanceReadService(LedgerReadBase):
    """Per-strategy performance derived from the ledger sleeve + snapshots."""

    def __init__(
        self,
        db: AsyncSession,
        market_data: PriceProvider | None = None,
        projections: AccountProjectionCache | None = None,
        prices: PriceCache | None = None,
    ) -> None:
        super().__init__(LedgerProjector(db), projections)
        self.db = db
        self.market_data = market_data
        self._price_cache = prices or PriceCache(market_data)

    async def list_strategy_performance(
        self,
        tenant_id: UUID,
        filters: ListPerformanceFilters | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ListPerformanceResult:
        stmt = (
            select(StrategyExecution)
            .options(joinedload(StrategyExecution.strategy))
            .where(StrategyExecution.tenant_id == tenant_id)
        )
        if filters:
            if filters.mode:
                stmt = stmt.where(StrategyExecution.mode == filters.mode)
            if filters.status:
                stmt = stmt.where(StrategyExecution.status == filters.status)

        total = (
            await self.db.execute(select(func.count()).select_from(stmt.subquery()))
        ).scalar() or 0

        stmt = (
            stmt.order_by(StrategyExecution.started_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        executions = (await self.db.execute(stmt)).unique().scalars().all()

        # Pre-warm the shared caches: fold each distinct account once and price the union of held symbols in one fetch, so per-strategy summaries hit the cache instead of folding/fetching per strategy.
        symbols: set[str] = set()
        for execution in executions:
            if execution.sleeve_id is None or execution.account_id is None:
                continue
            projection = await self._project(tenant_id, execution.account_id)
            sleeve = projection.sleeves.get(str(execution.sleeve_id))
            if sleeve is not None:
                symbols.update(sleeve.positions)
        if symbols:
            await self._price_cache.get(sorted(symbols))

        total_allocated = ZERO
        total_current = ZERO
        summaries: list[portfolio_pb2.StrategyPerformanceSummary] = []
        for execution in executions:
            summary = await self._summary(tenant_id, execution)
            summaries.append(summary)
            total_allocated += Decimal(summary.allocated_capital.value)
            total_current += Decimal(summary.current_value.value)

        combined = (
            (total_current - total_allocated) / total_allocated if total_allocated > 0 else None
        )
        return ListPerformanceResult(
            strategies=summaries,
            total_allocated=total_allocated,
            total_current_value=total_current,
            combined_return=combined,
            total=total,
        )

    async def get_strategy_performance(
        self, tenant_id: UUID, execution_id: UUID
    ) -> StrategyPerformanceDetail | None:
        execution = await self._execution(tenant_id, execution_id)
        if execution is None:
            return None
        sleeve_proj, prices = await self._sleeve_state(tenant_id, execution)
        metrics = await self._live_metrics(tenant_id, execution, sleeve_proj)
        positions = self._positions(sleeve_proj, prices) if sleeve_proj else []
        return StrategyPerformanceDetail(
            summary=await self._summary(tenant_id, execution),
            metrics=metrics,
            positions=positions,
        )

    async def get_strategy_equity_curve(
        self,
        tenant_id: UUID,
        execution_id: UUID,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        sample_interval_minutes: int = 0,
        benchmark_symbol: str = "",
    ) -> EquityCurveResult | None:
        execution = await self._execution(tenant_id, execution_id)
        if execution is None:
            return None
        series = await self._sleeve_series(tenant_id, execution.sleeve_id, start_time, end_time)
        equity_curve = [equity_point_to_proto(timestamp=ts, equity=eq) for ts, eq in series]
        benchmark = None
        if benchmark_symbol and self.market_data is not None and series:
            benchmark = await self._benchmark(benchmark_symbol, series)
        return EquityCurveResult(
            equity_curve=equity_curve,
            benchmark=benchmark,
            period_returns=self._period_returns([(t, e) for t, e in series]),
        )

    async def _benchmark(
        self, symbol: str, series: list[tuple[datetime, Decimal]]
    ) -> portfolio_pb2.BenchmarkData | None:
        """Benchmark equity series aligned to the sleeve curve, rebased to its start.

        Marks each curve point with the benchmark's close as-of that date (last
        close on/before the day, robust to weekend gaps), scaled so the benchmark
        starts at the strategy's starting equity — the same close feed used to
        mark positions, so the "vs SPY" line shares the strategy's axis.
        """
        assert self.market_data is not None
        start, end = series[0][0], series[-1][0]
        closes = await self.market_data.get_daily_closes(symbol, start, end + timedelta(days=1))
        if not closes:
            return None
        sorted_dates = sorted(closes)

        def as_of(day: date) -> float:
            chosen: date | None = None
            for cd in sorted_dates:
                if cd <= day:
                    chosen = cd
                else:
                    break
            return closes[chosen] if chosen is not None else closes[sorted_dates[0]]

        base_close = as_of(start.date())
        if not base_close:
            return None
        base_equity = float(series[0][1])
        points = [
            equity_point_to_proto(
                timestamp=ts,
                equity=Decimal(str(base_equity * as_of(ts.date()) / base_close)),
            )
            for ts, _ in series
        ]
        total_return = Decimal(str((as_of(end.date()) / base_close - 1) * 100))
        return benchmark_series_to_proto(symbol=symbol, points=points, total_return=total_return)

    async def book_totals(self, tenant_id: UUID) -> BookTotals:
        """Aggregate day/total return across the tenant's strategy sleeves.

        The account summary folds in non-strategy sleeves (idle cash, manual
        trades); this returns the strategy-only figures the UI's strategy rows
        weight-sum to, so ``ListPortfolios`` reconciles with ``ListStrategyPerformance``
        on a single basis. Day P&L uses the same ``current_value × return_1d``
        the client renders, so the header equals the sum of the rows exactly.
        """
        result = await self.list_strategy_performance(tenant_id, page=1, page_size=1000)
        day_pnl = ZERO
        for s in result.strategies:
            day_pnl += Decimal(s.current_value.value) * Decimal(s.returns.return_1d.value) / HUNDRED
        total_return = result.total_current_value - result.total_allocated
        prior = result.total_current_value - day_pnl
        return BookTotals(
            day_pnl=day_pnl,
            day_pnl_percent=(day_pnl / prior * HUNDRED) if prior else ZERO,
            total_return=total_return,
            total_return_percent=(
                result.combined_return * HUNDRED if result.combined_return is not None else ZERO
            ),
            has_strategies=bool(result.strategies) and result.total_allocated > 0,
        )

    async def _execution(self, tenant_id: UUID, execution_id: UUID) -> StrategyExecution | None:
        stmt = (
            select(StrategyExecution)
            .options(joinedload(StrategyExecution.strategy))
            .where(StrategyExecution.id == execution_id)
            .where(StrategyExecution.tenant_id == tenant_id)
        )
        return (await self.db.execute(stmt)).unique().scalar_one_or_none()

    async def _sleeve_state(
        self, tenant_id: UUID, execution: StrategyExecution
    ) -> tuple[SleeveProjection | None, dict[str, Decimal]]:
        if execution.sleeve_id is None or execution.account_id is None:
            return None, {}
        projection = await self._project(tenant_id, execution.account_id)
        sleeve = projection.sleeves.get(str(execution.sleeve_id))
        if sleeve is None:
            return None, {}
        symbols = sorted(sleeve.positions)
        prices = await self._price_cache.get(symbols) if symbols else {}
        return sleeve, prices

    async def _summary(
        self, tenant_id: UUID, execution: StrategyExecution
    ) -> portfolio_pb2.StrategyPerformanceSummary:
        sleeve, prices = await self._sleeve_state(tenant_id, execution)
        if sleeve is not None:
            from src.ledger.performance import sleeve_pnl

            marked = sleeve_pnl(str(execution.sleeve_id), sleeve, prices)
            current_value: Decimal | None = marked.equity
            positions_count = sum(1 for p in sleeve.positions.values() if p.qty != ZERO)
        else:
            # Unfunded execution: no sleeve to mark; live value/position count are not tracked off-ledger.
            current_value = None
            positions_count = 0

        series = await self._sleeve_series(tenant_id, execution.sleeve_id, None, None)
        returns = self._period_returns([(t, e) for t, e in series])

        return strategy_summary_to_proto(
            execution_id=execution.id,
            strategy_id=execution.strategy_id,
            strategy_name=execution.strategy.name if execution.strategy else "Unknown",
            mode=execution.mode,
            status=execution.status,
            color=execution.color,
            allocated_capital=execution.allocated_capital,
            current_value=current_value,
            positions_count=positions_count,
            returns=returns,
            started_at=execution.started_at,
            updated_at=execution.updated_at,
        )

    async def _live_metrics(
        self,
        tenant_id: UUID,
        execution: StrategyExecution,
        sleeve: SleeveProjection | None,
    ) -> portfolio_pb2.StrategyLiveMetrics:
        series = await self._sleeve_series(tenant_id, execution.sleeve_id, None, None)
        # Collapse to a daily grid so sqrt(252) annualization is correct on the ~hourly snapshot cadence (matches the account read path).
        equities = np.array([float(e) for _, e in _to_daily(series)], dtype=np.float64)
        # Numpy is CPU-bound — run it off the event loop (see portfolio_read_service).
        m = (
            await asyncio.to_thread(analytics.equity_metrics, equities)
            if len(equities) >= 2
            else None
        )

        # Trade stats from the sleeve's realized sells.
        stats = read_model.TradeStats(0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0)
        if execution.sleeve_id is not None and execution.account_id is not None:
            events = await self._projector.read_events(tenant_id, execution.account_id)
            stats = read_model.sleeve_trade_stats(events, str(execution.sleeve_id))

        current_equity = Decimal(str(equities[-1])) if len(equities) else None
        peak_equity = Decimal(str(float(np.max(equities)))) if len(equities) else None
        current_dd = None
        if len(equities):
            peak = float(np.max(equities))
            current_dd = Decimal(str((peak - float(equities[-1])) / peak * 100)) if peak else None

        return live_metrics_to_proto(
            m,
            stats,
            starting_capital=execution.allocated_capital,
            current_equity=current_equity,
            peak_equity=peak_equity,
            current_drawdown=current_dd,
        )

    def _positions(
        self, sleeve: SleeveProjection, prices: dict[str, Decimal]
    ) -> list[read_model.PositionView]:
        """The sleeve's open positions, marked via the shared portfolio read path."""
        account = AccountProjection(sleeves={"sleeve": sleeve})
        return read_model.aggregate_positions([account], prices)

    async def _sleeve_series(
        self,
        tenant_id: UUID,
        sleeve_id: UUID | None,
        start_time: datetime | None,
        end_time: datetime | None,
    ) -> list[tuple[datetime, Decimal]]:
        """The sleeve's equity time series from its snapshots (oldest-first).

        One point per ledger sequence, keeping the latest row written at that
        sequence — the same last-write-wins collapse the account curve applies
        per day. Repeats at one sequence are not curve movement, and counting
        them inflates period returns, volatility and Sharpe.
        """
        if sleeve_id is None:
            return []
        stmt = (
            select(SleeveSnapshot)
            .where(SleeveSnapshot.tenant_id == tenant_id)
            .where(SleeveSnapshot.sleeve_id == sleeve_id)
            .order_by(SleeveSnapshot.created_at)
        )
        # Filter the window in SQL rather than scanning every row in Python.
        if start_time is not None:
            stmt = stmt.where(SleeveSnapshot.created_at >= start_time)
        if end_time is not None:
            stmt = stmt.where(SleeveSnapshot.created_at <= end_time)
        rows = (await self.db.scalars(stmt)).all()
        by_sequence: dict[int, tuple[datetime, Decimal]] = {}
        for snap in rows:
            ts: datetime = snap.created_at
            previous = by_sequence.get(snap.as_of_sequence)
            if previous is None or ts >= previous[0]:
                by_sequence[snap.as_of_sequence] = (ts, snap.equity)
        return [by_sequence[seq] for seq in sorted(by_sequence)]

    def _period_returns(
        self, series: list[tuple[datetime, Decimal]]
    ) -> portfolio_pb2.StrategyPeriodReturns:
        """Compute standard period returns from an equity series (latest vs window start)."""
        if len(series) < 2:
            return period_returns_to_proto({})
        latest_ts, latest_eq = series[-1]
        kwargs: dict[str, Decimal] = {}
        # Day-return baseline: last snapshot on a PRIOR calendar day, not a rolling 24h window (else weekend gaps read as 0).
        prior_day = next((eq for ts, eq in reversed(series) if ts.date() < latest_ts.date()), None)
        if prior_day is not None and prior_day != 0:
            kwargs["return_1d"] = (latest_eq - prior_day) / prior_day * 100
        for key, days in _PERIOD_DAYS.items():
            if key == "return_1d":
                continue
            cutoff = latest_ts - timedelta(days=days)
            base = next((eq for ts, eq in series if ts >= cutoff), None)
            if base is not None and base != 0:
                kwargs[key] = (latest_eq - base) / base * 100
        # YTD
        ytd_cutoff = datetime(latest_ts.year, 1, 1, tzinfo=latest_ts.tzinfo)
        ytd_base = next((eq for ts, eq in series if ts >= ytd_cutoff), None)
        if ytd_base:
            kwargs["return_ytd"] = (latest_eq - ytd_base) / ytd_base * 100
        # ALL
        first_eq = series[0][1]
        if first_eq:
            kwargs["return_all"] = (latest_eq - first_eq) / first_eq * 100
        return period_returns_to_proto(kwargs)
