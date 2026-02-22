"""Strategy Service - Database models and Pydantic schemas."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class StrategyType(StrEnum):
    """Strategy types."""

    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    MOMENTUM = "momentum"
    BREAKOUT = "breakout"
    CUSTOM = "custom"


class StrategyStatus(StrEnum):
    """Strategy status."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class IndicatorType(StrEnum):
    """Available indicator types."""

    # Trend indicators
    SMA = "sma"
    EMA = "ema"
    MACD = "macd"
    ADX = "adx"

    # Momentum indicators
    RSI = "rsi"
    STOCHASTIC = "stochastic"
    CCI = "cci"
    WILLIAMS_R = "williams_r"

    # Volatility indicators
    BOLLINGER_BANDS = "bollinger_bands"
    ATR = "atr"
    KELTNER_CHANNEL = "keltner_channel"

    # Volume indicators
    OBV = "obv"
    MFI = "mfi"
    VWAP = "vwap"

    # Channel indicators
    DONCHIAN_CHANNEL = "donchian_channel"


class ConditionOperator(StrEnum):
    """Condition operators."""

    GREATER_THAN = "gt"
    LESS_THAN = "lt"
    EQUAL = "eq"
    GREATER_EQUAL = "gte"
    LESS_EQUAL = "lte"
    CROSS_ABOVE = "cross_above"
    CROSS_BELOW = "cross_below"


class ActionType(StrEnum):
    """Action types."""

    BUY = "buy"
    SELL = "sell"
    CLOSE_LONG = "close_long"
    CLOSE_SHORT = "close_short"
    CLOSE_ALL = "close_all"


# Request/Response Schemas
class IndicatorConfig(BaseModel):
    """Indicator configuration."""

    type: IndicatorType
    params: dict[str, Any] = Field(default_factory=dict)
    output_name: str


class ConditionConfig(BaseModel):
    """Trading condition configuration."""

    left: str  # Indicator output name or "price"
    operator: ConditionOperator
    right: str | float  # Another indicator or a value
    and_conditions: list["ConditionConfig"] | None = None
    or_conditions: list["ConditionConfig"] | None = None


class ActionConfig(BaseModel):
    """Trading action configuration."""

    type: ActionType
    quantity_type: str = "percent"  # percent, fixed, all
    quantity_value: float = 100.0
    order_type: str = "market"  # market, limit
    limit_offset_percent: float | None = None


class RiskConfig(BaseModel):
    """Risk management configuration."""

    stop_loss_percent: float | None = None
    take_profit_percent: float | None = None
    trailing_stop_percent: float | None = None
    max_position_size_percent: float = 100.0
    max_daily_loss_percent: float | None = None
    max_open_positions: int | None = None


class StrategyConfig(BaseModel):
    """Complete strategy configuration."""

    symbols: list[str]
    timeframe: str = "1D"
    indicators: list[IndicatorConfig] = Field(default_factory=list)
    entry_conditions: list[ConditionConfig] = Field(default_factory=list)
    exit_conditions: list[ConditionConfig] = Field(default_factory=list)
    entry_action: ActionConfig | None = None
    exit_action: ActionConfig | None = None
    risk: RiskConfig = Field(default_factory=RiskConfig)


class StrategyCreate(BaseModel):
    """Schema for creating a strategy."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    strategy_type: StrategyType = StrategyType.CUSTOM
    config: StrategyConfig


class StrategyUpdate(BaseModel):
    """Schema for updating a strategy."""

    name: str | None = None
    description: str | None = None
    status: StrategyStatus | None = None
    config: StrategyConfig | None = None


class StrategyResponse(BaseModel):
    """Schema for strategy response."""

    id: UUID
    tenant_id: UUID
    name: str
    description: str | None
    strategy_type: StrategyType
    status: StrategyStatus
    is_template: bool
    current_version: int
    created_at: datetime
    updated_at: datetime


class StrategyDetailResponse(StrategyResponse):
    """Schema for detailed strategy response with config."""

    config: StrategyConfig


class StrategyVersionResponse(BaseModel):
    """Schema for strategy version response."""

    id: UUID
    strategy_id: UUID
    version: int
    config: StrategyConfig
    created_at: datetime


class TemplateResponse(BaseModel):
    """Schema for strategy template response."""

    id: str
    name: str
    description: str
    strategy_type: StrategyType
    config: StrategyConfig
    tags: list[str] = Field(default_factory=list)


class IndicatorInfoResponse(BaseModel):
    """Schema for indicator information response."""

    type: IndicatorType
    name: str
    description: str
    params: list[dict[str, Any]]
    outputs: list[str]
    category: str
