"""Base types for strategy compilation and execution."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Bar:
    """OHLCV bar data."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    def to_dict(self) -> dict[str, datetime | float | int]:
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }
