"""Backtest Service - Pydantic schemas."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class BacktestStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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


class BacktestResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    strategy_id: UUID
    strategy_version: int
    start_date: datetime
    end_date: datetime
    initial_capital: float
    status: BacktestStatus
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
