"""Strategy Service - Pydantic schemas for API requests + proto enum helpers."""

from decimal import Decimal
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
    StrategyStatus,
)

# Proto enum prefixes for string conversion
_EXECUTION_STATUS_PREFIX = "EXECUTION_STATUS_"


# Conversion helpers: proto ValueType -> str (for display/API)


def execution_status_to_str(value: ExecutionStatus.ValueType) -> str:
    """Convert ExecutionStatus proto value to string."""
    name = ExecutionStatus.Name(value)
    if name.startswith(_EXECUTION_STATUS_PREFIX):
        return name[len(_EXECUTION_STATUS_PREFIX) :].lower()
    return name.lower()


class ConfigOverride(TypedDict, total=False):
    """Runtime configuration overrides."""

    symbols: list[str]


# Request field bounds. Caps guard the parser/DB against pathological input and
# the capital ceiling guards the money path against absurd or overflow values.
# MAX_SEXPR_LEN is public: the compile RPC bounds its input against the same cap.
MAX_SEXPR_LEN = 100_000
_MAX_DESCRIPTION_LEN = 2_000
_MAX_ALLOCATED_CAPITAL = Decimal("1000000000")


# Request Schemas


class StrategyCreate(BaseModel):
    """Schema for creating a strategy with S-expression config."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=_MAX_DESCRIPTION_LEN)
    config_sexpr: str = Field(
        ...,
        min_length=1,
        max_length=MAX_SEXPR_LEN,
        description="S-expression strategy definition",
        examples=[
            """(strategy "Balanced 60/40"
  :rebalance monthly
  (weight :method specified
    (asset VTI :weight 60)
    (asset BND :weight 40)))"""
        ],
    )


class StrategyUpdate(BaseModel):
    """Schema for updating a strategy."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=_MAX_DESCRIPTION_LEN)
    status: StrategyStatus.ValueType | None = None
    config_sexpr: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_SEXPR_LEN,
        description="New S-expression config (creates new version if changed)",
    )
    changelog: str | None = Field(
        default=None,
        max_length=_MAX_DESCRIPTION_LEN,
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
    allocated_capital: Decimal | None = Field(
        None,
        gt=0,
        le=_MAX_ALLOCATED_CAPITAL,
        description="Capital to allocate to this execution's ledger sleeve at start",
    )
    credentials_id: UUID | None = Field(
        None,
        description="Broker credentials anchoring the ledger account",
    )
