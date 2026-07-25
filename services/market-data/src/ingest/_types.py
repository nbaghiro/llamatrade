"""Shared structural types for the ingest package."""

from __future__ import annotations

from collections.abc import Awaitable
from datetime import datetime
from typing import Protocol

from src.models import Bar, Timeframe


class AlpacaBars(Protocol):
    """Narrow ``get_bars`` interface the ingest controllers need from an Alpaca client."""

    def get_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime | None = ...,
        limit: int = ...,
        adjustment: str = ...,
    ) -> Awaitable[list[Bar]]: ...
