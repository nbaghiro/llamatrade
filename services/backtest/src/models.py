"""Backtest Service - Pydantic schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from llamatrade_proto.generated.backtest_pb2 import (
    BACKTEST_STATUS_CANCELLED,
    BACKTEST_STATUS_COMPLETED,
    BACKTEST_STATUS_FAILED,
    BACKTEST_STATUS_PENDING,
    BACKTEST_STATUS_RUNNING,
    BacktestStatus,
)

# Re-export proto constants for convenience
__all__ = [
    "BACKTEST_STATUS_CANCELLED",
    "BACKTEST_STATUS_COMPLETED",
    "BACKTEST_STATUS_FAILED",
    "BACKTEST_STATUS_PENDING",
    "BACKTEST_STATUS_RUNNING",
    "BacktestStatus",
]

# ===================
# Conversion helpers: proto ValueType -> str (for display/API)
# ===================

_BACKTEST_STATUS_PREFIX = "BACKTEST_STATUS_"


def backtest_status_to_str(value: BacktestStatus.ValueType) -> str:
    """Convert BacktestStatus proto value to string."""
    name = BacktestStatus.Name(value)
    if name.startswith(_BACKTEST_STATUS_PREFIX):
        return name[len(_BACKTEST_STATUS_PREFIX) :].lower()
    return name.lower()


# Valid timeframes for backtesting.
# These values mirror the Timeframe enum in market_data.proto (single source of truth).
# The string format here is used for API/display; proto uses integer constants internally.
# See: libs/proto/llamatrade_proto/protos/market_data.proto
VALID_TIMEFRAMES = ("1Min", "5Min", "15Min", "30Min", "1H", "4H", "1D", "1W")
TimeframeType = Literal["1Min", "5Min", "15Min", "30Min", "1H", "4H", "1D", "1W"]


class BacktestCreate(BaseModel):
    strategy_id: UUID
    strategy_version: int | None = None
    name: str = Field(default="", max_length=255)
    start_date: datetime
    end_date: datetime
    initial_capital: float = Field(default=100000, gt=0)
    symbols: list[str] | None = None
    commission: float = Field(default=0, ge=0)
    slippage: float = Field(default=0, ge=0)
    # Phase 1: Timeframe selection
    timeframe: str = Field(default="1D", description="Data timeframe for backtest")
    # Phase 2: Benchmark configuration
    benchmark_symbol: str | None = Field(default="SPY", max_length=10)
    include_benchmark: bool = Field(default=True)

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, v: str) -> str:
        """Validate timeframe is supported."""
        if v not in VALID_TIMEFRAMES:
            raise ValueError(
                f"Invalid timeframe '{v}'. Must be one of: {', '.join(VALID_TIMEFRAMES)}"
            )
        return v


class BacktestMetrics(BaseModel):
    total_return: float
    annual_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_duration: int  # days
    win_rate: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float
    avg_holding_period: float  # days
    exposure_time: float  # percentage
    # Phase 5: Benchmark comparison metrics
    benchmark_return: float = 0
    benchmark_symbol: str = "SPY"
    alpha: float = 0
    beta: float = 0
    information_ratio: float = 0
    excess_return: float = 0
    # Indicates whether benchmark data was successfully fetched
    # When False, benchmark metrics (benchmark_return, alpha, beta, etc.) are defaults
    benchmark_data_available: bool = True


class TradeRecord(BaseModel):
    entry_date: datetime
    exit_date: datetime | None
    symbol: str
    side: str
    entry_price: float
    exit_price: float | None
    quantity: float
    pnl: float
    pnl_percent: float
    commission: float


class EquityPoint(BaseModel):
    date: datetime
    equity: float
    drawdown: float
    drawdown_percent: float


class BenchmarkEquityPoint(BaseModel):
    """Equity point for benchmark comparison overlay."""

    date: datetime
    equity: float


class BacktestResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    strategy_id: UUID
    strategy_version: int
    start_date: datetime
    end_date: datetime
    initial_capital: float
    status: BacktestStatus.ValueType
    progress: float = 0
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class BacktestResultResponse(BaseModel):
    id: UUID
    backtest_id: UUID
    metrics: BacktestMetrics
    equity_curve: list[EquityPoint]
    trades: list[TradeRecord]
    monthly_returns: dict[str, float]
    created_at: datetime
    # Phase 5: Benchmark equity curve for chart overlay
    benchmark_equity_curve: list[BenchmarkEquityPoint] = []
