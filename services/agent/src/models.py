"""Agent Service - Pydantic schemas.

These schemas are used for internal API communication and validation.
They follow the naming convention: *Create, *Response, *Update, *Request.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

# =============================================================================
# Session Schemas
# =============================================================================


class SessionCreate(BaseModel):
    """Schema for creating an agent session."""

    initial_message: str | None = Field(default=None, max_length=10000)
    ui_context: dict[str, Any] | None = None


class SessionResponse(BaseModel):
    """Schema for agent session response."""

    id: UUID
    tenant_id: UUID
    user_id: UUID
    title: str | None
    status: int  # AgentSessionStatus proto int value
    message_count: int
    created_at: datetime
    last_activity_at: datetime


class SessionListResponse(BaseModel):
    """Schema for list of sessions response."""

    sessions: list[SessionResponse]
    total: int
    page: int
    page_size: int


# =============================================================================
# Message Schemas
# =============================================================================


class MessageCreate(BaseModel):
    """Schema for creating a message."""

    content: str = Field(..., min_length=1, max_length=10000)
    ui_context: dict[str, Any] | None = None


class MessageResponse(BaseModel):
    """Schema for message response."""

    id: UUID
    session_id: UUID
    role: int  # MessageRole proto int value
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    created_at: datetime


class ToolCallResponse(BaseModel):
    """Schema for tool call response."""

    id: str
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None = None
    duration_ms: int | None = None
    success: bool = True


# =============================================================================
# Artifact Schemas
# =============================================================================


class ArtifactResponse(BaseModel):
    """Schema for pending artifact response."""

    id: UUID
    session_id: UUID
    artifact_type: int  # ArtifactType proto int value
    name: str
    description: str | None
    preview_json: dict[str, Any]
    is_committed: bool
    committed_resource_id: UUID | None
    created_at: datetime


class ArtifactCommitRequest(BaseModel):
    """Schema for committing an artifact."""

    overrides: dict[str, str] | None = None


class ArtifactCommitResponse(BaseModel):
    """Schema for artifact commit response."""

    success: bool
    resource_id: UUID | None
    resource_type: str | None


# =============================================================================
# Context Schemas
# =============================================================================


class UIContextData(BaseModel):
    """Schema for UI context data passed to the agent."""

    page: str | None = None
    strategy_id: str | None = None
    backtest_id: str | None = None
    suggested_prompts: list[str] | None = None


# =============================================================================
# Stream Event Schemas
# =============================================================================


class StreamEvent(BaseModel):
    """Schema for stream events sent to the client."""

    event_type: int  # StreamEventType proto int value
    session_id: UUID | None = None
    content_delta: str | None = None
    tool_name: str | None = None
    tool_status: str | None = None
    tool_result_preview: str | None = None
    artifact: ArtifactResponse | None = None
    error_message: str | None = None
    message_id: UUID | None = None


# =============================================================================
# Validation Schemas
# =============================================================================


class DSLValidationResult(BaseModel):
    """Schema for DSL validation result."""

    valid: bool
    errors: list[str]
    warnings: list[str]
    detected_symbols: list[str]
    detected_indicators: list[str]


class StrategyArtifactData(BaseModel):
    """Schema for strategy artifact data stored in pending_artifacts."""

    name: str
    description: str | None = None
    dsl_code: str
    config_json: dict[str, Any] | None = None
    symbols: list[str] = Field(default_factory=list)
    timeframe: str = "1D"
