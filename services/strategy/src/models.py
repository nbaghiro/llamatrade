"""Strategy Service - Pydantic schemas for API requests/responses."""

from datetime import datetime
from enum import StrEnum
from typing import TypedDict
from uuid import UUID

from pydantic import BaseModel, Field


# TypedDict for strategy config JSON (parsed S-expression)
class StrategyConfigJSON(TypedDict, total=False):
    """JSON representation of parsed strategy S-expression."""

    name: str
    symbols: list[str]
    timeframe: str
    entry: str | dict[str, object]  # Condition expression
    exit: str | dict[str, object]  # Condition expression
    stop_loss_pct: float
    take_profit_pct: float
    trailing_stop_pct: float
    sizing: dict[str, str | float]


class ConfigOverride(TypedDict, total=False):
    """Runtime configuration overrides."""

    symbols: list[str]
    timeframe: str
    stop_loss_pct: float
    take_profit_pct: float
    sizing_type: str
    sizing_value: float


class IndicatorParamInfo(TypedDict):
    """Indicator parameter metadata."""

    name: str
    type: str  # "int", "float", "str"
    default: int | float | str | None
    min: int | float | None
    max: int | float | None
    description: str


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


class DeploymentStatus(StrEnum):
    """Deployment lifecycle status."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class DeploymentEnvironment(StrEnum):
    """Trading environment."""

    PAPER = "paper"
    LIVE = "live"


# ===================
# Request Schemas
# ===================


class StrategyCreate(BaseModel):
    """Schema for creating a strategy with S-expression config."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    config_sexpr: str = Field(
        ...,
        description="S-expression strategy definition",
        examples=[
            """(strategy
  :name "RSI Mean Reversion"
  :symbols ["AAPL" "MSFT"]
  :timeframe "1D"
  :entry (< (rsi close 14) 30)
  :exit (> (rsi close 14) 70)
  :stop-loss-pct 2.0
  :take-profit-pct 6.0)"""
        ],
    )


class StrategyUpdate(BaseModel):
    """Schema for updating a strategy."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    status: StrategyStatus | None = None
    config_sexpr: str | None = Field(
        None,
        description="New S-expression config (creates new version if changed)",
    )


class DeploymentCreate(BaseModel):
    """Schema for creating a deployment."""

    version: int | None = Field(
        None,
        description="Strategy version to deploy (defaults to current_version)",
    )
    environment: DeploymentEnvironment = DeploymentEnvironment.PAPER
    config_override: ConfigOverride | None = Field(
        None,
        description="Runtime config overrides (e.g., different symbols)",
    )


# ===================
# Response Schemas
# ===================


class StrategyResponse(BaseModel):
    """Basic strategy info (without config)."""

    id: UUID
    name: str
    description: str | None
    strategy_type: StrategyType
    status: StrategyStatus
    current_version: int
    created_at: datetime
    updated_at: datetime


class StrategyDetailResponse(StrategyResponse):
    """Full strategy response with config."""

    config_sexpr: str
    config_json: StrategyConfigJSON
    symbols: list[str]
    timeframe: str


class StrategyVersionResponse(BaseModel):
    """Strategy version info."""

    version: int
    config_sexpr: str
    config_json: StrategyConfigJSON
    symbols: list[str]
    timeframe: str
    changelog: str | None
    created_at: datetime


class DeploymentResponse(BaseModel):
    """Deployment info."""

    id: UUID
    strategy_id: UUID
    version: int
    environment: DeploymentEnvironment
    status: DeploymentStatus
    started_at: datetime | None
    stopped_at: datetime | None
    config_override: ConfigOverride | None
    error_message: str | None
    created_at: datetime


class ValidationResult(BaseModel):
    """Strategy validation result."""

    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ===================
# Legacy Support (for backwards compatibility)
# ===================


class IndicatorType(StrEnum):
    """Available indicator types."""

    SMA = "sma"
    EMA = "ema"
    MACD = "macd"
    ADX = "adx"
    RSI = "rsi"
    STOCHASTIC = "stochastic"
    CCI = "cci"
    WILLIAMS_R = "williams_r"
    BOLLINGER_BANDS = "bollinger_bands"
    ATR = "atr"
    KELTNER_CHANNEL = "keltner_channel"
    OBV = "obv"
    MFI = "mfi"
    VWAP = "vwap"
    DONCHIAN_CHANNEL = "donchian_channel"


class IndicatorInfoResponse(BaseModel):
    """Indicator metadata."""

    type: IndicatorType
    name: str
    description: str
    params: list[IndicatorParamInfo]
    outputs: list[str]
    category: str


class TemplateResponse(BaseModel):
    """Strategy template info."""

    id: str
    name: str
    description: str | None
    strategy_type: StrategyType
    config_sexpr: str
    config_json: StrategyConfigJSON
    tags: list[str] = Field(default_factory=list)
    difficulty: str = "beginner"
