"""Shared Pydantic models for LlamaTrade services."""

from datetime import datetime
from typing import Any, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

T = TypeVar("T")


class TenantContext(BaseModel):
    """Tenant context extracted from JWT."""

    tenant_id: UUID
    user_id: UUID
    email: EmailStr
    roles: list[str] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class UserInfo(BaseModel):
    """User information for responses."""

    id: UUID
    email: EmailStr
    roles: list[str]
    is_active: bool
    created_at: datetime


class PaginatedResponse[T](BaseModel):
    """Generic paginated response wrapper."""

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(
        cls, items: list[T], total: int, page: int, page_size: int
    ) -> "PaginatedResponse[T]":
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )


class ErrorResponse(BaseModel):
    """Standard error response format."""

    error: str
    detail: str | None = None
    code: str | None = None
    request_id: str | None = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    service: str
    version: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    dependencies: dict[str, str] = Field(default_factory=dict)


# Strategy-related models
class StrategyConfig(BaseModel):
    """Strategy configuration schema."""

    name: str
    description: str | None = None
    symbols: list[str]
    timeframe: str = "1D"
    indicators: list[dict[str, Any]] = Field(default_factory=list)
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    risk_management: dict[str, Any] = Field(default_factory=dict)


class IndicatorConfig(BaseModel):
    """Indicator configuration."""

    type: str
    params: dict[str, Any] = Field(default_factory=dict)
    output_name: str


class ConditionConfig(BaseModel):
    """Trading condition configuration."""

    type: str  # compare, cross_above, cross_below, threshold, and_gate, or_gate
    left: str
    right: str | float
    operator: str | None = None


class ActionConfig(BaseModel):
    """Trading action configuration."""

    type: str  # buy, sell, close_position
    quantity_type: str = "percent"  # percent, fixed, all
    quantity_value: float = 100.0
    order_type: str = "market"
    limit_offset: float | None = None


class RiskConfig(BaseModel):
    """Risk management configuration."""

    stop_loss_percent: float | None = None
    take_profit_percent: float | None = None
    trailing_stop_percent: float | None = None
    max_position_size_percent: float = 100.0
    max_daily_loss_percent: float | None = None


# Order-related models
class OrderRequest(BaseModel):
    """Order request schema."""

    symbol: str
    side: str  # buy, sell
    qty: float
    order_type: str = "market"
    limit_price: float | None = None
    stop_price: float | None = None
    time_in_force: str = "day"


class OrderResponse(BaseModel):
    """Order response schema."""

    id: UUID
    alpaca_order_id: str | None = None
    symbol: str
    side: str
    qty: float
    order_type: str
    status: str
    filled_qty: float = 0
    filled_avg_price: float | None = None
    submitted_at: datetime
    filled_at: datetime | None = None


# Backtest-related models
class BacktestRequest(BaseModel):
    """Backtest run request."""

    strategy_id: UUID
    strategy_version: int | None = None
    start_date: datetime
    end_date: datetime
    initial_capital: float = 100000.0
    symbols: list[str] | None = None


class BacktestMetrics(BaseModel):
    """Backtest performance metrics."""

    total_return: float
    annual_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float
    avg_loss: float
    avg_holding_period: float


class BacktestResult(BaseModel):
    """Backtest result schema."""

    id: UUID
    backtest_id: UUID
    metrics: BacktestMetrics
    equity_curve: list[dict[str, Any]]
    trades: list[dict[str, Any]]
    created_at: datetime


# Portfolio-related models
class Position(BaseModel):
    """Portfolio position."""

    symbol: str
    qty: float
    cost_basis: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_percent: float


class PortfolioSummary(BaseModel):
    """Portfolio summary."""

    total_equity: float
    cash: float
    market_value: float
    total_pnl: float
    total_pnl_percent: float
    positions: list[Position]
    updated_at: datetime
