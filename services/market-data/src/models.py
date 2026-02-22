"""Market Data Service - Pydantic schemas."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Timeframe(StrEnum):
    """Supported timeframes."""

    MINUTE_1 = "1Min"
    MINUTE_5 = "5Min"
    MINUTE_15 = "15Min"
    MINUTE_30 = "30Min"
    HOUR_1 = "1Hour"
    HOUR_4 = "4Hour"
    DAY_1 = "1Day"
    WEEK_1 = "1Week"


class Bar(BaseModel):
    """OHLCV bar data."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float | None = None
    trade_count: int | None = None


class Quote(BaseModel):
    """Quote data."""

    symbol: str
    bid_price: float
    bid_size: int
    ask_price: float
    ask_size: int
    timestamp: datetime


class Trade(BaseModel):
    """Trade data."""

    symbol: str
    price: float
    size: int
    timestamp: datetime
    exchange: str | None = None


class Snapshot(BaseModel):
    """Market snapshot for a symbol."""

    symbol: str
    latest_trade: Trade | None = None
    latest_quote: Quote | None = None
    minute_bar: Bar | None = None
    daily_bar: Bar | None = None
    prev_daily_bar: Bar | None = None


class BarsRequest(BaseModel):
    """Request for historical bars."""

    symbols: list[str]
    timeframe: Timeframe = Timeframe.DAY_1
    start: datetime
    end: datetime | None = None
    limit: int = Field(default=1000, ge=1, le=10000)
    adjustment: str = "raw"  # raw, split, dividend, all


class BarsResponse(BaseModel):
    """Response containing historical bars."""

    bars: dict[str, list[Bar]]
    next_page_token: str | None = None


class QuotesRequest(BaseModel):
    """Request for latest quotes."""

    symbols: list[str]


class StreamSubscription(BaseModel):
    """WebSocket stream subscription request."""

    action: str  # subscribe, unsubscribe
    trades: list[str] | None = None
    quotes: list[str] | None = None
    bars: list[str] | None = None


class StreamMessage(BaseModel):
    """WebSocket stream message."""

    type: str  # trade, quote, bar, error
    symbol: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
