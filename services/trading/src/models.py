"""Trading Service - Pydantic schemas."""

from datetime import datetime
from decimal import Decimal
from enum import IntEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from llamatrade_proto.generated.common_pb2 import (
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
    TIME_IN_FORCE_DAY,
    TIME_IN_FORCE_FOK,
    TIME_IN_FORCE_GTC,
    TIME_IN_FORCE_IOC,
    OrderSide,
    OrderType,
    TimeInForce,
)


class BracketType(IntEnum):
    """Bracket order type (service-specific, not proto-defined)."""

    STOP_LOSS = 1
    TAKE_PROFIT = 2


def order_side_to_str(value: OrderSide.ValueType) -> Literal["buy", "sell"]:
    """Convert OrderSide proto value to string for Alpaca API."""
    return "sell" if value == ORDER_SIDE_SELL else "buy"


def signal_type_to_order_side(signal_type: str) -> OrderSide.ValueType:
    """Broker side for a strategy signal type: ``cover`` buys back, ``short`` sells."""
    return ORDER_SIDE_BUY if signal_type in ("buy", "cover") else ORDER_SIDE_SELL


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


class OrderCreate(BaseModel):
    symbol: str
    side: OrderSide.ValueType
    qty: Decimal = Field(..., gt=0)
    order_type: OrderType.ValueType = ORDER_TYPE_MARKET
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    trail_percent: Decimal | None = None
    time_in_force: TimeInForce.ValueType = TIME_IN_FORCE_DAY
    extended_hours: bool = False
    # Bracket order fields (stop-loss/take-profit)
    stop_loss_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    bracket_time_in_force: TimeInForce.ValueType = TIME_IN_FORCE_GTC
    # Ledger attribution, fixed at origination (portfolio-ledger.md); None → resolved from the session (strategy sleeve) or Manual sleeve.
    sleeve_id: UUID | None = None
    account_id: UUID | None = None
    # Reference price for market orders (signal price), used to size the §4 cash reservation; never sent to the broker.
    est_price: Decimal | None = None

    @model_validator(mode="after")
    def _validate_price_for_type(self) -> OrderCreate:
        """Reject orders missing the price their type requires.

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


# Key under which the degradation marker is stored in TradingSession.config.
SESSION_DEGRADED_KEY = "degraded"


class SessionDegradation(BaseModel):
    """A non-fatal condition flagging a still-running session for user attention."""

    reason: str
    symbols: list[str] = Field(default_factory=list)
    detail: str = ""
    detected_at: datetime


class SessionResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    strategy_id: UUID
    mode: ExecutionMode.ValueType
    status: ExecutionStatus.ValueType
    started_at: datetime
    stopped_at: datetime | None = None
    pnl: Decimal = Decimal("0")
    trades_count: int = 0
    name: str = ""
    # Ledger identity (None for legacy/unfunded sessions)
    sleeve_id: UUID | None = None
    account_id: UUID | None = None
    # Set while the session runs but needs a user decision (e.g. delisted symbol)
    degraded: SessionDegradation | None = None


class RiskLimits(BaseModel):
    max_position_size: Decimal | None = None
    max_daily_loss: Decimal | None = None
    max_order_value: Decimal | None = None
    allowed_symbols: list[str] | None = None
    # Safety flags
    allow_outside_market_hours: bool = False  # For paper trading/testing only


class RiskCheckResult(BaseModel):
    passed: bool
    violations: list[str] = Field(default_factory=list)
