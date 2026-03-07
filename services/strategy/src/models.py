"""Strategy Service - Pydantic schemas for API requests/responses."""

from datetime import datetime
from enum import StrEnum
from typing import TypedDict
from uuid import UUID

from pydantic import BaseModel, Field

# Import proto enum descriptors for conversion helpers and constants
from llamatrade_proto.generated.common_pb2 import (
    EXECUTION_MODE_PAPER,
)
from llamatrade_proto.generated.common_pb2 import (
    ExecutionMode as ExecutionModeEnum,
)
from llamatrade_proto.generated.common_pb2 import (
    ExecutionStatus as ExecutionStatusEnum,
)
from llamatrade_proto.generated.strategy_pb2 import (
    StrategyStatus as StrategyStatusEnum,
)

# Proto enum prefixes for string conversion
_STRATEGY_STATUS_PREFIX = "STRATEGY_STATUS_"
_EXECUTION_STATUS_PREFIX = "EXECUTION_STATUS_"
_EXECUTION_MODE_PREFIX = "EXECUTION_MODE_"


# ===================
# Conversion helpers: proto int -> str (for display/API)
# ===================


def strategy_status_to_str(value: int) -> str:
    """Convert StrategyStatus proto int to string."""
    name = StrategyStatusEnum.Name(value)
    if name.startswith(_STRATEGY_STATUS_PREFIX):
        return name[len(_STRATEGY_STATUS_PREFIX) :].lower()
    return name.lower()


def execution_status_to_str(value: int) -> str:
    """Convert ExecutionStatus proto int to string."""
    name = ExecutionStatusEnum.Name(value)
    if name.startswith(_EXECUTION_STATUS_PREFIX):
        return name[len(_EXECUTION_STATUS_PREFIX) :].lower()
    return name.lower()


def execution_mode_to_str(value: int) -> str:
    """Convert ExecutionMode proto int to string."""
    name = ExecutionModeEnum.Name(value)
    if name.startswith(_EXECUTION_MODE_PREFIX):
        return name[len(_EXECUTION_MODE_PREFIX) :].lower()
    return name.lower()


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
    """Strategy types (business categorization, not proto-defined)."""

    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    MOMENTUM = "momentum"
    BREAKOUT = "breakout"
    CUSTOM = "custom"


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
    parameters: dict[str, str] | None = Field(
        default=None,
        description="Additional parameters (e.g., ui_state for visual builder)",
    )


class StrategyUpdate(BaseModel):
    """Schema for updating a strategy."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: int | None = None  # StrategyStatus proto int
    config_sexpr: str | None = Field(
        default=None,
        description="New S-expression config (creates new version if changed)",
    )
    parameters: dict[str, str] | None = Field(
        default=None,
        description="Additional parameters (e.g., ui_state for visual builder)",
    )
    changelog: str | None = Field(
        default=None,
        description="Change summary for version history (only used when config_sexpr changes)",
    )


class ExecutionCreate(BaseModel):
    """Schema for creating an execution."""

    version: int | None = Field(
        None,
        description="Strategy version to execute (defaults to current_version)",
    )
    mode: int = EXECUTION_MODE_PAPER  # ExecutionMode proto int
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
    status: int  # StrategyStatus proto int
    current_version: int
    created_at: datetime
    updated_at: datetime


class StrategyDetailResponse(StrategyResponse):
    """Full strategy response with config."""

    config_sexpr: str
    config_json: StrategyConfigJSON
    symbols: list[str]
    timeframe: str
    parameters: dict[str, str] = Field(default_factory=dict)


class StrategyVersionResponse(BaseModel):
    """Strategy version info."""

    version: int
    config_sexpr: str
    config_json: StrategyConfigJSON
    symbols: list[str]
    timeframe: str
    changelog: str | None
    created_at: datetime
    parameters: dict[str, str] = Field(default_factory=dict)


class ExecutionResponse(BaseModel):
    """Execution info."""

    id: UUID
    strategy_id: UUID
    version: int
    mode: int  # ExecutionMode proto int
    status: int  # ExecutionStatus proto int
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
    detected_symbols: list[str] = Field(default_factory=list)
    detected_indicators: list[str] = Field(default_factory=list)


# ===================
# Indicator Types
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
