"""Portfolio Service - Pydantic schemas (read-side response shapes)."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class PositionResponse(BaseModel):
    symbol: str
    qty: Decimal
    side: str
    cost_basis: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_percent: Decimal
    current_price: Decimal
    avg_entry_price: Decimal


class PortfolioSummary(BaseModel):
    total_equity: Decimal
    cash: Decimal
    market_value: Decimal
    total_unrealized_pnl: Decimal
    total_realized_pnl: Decimal
    day_pnl: Decimal
    day_pnl_percent: Decimal
    total_pnl_percent: Decimal
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
    equity: Decimal
    cash: Decimal
    market_value: Decimal


class TransactionResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    type: int  # TransactionType proto value
    symbol: str | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    amount: Decimal
    fees: Decimal = Decimal("0")
    description: str | None = None
    reference_id: str | None = None
    created_at: datetime
