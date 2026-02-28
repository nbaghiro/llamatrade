"""Trading Service - Pydantic schemas."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class OrderStatus(StrEnum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class TimeInForce(StrEnum):
    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


class TradingMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class OrderCreate(BaseModel):
    symbol: str
    side: OrderSide
    qty: float = Field(..., gt=0)
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    stop_price: float | None = None
    trail_percent: float | None = None
    time_in_force: TimeInForce = TimeInForce.DAY
    extended_hours: bool = False
    # Bracket order fields (stop-loss/take-profit)
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    bracket_time_in_force: TimeInForce = TimeInForce.GTC


class BracketType(StrEnum):
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


class BracketOrderInfo(BaseModel):
    """Information about bracket orders (stop-loss/take-profit) attached to a parent order."""

    stop_loss_order_id: UUID | None = None
    take_profit_order_id: UUID | None = None


class OrderResponse(BaseModel):
    id: UUID
    alpaca_order_id: str | None = None
    symbol: str
    side: OrderSide
    qty: float
    order_type: OrderType
    limit_price: float | None = None
    stop_price: float | None = None
    status: OrderStatus
    filled_qty: float = 0
    filled_avg_price: float | None = None
    submitted_at: datetime
    filled_at: datetime | None = None
    # Bracket order fields
    parent_order_id: UUID | None = None
    bracket_type: BracketType | None = None
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    bracket_orders: BracketOrderInfo | None = None


class SessionCreate(BaseModel):
    strategy_id: UUID
    credentials_id: UUID
    name: str = Field(..., min_length=1, max_length=100)
    mode: TradingMode = TradingMode.PAPER
    strategy_version: int | None = None
    symbols: list[str] | None = None
    config: dict | None = None


class SessionResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    strategy_id: UUID
    mode: TradingMode
    status: SessionStatus
    started_at: datetime
    stopped_at: datetime | None = None
    pnl: float = 0
    trades_count: int = 0


class PositionResponse(BaseModel):
    symbol: str
    qty: float
    side: str
    cost_basis: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_percent: float
    current_price: float


class RiskLimits(BaseModel):
    max_position_size: float | None = None
    max_daily_loss: float | None = None
    max_order_value: float | None = None
    allowed_symbols: list[str] | None = None


class RiskCheckResult(BaseModel):
    passed: bool
    violations: list[str] = Field(default_factory=list)
