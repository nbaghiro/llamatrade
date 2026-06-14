"""Strategy performance schemas + proto enum helpers.

The response DTOs (summaries, metrics, equity points, filters) and the
mode/status string mappings shared by the ledger-backed
``StrategyPerformanceReadService`` and the Connect servicer. Reads derive from
the ledger projection — there is no table-backed service here.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

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
