"""Strategy management models."""

from datetime import datetime
from enum import Enum as PyEnum
from uuid import UUID

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from llamatrade_db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class StrategyType(PyEnum):
    """Types of trading strategies."""

    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    MOMENTUM = "momentum"
    BREAKOUT = "breakout"
    CUSTOM = "custom"


class StrategyStatus(PyEnum):
    """Strategy lifecycle status."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class DeploymentStatus(PyEnum):
    """Deployment lifecycle status."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class DeploymentEnvironment(PyEnum):
    """Trading environment for deployment."""

    PAPER = "paper"
    LIVE = "live"


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
    status: Mapped[StrategyStatus] = mapped_column(
        Enum(StrategyStatus, name="strategy_status_enum"),
        nullable=False,
        default=StrategyStatus.DRAFT,
    )
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    # Relationships
    versions: Mapped[list["StrategyVersion"]] = relationship(
        "StrategyVersion",
        back_populates="strategy",
        cascade="all, delete-orphan",
        order_by="StrategyVersion.version.desc()",
    )
    deployments: Mapped[list["StrategyDeployment"]] = relationship(
        "StrategyDeployment",
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
    config_json: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Denormalized fields for efficient filtering
    symbols: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)

    changelog: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    # Relationships
    strategy: Mapped["Strategy"] = relationship("Strategy", back_populates="versions")


class StrategyDeployment(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """
    Links a strategy version to live or paper trading.

    Tracks the deployment state of a strategy - whether it's running,
    paused, or stopped, and which version is deployed.
    """

    __tablename__ = "strategy_deployments"
    __table_args__ = (
        Index("ix_deployments_tenant_status", "tenant_id", "status"),
        Index("ix_deployments_strategy", "strategy_id"),
    )

    strategy_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("strategies.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    environment: Mapped[DeploymentEnvironment] = mapped_column(
        Enum(DeploymentEnvironment, name="deployment_environment_enum"),
        nullable=False,
    )
    status: Mapped[DeploymentStatus] = mapped_column(
        Enum(DeploymentStatus, name="deployment_status_enum"),
        nullable=False,
        default=DeploymentStatus.PENDING,
    )

    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Runtime configuration overrides (e.g., different symbols, risk params)
    config_override: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Error info if status is ERROR
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    strategy: Mapped["Strategy"] = relationship("Strategy", back_populates="deployments")


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
    config_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Metadata
    tags: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    difficulty: Mapped[str] = mapped_column(String(20), default="beginner", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
