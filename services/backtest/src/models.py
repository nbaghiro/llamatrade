"""Backtest Service - Pydantic schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

# Valid timeframes; string form mirrors the Timeframe enum in market_data.proto
# (single source of truth). See: libs/proto/llamatrade_proto/protos/market_data.proto
VALID_TIMEFRAMES = ("1Min", "5Min", "15Min", "30Min", "1H", "4H", "1D", "1W")
TimeframeType = Literal["1Min", "5Min", "15Min", "30Min", "1H", "4H", "1D", "1W"]


class BacktestCreate(BaseModel):
    strategy_id: UUID
    strategy_version: int | None = None
    name: str = Field(default="", max_length=255)
    start_date: datetime
    end_date: datetime
    initial_capital: float = Field(default=100000, gt=0)
    symbols: list[str] | None = None
    commission: float = Field(default=0, ge=0)
    slippage: float = Field(default=0, ge=0)
    timeframe: str = Field(default="1D", description="Data timeframe for backtest")
    # Benchmark configuration
    benchmark_symbol: str | None = Field(default="SPY", max_length=10)
    include_benchmark: bool = Field(default=True)

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, v: str) -> str:
        """Validate timeframe is supported."""
        if v not in VALID_TIMEFRAMES:
            raise ValueError(
                f"Invalid timeframe '{v}'. Must be one of: {', '.join(VALID_TIMEFRAMES)}"
            )
        return v
