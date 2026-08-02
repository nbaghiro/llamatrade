"""Tests for llamatrade_db.models.strategy module."""

from llamatrade_db.models.strategy import (
    Strategy,
    StrategyExecution,
    StrategyType,
    StrategyVersion,
)
from llamatrade_proto.generated.common_pb2 import (
    EXECUTION_MODE_LIVE,
    EXECUTION_MODE_PAPER,
    EXECUTION_STATUS_ERROR,
    EXECUTION_STATUS_PAUSED,
    EXECUTION_STATUS_PENDING,
    EXECUTION_STATUS_RUNNING,
    EXECUTION_STATUS_STOPPED,
)
from llamatrade_proto.generated.strategy_pb2 import (
    STRATEGY_STATUS_ACTIVE,
    STRATEGY_STATUS_ARCHIVED,
    STRATEGY_STATUS_DRAFT,
    STRATEGY_STATUS_PAUSED,
)


class TestStrategyType:
    """Tests for StrategyType enum (business categorization, not proto-defined)."""

    def test_strategy_type_values(self) -> None:
        """Test StrategyType has expected values."""
        assert StrategyType.TREND_FOLLOWING.value == "trend_following"
        assert StrategyType.MEAN_REVERSION.value == "mean_reversion"
        assert StrategyType.MOMENTUM.value == "momentum"
        assert StrategyType.BREAKOUT.value == "breakout"
        assert StrategyType.CUSTOM.value == "custom"

    def test_strategy_type_count(self) -> None:
        """Test StrategyType has 5 values."""
        assert len(StrategyType) == 5


class TestStrategyStatus:
    """Tests for StrategyStatus proto constants."""

    def test_strategy_status_values(self) -> None:
        """Test StrategyStatus has expected int values (from proto)."""
        assert STRATEGY_STATUS_DRAFT == 1
        assert STRATEGY_STATUS_ACTIVE == 2
        assert STRATEGY_STATUS_PAUSED == 3
        assert STRATEGY_STATUS_ARCHIVED == 4


class TestExecutionStatus:
    """Tests for ExecutionStatus proto constants."""

    def test_execution_status_values(self) -> None:
        """Test ExecutionStatus has expected int values (from proto)."""
        assert EXECUTION_STATUS_PENDING == 1
        assert EXECUTION_STATUS_RUNNING == 2
        assert EXECUTION_STATUS_PAUSED == 3
        assert EXECUTION_STATUS_STOPPED == 4
        assert EXECUTION_STATUS_ERROR == 5


class TestExecutionMode:
    """Tests for ExecutionMode proto constants."""

    def test_execution_mode_values(self) -> None:
        """Test ExecutionMode has expected int values (from proto)."""
        assert EXECUTION_MODE_PAPER == 1
        assert EXECUTION_MODE_LIVE == 2


class TestStrategy:
    """Tests for Strategy model."""

    def test_strategy_tablename(self) -> None:
        """Test Strategy has correct tablename."""
        assert Strategy.__tablename__ == "strategies"

    def test_strategy_has_required_columns(self) -> None:
        """Test Strategy has all required columns."""
        columns = Strategy.__table__.columns
        assert "id" in columns
        assert "tenant_id" in columns
        assert "name" in columns
        assert "description" in columns
        assert "status" in columns
        assert "is_public" in columns
        assert "current_version" in columns
        assert "created_by" in columns
        assert "created_at" in columns
        assert "updated_at" in columns

    def test_strategy_name_not_nullable(self) -> None:
        """Test name column is not nullable."""
        col = Strategy.__table__.columns["name"]
        assert col.nullable is False

    def test_strategy_has_relationships(self) -> None:
        """Test Strategy has expected relationships."""
        assert hasattr(Strategy, "versions")
        assert hasattr(Strategy, "executions")

    def test_strategy_has_indexes(self) -> None:
        """Test Strategy has expected indexes."""
        table_args = Strategy.__table_args__
        assert table_args is not None
        # Should have at least 2 indexes (tenant_name, tenant_status)
        from sqlalchemy import Index

        indexes = [arg for arg in table_args if isinstance(arg, Index)]
        assert len(indexes) >= 2


class TestStrategyVersion:
    """Tests for StrategyVersion model."""

    def test_strategy_version_tablename(self) -> None:
        """Test StrategyVersion has correct tablename."""
        assert StrategyVersion.__tablename__ == "strategy_versions"

    def test_strategy_version_has_required_columns(self) -> None:
        """Test StrategyVersion has all required columns."""
        columns = StrategyVersion.__table__.columns
        assert "id" in columns
        assert "strategy_id" in columns
        assert "version" in columns
        assert "config_sexpr" in columns
        assert "symbols" in columns
        assert "rebalance" in columns
        assert "changelog" in columns
        # Derived representations are not stored — the DSL string is the source of truth.
        assert "config_json" not in columns
        assert "parameters" not in columns
        assert "timeframe" not in columns
        assert "created_by" in columns

    def test_config_sexpr_not_nullable(self) -> None:
        """Test config_sexpr is not nullable."""
        col = StrategyVersion.__table__.columns["config_sexpr"]
        assert col.nullable is False

    def test_config_sexpr_is_the_stored_representation(self) -> None:
        """The DSL string is stored and required; derived forms are not stored."""
        assert StrategyVersion.__table__.columns["config_sexpr"].nullable is False
        assert "config_json" not in StrategyVersion.__table__.columns
        assert "parameters" not in StrategyVersion.__table__.columns

    def test_has_strategy_relationship(self) -> None:
        """Test StrategyVersion has strategy relationship."""
        assert hasattr(StrategyVersion, "strategy")


class TestStrategyExecution:
    """Tests for StrategyExecution model."""

    def test_strategy_execution_tablename(self) -> None:
        """Test StrategyExecution has correct tablename."""
        assert StrategyExecution.__tablename__ == "strategy_executions"

    def test_strategy_execution_has_required_columns(self) -> None:
        """Test StrategyExecution has all required columns."""
        columns = StrategyExecution.__table__.columns
        assert "id" in columns
        assert "tenant_id" in columns
        assert "strategy_id" in columns
        assert "version" in columns
        assert "mode" in columns
        assert "status" in columns
        assert "started_at" in columns
        assert "stopped_at" in columns
        assert "config_override" in columns
        assert "error_message" in columns

    def test_has_strategy_relationship(self) -> None:
        """Test StrategyExecution has strategy relationship."""
        assert hasattr(StrategyExecution, "strategy")
