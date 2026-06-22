"""Ledger-backed strategy performance.

Drop-in replacement for ``StrategyPerformanceService``'s read methods, deriving
per-strategy performance from the strategy **sleeve** projection (current value,
positions, realized P&L) and its ``SleeveSnapshot`` equity series (returns,
risk metrics) — instead of the unpopulated ``StrategyPerformance{Metrics,
Snapshot}`` tables. Returns the same response schemas so the servicer's proto
mappers are unchanged.

Strategy identity (name/mode/status/started_at) still comes from
``StrategyExecution``; ``execution.sleeve_id``/``account_id`` (set when the
sleeve is funded) link the execution to its ledger sleeve.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from llamatrade_db.models.ledger import SleeveSnapshot
from llamatrade_db.models.strategy import StrategyExecution

from src.ledger import analytics, read_model
from src.ledger.projection import SleeveProjection
from src.ledger.projector import LedgerProjector
from src.ports import PriceProvider
from src.services.strategy_performance_service import (
    EquityCurveResult,
    EquityPoint,
    ListPerformanceFilters,
    ListPerformanceResult,
    LiveMetrics,
    PeriodReturns,
    PositionSummary,
    StrategyPerformanceDetail,
    StrategyPerformanceSummary,
    execution_mode_to_str,
    execution_status_to_str,
)

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


class StrategyPerformanceReadService:
    """Per-strategy performance derived from the ledger sleeve + snapshots."""

    def __init__(self, db: AsyncSession, market_data: PriceProvider | None = None) -> None:
        self.db = db
        self.market_data = market_data
        self._projector = LedgerProjector(db)

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

        total_allocated = ZERO
        total_current = ZERO
        summaries: list[StrategyPerformanceSummary] = []
        for execution in executions:
            summary = await self._summary(tenant_id, execution)
            summaries.append(summary)
            total_allocated += summary.allocated_capital or ZERO
            total_current += summary.current_value or ZERO

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
    ) -> EquityCurveResult | None:
        execution = await self._execution(tenant_id, execution_id)
        if execution is None:
            return None
        series = await self._sleeve_series(tenant_id, execution.sleeve_id, start_time, end_time)
        equity_curve = [
            EquityPoint(timestamp=ts, equity=eq, return_percent=None, drawdown=None)
            for ts, eq in series
        ]
        return EquityCurveResult(
            equity_curve=equity_curve,
            period_returns=self._period_returns([(t, float(e)) for t, e in series]),
        )

    # ----------------------------------------------------------------- helpers

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
        projection = await self._projector.project_account(tenant_id, execution.account_id)
        sleeve = projection.sleeves.get(str(execution.sleeve_id))
        if sleeve is None:
            return None, {}
        symbols = sorted(sleeve.positions)
        prices: dict[str, Decimal] = {}
        if symbols and self.market_data is not None:
            prices = await self.market_data.get_prices(symbols)
        return sleeve, prices

    async def _summary(
        self, tenant_id: UUID, execution: StrategyExecution
    ) -> StrategyPerformanceSummary:
        sleeve, prices = await self._sleeve_state(tenant_id, execution)
        if sleeve is not None:
            from src.ledger.performance import sleeve_pnl

            marked = sleeve_pnl(str(execution.sleeve_id), sleeve, prices)
            current_value: Decimal | None = marked.equity
            positions_count = sum(1 for p in sleeve.positions.values() if p.qty != ZERO)
        else:
            # Unfunded execution: no sleeve to mark; live value/position count are
            # not tracked off-ledger.
            current_value = None
            positions_count = 0

        series = await self._sleeve_series(tenant_id, execution.sleeve_id, None, None)
        returns = self._period_returns([(t, float(e)) for t, e in series])

        return StrategyPerformanceSummary(
            execution_id=execution.id,
            strategy_id=execution.strategy_id,
            strategy_name=execution.strategy.name if execution.strategy else "Unknown",
            mode=execution_mode_to_str(execution.mode),
            status=execution_status_to_str(execution.status),
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
    ) -> LiveMetrics:
        series = await self._sleeve_series(tenant_id, execution.sleeve_id, None, None)
        equities = np.array([float(e) for _, e in series], dtype=np.float64)
        # Numpy is CPU-bound — run it off the event loop (see portfolio_read_service).
        m = await asyncio.to_thread(analytics.equity_metrics, equities) if len(equities) >= 2 else None

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

        return LiveMetrics(
            sharpe_ratio=Decimal(str(m.sharpe_ratio)) if m else None,
            sortino_ratio=Decimal(str(m.sortino_ratio)) if m else None,
            max_drawdown=Decimal(str(m.max_drawdown)) if m else None,
            current_drawdown=current_dd,
            volatility=Decimal(str(m.volatility)) if m else None,
            total_trades=stats.total_trades,
            winning_trades=stats.winning_trades,
            losing_trades=stats.losing_trades,
            win_rate=Decimal(str(stats.win_rate)),
            profit_factor=Decimal(str(stats.profit_factor)),
            average_win=Decimal(str(stats.average_win)),
            average_loss=Decimal(str(stats.average_loss)),
            starting_capital=execution.allocated_capital,
            current_equity=current_equity,
            peak_equity=peak_equity,
            total_pnl=Decimal(str(stats.realized_pnl)),
            calculated_at=datetime.now(UTC),
        )

    def _positions(
        self, sleeve: SleeveProjection, prices: dict[str, Decimal]
    ) -> list[PositionSummary]:
        out: list[PositionSummary] = []
        for symbol, pos in sorted(sleeve.positions.items()):
            if pos.qty == ZERO:
                continue
            avg = pos.cost_basis / pos.qty
            price = prices.get(symbol)
            market_value = pos.qty * price if price is not None else pos.cost_basis
            unrealized = market_value - pos.cost_basis
            upct = (unrealized / pos.cost_basis * 100) if pos.cost_basis else ZERO
            out.append(
                PositionSummary(
                    symbol=symbol,
                    qty=pos.qty,
                    avg_entry_price=avg,
                    current_price=price,
                    market_value=market_value,
                    unrealized_pnl=unrealized,
                    unrealized_pnl_percent=upct,
                )
            )
        return out

    async def _sleeve_series(
        self,
        tenant_id: UUID,
        sleeve_id: UUID | None,
        start_time: datetime | None,
        end_time: datetime | None,
    ) -> list[tuple[datetime, Decimal]]:
        """The sleeve's equity time series from its snapshots (oldest-first)."""
        if sleeve_id is None:
            return []
        stmt = (
            select(SleeveSnapshot)
            .where(SleeveSnapshot.tenant_id == tenant_id)
            .where(SleeveSnapshot.sleeve_id == sleeve_id)
            .order_by(SleeveSnapshot.created_at)
        )
        rows = (await self.db.scalars(stmt)).all()
        out: list[tuple[datetime, Decimal]] = []
        for snap in rows:
            ts: datetime = snap.created_at
            if start_time and ts < start_time:
                continue
            if end_time and ts > end_time:
                continue
            out.append((ts, snap.equity))
        return out

    def _period_returns(self, series: list[tuple[datetime, float]]) -> PeriodReturns:
        """Compute standard period returns from an equity series (latest vs window start)."""
        if len(series) < 2:
            return PeriodReturns()
        latest_ts, latest_eq = series[-1]
        kwargs: dict[str, Decimal] = {}
        for key, days in _PERIOD_DAYS.items():
            cutoff = latest_ts - timedelta(days=days)
            base = next((eq for ts, eq in series if ts >= cutoff), None)
            if base is not None and base != 0:
                kwargs[key] = Decimal(str((latest_eq - base) / base * 100))
        # YTD
        ytd_cutoff = datetime(latest_ts.year, 1, 1, tzinfo=latest_ts.tzinfo)
        ytd_base = next((eq for ts, eq in series if ts >= ytd_cutoff), None)
        if ytd_base:
            kwargs["return_ytd"] = Decimal(str((latest_eq - ytd_base) / ytd_base * 100))
        # ALL
        first_eq = series[0][1]
        if first_eq:
            kwargs["return_all"] = Decimal(str((latest_eq - first_eq) / first_eq * 100))
        return PeriodReturns(**kwargs)
