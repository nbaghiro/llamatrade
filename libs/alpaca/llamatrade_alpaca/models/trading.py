"""Trading models for Alpaca API."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .market_data import parse_timestamp


class OrderSide(StrEnum):
    """Order side."""

    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    """Order type."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class OrderStatus(StrEnum):
    """Order status."""

    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    DONE_FOR_DAY = "done_for_day"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REPLACED = "replaced"
    PENDING_CANCEL = "pending_cancel"
    PENDING_REPLACE = "pending_replace"
    PENDING_NEW = "pending_new"
    ACCEPTED = "accepted"
    ACCEPTED_FOR_BIDDING = "accepted_for_bidding"
    STOPPED = "stopped"
    REJECTED = "rejected"
    SUSPENDED = "suspended"
    CALCULATED = "calculated"


class TimeInForce(StrEnum):
    """Time in force for orders."""

    DAY = "day"
    GTC = "gtc"  # Good till cancelled
    OPG = "opg"  # Market on open
    CLS = "cls"  # Market on close
    IOC = "ioc"  # Immediate or cancel
    FOK = "fok"  # Fill or kill


class PositionSide(StrEnum):
    """Position side."""

    LONG = "long"
    SHORT = "short"


class Order(BaseModel):
    """Order model."""

    id: str = Field(description="Alpaca order ID")
    client_order_id: str | None = Field(default=None, description="Client-provided order ID")
    symbol: str
    side: OrderSide
    qty: float
    filled_qty: float = 0
    order_type: OrderType
    status: OrderStatus
    time_in_force: TimeInForce
    limit_price: float | None = None
    stop_price: float | None = None
    filled_avg_price: float | None = None
    created_at: datetime
    submitted_at: datetime | None = None
    filled_at: datetime | None = None
    expired_at: datetime | None = None
    canceled_at: datetime | None = None
    extended_hours: bool = False


class Position(BaseModel):
    """Position model."""

    symbol: str
    qty: float = Field(description="Number of shares (positive for long, negative for short)")
    side: PositionSide
    avg_entry_price: float = Field(description="Average entry price")
    market_value: float = Field(description="Current market value")
    cost_basis: float = Field(description="Total cost basis")
    unrealized_pl: float = Field(description="Unrealized profit/loss")
    unrealized_plpc: float = Field(description="Unrealized P/L percentage")
    current_price: float = Field(description="Current price")
    lastday_price: float | None = Field(default=None, description="Previous day's close price")
    change_today: float | None = Field(default=None, description="Percent change from last day")


class Account(BaseModel):
    """Alpaca account model."""

    id: str
    account_number: str
    status: str
    currency: str = "USD"
    cash: float
    portfolio_value: float
    buying_power: float
    equity: float
    last_equity: float | None = None
    long_market_value: float = 0
    short_market_value: float = 0
    initial_margin: float = 0
    maintenance_margin: float = 0
    daytrade_count: int = 0
    pattern_day_trader: bool = False
    trading_blocked: bool = False
    transfers_blocked: bool = False
    account_blocked: bool = False


class MarketClock(BaseModel):
    """Market clock information from Alpaca API.

    Provides accurate market status accounting for DST and holidays.
    """

    timestamp: datetime = Field(description="Current time")
    is_open: bool = Field(description="Whether market is currently open")
    next_open: datetime = Field(description="Next market open time")
    next_close: datetime = Field(description="Next market close time")


def parse_order(data: dict[str, Any]) -> Order:
    """Parse Alpaca order JSON to Order model.

    Args:
        data: Raw order data from Alpaca API

    Returns:
        Order model instance
    """
    return Order(
        id=data["id"],
        client_order_id=data.get("client_order_id"),
        symbol=data["symbol"],
        side=OrderSide(data["side"]),
        qty=float(data.get("qty") or data.get("notional") or 0),
        filled_qty=float(data.get("filled_qty", 0)),
        order_type=OrderType(data["type"]),
        status=OrderStatus(data["status"]),
        time_in_force=TimeInForce(data["time_in_force"]),
        limit_price=float(data["limit_price"]) if data.get("limit_price") else None,
        stop_price=float(data["stop_price"]) if data.get("stop_price") else None,
        filled_avg_price=float(data["filled_avg_price"]) if data.get("filled_avg_price") else None,
        created_at=parse_timestamp(data["created_at"]),
        submitted_at=parse_timestamp(data["submitted_at"]) if data.get("submitted_at") else None,
        filled_at=parse_timestamp(data["filled_at"]) if data.get("filled_at") else None,
        expired_at=parse_timestamp(data["expired_at"]) if data.get("expired_at") else None,
        canceled_at=parse_timestamp(data["canceled_at"]) if data.get("canceled_at") else None,
        extended_hours=data.get("extended_hours", False),
    )


def parse_position(data: dict[str, Any]) -> Position:
    """Parse Alpaca position JSON to Position model.

    Args:
        data: Raw position data from Alpaca API

    Returns:
        Position model instance
    """
    return Position(
        symbol=data["symbol"],
        qty=float(data["qty"]),
        side=PositionSide(data["side"]),
        avg_entry_price=float(data["avg_entry_price"]),
        market_value=float(data["market_value"]),
        cost_basis=float(data["cost_basis"]),
        unrealized_pl=float(data["unrealized_pl"]),
        unrealized_plpc=float(data["unrealized_plpc"]),
        current_price=float(data["current_price"]),
        lastday_price=float(data["lastday_price"]) if data.get("lastday_price") else None,
        change_today=float(data["change_today"]) if data.get("change_today") else None,
    )


def parse_account(data: dict[str, Any]) -> Account:
    """Parse Alpaca account JSON to Account model.

    Args:
        data: Raw account data from Alpaca API

    Returns:
        Account model instance
    """
    return Account(
        id=data["id"],
        account_number=data["account_number"],
        status=data["status"],
        currency=data.get("currency", "USD"),
        cash=float(data["cash"]),
        portfolio_value=float(data["portfolio_value"]),
        buying_power=float(data["buying_power"]),
        equity=float(data["equity"]),
        last_equity=float(data["last_equity"]) if data.get("last_equity") else None,
        long_market_value=float(data.get("long_market_value", 0)),
        short_market_value=float(data.get("short_market_value", 0)),
        initial_margin=float(data.get("initial_margin", 0)),
        maintenance_margin=float(data.get("maintenance_margin", 0)),
        daytrade_count=int(data.get("daytrade_count", 0)),
        pattern_day_trader=data.get("pattern_day_trader", False),
        trading_blocked=data.get("trading_blocked", False),
        transfers_blocked=data.get("transfers_blocked", False),
        account_blocked=data.get("account_blocked", False),
    )


def parse_clock(data: dict[str, Any]) -> MarketClock:
    """Parse Alpaca clock JSON to MarketClock model.

    Args:
        data: Raw clock data from Alpaca API

    Returns:
        MarketClock model instance
    """
    return MarketClock(
        timestamp=parse_timestamp(data["timestamp"]),
        is_open=data["is_open"],
        next_open=parse_timestamp(data["next_open"]),
        next_close=parse_timestamp(data["next_close"]),
    )
