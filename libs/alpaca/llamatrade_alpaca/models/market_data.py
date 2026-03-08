"""Market data models for Alpaca API."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class Timeframe(StrEnum):
    """Supported bar timeframes."""

    MINUTE_1 = "1Min"
    MINUTE_5 = "5Min"
    MINUTE_15 = "15Min"
    MINUTE_30 = "30Min"
    HOUR_1 = "1Hour"
    HOUR_4 = "4Hour"
    DAY_1 = "1Day"
    WEEK_1 = "1Week"
    MONTH_1 = "1Month"


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


def parse_timestamp(ts: str) -> datetime:
    """Parse Alpaca timestamp string to datetime.

    Args:
        ts: Timestamp string (usually ISO format with Z suffix)

    Returns:
        Timezone-aware datetime
    """
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def parse_bar(data: dict[str, Any]) -> Bar:
    """Parse Alpaca bar JSON to Bar model.

    Args:
        data: Raw bar data from Alpaca API

    Returns:
        Bar model instance
    """
    return Bar(
        timestamp=parse_timestamp(data["t"]),
        open=data["o"],
        high=data["h"],
        low=data["l"],
        close=data["c"],
        volume=data["v"],
        vwap=data.get("vw"),
        trade_count=data.get("n"),
    )


def parse_quote(data: dict[str, Any], symbol: str) -> Quote:
    """Parse Alpaca quote JSON to Quote model.

    Args:
        data: Raw quote data from Alpaca API
        symbol: Stock symbol

    Returns:
        Quote model instance
    """
    return Quote(
        symbol=symbol,
        bid_price=data["bp"],
        bid_size=data["bs"],
        ask_price=data["ap"],
        ask_size=data["as"],
        timestamp=parse_timestamp(data["t"]),
    )


def parse_trade(data: dict[str, Any], symbol: str) -> Trade:
    """Parse Alpaca trade JSON to Trade model.

    Args:
        data: Raw trade data from Alpaca API
        symbol: Stock symbol

    Returns:
        Trade model instance
    """
    return Trade(
        symbol=symbol,
        price=data["p"],
        size=data["s"],
        timestamp=parse_timestamp(data["t"]),
        exchange=data.get("x"),
    )


def parse_snapshot(data: dict[str, Any], symbol: str) -> Snapshot:
    """Parse Alpaca snapshot JSON to Snapshot model.

    Args:
        data: Raw snapshot data from Alpaca API
        symbol: Stock symbol

    Returns:
        Snapshot model instance
    """
    return Snapshot(
        symbol=symbol,
        latest_trade=parse_trade(data["latestTrade"], symbol) if data.get("latestTrade") else None,
        latest_quote=parse_quote(data["latestQuote"], symbol) if data.get("latestQuote") else None,
        minute_bar=parse_bar(data["minuteBar"]) if data.get("minuteBar") else None,
        daily_bar=parse_bar(data["dailyBar"]) if data.get("dailyBar") else None,
        prev_daily_bar=parse_bar(data["prevDailyBar"]) if data.get("prevDailyBar") else None,
    )
