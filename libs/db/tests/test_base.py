"""Tests for the llamatrade_db.base mixins (column type/default contracts)."""

from uuid import UUID

from sqlalchemy import DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from llamatrade_db.base import (
    Base,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class TestUUIDPrimaryKeyMixin:
    def test_id_is_uuid_primary_key_with_uuid4_default(self) -> None:
        """The id column pairs the PG UUID type with a client-side uuid4 default."""

        class UuidPkModel(Base, UUIDPrimaryKeyMixin):
            __tablename__ = "test_uuid_pk"
            name: Mapped[str] = mapped_column(String(100))

        column = UuidPkModel.__table__.columns["id"]
        assert column.primary_key is True
        assert isinstance(column.type, PG_UUID)
        assert column.type.as_uuid is True
        # SQLAlchemy wraps zero-arg callables, so assert the behavior, not identity.
        assert column.default is not None and column.default.is_callable
        generated = {column.default.arg({}) for _ in range(3)}
        assert len(generated) == 3 and all(isinstance(v, UUID) for v in generated)


class TestTenantMixin:
    def test_tenant_id_is_required_uuid(self) -> None:
        class TenantModel(Base, TenantMixin):
            __tablename__ = "test_tenant"
            id: Mapped[int] = mapped_column(primary_key=True)

        column = TenantModel.__table__.columns["tenant_id"]
        assert column.nullable is False
        assert isinstance(column.type, PG_UUID)

    def test_mixin_contributes_named_tenant_index(self) -> None:
        """__table_args__ carries exactly the ix_<table>_tenant_id index on tenant_id."""

        class TenantIndexModel(Base, TenantMixin):
            __tablename__ = "test_tenant_index"
            id: Mapped[int] = mapped_column(primary_key=True)

        indexes = [arg for arg in TenantIndexModel.__table_args__ if isinstance(arg, Index)]
        (tenant_index,) = indexes
        assert tenant_index.name == "ix_test_tenant_index_tenant_id"
        assert list(tenant_index.expressions) == ["tenant_id"]


class TestTimestampMixin:
    def test_timestamp_columns_are_tz_aware_with_server_defaults(self) -> None:
        """created_at/updated_at: timezone-aware, required, server-defaulted;
        updated_at also refreshes via onupdate."""

        class TimestampModel(Base, TimestampMixin):
            __tablename__ = "test_timestamp"
            id: Mapped[int] = mapped_column(primary_key=True)

        created = TimestampModel.__table__.columns["created_at"]
        updated = TimestampModel.__table__.columns["updated_at"]
        for column in (created, updated):
            assert column.nullable is False
            assert isinstance(column.type, DateTime)
            assert column.type.timezone is True
            assert column.server_default is not None
        assert created.onupdate is None
        assert updated.onupdate is not None


class TestMixinCombinations:
    def test_all_mixins_compose_without_clobbering_table_args(self) -> None:
        """All three mixins stack on one model; the tenant index survives the merge."""

        class AllMixinsModel(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
            __tablename__ = "test_all_mixins"
            name: Mapped[str] = mapped_column(String(100))

        columns = AllMixinsModel.__table__.columns
        assert {"id", "tenant_id", "created_at", "updated_at", "name"} <= set(columns.keys())
        index_names = {i.name for i in AllMixinsModel.__table__.indexes}
        assert "ix_test_all_mixins_tenant_id" in index_names
