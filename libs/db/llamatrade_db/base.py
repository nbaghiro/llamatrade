"""Base class and mixins for SQLAlchemy ORM models."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

# Type alias for SQLAlchemy __table_args__
# Can be a tuple of schema items (Index, Constraint, etc.) optionally ending with a dict
TableArgsType = tuple[Any, ...]


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class UUIDPrimaryKeyMixin:
    """Mixin that adds a UUID primary key column."""

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )


class TenantMixin:
    """Mixin that adds tenant_id column with index for multi-tenant tables."""

    # Note: index is created via __table_args__ below with explicit name
    # Do NOT add index=True here as it creates a duplicate index
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
    )

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> TableArgsType:
        """Create index on tenant_id for efficient tenant filtering."""
        existing_args: TableArgsType | dict[str, Any] | None = getattr(
            super(), "__table_args__", None
        )
        # __tablename__ is defined on concrete model classes that inherit this mixin
        tablename: str = getattr(cls, "__tablename__", "unknown")
        tenant_index: Index = Index(
            f"ix_{tablename}_tenant_id",
            "tenant_id",
        )

        if existing_args is None:
            return (tenant_index,)
        elif isinstance(existing_args, dict):
            return (tenant_index, existing_args)
        else:
            # existing_args must be a tuple at this point
            return existing_args + (tenant_index,)


class TimestampMixin:
    """Mixin that adds created_at and updated_at columns with automatic timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
