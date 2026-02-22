"""Strategy management models."""

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from llamatrade_db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Strategy(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """Trading strategy definition."""

    __tablename__ = "strategies"
    __table_args__ = (Index("ix_strategies_tenant_name", "tenant_id", "name"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    strategy_type: Mapped[str] = mapped_column(String(50), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    # Relationships
    versions: Mapped[list["StrategyVersion"]] = relationship(
        "StrategyVersion", back_populates="strategy"
    )


class StrategyVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Version history for a strategy."""

    __tablename__ = "strategy_versions"
    __table_args__ = (
        Index("ix_strategy_versions_strategy_version", "strategy_id", "version", unique=True),
    )

    strategy_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("strategies.id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    changelog: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    # Relationships
    strategy: Mapped["Strategy"] = relationship("Strategy", back_populates="versions")


class StrategyTemplate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Pre-built strategy templates (not tenant-scoped)."""

    __tablename__ = "strategy_templates"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    strategy_type: Mapped[str] = mapped_column(String(50), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    indicators: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
