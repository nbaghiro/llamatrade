"""Trading models for Alpaca API."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
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
    qty: Decimal
    filled_qty: Decimal = Decimal("0")
    order_type: OrderType
    status: OrderStatus
    time_in_force: TimeInForce
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    filled_avg_price: Decimal | None = None
    created_at: datetime
    submitted_at: datetime | None = None
    filled_at: datetime | None = None
    expired_at: datetime | None = None
    canceled_at: datetime | None = None
    extended_hours: bool = False


class Position(BaseModel):
    """Position model."""

    symbol: str
    qty: Decimal = Field(description="Number of shares (positive for long, negative for short)")
    side: PositionSide
    avg_entry_price: Decimal = Field(description="Average entry price")
    market_value: Decimal = Field(description="Current market value")
    cost_basis: Decimal = Field(description="Total cost basis")
    unrealized_pl: Decimal = Field(description="Unrealized profit/loss")
    unrealized_plpc: Decimal = Field(description="Unrealized P/L percentage")
    current_price: Decimal = Field(description="Current price")
    lastday_price: Decimal | None = Field(default=None, description="Previous day's close price")
    change_today: Decimal | None = Field(default=None, description="Percent change from last day")


class Account(BaseModel):
    """Alpaca account model."""

    id: str
    account_number: str
    status: str
    currency: str = "USD"
    cash: Decimal
    portfolio_value: Decimal
    buying_power: Decimal
    equity: Decimal
    last_equity: Decimal | None = None
    long_market_value: Decimal = Decimal("0")
    short_market_value: Decimal = Decimal("0")
    initial_margin: Decimal = Decimal("0")
    maintenance_margin: Decimal = Decimal("0")
    daytrade_count: int = 0
    pattern_day_trader: bool = False
    trading_blocked: bool = False
    transfers_blocked: bool = False
    account_blocked: bool = False
    # Alpaca reports buying-power multiplier as a string: "1" = cash account,
    # "2"/"4" = margin. The ledger models margin-account settlement only.
    multiplier: str = "2"


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
        qty=Decimal(str(data.get("qty") or data.get("notional") or 0)),
        filled_qty=Decimal(str(data.get("filled_qty", 0))),
        order_type=OrderType(data["type"]),
        status=OrderStatus(data["status"]),
        time_in_force=TimeInForce(data["time_in_force"]),
        limit_price=Decimal(str(data["limit_price"])) if data.get("limit_price") else None,
        stop_price=Decimal(str(data["stop_price"])) if data.get("stop_price") else None,
        filled_avg_price=Decimal(str(data["filled_avg_price"]))
        if data.get("filled_avg_price")
        else None,
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
        qty=Decimal(str(data["qty"])),
        side=PositionSide(data["side"]),
        avg_entry_price=Decimal(str(data["avg_entry_price"])),
        market_value=Decimal(str(data["market_value"])),
        cost_basis=Decimal(str(data["cost_basis"])),
        unrealized_pl=Decimal(str(data["unrealized_pl"])),
        unrealized_plpc=Decimal(str(data["unrealized_plpc"])),
        current_price=Decimal(str(data["current_price"])),
        lastday_price=Decimal(str(data["lastday_price"])) if data.get("lastday_price") else None,
        change_today=Decimal(str(data["change_today"])) if data.get("change_today") else None,
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
        cash=Decimal(str(data["cash"])),
        portfolio_value=Decimal(str(data["portfolio_value"])),
        buying_power=Decimal(str(data["buying_power"])),
        equity=Decimal(str(data["equity"])),
        last_equity=Decimal(str(data["last_equity"])) if data.get("last_equity") else None,
        long_market_value=Decimal(str(data.get("long_market_value", 0))),
        short_market_value=Decimal(str(data.get("short_market_value", 0))),
        initial_margin=Decimal(str(data.get("initial_margin", 0))),
        maintenance_margin=Decimal(str(data.get("maintenance_margin", 0))),
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


class Asset(BaseModel):
    """Tradable-asset metadata from Alpaca's /v2/assets endpoint."""

    id: str
    symbol: str
    name: str = ""
    asset_class: str = Field(default="us_equity", description="Alpaca 'class' field")
    exchange: str = ""
    status: str = Field(description="'active' or 'inactive'")
    tradable: bool = Field(description="Whether the asset can currently be traded")
    fractionable: bool = False


def parse_asset(data: dict[str, Any]) -> Asset:
    """Parse Alpaca asset JSON to an Asset model."""
    return Asset(
        id=data["id"],
        symbol=data["symbol"],
        name=data.get("name", ""),
        asset_class=data.get("class", "us_equity"),
        exchange=data.get("exchange", ""),
        status=data["status"],
        tradable=bool(data.get("tradable", False)),
        fractionable=bool(data.get("fractionable", False)),
    )


class CorporateActionType(StrEnum):
    """Top-level corporate-action category (``ca_type``)."""

    DIVIDEND = "dividend"
    MERGER = "merger"
    SPINOFF = "spinoff"
    SPLIT = "split"


class CorporateActionDateType(StrEnum):
    """Which announcement date the ``since``/``until`` filter applies to."""

    DECLARATION_DATE = "declaration_date"
    EX_DATE = "ex_date"
    RECORD_DATE = "record_date"
    PAYABLE_DATE = "payable_date"


class CorporateAnnouncement(BaseModel):
    """One announced corporate action from ``/v2/corporate_actions/announcements``.

    ``ca_sub_type`` stays a raw string: Alpaca's documented sub-type vocabulary
    (cash/stock, merger_update/merger_completion, spinoff, stock_split/unit_split/
    reverse_split/recapitalization) is open-ended in practice, and a strict enum
    would make an unseen sub-type fail the whole fetch. Consumers route on
    ``ca_type`` plus the rate/symbol fields, which are closed.
    """

    id: str = Field(description="Announcement ID")
    corporate_action_id: str = Field(default="", description="Issuer-side action ID")
    ca_type: CorporateActionType
    ca_sub_type: str = ""
    initiating_symbol: str = ""
    initiating_original_cusip: str = ""
    target_symbol: str = ""
    target_original_cusip: str = ""
    declaration_date: date | None = None
    ex_date: date | None = None
    record_date: date | None = None
    payable_date: date | None = None
    cash: Decimal | None = Field(default=None, description="Cash paid per share")
    old_rate: Decimal | None = Field(default=None, description="Shares held before the action")
    new_rate: Decimal | None = Field(default=None, description="Shares held after the action")


def parse_date(value: str) -> date | None:
    """Parse an Alpaca ``YYYY-MM-DD`` date field, or None if absent/malformed."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_decimal(value: object) -> Decimal | None:
    """Parse an Alpaca numeric string field, or None if absent/malformed."""
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def parse_corporate_announcement(data: dict[str, Any]) -> CorporateAnnouncement:
    """Parse Alpaca announcement JSON to a CorporateAnnouncement model.

    Args:
        data: Raw announcement data from Alpaca API

    Returns:
        CorporateAnnouncement model instance
    """
    return CorporateAnnouncement(
        id=str(data["id"]),
        corporate_action_id=str(data.get("corporate_action_id") or ""),
        ca_type=CorporateActionType(str(data["ca_type"]).lower()),
        ca_sub_type=str(data.get("ca_sub_type") or ""),
        initiating_symbol=str(data.get("initiating_symbol") or ""),
        initiating_original_cusip=str(data.get("initiating_original_cusip") or ""),
        target_symbol=str(data.get("target_symbol") or ""),
        target_original_cusip=str(data.get("target_original_cusip") or ""),
        declaration_date=parse_date(str(data.get("declaration_date") or "")),
        ex_date=parse_date(str(data.get("ex_date") or "")),
        record_date=parse_date(str(data.get("record_date") or "")),
        payable_date=parse_date(str(data.get("payable_date") or "")),
        cash=_parse_decimal(data.get("cash")),
        old_rate=_parse_decimal(data.get("old_rate")),
        new_rate=_parse_decimal(data.get("new_rate")),
    )
