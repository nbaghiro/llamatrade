"""Agent conversation models.

This module contains models for the AI Strategy Agent (Copilot) feature.
All tables are tenant-scoped for multi-tenancy isolation.

Tables:
- agent_sessions: Conversation threads
- agent_messages: Individual chat messages
- pending_artifacts: Generated resources awaiting user confirmation
- tool_call_logs: Audit trail of tool executions
- agent_memory_facts: Extracted user facts and preferences
- agent_memory_embeddings: Vector embeddings for semantic search
- agent_session_summaries: Condensed session summaries
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from llamatrade_db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from llamatrade_db.models._enum_types import (
    AgentSessionStatusType,
    ArtifactTypeType,
    MemoryFactCategoryType,
    MessageRoleType,
)
from llamatrade_proto.generated import agent_pb2

# =============================================================================
# Memory Fact Categories (stored as PostgreSQL ENUM)
# =============================================================================


class MemoryFactCategory(StrEnum):
    """Categories for extracted memory facts."""

    USER_PREFERENCE = "user_preference"  # "prefers momentum strategies"
    RISK_TOLERANCE = "risk_tolerance"  # "moderate risk, max 15% drawdown"
    INVESTMENT_GOAL = "investment_goal"  # "retirement in 10 years"
    ASSET_PREFERENCE = "asset_preference"  # "likes tech, avoids energy"
    STRATEGY_DECISION = "strategy_decision"  # "chose 60/40 allocation"
    TRADING_BEHAVIOR = "trading_behavior"  # "rebalances monthly"
    FEEDBACK = "feedback"  # "liked the momentum suggestion"


# Note: Enum type decorators are defined in _enum_types.py
# They convert between proto int values and PostgreSQL ENUM strings


class AgentSession(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """
    Agent conversation session.

    Each session represents a conversation thread between the user and the
    AI Strategy Agent. Sessions can be resumed and maintain full context.
    """

    __tablename__ = "agent_sessions"
    __table_args__ = (
        Index("ix_agent_sessions_tenant_user", "tenant_id", "user_id"),
        Index("ix_agent_sessions_tenant_status", "tenant_id", "status"),
        Index("ix_agent_sessions_last_activity", "last_activity_at"),
    )

    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[agent_pb2.AgentSessionStatus.ValueType] = mapped_column(
        AgentSessionStatusType(), nullable=False, default=1
    )  # ACTIVE=1
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    messages: Mapped[list[AgentMessage]] = relationship(
        "AgentMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AgentMessage.created_at.asc()",
    )
    pending_artifacts: Mapped[list[PendingArtifact]] = relationship(
        "PendingArtifact",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    tool_call_logs: Mapped[list[ToolCallLog]] = relationship(
        "ToolCallLog",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    summary: Mapped[AgentSessionSummary | None] = relationship(
        "AgentSessionSummary",
        back_populates="session",
        cascade="all, delete-orphan",
        uselist=False,  # 1:1 relationship
    )


class AgentMessage(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """
    Individual message in an agent conversation.

    Stores both user and assistant messages. Tool calls made during
    assistant responses are stored as JSON for the full context.
    """

    __tablename__ = "agent_messages"
    __table_args__ = (
        Index("ix_agent_messages_session", "session_id"),
        Index("ix_agent_messages_tenant_session", "tenant_id", "session_id"),
    )

    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[agent_pb2.MessageRole.ValueType] = mapped_column(MessageRoleType(), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Tool calls made during this assistant message (JSON array)
    # Format: [{"id": "...", "name": "...", "arguments": {...}, "result": {...}}]
    tool_calls_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    session: Mapped[AgentSession] = relationship("AgentSession", back_populates="messages")


class PendingArtifact(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """
    Generated resource awaiting user confirmation.

    When the agent generates a strategy (or other resource), it's stored
    here as a "pending" artifact. The user can review, modify, and then
    commit it to create the actual resource.
    """

    __tablename__ = "pending_artifacts"
    __table_args__ = (
        Index("ix_pending_artifacts_session", "session_id"),
        Index("ix_pending_artifacts_tenant", "tenant_id"),
        Index("ix_pending_artifacts_committed", "is_committed"),
    )

    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_type: Mapped[agent_pb2.ArtifactType.ValueType] = mapped_column(
        ArtifactTypeType(), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Full artifact content as JSON (e.g., strategy DSL, config, etc.)
    artifact_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Commit state
    is_committed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    committed_resource_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    session: Mapped[AgentSession] = relationship("AgentSession", back_populates="pending_artifacts")


class ToolCallLog(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """
    Audit log of tool executions.

    Tracks every tool call made by the agent for debugging, analytics,
    and rate limiting purposes.
    """

    __tablename__ = "tool_call_logs"
    __table_args__ = (
        Index("ix_tool_call_logs_session", "session_id"),
        Index("ix_tool_call_logs_tenant_tool", "tenant_id", "tool_name"),
        Index("ix_tool_call_logs_tenant_created", "tenant_id", "created_at"),
    )

    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    arguments_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    session: Mapped[AgentSession] = relationship("AgentSession", back_populates="tool_call_logs")


# =============================================================================
# Memory Models
# =============================================================================


class AgentMemoryFact(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """
    Extracted user facts for cross-session memory.

    Each fact represents a piece of information learned about the user
    during conversations, such as preferences, goals, or decisions.
    Facts can be superseded when updated information is learned.
    """

    __tablename__ = "agent_memory_facts"
    __table_args__ = (
        Index("ix_agent_memory_facts_tenant_user", "tenant_id", "user_id"),
        Index("ix_agent_memory_facts_tenant_category", "tenant_id", "category"),
        Index("ix_agent_memory_facts_tenant_active", "tenant_id", "is_active"),
        Index("ix_agent_memory_facts_last_accessed", "last_accessed_at"),
    )

    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    category: Mapped[str] = mapped_column(MemoryFactCategoryType(), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)

    # Source tracking
    source_session_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_message_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    extraction_method: Mapped[str] = mapped_column(
        String(20), nullable=False, default="heuristic"
    )  # "heuristic" | "llm"

    # Lifecycle management
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    supersedes_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_memory_facts.id", ondelete="SET NULL"),
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Access tracking for relevance decay
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class AgentMemoryEmbedding(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """
    Vector embeddings for semantic memory search.

    Stores embeddings for facts, summaries, and strategies to enable
    semantic similarity search via pgvector.
    """

    __tablename__ = "agent_memory_embeddings"
    __table_args__ = (
        Index("ix_agent_memory_embeddings_tenant_user", "tenant_id", "user_id"),
        Index("ix_agent_memory_embeddings_source", "source_id"),
        # Note: Vector index is created in migration with specific parameters
    )

    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    embedding_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "fact" | "summary" | "strategy"

    # Vector embedding - stored as array, indexed via pgvector
    # Using ARRAY for compatibility; pgvector operations done via raw SQL
    embedding: Mapped[list[float]] = mapped_column(ARRAY(Float, dimensions=1536), nullable=False)

    # Source reference
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    embedding_model: Mapped[str] = mapped_column(
        String(50), nullable=False, default="text-embedding-3-small"
    )


class AgentSessionSummary(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """
    Condensed summaries of agent conversation sessions.

    Generated when a session completes or after extended inactivity.
    Enables quick recall of past conversation context without
    loading full message history.
    """

    __tablename__ = "agent_session_summaries"
    __table_args__ = (
        Index("ix_agent_session_summaries_tenant_user", "tenant_id", "user_id"),
        Index("ix_agent_session_summaries_session", "session_id"),
    )

    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # 1:1 with sessions
    )

    # Summary content
    summary_short: Mapped[str] = mapped_column(Text, nullable=False)  # 1-2 sentences
    summary_detailed: Mapped[str] = mapped_column(Text, nullable=False)  # Full summary

    # Structured metadata (JSONB for flexibility)
    topics: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    strategies_discussed: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    decisions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    # State tracking for incremental updates
    message_count_at_summary: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    session: Mapped[AgentSession] = relationship("AgentSession", back_populates="summary")
