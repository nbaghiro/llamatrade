"""Strategy management models.

Enum columns use PostgreSQL native ENUM types with TypeDecorators for transparent
conversion between proto int values and DB enum strings.

StrategyType remains as Postgres ENUM because it represents business categories
(TREND_FOLLOWING, MOMENTUM, etc.) which are not in proto definitions.

See libs/db/llamatrade_db/models/enum_types.py for TypeDecorator implementations.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from llamatrade_db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from llamatrade_db.models._enum_types import (
    ExecutionModeType,
    ExecutionStatusType,
    StrategyStatusType,
)

if TYPE_CHECKING:
    from llamatrade_db.models.portfolio import (
        StrategyPerformanceMetrics,
        StrategyPerformanceSnapshot,
    )


class StrategyType(PyEnum):
    """Types of trading strategies (business categorization, not proto-defined)."""

    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    MOMENTUM = "momentum"
    BREAKOUT = "breakout"
    CUSTOM = "custom"


class Strategy(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """
    Trading strategy definition.

    Stores metadata about a strategy. The actual configuration is stored
    in StrategyVersion records, with current_version pointing to the active version.
    """

    __tablename__ = "strategies"
    __table_args__ = (
        Index("ix_strategies_tenant_name", "tenant_id", "name"),
        Index("ix_strategies_tenant_status", "tenant_id", "status"),
        Index("ix_strategies_tenant_type", "tenant_id", "strategy_type"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    strategy_type: Mapped[StrategyType] = mapped_column(
        Enum(StrategyType, name="strategy_type_enum"),
        nullable=False,
        default=StrategyType.CUSTOM,
    )
    status: Mapped[int] = mapped_column(StrategyStatusType(), nullable=False, default=1)  # DRAFT=1
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    # Relationships
    versions: Mapped[list[StrategyVersion]] = relationship(
        "StrategyVersion",
        back_populates="strategy",
        cascade="all, delete-orphan",
        order_by="StrategyVersion.version.desc()",
    )
    executions: Mapped[list[StrategyExecution]] = relationship(
        "StrategyExecution",
        back_populates="strategy",
        cascade="all, delete-orphan",
    )


class StrategyVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Immutable version snapshot of a strategy configuration.

    Each time a strategy's configuration changes, a new version is created.
    The config_sexpr field stores the canonical S-expression format, while
    config_json stores a parsed JSON representation for querying.
    """

    __tablename__ = "strategy_versions"
    __table_args__ = (
        Index("ix_strategy_versions_strategy_version", "strategy_id", "version", unique=True),
        Index("ix_strategy_versions_symbols", "symbols", postgresql_using="gin"),
    )

    strategy_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("strategies.id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    # S-expression source (canonical format)
    config_sexpr: Mapped[str] = mapped_column(Text, nullable=False)

    # Parsed JSON for querying (denormalized from config_sexpr)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Denormalized fields for efficient filtering
    symbols: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)

    # Additional parameters (e.g., ui_state for visual builder)
    parameters: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    changelog: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    # Relationships
    strategy: Mapped[Strategy] = relationship("Strategy", back_populates="versions")


class StrategyExecution(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """
    Links a strategy version to live or paper trading.

    Tracks the execution state of a strategy - whether it's running,
    paused, or stopped, and which version is being executed.
    """

    __tablename__ = "strategy_executions"
    __table_args__ = (
        Index("ix_executions_tenant_status", "tenant_id", "status"),
        Index("ix_executions_strategy", "strategy_id"),
    )

    strategy_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("strategies.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    mode: Mapped[int] = mapped_column(ExecutionModeType(), nullable=False)
    status: Mapped[int] = mapped_column(
        ExecutionStatusType(), nullable=False, default=1
    )  # PENDING=1

    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Runtime configuration overrides (e.g., different symbols, risk params)
    config_override: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Error info if status is ERROR
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Performance tracking columns
    allocated_capital: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    current_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    positions_count: Mapped[int] = mapped_column(
        Integer, nullable=True, default=0, server_default="0"
    )
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)  # UI color for charts

    # Relationships
    strategy: Mapped[Strategy] = relationship("Strategy", back_populates="executions")
    performance_metrics: Mapped[StrategyPerformanceMetrics | None] = relationship(
        "StrategyPerformanceMetrics",
        back_populates="execution",
        uselist=False,
        cascade="all, delete-orphan",
    )
    performance_snapshots: Mapped[list[StrategyPerformanceSnapshot]] = relationship(
        "StrategyPerformanceSnapshot",
        back_populates="execution",
        cascade="all, delete-orphan",
    )


class StrategyTemplate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Pre-built strategy templates (not tenant-scoped).

    Templates provide starting points for users to create their own strategies.
    They include a complete S-expression configuration that can be customized.
    """

    __tablename__ = "strategy_templates"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    strategy_type: Mapped[StrategyType] = mapped_column(
        Enum(StrategyType, name="strategy_type_enum", create_constraint=False),
        nullable=False,
    )

    # S-expression template
    config_sexpr: Mapped[str] = mapped_column(Text, nullable=False)

    # Parsed JSON for display
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Metadata
    tags: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    difficulty: Mapped[str] = mapped_column(String(20), default="beginner", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
