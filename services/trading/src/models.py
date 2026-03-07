"""Trading Service - Pydantic schemas."""

from datetime import datetime
from enum import IntEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from llamatrade_proto.generated.common_pb2 import (
    EXECUTION_MODE_LIVE,
    EXECUTION_MODE_PAPER,
    EXECUTION_STATUS_ERROR,
    EXECUTION_STATUS_PAUSED,
    EXECUTION_STATUS_PENDING,
    EXECUTION_STATUS_RUNNING,
    EXECUTION_STATUS_STOPPED,
)
from llamatrade_proto.generated.trading_pb2 import (
    ORDER_SIDE_BUY,
    ORDER_SIDE_SELL,
    ORDER_STATUS_ACCEPTED,
    ORDER_STATUS_CANCELLED,
    ORDER_STATUS_EXPIRED,
    ORDER_STATUS_FILLED,
    ORDER_STATUS_PARTIAL,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_REJECTED,
    ORDER_STATUS_SUBMITTED,
    ORDER_TYPE_LIMIT,
    ORDER_TYPE_MARKET,
    ORDER_TYPE_STOP,
    ORDER_TYPE_STOP_LIMIT,
    ORDER_TYPE_TRAILING_STOP,
    POSITION_SIDE_LONG,
    POSITION_SIDE_SHORT,
    TIME_IN_FORCE_CLS,
    TIME_IN_FORCE_DAY,
    TIME_IN_FORCE_FOK,
    TIME_IN_FORCE_GTC,
    TIME_IN_FORCE_IOC,
    TIME_IN_FORCE_OPG,
)


class BracketType(IntEnum):
    """Bracket order type (service-specific, not proto-defined)."""

    STOP_LOSS = 1
    TAKE_PROFIT = 2


# ===================
# Conversion helpers: proto int -> str (for Alpaca API)
# ===================

_ORDER_SIDE_TO_STR: dict[int, str] = {
    ORDER_SIDE_BUY: "buy",
    ORDER_SIDE_SELL: "sell",
}

_ORDER_TYPE_TO_STR: dict[int, str] = {
    ORDER_TYPE_MARKET: "market",
    ORDER_TYPE_LIMIT: "limit",
    ORDER_TYPE_STOP: "stop",
    ORDER_TYPE_STOP_LIMIT: "stop_limit",
    ORDER_TYPE_TRAILING_STOP: "trailing_stop",
}

_ORDER_STATUS_TO_STR: dict[int, str] = {
    ORDER_STATUS_PENDING: "pending",
    ORDER_STATUS_SUBMITTED: "submitted",
    ORDER_STATUS_ACCEPTED: "accepted",
    ORDER_STATUS_PARTIAL: "partial",
    ORDER_STATUS_FILLED: "filled",
    ORDER_STATUS_CANCELLED: "cancelled",
    ORDER_STATUS_REJECTED: "rejected",
    ORDER_STATUS_EXPIRED: "expired",
}

_TIME_IN_FORCE_TO_STR: dict[int, str] = {
    TIME_IN_FORCE_DAY: "day",
    TIME_IN_FORCE_GTC: "gtc",
    TIME_IN_FORCE_IOC: "ioc",
    TIME_IN_FORCE_FOK: "fok",
    TIME_IN_FORCE_OPG: "opg",
    TIME_IN_FORCE_CLS: "cls",
}

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

_POSITION_SIDE_TO_STR: dict[int, str] = {
    POSITION_SIDE_LONG: "long",
    POSITION_SIDE_SHORT: "short",
}

_BRACKET_TYPE_TO_STR: dict[int, str] = {
    BracketType.STOP_LOSS: "stop_loss",
    BracketType.TAKE_PROFIT: "take_profit",
}


def order_side_to_str(value: int) -> str:
    """Convert OrderSide proto value to string for Alpaca API."""
    return _ORDER_SIDE_TO_STR.get(value, "buy")


def order_type_to_str(value: int) -> str:
    """Convert OrderType proto value to string for Alpaca API."""
    return _ORDER_TYPE_TO_STR.get(value, "market")


def order_status_to_str(value: int) -> str:
    """Convert OrderStatus proto value to string."""
    return _ORDER_STATUS_TO_STR.get(value, "pending")


def time_in_force_to_str(value: int) -> str:
    """Convert TimeInForce proto value to string for Alpaca API."""
    return _TIME_IN_FORCE_TO_STR.get(value, "day")


def trading_mode_to_str(value: int) -> str:
    """Convert ExecutionMode proto value to string."""
    return _EXECUTION_MODE_TO_STR.get(value, "paper")


def session_status_to_str(value: int) -> str:
    """Convert ExecutionStatus proto value to string."""
    return _EXECUTION_STATUS_TO_STR.get(value, "pending")


def position_side_to_str(value: int) -> str:
    """Convert PositionSide proto value to string."""
    return _POSITION_SIDE_TO_STR.get(value, "long")


def bracket_type_to_str(value: BracketType | int) -> str:
    """Convert BracketType to string for Alpaca API."""
    return _BRACKET_TYPE_TO_STR.get(int(value), "stop_loss")


class OrderCreate(BaseModel):
    symbol: str
    side: int  # OrderSide proto value
    qty: float = Field(..., gt=0)
    order_type: int = ORDER_TYPE_MARKET  # OrderType proto value
    limit_price: float | None = None
    stop_price: float | None = None
    trail_percent: float | None = None
    time_in_force: int = TIME_IN_FORCE_DAY  # TimeInForce proto value
    extended_hours: bool = False
    # Bracket order fields (stop-loss/take-profit)
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    bracket_time_in_force: int = TIME_IN_FORCE_GTC


class BracketOrderInfo(BaseModel):
    """Information about bracket orders (stop-loss/take-profit) attached to a parent order."""

    stop_loss_order_id: UUID | None = None
    take_profit_order_id: UUID | None = None


class OrderResponse(BaseModel):
    id: UUID
    client_order_id: str | None = None
    alpaca_order_id: str | None = None
    symbol: str
    side: int  # OrderSide proto value
    qty: float
    order_type: int  # OrderType proto value
    limit_price: float | None = None
    stop_price: float | None = None
    status: int  # OrderStatus proto value
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
    mode: int = EXECUTION_MODE_PAPER  # ExecutionMode proto value
    strategy_version: int | None = None
    symbols: list[str] | None = None
    config: dict[str, Any] | None = None


class SessionResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    strategy_id: UUID
    mode: int  # ExecutionMode proto value
    status: int  # ExecutionStatus proto value
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
    # Safety flags
    allow_outside_market_hours: bool = False  # For paper trading/testing only


class RiskCheckResult(BaseModel):
    passed: bool
    violations: list[str] = Field(default_factory=list)
