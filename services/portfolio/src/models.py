"""Portfolio Service - Pydantic schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

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

# ===================
# Conversion helpers: proto int -> str (for display/API)
# ===================

_TRANSACTION_TYPE_TO_STR: dict[int, str] = {
    TRANSACTION_TYPE_BUY: "buy",
    TRANSACTION_TYPE_SELL: "sell",
    TRANSACTION_TYPE_DEPOSIT: "deposit",
    TRANSACTION_TYPE_WITHDRAWAL: "withdrawal",
    TRANSACTION_TYPE_DIVIDEND: "dividend",
    TRANSACTION_TYPE_INTEREST: "interest",
    TRANSACTION_TYPE_FEE: "fee",
    TRANSACTION_TYPE_TRANSFER_IN: "transfer_in",
    TRANSACTION_TYPE_TRANSFER_OUT: "transfer_out",
}


def transaction_type_to_str(value: int) -> str:
    """Convert TransactionType proto value to string."""
    return _TRANSACTION_TYPE_TO_STR.get(value, "unknown")


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


class TransactionCreate(BaseModel):
    type: int  # TransactionType proto value
    symbol: str | None = None
    qty: float | None = None
    price: float | None = None
    amount: float
    commission: float = 0
    description: str | None = None
