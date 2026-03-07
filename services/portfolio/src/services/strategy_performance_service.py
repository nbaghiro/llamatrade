"""Strategy performance service for live trading metrics."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from llamatrade_db import get_db
from llamatrade_db.models.portfolio import (
    StrategyPerformanceMetrics,
    StrategyPerformanceSnapshot,
)
from llamatrade_db.models.strategy import StrategyExecution
from llamatrade_proto.generated.common_pb2 import (
    EXECUTION_MODE_LIVE,
    EXECUTION_MODE_PAPER,
    EXECUTION_STATUS_ERROR,
    EXECUTION_STATUS_PAUSED,
    EXECUTION_STATUS_PENDING,
    EXECUTION_STATUS_RUNNING,
    EXECUTION_STATUS_STOPPED,
)

# =============================================================================
# Proto int -> string conversion helpers
# =============================================================================

_EXECUTION_MODE_TO_STR: dict[int, str] = {
    EXECUTION_MODE_PAPER: "paper",
    EXECUTION_MODE_LIVE: "live",
}

_EXECUTION_STATUS_TO_STR: dict[int, str] = {
    EXECUTION_STATUS_PENDING: "pending",
    EXECUTION_STATUS_RUNNING: "running",
    EXECUTION_STATUS_PAUSED: "paused",
    EXECUTION_STATUS_STOPPED: "stopped",
    EXECUTION_STATUS_ERROR: "error",
}


def _execution_mode_to_str(value: int) -> str:
    """Convert ExecutionMode proto value to string."""
    return _EXECUTION_MODE_TO_STR.get(value, "paper")


def _execution_status_to_str(value: int) -> str:
    """Convert ExecutionStatus proto value to string."""
    return _EXECUTION_STATUS_TO_STR.get(value, "pending")


# =============================================================================
# PYDANTIC MODELS
# =============================================================================


class PeriodReturns(BaseModel):
    """Returns for various time periods."""

    return_1d: Decimal | None = None
    return_1w: Decimal | None = None
    return_1m: Decimal | None = None
    return_3m: Decimal | None = None
    return_6m: Decimal | None = None
    return_1y: Decimal | None = None
    return_ytd: Decimal | None = None
    return_all: Decimal | None = None


class StrategyPerformanceSummary(BaseModel):
    """Summary of a strategy's performance."""

    execution_id: UUID
    strategy_id: UUID
    strategy_name: str
    mode: str
    status: str
    color: str | None
    allocated_capital: Decimal | None
    current_value: Decimal | None
    positions_count: int
    returns: PeriodReturns
    started_at: datetime | None
    updated_at: datetime


class LiveMetrics(BaseModel):
    """Detailed live metrics for a strategy."""

    sharpe_ratio: Decimal | None = None
    sortino_ratio: Decimal | None = None
    calmar_ratio: Decimal | None = None
    max_drawdown: Decimal | None = None
    current_drawdown: Decimal | None = None
    volatility: Decimal | None = None
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: Decimal | None = None
    profit_factor: Decimal | None = None
    average_win: Decimal | None = None
    average_loss: Decimal | None = None
    starting_capital: Decimal | None = None
    current_equity: Decimal | None = None
    peak_equity: Decimal | None = None
    total_pnl: Decimal | None = None
    benchmark_symbol: str | None = None
    alpha: Decimal | None = None
    beta: Decimal | None = None
    correlation: Decimal | None = None
    calculated_at: datetime | None = None


class EquityPoint(BaseModel):
    """Point in equity curve time series."""

    timestamp: datetime
    equity: Decimal
    return_percent: Decimal | None = None
    drawdown: Decimal | None = None
    benchmark_value: Decimal | None = None


class PositionSummary(BaseModel):
    """Summary of an open position."""

    symbol: str
    qty: Decimal
    avg_entry_price: Decimal
    current_price: Decimal | None
    market_value: Decimal | None
    unrealized_pnl: Decimal | None
    unrealized_pnl_percent: Decimal | None


class StrategyPerformanceDetail(BaseModel):
    """Detailed performance for a single strategy."""

    summary: StrategyPerformanceSummary
    metrics: LiveMetrics
    positions: list[PositionSummary]


class ListPerformanceFilters(BaseModel):
    """Filters for listing strategy performance."""

    mode: int | None = None  # ExecutionMode proto value
    status: int | None = None  # ExecutionStatus proto value


class ListPerformanceResult(BaseModel):
    """Result of listing strategy performance."""

    strategies: list[StrategyPerformanceSummary]
    total_allocated: Decimal
    total_current_value: Decimal
    combined_return: Decimal | None
    total: int


class EquityCurveResult(BaseModel):
    """Equity curve data for a strategy."""

    equity_curve: list[EquityPoint]
    benchmark_symbol: str | None = None
    benchmark_return: Decimal | None = None
    period_returns: PeriodReturns


# =============================================================================
# SERVICE
# =============================================================================


class StrategyPerformanceService:
    """Service for strategy performance queries."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_strategy_performance(
        self,
        tenant_id: UUID,
        filters: ListPerformanceFilters | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ListPerformanceResult:
        """
        List all deployed strategies with performance summaries.

        Returns a list of strategy summaries with key metrics for the portfolio overview.
        """
        # Build query
        stmt = (
            select(StrategyExecution)
            .options(joinedload(StrategyExecution.strategy))
            .options(joinedload(StrategyExecution.performance_metrics))
            .where(StrategyExecution.tenant_id == tenant_id)
        )

        # Apply filters
        if filters:
            if filters.mode:
                stmt = stmt.where(StrategyExecution.mode == filters.mode)
            if filters.status:
                stmt = stmt.where(StrategyExecution.status == filters.status)

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0

        # Apply pagination and ordering
        stmt = stmt.order_by(StrategyExecution.started_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(stmt)
        executions = result.unique().scalars().all()

        # Calculate aggregates
        total_allocated = Decimal("0")
        total_current_value = Decimal("0")

        summaries: list[StrategyPerformanceSummary] = []
        for execution in executions:
            summary = self._to_summary(execution)
            summaries.append(summary)

            if execution.allocated_capital:
                total_allocated += execution.allocated_capital
            if execution.current_value:
                total_current_value += execution.current_value

        # Calculate combined return
        combined_return = None
        if total_allocated > 0:
            combined_return = (total_current_value - total_allocated) / total_allocated

        return ListPerformanceResult(
            strategies=summaries,
            total_allocated=total_allocated,
            total_current_value=total_current_value,
            combined_return=combined_return,
            total=total,
        )

    async def get_strategy_performance(
        self,
        tenant_id: UUID,
        execution_id: UUID,
    ) -> StrategyPerformanceDetail | None:
        """
        Get detailed performance for a single strategy.

        Includes summary, detailed metrics, and current positions.
        """
        # Get execution with related data
        stmt = (
            select(StrategyExecution)
            .options(joinedload(StrategyExecution.strategy))
            .options(joinedload(StrategyExecution.performance_metrics))
            .where(StrategyExecution.id == execution_id)
            .where(StrategyExecution.tenant_id == tenant_id)
        )

        result = await self.db.execute(stmt)
        execution = result.unique().scalar_one_or_none()

        if not execution:
            return None

        # Get positions for this execution
        # Note: In real implementation, positions would be linked to the execution
        # For now, we return an empty list as positions are tracked separately
        positions: list[PositionSummary] = []

        return StrategyPerformanceDetail(
            summary=self._to_summary(execution),
            metrics=self._to_metrics(execution.performance_metrics),
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
        """
        Get equity curve time series for a strategy.

        Optionally filtered by time range and downsampled.
        """
        # Verify execution exists and belongs to tenant
        exec_stmt = (
            select(StrategyExecution)
            .options(joinedload(StrategyExecution.performance_metrics))
            .where(StrategyExecution.id == execution_id)
            .where(StrategyExecution.tenant_id == tenant_id)
        )
        exec_result = await self.db.execute(exec_stmt)
        execution = exec_result.unique().scalar_one_or_none()

        if not execution:
            return None

        # Build snapshot query
        stmt = (
            select(StrategyPerformanceSnapshot)
            .where(StrategyPerformanceSnapshot.execution_id == execution_id)
            .where(StrategyPerformanceSnapshot.tenant_id == tenant_id)
        )

        if start_time:
            stmt = stmt.where(StrategyPerformanceSnapshot.snapshot_time >= start_time)
        if end_time:
            stmt = stmt.where(StrategyPerformanceSnapshot.snapshot_time <= end_time)

        stmt = stmt.order_by(StrategyPerformanceSnapshot.snapshot_time.asc())

        result = await self.db.execute(stmt)
        snapshots = result.scalars().all()

        # Convert to equity points
        equity_curve: list[EquityPoint] = []
        for snapshot in snapshots:
            equity_curve.append(
                EquityPoint(
                    timestamp=snapshot.snapshot_time,
                    equity=snapshot.equity,
                    return_percent=snapshot.cumulative_return,
                    drawdown=snapshot.drawdown,
                    benchmark_value=None,  # Benchmark not stored in snapshots
                )
            )

        # Downsample if requested
        if sample_interval_minutes > 0 and len(equity_curve) > 0:
            equity_curve = self._downsample_curve(equity_curve, sample_interval_minutes)

        # Get period returns from metrics
        period_returns = PeriodReturns()
        if execution.performance_metrics:
            metrics = execution.performance_metrics
            period_returns = PeriodReturns(
                return_1d=metrics.return_1d,
                return_1w=metrics.return_1w,
                return_1m=metrics.return_1m,
                return_3m=metrics.return_3m,
                return_6m=metrics.return_6m,
                return_1y=metrics.return_1y,
                return_ytd=metrics.return_ytd,
                return_all=metrics.return_all,
            )

        return EquityCurveResult(
            equity_curve=equity_curve,
            benchmark_symbol=execution.performance_metrics.benchmark_symbol
            if execution.performance_metrics
            else None,
            benchmark_return=None,  # Would need to fetch from market data
            period_returns=period_returns,
        )

    async def record_snapshot(
        self,
        tenant_id: UUID,
        execution_id: UUID,
        equity: Decimal,
        cash: Decimal,
        positions_value: Decimal,
        daily_return: Decimal | None = None,
        cumulative_return: Decimal | None = None,
        drawdown: Decimal | None = None,
    ) -> StrategyPerformanceSnapshot:
        """
        Record a performance snapshot (called by background job).

        This is typically called periodically to capture equity curve data.
        """
        snapshot = StrategyPerformanceSnapshot(
            tenant_id=tenant_id,
            execution_id=execution_id,
            snapshot_time=datetime.now(UTC),
            equity=equity,
            cash=cash,
            positions_value=positions_value,
            daily_return=daily_return,
            cumulative_return=cumulative_return,
            drawdown=drawdown,
        )
        self.db.add(snapshot)
        await self.db.commit()
        await self.db.refresh(snapshot)
        return snapshot

    async def update_metrics(
        self,
        tenant_id: UUID,
        execution_id: UUID,
        metrics: LiveMetrics,
    ) -> StrategyPerformanceMetrics:
        """
        Update or create performance metrics for an execution (called by background job).

        This is typically called periodically to recalculate aggregate metrics.
        """
        # Check for existing metrics
        stmt = select(StrategyPerformanceMetrics).where(
            StrategyPerformanceMetrics.execution_id == execution_id,
            StrategyPerformanceMetrics.tenant_id == tenant_id,
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing
            existing.return_1d = getattr(metrics, "return_1d", None)
            existing.sharpe_ratio = metrics.sharpe_ratio
            existing.sortino_ratio = metrics.sortino_ratio
            existing.max_drawdown = metrics.max_drawdown
            existing.current_drawdown = metrics.current_drawdown
            existing.volatility = metrics.volatility
            existing.total_trades = metrics.total_trades
            existing.winning_trades = metrics.winning_trades
            existing.losing_trades = metrics.losing_trades
            existing.win_rate = metrics.win_rate
            existing.profit_factor = metrics.profit_factor
            existing.current_equity = metrics.current_equity
            existing.peak_equity = metrics.peak_equity
            existing.total_pnl = metrics.total_pnl
            existing.alpha = metrics.alpha
            existing.beta = metrics.beta
            existing.calculated_at = datetime.now(UTC)
            await self.db.commit()
            await self.db.refresh(existing)
            return existing
        else:
            # Create new
            new_metrics = StrategyPerformanceMetrics(
                tenant_id=tenant_id,
                execution_id=execution_id,
                sharpe_ratio=metrics.sharpe_ratio,
                sortino_ratio=metrics.sortino_ratio,
                max_drawdown=metrics.max_drawdown,
                current_drawdown=metrics.current_drawdown,
                volatility=metrics.volatility,
                total_trades=metrics.total_trades,
                winning_trades=metrics.winning_trades,
                losing_trades=metrics.losing_trades,
                win_rate=metrics.win_rate,
                profit_factor=metrics.profit_factor,
                starting_capital=metrics.starting_capital,
                current_equity=metrics.current_equity,
                peak_equity=metrics.peak_equity,
                total_pnl=metrics.total_pnl,
                alpha=metrics.alpha,
                beta=metrics.beta,
                calculated_at=datetime.now(UTC),
            )
            self.db.add(new_metrics)
            await self.db.commit()
            await self.db.refresh(new_metrics)
            return new_metrics

    # ===================
    # Private helpers
    # ===================

    def _to_summary(self, execution: StrategyExecution) -> StrategyPerformanceSummary:
        """Convert execution to summary."""
        returns = PeriodReturns()
        if execution.performance_metrics:
            m = execution.performance_metrics
            returns = PeriodReturns(
                return_1d=m.return_1d,
                return_1w=m.return_1w,
                return_1m=m.return_1m,
                return_3m=m.return_3m,
                return_6m=m.return_6m,
                return_1y=m.return_1y,
                return_ytd=m.return_ytd,
                return_all=m.return_all,
            )

        return StrategyPerformanceSummary(
            execution_id=execution.id,
            strategy_id=execution.strategy_id,
            strategy_name=execution.strategy.name if execution.strategy else "Unknown",
            mode=_execution_mode_to_str(execution.mode),
            status=_execution_status_to_str(execution.status),
            color=execution.color,
            allocated_capital=execution.allocated_capital,
            current_value=execution.current_value,
            positions_count=execution.positions_count or 0,
            returns=returns,
            started_at=execution.started_at,
            updated_at=execution.updated_at,
        )

    def _to_metrics(self, metrics: StrategyPerformanceMetrics | None) -> LiveMetrics:
        """Convert DB metrics to response model."""
        if not metrics:
            return LiveMetrics()

        return LiveMetrics(
            sharpe_ratio=metrics.sharpe_ratio,
            sortino_ratio=metrics.sortino_ratio,
            calmar_ratio=metrics.calmar_ratio,
            max_drawdown=metrics.max_drawdown,
            current_drawdown=metrics.current_drawdown,
            volatility=metrics.volatility,
            total_trades=metrics.total_trades or 0,
            winning_trades=metrics.winning_trades or 0,
            losing_trades=metrics.losing_trades or 0,
            win_rate=metrics.win_rate,
            profit_factor=metrics.profit_factor,
            average_win=metrics.average_win,
            average_loss=metrics.average_loss,
            starting_capital=metrics.starting_capital,
            current_equity=metrics.current_equity,
            peak_equity=metrics.peak_equity,
            total_pnl=metrics.total_pnl,
            benchmark_symbol=metrics.benchmark_symbol,
            alpha=metrics.alpha,
            beta=metrics.beta,
            correlation=metrics.correlation,
            calculated_at=metrics.calculated_at,
        )

    def _downsample_curve(
        self, curve: list[EquityPoint], interval_minutes: int
    ) -> list[EquityPoint]:
        """Downsample equity curve to reduce data points."""
        if not curve or interval_minutes <= 0:
            return curve

        result: list[EquityPoint] = []
        interval = timedelta(minutes=interval_minutes)
        last_time = None

        for point in curve:
            if last_time is None or point.timestamp - last_time >= interval:
                result.append(point)
                last_time = point.timestamp

        # Always include the last point
        if result and curve and result[-1] != curve[-1]:
            result.append(curve[-1])

        return result


async def get_strategy_performance_service(
    db: AsyncSession = Depends(get_db),
) -> StrategyPerformanceService:
    """Dependency to get strategy performance service."""
    return StrategyPerformanceService(db)
