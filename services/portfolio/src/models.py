"""Portfolio Service - Pydantic schemas (read-side response shapes)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PositionResponse(BaseModel):
    symbol: str
    qty: float
    side: str
    cost_basis: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_percent: float
    current_price: float
    avg_entry_price: float


class PortfolioSummary(BaseModel):
    total_equity: float
    cash: float
    market_value: float
    total_unrealized_pnl: float
    total_realized_pnl: float
    day_pnl: float
    day_pnl_percent: float
    total_pnl_percent: float
    positions_count: int
    updated_at: datetime


class PerformanceMetrics(BaseModel):
    period: str  # 1D, 1W, 1M, 3M, 6M, 1Y, YTD, ALL
    total_return: float
    total_return_percent: float
    annualized_return: float
    volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    best_day: float
    worst_day: float
    avg_daily_return: float
    # Additional period returns
    ytd_return: float = 0.0
    mtd_return: float = 0.0
    wtd_return: float = 0.0
    # Benchmark comparison
    beta: float = 0.0
    alpha: float = 0.0
    benchmark_return: float = 0.0


class EquityPoint(BaseModel):
    timestamp: datetime
    equity: float
    cash: float
    market_value: float


class TransactionResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    type: int  # TransactionType proto value
    symbol: str | None = None
    quantity: float | None = None
    price: float | None = None
    amount: float
    fees: float = 0
    description: str | None = None
    reference_id: str | None = None
    created_at: datetime
