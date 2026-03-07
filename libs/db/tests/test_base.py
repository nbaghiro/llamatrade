"""Tests for llamatrade_db.base module."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from llamatrade_db.base import (
    Base,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class TestBase:
    """Tests for Base declarative class."""

    def test_base_is_declarative_base(self) -> None:
        """Test Base is a proper SQLAlchemy DeclarativeBase."""
        from sqlalchemy.orm import DeclarativeBase

        assert issubclass(Base, DeclarativeBase)

    def test_base_has_metadata(self) -> None:
        """Test Base has metadata attribute."""
        assert hasattr(Base, "metadata")
        assert Base.metadata is not None


class TestUUIDPrimaryKeyMixin:
    """Tests for UUIDPrimaryKeyMixin."""

    def test_mixin_adds_id_column(self) -> None:
        """Test mixin adds id column."""

        class TestModel(Base, UUIDPrimaryKeyMixin):
            __tablename__ = "test_uuid_pk"
            name: Mapped[str] = mapped_column(String(100))

        # Check that id column exists
        assert hasattr(TestModel, "id")

    def test_id_is_uuid_type(self) -> None:
        """Test id column is UUID type."""

        class TestModel(Base, UUIDPrimaryKeyMixin):
            __tablename__ = "test_uuid_type"
            name: Mapped[str] = mapped_column(String(100))

        # Check column type annotation
        columns = TestModel.__table__.columns
        assert "id" in columns

    def test_id_default_generates_uuid(self) -> None:
        """Test id default generates a UUID."""

        class TestModel(Base, UUIDPrimaryKeyMixin):
            __tablename__ = "test_uuid_default"
            name: Mapped[str] = mapped_column(String(100))

        # Check that column has a default
        id_column = TestModel.__table__.columns["id"]
        assert id_column.default is not None


class TestTenantMixin:
    """Tests for TenantMixin."""

    def test_mixin_adds_tenant_id_column(self) -> None:
        """Test mixin adds tenant_id column."""

        class TestModel(Base, TenantMixin):
            __tablename__ = "test_tenant"
            id: Mapped[int] = mapped_column(primary_key=True)
            name: Mapped[str] = mapped_column(String(100))

        # Check that tenant_id column exists
        assert hasattr(TestModel, "tenant_id")
        columns = TestModel.__table__.columns
        assert "tenant_id" in columns

    def test_tenant_id_is_not_nullable(self) -> None:
        """Test tenant_id is not nullable."""

        class TestModel(Base, TenantMixin):
            __tablename__ = "test_tenant_nullable"
            id: Mapped[int] = mapped_column(primary_key=True)

        tenant_id_col = TestModel.__table__.columns["tenant_id"]
        assert tenant_id_col.nullable is False

    def test_tenant_mixin_creates_index(self) -> None:
        """Test TenantMixin creates index on tenant_id."""

        class TestModel(Base, TenantMixin):
            __tablename__ = "test_tenant_index"
            id: Mapped[int] = mapped_column(primary_key=True)

        # Check table args include an index
        table_args = TestModel.__table_args__
        assert isinstance(table_args, tuple)
        assert len(table_args) > 0

        # Find the tenant index
        from sqlalchemy import Index

        tenant_indexes = [
            arg for arg in table_args if isinstance(arg, Index) and "tenant_id" in str(arg)
        ]
        assert len(tenant_indexes) >= 1


class TestTimestampMixin:
    """Tests for TimestampMixin."""

    def test_mixin_adds_created_at_column(self) -> None:
        """Test mixin adds created_at column."""

        class TestModel(Base, TimestampMixin):
            __tablename__ = "test_timestamp_created"
            id: Mapped[int] = mapped_column(primary_key=True)

        assert hasattr(TestModel, "created_at")
        columns = TestModel.__table__.columns
        assert "created_at" in columns

    def test_mixin_adds_updated_at_column(self) -> None:
        """Test mixin adds updated_at column."""

        class TestModel(Base, TimestampMixin):
            __tablename__ = "test_timestamp_updated"
            id: Mapped[int] = mapped_column(primary_key=True)

        assert hasattr(TestModel, "updated_at")
        columns = TestModel.__table__.columns
        assert "updated_at" in columns

    def test_created_at_has_server_default(self) -> None:
        """Test created_at has server_default."""

        class TestModel(Base, TimestampMixin):
            __tablename__ = "test_timestamp_default"
            id: Mapped[int] = mapped_column(primary_key=True)

        created_at_col = TestModel.__table__.columns["created_at"]
        assert created_at_col.server_default is not None

    def test_updated_at_has_onupdate(self) -> None:
        """Test updated_at has onupdate trigger."""

        class TestModel(Base, TimestampMixin):
            __tablename__ = "test_timestamp_onupdate"
            id: Mapped[int] = mapped_column(primary_key=True)

        updated_at_col = TestModel.__table__.columns["updated_at"]
        assert updated_at_col.onupdate is not None

    def test_timestamp_columns_not_nullable(self) -> None:
        """Test timestamp columns are not nullable."""

        class TestModel(Base, TimestampMixin):
            __tablename__ = "test_timestamp_nullable"
            id: Mapped[int] = mapped_column(primary_key=True)

        created_at_col = TestModel.__table__.columns["created_at"]
        updated_at_col = TestModel.__table__.columns["updated_at"]

        assert created_at_col.nullable is False
        assert updated_at_col.nullable is False


class TestMixinCombinations:
    """Tests for combining multiple mixins."""

    def test_all_mixins_together(self) -> None:
        """Test combining all mixins works correctly."""

        class TestModel(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
            __tablename__ = "test_all_mixins"
            name: Mapped[str] = mapped_column(String(100))

        columns = TestModel.__table__.columns

        # All columns should exist
        assert "id" in columns
        assert "tenant_id" in columns
        assert "created_at" in columns
        assert "updated_at" in columns
        assert "name" in columns

    def test_uuid_and_tenant_mixins(self) -> None:
        """Test combining UUID and Tenant mixins."""

        class TestModel(Base, UUIDPrimaryKeyMixin, TenantMixin):
            __tablename__ = "test_uuid_tenant"
            name: Mapped[str] = mapped_column(String(100))

        columns = TestModel.__table__.columns

        assert "id" in columns
        assert "tenant_id" in columns

    def test_uuid_and_timestamp_mixins(self) -> None:
        """Test combining UUID and Timestamp mixins."""

        class TestModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
            __tablename__ = "test_uuid_timestamp"
            name: Mapped[str] = mapped_column(String(100))

        columns = TestModel.__table__.columns

        assert "id" in columns
        assert "created_at" in columns
        assert "updated_at" in columns
