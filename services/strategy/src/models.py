"""Strategy Service - Pydantic schemas for API requests/responses."""

from datetime import datetime
from typing import TypedDict
from uuid import UUID

from pydantic import BaseModel, Field

# Import proto enum types for proper typing
from llamatrade_proto.generated.common_pb2 import (
    EXECUTION_MODE_PAPER,
    ExecutionMode,
    ExecutionStatus,
)
from llamatrade_proto.generated.strategy_pb2 import (
    AssetClass,
    IndicatorType,
    StrategyStatus,
    TemplateCategory,
    TemplateDifficulty,
)

# Proto enum prefixes for string conversion
_STRATEGY_STATUS_PREFIX = "STRATEGY_STATUS_"
_EXECUTION_STATUS_PREFIX = "EXECUTION_STATUS_"
_EXECUTION_MODE_PREFIX = "EXECUTION_MODE_"
_TEMPLATE_CATEGORY_PREFIX = "TEMPLATE_CATEGORY_"
_ASSET_CLASS_PREFIX = "ASSET_CLASS_"
_INDICATOR_TYPE_PREFIX = "INDICATOR_TYPE_"
_TEMPLATE_DIFFICULTY_PREFIX = "TEMPLATE_DIFFICULTY_"


# ===================
# Conversion helpers: proto ValueType -> str (for display/API)
# ===================


def strategy_status_to_str(value: StrategyStatus.ValueType) -> str:
    """Convert StrategyStatus proto value to string."""
    name = StrategyStatus.Name(value)
    if name.startswith(_STRATEGY_STATUS_PREFIX):
        return name[len(_STRATEGY_STATUS_PREFIX) :].lower()
    return name.lower()


def execution_status_to_str(value: ExecutionStatus.ValueType) -> str:
    """Convert ExecutionStatus proto value to string."""
    name = ExecutionStatus.Name(value)
    if name.startswith(_EXECUTION_STATUS_PREFIX):
        return name[len(_EXECUTION_STATUS_PREFIX) :].lower()
    return name.lower()


def execution_mode_to_str(value: ExecutionMode.ValueType) -> str:
    """Convert ExecutionMode proto value to string."""
    name = ExecutionMode.Name(value)
    if name.startswith(_EXECUTION_MODE_PREFIX):
        return name[len(_EXECUTION_MODE_PREFIX) :].lower()
    return name.lower()


def template_category_to_str(value: TemplateCategory.ValueType) -> str:
    """Convert TemplateCategory proto value to kebab-case string."""
    name = TemplateCategory.Name(value)
    if name.startswith(_TEMPLATE_CATEGORY_PREFIX):
        # Convert SNAKE_CASE to kebab-case: BUY_AND_HOLD -> buy-and-hold
        return name[len(_TEMPLATE_CATEGORY_PREFIX) :].lower().replace("_", "-")
    return name.lower().replace("_", "-")


def asset_class_to_str(value: AssetClass.ValueType) -> str:
    """Convert AssetClass proto value to kebab-case string."""
    name = AssetClass.Name(value)
    if name.startswith(_ASSET_CLASS_PREFIX):
        return name[len(_ASSET_CLASS_PREFIX) :].lower().replace("_", "-")
    return name.lower().replace("_", "-")


def indicator_type_to_str(value: IndicatorType.ValueType) -> str:
    """Convert IndicatorType proto value to lowercase string."""
    name = IndicatorType.Name(value)
    if name.startswith(_INDICATOR_TYPE_PREFIX):
        return name[len(_INDICATOR_TYPE_PREFIX) :].lower()
    return name.lower()


def template_difficulty_to_str(value: TemplateDifficulty.ValueType) -> str:
    """Convert TemplateDifficulty proto value to lowercase string."""
    name = TemplateDifficulty.Name(value)
    if name.startswith(_TEMPLATE_DIFFICULTY_PREFIX):
        return name[len(_TEMPLATE_DIFFICULTY_PREFIX) :].lower()
    return name.lower()


# ===================
# String to Proto conversion helpers (for API request filters)
# ===================


def str_to_template_category(value: str) -> TemplateCategory.ValueType | None:
    """Convert kebab-case string to TemplateCategory proto value."""
    if not value:
        return None
    # Convert kebab-case to SNAKE_CASE: buy-and-hold -> BUY_AND_HOLD
    enum_name = f"{_TEMPLATE_CATEGORY_PREFIX}{value.upper().replace('-', '_')}"
    try:
        return TemplateCategory.Value(enum_name)
    except ValueError:
        return None


def str_to_asset_class(value: str) -> AssetClass.ValueType | None:
    """Convert kebab-case string to AssetClass proto value."""
    if not value:
        return None
    enum_name = f"{_ASSET_CLASS_PREFIX}{value.upper().replace('-', '_')}"
    try:
        return AssetClass.Value(enum_name)
    except ValueError:
        return None


def str_to_template_difficulty(value: str) -> TemplateDifficulty.ValueType | None:
    """Convert lowercase string to TemplateDifficulty proto value."""
    if not value:
        return None
    enum_name = f"{_TEMPLATE_DIFFICULTY_PREFIX}{value.upper()}"
    try:
        return TemplateDifficulty.Value(enum_name)
    except ValueError:
        return None


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


# TemplateCategory, AssetClass, IndicatorType, TemplateDifficulty are now imported from proto


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
    status: StrategyStatus.ValueType | None = None
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
    mode: ExecutionMode.ValueType = EXECUTION_MODE_PAPER
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
    status: StrategyStatus.ValueType
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
    mode: ExecutionMode.ValueType
    status: ExecutionStatus.ValueType
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

# IndicatorType is now imported from proto


class IndicatorInfoResponse(BaseModel):
    """Indicator metadata."""

    type: IndicatorType.ValueType
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
    category: TemplateCategory.ValueType
    asset_class: AssetClass.ValueType
    config_sexpr: str
    config_json: StrategyConfigJSON
    tags: list[str] = Field(default_factory=list)
    difficulty: TemplateDifficulty.ValueType
