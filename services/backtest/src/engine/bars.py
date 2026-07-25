"""OHLCV bar type for fetched market-data bars — the service's data boundary type."""

from datetime import datetime
from typing import TypedDict


class BarData(TypedDict):
    """A single OHLCV bar as fetched from the market-data service."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
