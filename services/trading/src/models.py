"""Trading Service - Pydantic schemas."""

from datetime import datetime
from enum import IntEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from llamatrade_proto.generated.common_pb2 import (
    EXECUTION_MODE_PAPER,
    ExecutionMode,
    ExecutionStatus,
)
from llamatrade_proto.generated.trading_pb2 import (
    ORDER_SIDE_BUY,
    ORDER_SIDE_SELL,
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
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    TimeInForce,
)


class BracketType(IntEnum):
    """Bracket order type (service-specific, not proto-defined)."""

    STOP_LOSS = 1
    TAKE_PROFIT = 2


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

_TIME_IN_FORCE_TO_STR: dict[int, str] = {
    TIME_IN_FORCE_DAY: "day",
    TIME_IN_FORCE_GTC: "gtc",
    TIME_IN_FORCE_IOC: "ioc",
    TIME_IN_FORCE_FOK: "fok",
    TIME_IN_FORCE_OPG: "opg",
    TIME_IN_FORCE_CLS: "cls",
}

_POSITION_SIDE_TO_STR: dict[int, str] = {
    POSITION_SIDE_LONG: "long",
    POSITION_SIDE_SHORT: "short",
}

_BRACKET_TYPE_TO_STR: dict[int, str] = {
    BracketType.STOP_LOSS: "stop_loss",
    BracketType.TAKE_PROFIT: "take_profit",
}


def order_side_to_str(value: OrderSide.ValueType) -> Literal["buy", "sell"]:
    """Convert OrderSide proto value to string for Alpaca API."""
    return "sell" if value == ORDER_SIDE_SELL else "buy"


def order_type_to_str(
    value: OrderType.ValueType,
) -> Literal["market", "limit", "stop", "stop_limit"]:
    """Convert OrderType proto value to string for Alpaca API."""
    mapping: dict[int, Literal["market", "limit", "stop", "stop_limit"]] = {
        ORDER_TYPE_MARKET: "market",
        ORDER_TYPE_LIMIT: "limit",
        ORDER_TYPE_STOP: "stop",
        ORDER_TYPE_STOP_LIMIT: "stop_limit",
    }
    return mapping.get(value, "market")


def time_in_force_to_str(value: TimeInForce.ValueType) -> Literal["day", "gtc", "ioc", "fok"]:
    """Convert TimeInForce proto value to string for Alpaca API."""
    mapping: dict[int, Literal["day", "gtc", "ioc", "fok"]] = {
        TIME_IN_FORCE_DAY: "day",
        TIME_IN_FORCE_GTC: "gtc",
        TIME_IN_FORCE_IOC: "ioc",
        TIME_IN_FORCE_FOK: "fok",
    }
    return mapping.get(value, "day")


def position_side_to_str(value: PositionSide.ValueType) -> str:
    """Convert PositionSide proto value to string."""
    return _POSITION_SIDE_TO_STR.get(value, "long")


def bracket_type_to_str(value: BracketType | int) -> Literal["stop_loss", "take_profit"]:
    """Convert BracketType to string for Alpaca API."""
    return "take_profit" if int(value) == BracketType.TAKE_PROFIT else "stop_loss"


class OrderCreate(BaseModel):
    symbol: str
    side: OrderSide.ValueType
    qty: float = Field(..., gt=0)
    order_type: OrderType.ValueType = ORDER_TYPE_MARKET
    limit_price: float | None = None
    stop_price: float | None = None
    trail_percent: float | None = None
    time_in_force: TimeInForce.ValueType = TIME_IN_FORCE_DAY
    extended_hours: bool = False
    # Bracket order fields (stop-loss/take-profit)
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    bracket_time_in_force: TimeInForce.ValueType = TIME_IN_FORCE_GTC
    # Ledger attribution, fixed at origination (CONTRACTS.md §5).
    # None → resolved from the session (strategy sleeve) or Manual sleeve.
    sleeve_id: UUID | None = None
    account_id: UUID | None = None
    # Reference price for market orders (signal price), used to size the
    # §4 cash reservation. Never sent to the broker.
    est_price: float | None = None

    @model_validator(mode="after")
    def _validate_price_for_type(self) -> OrderCreate:
        """Reject orders missing the price their type requires (6A).

        A limit/stop/trailing order with no price would only be rejected at the
        broker after a wasted round-trip — fail fast with a clear message
        instead. Market orders need no price.
        """
        if self.order_type == ORDER_TYPE_LIMIT and not (self.limit_price and self.limit_price > 0):
            raise ValueError("limit order requires a positive limit_price")
        if self.order_type == ORDER_TYPE_STOP and not (self.stop_price and self.stop_price > 0):
            raise ValueError("stop order requires a positive stop_price")
        if self.order_type == ORDER_TYPE_STOP_LIMIT and not (
            self.limit_price and self.limit_price > 0 and self.stop_price and self.stop_price > 0
        ):
            raise ValueError("stop-limit order requires positive limit_price and stop_price")
        if self.order_type == ORDER_TYPE_TRAILING_STOP and not (
            self.trail_percent and self.trail_percent > 0
        ):
            raise ValueError("trailing-stop order requires a positive trail_percent")
        return self


class BracketOrderInfo(BaseModel):
    """Information about bracket orders (stop-loss/take-profit) attached to a parent order."""

    stop_loss_order_id: UUID | None = None
    take_profit_order_id: UUID | None = None


class OrderResponse(BaseModel):
    id: UUID
    client_order_id: str | None = None
    alpaca_order_id: str | None = None
    symbol: str
    side: OrderSide.ValueType
    qty: float
    order_type: OrderType.ValueType
    limit_price: float | None = None
    stop_price: float | None = None
    status: OrderStatus.ValueType
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
    mode: ExecutionMode.ValueType = EXECUTION_MODE_PAPER
    strategy_version: int | None = None
    symbols: list[str] | None = None
    config: dict[str, Any] | None = None


class SessionResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    strategy_id: UUID
    mode: ExecutionMode.ValueType
    status: ExecutionStatus.ValueType
    started_at: datetime
    stopped_at: datetime | None = None
    pnl: float = 0
    trades_count: int = 0
    name: str = ""
    # Ledger identity (None for legacy/unfunded sessions)
    sleeve_id: UUID | None = None
    account_id: UUID | None = None


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
