"""Unit tests for StrategyService with allocation-based DSL support."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from llamatrade_proto.generated.common_pb2 import EXECUTION_MODE_PAPER
from llamatrade_proto.generated.strategy_pb2 import (
    STRATEGY_STATUS_ACTIVE,
)

from src.models import ExecutionCreate, StrategyCreate, StrategyUpdate
from src.services.strategy_service import StrategyService

# ===================
# Sample S-expressions (allocation-based format)
# ===================

VALID_RSI_STRATEGY = """(strategy "RSI Mean Reversion"
  :rebalance daily
  :benchmark SPY
  (if (< (rsi SPY 14) 30)
    (asset SPY :weight 100)
    (else (asset TLT :weight 100))))"""

VALID_MA_CROSSOVER = """(strategy "MA Crossover"
  :rebalance daily
  :benchmark SPY
  (if (crosses-above (sma SPY 20) (sma SPY 50))
    (asset SPY :weight 100)
    (else (asset AGG :weight 100))))"""

VALID_EQUAL_WEIGHT = """(strategy "Equal Weight Portfolio"
  :rebalance monthly
  :benchmark SPY
  (weight :method equal
    (asset QQQ)
    (asset IWM)))"""

INVALID_SYNTAX = '(strategy "broken'  # Missing closing quotes and paren

INVALID_MISSING_BODY = """(strategy "No Body"
  :benchmark SPY
  :rebalance monthly)"""


# Proto status int mappings for tests
_STATUS_STR_TO_INT = {"draft": 1, "active": 2, "paused": 3, "archived": 4}


def make_mock_strategy(
    id: UUID | None = None,
    tenant_id: UUID | None = None,
    name: str = "Test Strategy",
    description: str | None = None,
    status: int | str = 1,  # Proto int or string: DRAFT=1, ACTIVE=2, PAUSED=3, ARCHIVED=4
    current_version: int = 1,
    created_by: UUID | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> MagicMock:
    """Create a mock Strategy object."""
    # Convert string status to int if needed
    status_int = _STATUS_STR_TO_INT.get(status, status) if isinstance(status, str) else status

    now = datetime.now(UTC)
    strategy = MagicMock()
    strategy.id = id or uuid4()
    strategy.tenant_id = tenant_id or uuid4()
    strategy.name = name
    strategy.description = description
    strategy.status = status_int  # DB TypeDecorator returns proto int directly
    strategy.current_version = current_version
    strategy.created_by = created_by or uuid4()
    strategy.created_at = created_at or now
    strategy.updated_at = updated_at or now
    return strategy


def make_mock_version(
    id: UUID | None = None,
    strategy_id: UUID | None = None,
    version: int = 1,
    config_sexpr: str | None = None,
    config_json: dict[str, str] | None = None,
    symbols: list[str] | None = None,
    timeframe: str = "1D",
    changelog: str | None = None,
    created_by: UUID | None = None,
    created_at: datetime | None = None,
    parameters: dict[str, object] | None = None,
) -> MagicMock:
    """Create a mock StrategyVersion object."""
    ver = MagicMock()
    ver.id = id or uuid4()
    ver.strategy_id = strategy_id or uuid4()
    ver.version = version
    ver.config_sexpr = config_sexpr or VALID_RSI_STRATEGY
    ver.config_json = config_json or {"name": "Test Strategy"}
    ver.symbols = symbols or ["SPY", "TLT"]
    ver.timeframe = timeframe
    ver.changelog = changelog
    ver.created_by = created_by or uuid4()
    ver.created_at = created_at or datetime.now(UTC)
    ver.parameters = parameters or {}
    return ver


# ===================
# Fixtures
# ===================


@pytest.fixture
def tenant_id() -> UUID:
    """Generate a test tenant ID."""
    return uuid4()


@pytest.fixture
def user_id() -> UUID:
    """Generate a test user ID."""
    return uuid4()


@pytest.fixture
def strategy_id() -> UUID:
    """Generate a test strategy ID."""
    return uuid4()


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create a mock async database session."""
    from sqlalchemy.ext.asyncio import AsyncSession

    db = AsyncMock(spec=AsyncSession)
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    db.delete = AsyncMock()
    return db


# ===================
# Create Strategy Tests
# ===================


class TestCreateStrategy:
    """Tests for StrategyService.create_strategy."""

    async def test_create_strategy_success(
        self, mock_db: AsyncMock, tenant_id: UUID, user_id: UUID
    ) -> None:
        """Test creating a strategy with valid S-expression."""
        service = StrategyService(mock_db)

        # Setup mock to return the created strategy
        mock_strategy = make_mock_strategy(tenant_id=tenant_id, created_by=user_id)
        mock_version = make_mock_version(
            strategy_id=mock_strategy.id,
            config_sexpr=VALID_RSI_STRATEGY,
            symbols=["SPY", "TLT"],
            timeframe="1D",
        )

        # Mock refresh to set required attributes
        def set_strategy_attrs(obj: MagicMock) -> None:
            obj.id = mock_strategy.id
            obj.created_at = datetime.now(UTC)
            obj.updated_at = datetime.now(UTC)

        mock_db.refresh = AsyncMock(side_effect=set_strategy_attrs)

        # Mock execute to return proper result with fetchall()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []  # No existing names
        mock_db.execute = AsyncMock(return_value=mock_result)

        data = StrategyCreate(
            name="Test RSI Strategy",
            description="A test strategy",
            config_sexpr=VALID_RSI_STRATEGY,
        )

        with patch.object(service, "_get_version", return_value=mock_version):
            result = await service.create_strategy(
                tenant_id=tenant_id,
                user_id=user_id,
                data=data,
            )

        # Verify db operations
        assert mock_db.add.call_count >= 1  # Strategy and version
        mock_db.flush.assert_called()
        mock_db.commit.assert_called()
        assert result is not None

    async def test_create_strategy_invalid_syntax(
        self, mock_db: AsyncMock, tenant_id: UUID, user_id: UUID
    ) -> None:
        """Test creating a strategy with invalid S-expression raises error."""
        service = StrategyService(mock_db)

        data = StrategyCreate(
            name="Invalid Strategy",
            config_sexpr=INVALID_SYNTAX,
        )

        with pytest.raises(Exception):  # Parser will raise an error
            await service.create_strategy(
                tenant_id=tenant_id,
                user_id=user_id,
                data=data,
            )

    async def test_create_strategy_missing_body(
        self, mock_db: AsyncMock, tenant_id: UUID, user_id: UUID
    ) -> None:
        """Test creating a strategy without body raises validation error."""
        service = StrategyService(mock_db)

        data = StrategyCreate(
            name="No Body Strategy",
            config_sexpr=INVALID_MISSING_BODY,
        )

        with pytest.raises(ValueError) as exc_info:
            await service.create_strategy(
                tenant_id=tenant_id,
                user_id=user_id,
                data=data,
            )
        assert "Invalid strategy" in str(exc_info.value)

    async def test_create_strategy_extracts_symbols(
        self, mock_db: AsyncMock, tenant_id: UUID, user_id: UUID
    ) -> None:
        """Test that symbols are extracted from S-expression."""
        from llamatrade_compiler import get_required_symbols
        from llamatrade_dsl import parse_strategy

        ast = parse_strategy(VALID_RSI_STRATEGY)
        symbols = get_required_symbols(ast)
        assert "SPY" in symbols


# ===================
# Get Strategy Tests
# ===================


class TestGetStrategy:
    """Tests for StrategyService.get_strategy."""

    async def test_get_strategy_found(
        self, mock_db: AsyncMock, tenant_id: UUID, strategy_id: UUID
    ) -> None:
        """Test getting an existing strategy."""
        service = StrategyService(mock_db)

        mock_strategy = make_mock_strategy(
            id=strategy_id,
            tenant_id=tenant_id,
            current_version=1,
        )
        mock_version = make_mock_version(strategy_id=strategy_id)

        # Setup db mock to return the strategy
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_strategy
        mock_db.execute.return_value = mock_result

        with (
            patch.object(service, "_get_strategy_by_id", return_value=mock_strategy),
            patch.object(service, "_get_version", return_value=mock_version),
        ):
            result = await service.get_strategy(
                tenant_id=tenant_id,
                strategy_id=strategy_id,
            )

        assert result is not None
        assert result.id == strategy_id

    async def test_get_strategy_not_found(self, mock_db: AsyncMock, tenant_id: UUID) -> None:
        """Test getting a non-existent strategy returns None."""
        service = StrategyService(mock_db)
        non_existent_id = uuid4()

        with patch.object(service, "_get_strategy_by_id", return_value=None):
            result = await service.get_strategy(
                tenant_id=tenant_id,
                strategy_id=non_existent_id,
            )

        assert result is None

    async def test_get_strategy_tenant_isolation(
        self, mock_db: AsyncMock, strategy_id: UUID
    ) -> None:
        """Test that strategy lookup is scoped to tenant."""
        service = StrategyService(mock_db)

        # Strategy belongs to tenant A
        tenant_a = uuid4()
        tenant_b = uuid4()
        mock_strategy = make_mock_strategy(
            id=strategy_id,
            tenant_id=tenant_a,
        )
        mock_version = make_mock_version(strategy_id=strategy_id)

        # Mock returns the strategy only for tenant A
        async def tenant_scoped_lookup(tid: UUID, sid: UUID) -> MagicMock | None:
            if tid == tenant_a:
                return mock_strategy
            return None

        async def get_version_mock(tid: UUID, sid: UUID, version: int) -> MagicMock:
            return mock_version

        with (
            patch.object(service, "_get_strategy_by_id", side_effect=tenant_scoped_lookup),
            patch.object(service, "_get_version", side_effect=get_version_mock),
        ):
            # Tenant A can access
            result_a = await service.get_strategy(tenant_a, strategy_id)
            assert result_a is not None

            # Tenant B cannot access
            result_b = await service.get_strategy(tenant_b, strategy_id)
            assert result_b is None


# ===================
# List Strategies Tests
# ===================


class TestListStrategies:
    """Tests for StrategyService.list_strategies."""

    async def test_list_strategies_empty(self, mock_db: AsyncMock, tenant_id: UUID) -> None:
        """Test listing strategies when none exist."""
        service = StrategyService(mock_db)

        # Mock count returns 0
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        # Mock list returns empty
        mock_list_result = MagicMock()
        mock_list_result.all.return_value = []

        mock_db.execute.side_effect = [mock_count_result, mock_list_result]

        strategies, total = await service.list_strategies(
            tenant_id=tenant_id,
            page=1,
            page_size=20,
        )

        assert strategies == []
        assert total == 0

    async def test_list_strategies_with_results(
        self, mock_db: AsyncMock, tenant_id: UUID, user_id: UUID
    ) -> None:
        """Test listing strategies returns correct results."""
        service = StrategyService(mock_db)

        mock_strategies = [
            make_mock_strategy(
                tenant_id=tenant_id,
                name=f"Strategy {i}",
                created_by=user_id,
            )
            for i in range(3)
        ]

        # Mock count returns 3
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 3

        # Mock list returns (strategy, symbols, timeframe) rows from the version join
        mock_list_result = MagicMock()
        mock_list_result.all.return_value = [
            (s, ["SPY", "TLT"], "1D") for s in mock_strategies
        ]

        mock_db.execute.side_effect = [mock_count_result, mock_list_result]

        strategies, total = await service.list_strategies(
            tenant_id=tenant_id,
            page=1,
            page_size=20,
        )

        assert len(strategies) == 3
        assert total == 3
        # Summaries now carry the current version's symbols + timeframe
        assert strategies[0].symbols == ["SPY", "TLT"]
        assert strategies[0].timeframe == "1D"

    async def test_list_strategies_filter_by_status(
        self, mock_db: AsyncMock, tenant_id: UUID
    ) -> None:
        """Test filtering strategies by status."""
        service = StrategyService(mock_db)

        # Setup mocks
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        mock_list_result = MagicMock()
        mock_active_strategy = make_mock_strategy(
            tenant_id=tenant_id,
            status="active",
        )
        mock_list_result.all.return_value = [(mock_active_strategy, ["SPY"], "1D")]

        mock_db.execute.side_effect = [mock_count_result, mock_list_result]

        strategies, total = await service.list_strategies(
            tenant_id=tenant_id,
            status=STRATEGY_STATUS_ACTIVE,
            page=1,
            page_size=20,
        )

        assert len(strategies) == 1
        assert total == 1


# ===================
# Update Strategy Tests
# ===================


class TestUpdateStrategy:
    """Tests for StrategyService.update_strategy."""

    async def test_update_strategy_metadata_only(
        self, mock_db: AsyncMock, tenant_id: UUID, user_id: UUID, strategy_id: UUID
    ) -> None:
        """Test updating only metadata (no new version)."""
        service = StrategyService(mock_db)

        mock_strategy = make_mock_strategy(
            id=strategy_id,
            tenant_id=tenant_id,
            name="Old Name",
            current_version=1,
        )
        mock_version = make_mock_version(strategy_id=strategy_id)

        with (
            patch.object(service, "_get_strategy_by_id", return_value=mock_strategy),
            patch.object(service, "_get_version", return_value=mock_version),
        ):
            data = StrategyUpdate(
                name="New Name",
                description="Updated description",
            )

            await service.update_strategy(
                tenant_id=tenant_id,
                user_id=user_id,
                strategy_id=strategy_id,
                data=data,
            )

        # Verify only metadata updated
        mock_db.commit.assert_called()
        assert mock_strategy.name == "New Name"
        assert mock_strategy.description == "Updated description"
        # Version should not have changed
        assert mock_strategy.current_version == 1

    async def test_update_strategy_new_config_creates_version(
        self, mock_db: AsyncMock, tenant_id: UUID, user_id: UUID, strategy_id: UUID
    ) -> None:
        """Test updating config creates a new version."""
        service = StrategyService(mock_db)

        mock_strategy = make_mock_strategy(
            id=strategy_id,
            tenant_id=tenant_id,
            current_version=1,
        )
        mock_version = make_mock_version(strategy_id=strategy_id, version=2)

        with (
            patch.object(service, "_get_strategy_by_id", return_value=mock_strategy),
            patch.object(service, "_get_version", return_value=mock_version),
        ):
            data = StrategyUpdate(
                config_sexpr=VALID_MA_CROSSOVER,
            )

            await service.update_strategy(
                tenant_id=tenant_id,
                user_id=user_id,
                strategy_id=strategy_id,
                data=data,
            )

        # Verify new version was created
        mock_db.add.assert_called()  # Should add new version
        mock_db.commit.assert_called()
        assert mock_strategy.current_version == 2

    async def test_update_strategy_persists_changelog(
        self, mock_db: AsyncMock, tenant_id: UUID, user_id: UUID, strategy_id: UUID
    ) -> None:
        """Test that changelog is persisted when updating config."""
        service = StrategyService(mock_db)

        mock_strategy = make_mock_strategy(
            id=strategy_id,
            tenant_id=tenant_id,
            current_version=1,
        )
        mock_version = make_mock_version(strategy_id=strategy_id, version=2)

        with (
            patch.object(service, "_get_strategy_by_id", return_value=mock_strategy),
            patch.object(service, "_get_version", return_value=mock_version),
        ):
            data = StrategyUpdate(
                config_sexpr=VALID_MA_CROSSOVER,
                changelog="Updated to MA crossover strategy",
            )

            await service.update_strategy(
                tenant_id=tenant_id,
                user_id=user_id,
                strategy_id=strategy_id,
                data=data,
            )

        # Verify changelog was passed to the new version
        # The add() call should have been made with a StrategyVersion containing changelog
        add_call_args = mock_db.add.call_args
        added_version = add_call_args[0][0]  # First positional arg
        assert added_version.changelog == "Updated to MA crossover strategy"

    async def test_update_strategy_not_found(
        self, mock_db: AsyncMock, tenant_id: UUID, user_id: UUID
    ) -> None:
        """Test updating non-existent strategy returns None."""
        service = StrategyService(mock_db)

        with patch.object(service, "_get_strategy_by_id", return_value=None):
            data = StrategyUpdate(name="New Name")

            result = await service.update_strategy(
                tenant_id=tenant_id,
                user_id=user_id,
                strategy_id=uuid4(),
                data=data,
            )

        assert result is None

    async def test_update_strategy_invalid_config(
        self, mock_db: AsyncMock, tenant_id: UUID, user_id: UUID, strategy_id: UUID
    ) -> None:
        """Test updating with invalid config raises error."""
        service = StrategyService(mock_db)

        mock_strategy = make_mock_strategy(
            id=strategy_id,
            tenant_id=tenant_id,
        )

        with patch.object(service, "_get_strategy_by_id", return_value=mock_strategy):
            data = StrategyUpdate(
                config_sexpr=INVALID_SYNTAX,
            )

            with pytest.raises(Exception):  # Parser error
                await service.update_strategy(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    strategy_id=strategy_id,
                    data=data,
                )


# ===================
# Delete Strategy Tests
# ===================


class TestDeleteStrategy:
    """Tests for StrategyService.delete_strategy."""

    async def test_delete_strategy_archives(
        self, mock_db: AsyncMock, tenant_id: UUID, strategy_id: UUID
    ) -> None:
        """Test deleting a strategy archives it (soft delete)."""
        service = StrategyService(mock_db)

        mock_strategy = make_mock_strategy(
            id=strategy_id,
            tenant_id=tenant_id,
            status="draft",
        )

        # No active executions (count 0) and no pending ones to cancel.
        no_executions = MagicMock()
        no_executions.scalar_one.return_value = 0
        no_executions.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=no_executions)

        with patch.object(service, "_get_strategy_by_id", return_value=mock_strategy):
            result = await service.delete_strategy(
                tenant_id=tenant_id,
                strategy_id=strategy_id,
            )

        assert result is True
        # StrategyStatus: ARCHIVED=4
        assert mock_strategy.status == 4
        mock_db.commit.assert_called()

    async def test_delete_strategy_not_found(self, mock_db: AsyncMock, tenant_id: UUID) -> None:
        """Test deleting non-existent strategy returns False."""
        service = StrategyService(mock_db)

        with patch.object(service, "_get_strategy_by_id", return_value=None):
            result = await service.delete_strategy(
                tenant_id=tenant_id,
                strategy_id=uuid4(),
            )

        assert result is False


# ===================
# Status Management Tests
# ===================


class TestStatusManagement:
    """Tests for activate_strategy and pause_strategy."""

    async def test_activate_strategy(
        self, mock_db: AsyncMock, tenant_id: UUID, strategy_id: UUID
    ) -> None:
        """Test activating a draft strategy."""
        service = StrategyService(mock_db)

        mock_strategy = make_mock_strategy(
            id=strategy_id,
            tenant_id=tenant_id,
            status="draft",
        )

        with patch.object(service, "_get_strategy_by_id", return_value=mock_strategy):
            await service.activate_strategy(
                tenant_id=tenant_id,
                strategy_id=strategy_id,
            )

        # StrategyStatus: ACTIVE=2
        assert mock_strategy.status == 2
        mock_db.commit.assert_called()

    async def test_pause_strategy(
        self, mock_db: AsyncMock, tenant_id: UUID, strategy_id: UUID
    ) -> None:
        """Test pausing an active strategy."""
        service = StrategyService(mock_db)

        mock_strategy = make_mock_strategy(
            id=strategy_id,
            tenant_id=tenant_id,
            status="active",
        )

        with patch.object(service, "_get_strategy_by_id", return_value=mock_strategy):
            await service.pause_strategy(
                tenant_id=tenant_id,
                strategy_id=strategy_id,
            )

        # StrategyStatus: PAUSED=3
        assert mock_strategy.status == 3
        mock_db.commit.assert_called()

    async def test_activate_archived_strategy_fails(
        self, mock_db: AsyncMock, tenant_id: UUID, strategy_id: UUID
    ) -> None:
        """Test that activating an archived strategy raises ValueError."""
        service = StrategyService(mock_db)

        mock_strategy = make_mock_strategy(
            id=strategy_id,
            tenant_id=tenant_id,
            status="archived",
        )

        with patch.object(service, "_get_strategy_by_id", return_value=mock_strategy):
            with pytest.raises(ValueError, match="Invalid status transition"):
                await service.activate_strategy(
                    tenant_id=tenant_id,
                    strategy_id=strategy_id,
                )

    async def test_pause_draft_strategy_fails(
        self, mock_db: AsyncMock, tenant_id: UUID, strategy_id: UUID
    ) -> None:
        """Test that pausing a draft strategy raises ValueError."""
        service = StrategyService(mock_db)

        mock_strategy = make_mock_strategy(
            id=strategy_id,
            tenant_id=tenant_id,
            status="draft",
        )

        with patch.object(service, "_get_strategy_by_id", return_value=mock_strategy):
            with pytest.raises(ValueError, match="Invalid status transition"):
                await service.pause_strategy(
                    tenant_id=tenant_id,
                    strategy_id=strategy_id,
                )

    async def test_update_status_via_update_validates_transition(
        self, mock_db: AsyncMock, tenant_id: UUID, user_id: UUID, strategy_id: UUID
    ) -> None:
        """Test that updating status via update_strategy validates transition."""
        from src.models import StrategyUpdate

        service = StrategyService(mock_db)

        mock_strategy = make_mock_strategy(
            id=strategy_id,
            tenant_id=tenant_id,
            status="archived",
        )

        with patch.object(service, "_get_strategy_by_id", return_value=mock_strategy):
            with pytest.raises(ValueError, match="Invalid status transition"):
                await service.update_strategy(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    strategy_id=strategy_id,
                    data=StrategyUpdate(status=STRATEGY_STATUS_ACTIVE),
                )


# ===================
# Version Management Tests
# ===================


class TestVersionManagement:
    """Tests for version listing and retrieval."""

    async def test_list_versions(
        self, mock_db: AsyncMock, tenant_id: UUID, strategy_id: UUID, user_id: UUID
    ) -> None:
        """Test listing all versions of a strategy."""
        service = StrategyService(mock_db)

        mock_strategy = make_mock_strategy(
            id=strategy_id,
            tenant_id=tenant_id,
        )
        mock_versions = [
            make_mock_version(strategy_id=strategy_id, version=2),
            make_mock_version(strategy_id=strategy_id, version=1),
        ]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_versions

        with patch.object(service, "_get_strategy_by_id", return_value=mock_strategy):
            mock_db.execute.return_value = mock_result

            versions = await service.list_versions(
                tenant_id=tenant_id,
                strategy_id=strategy_id,
            )

        assert len(versions) == 2
        assert versions[0].version == 2  # Newest first

    async def test_get_version(
        self, mock_db: AsyncMock, tenant_id: UUID, strategy_id: UUID
    ) -> None:
        """Test getting a specific version."""
        service = StrategyService(mock_db)

        mock_strategy = make_mock_strategy(
            id=strategy_id,
            tenant_id=tenant_id,
        )
        mock_version = make_mock_version(
            strategy_id=strategy_id,
            version=1,
            config_sexpr=VALID_RSI_STRATEGY,
        )

        with (
            patch.object(service, "_get_strategy_by_id", return_value=mock_strategy),
            patch.object(service, "_get_version", return_value=mock_version),
        ):
            version = await service.get_version(
                tenant_id=tenant_id,
                strategy_id=strategy_id,
                version=1,
            )

        assert version is not None
        assert version.version == 1

    async def test_list_versions_strategy_not_found(
        self, mock_db: AsyncMock, tenant_id: UUID
    ) -> None:
        """Test listing versions of non-existent strategy."""
        service = StrategyService(mock_db)

        with patch.object(service, "_get_strategy_by_id", return_value=None):
            versions = await service.list_versions(
                tenant_id=tenant_id,
                strategy_id=uuid4(),
            )

        assert versions == []


# ===================
# Clone Strategy Tests
# ===================


class TestCloneStrategy:
    """Tests for StrategyService.clone_strategy."""

    async def test_clone_strategy_success(
        self, mock_db: AsyncMock, tenant_id: UUID, user_id: UUID, strategy_id: UUID
    ) -> None:
        """Test cloning a strategy."""
        service = StrategyService(mock_db)

        make_mock_strategy(
            id=strategy_id,
            tenant_id=tenant_id,
            name="Original",
        )
        make_mock_version(
            strategy_id=strategy_id,
            config_sexpr=VALID_RSI_STRATEGY,
        )

        with (
            patch.object(service, "get_strategy") as mock_get,
            patch.object(service, "create_strategy") as mock_create,
        ):
            # Setup get_strategy to return original
            mock_get.return_value = MagicMock(
                name="Original",
                config_sexpr=VALID_RSI_STRATEGY,
            )

            # Setup create_strategy to return cloned
            mock_create.return_value = MagicMock(
                name="Cloned Strategy",
            )

            await service.clone_strategy(
                tenant_id=tenant_id,
                user_id=user_id,
                strategy_id=strategy_id,
                new_name="Cloned Strategy",
            )

        mock_get.assert_called_once()
        mock_create.assert_called_once()

    async def test_clone_strategy_not_found(
        self, mock_db: AsyncMock, tenant_id: UUID, user_id: UUID
    ) -> None:
        """Test cloning non-existent strategy returns None."""
        service = StrategyService(mock_db)

        with patch.object(service, "get_strategy", return_value=None):
            result = await service.clone_strategy(
                tenant_id=tenant_id,
                user_id=user_id,
                strategy_id=uuid4(),
                new_name="Clone",
            )

        assert result is None


# ===================
# Validation Tests
# ===================


class TestValidation:
    """Tests for StrategyService.validate_config."""

    async def test_validate_valid_config(self, mock_db: AsyncMock) -> None:
        """Test validating a valid S-expression."""
        service = StrategyService(mock_db)

        result = await service.validate_config(VALID_RSI_STRATEGY)

        assert result.valid is True
        assert result.errors == []

    async def test_validate_invalid_syntax(self, mock_db: AsyncMock) -> None:
        """Test validating invalid syntax returns error."""
        service = StrategyService(mock_db)

        result = await service.validate_config(INVALID_SYNTAX)

        assert result.valid is False
        assert len(result.errors) > 0

    async def test_validate_missing_body(self, mock_db: AsyncMock) -> None:
        """Test validating config with missing body."""
        service = StrategyService(mock_db)

        result = await service.validate_config(INVALID_MISSING_BODY)

        assert result.valid is False


# ===================
# Execution Tests
# ===================


class TestExecutions:
    """Tests for execution operations."""

    async def test_create_execution_paper(
        self, mock_db: AsyncMock, tenant_id: UUID, strategy_id: UUID
    ) -> None:
        """Test creating a paper trading execution."""
        service = StrategyService(mock_db)

        mock_strategy = make_mock_strategy(
            id=strategy_id,
            tenant_id=tenant_id,
            current_version=1,
        )
        mock_version = make_mock_version(strategy_id=strategy_id)

        # Setup mock refresh to set execution attributes
        def set_execution_attrs(execution: MagicMock) -> None:
            execution.id = uuid4()
            execution.created_at = datetime.now(UTC)
            execution.updated_at = datetime.now(UTC)

        mock_db.refresh = AsyncMock(side_effect=set_execution_attrs)

        with (
            patch.object(service, "_get_strategy_by_id", return_value=mock_strategy),
            patch.object(service, "_get_version", return_value=mock_version),
        ):
            data = ExecutionCreate(
                version=None,
                mode=EXECUTION_MODE_PAPER,
                config_override=None,
            )

            result = await service.create_execution(
                tenant_id=tenant_id,
                strategy_id=strategy_id,
                data=data,
            )

        mock_db.add.assert_called()
        mock_db.commit.assert_called()
        assert result is not None
        # ExecutionStatus: PENDING=1
        assert result.status == 1

    async def test_create_execution_strategy_not_found(
        self, mock_db: AsyncMock, tenant_id: UUID
    ) -> None:
        """Test creating execution for non-existent strategy."""
        service = StrategyService(mock_db)

        with patch.object(service, "_get_strategy_by_id", return_value=None):
            data = ExecutionCreate(version=None, mode=EXECUTION_MODE_PAPER, config_override=None)

            result = await service.create_execution(
                tenant_id=tenant_id,
                strategy_id=uuid4(),
                data=data,
            )

        assert result is None

    async def test_create_execution_invalid_version(
        self, mock_db: AsyncMock, tenant_id: UUID, strategy_id: UUID
    ) -> None:
        """Test creating execution with non-existent version."""
        service = StrategyService(mock_db)

        mock_strategy = make_mock_strategy(
            id=strategy_id,
            tenant_id=tenant_id,
            current_version=1,
        )

        with (
            patch.object(service, "_get_strategy_by_id", return_value=mock_strategy),
            patch.object(service, "_get_version", return_value=None),
        ):
            data = ExecutionCreate(
                version=999,  # Non-existent version
                mode=EXECUTION_MODE_PAPER,
                config_override=None,
            )

            with pytest.raises(ValueError) as exc_info:
                await service.create_execution(
                    tenant_id=tenant_id,
                    strategy_id=strategy_id,
                    data=data,
                )
            assert "not found" in str(exc_info.value)

    async def test_list_executions(
        self, mock_db: AsyncMock, tenant_id: UUID, strategy_id: UUID
    ) -> None:
        """Test listing executions for a strategy."""
        service = StrategyService(mock_db)

        # DB TypeDecorator returns proto int values directly
        # ExecutionMode: PAPER=1, LIVE=2
        # ExecutionStatus: PENDING=1, RUNNING=2, PAUSED=3, STOPPED=4, ERROR=5

        mock_execution = MagicMock()
        mock_execution.id = uuid4()
        mock_execution.strategy_id = strategy_id
        mock_execution.tenant_id = tenant_id
        mock_execution.version = 1
        mock_execution.mode = 1  # PAPER
        mock_execution.status = 1  # PENDING
        mock_execution.started_at = None
        mock_execution.stopped_at = None
        mock_execution.config_override = None
        mock_execution.error_message = None
        mock_execution.created_at = datetime.now(UTC)
        mock_execution.allocated_capital = None
        mock_execution.credentials_id = None
        mock_execution.sleeve_id = None
        mock_execution.account_id = None

        # Mock count query result (returns scalar for total)
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        # Mock list query result
        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = [mock_execution]

        # Return different results for count vs list queries
        mock_db.execute.side_effect = [mock_count_result, mock_list_result]

        executions, total = await service.list_executions(
            tenant_id=tenant_id,
            strategy_id=strategy_id,
        )

        assert len(executions) == 1
        assert total == 1


# ===================
# Search and Sort Tests
# ===================


class TestSearchAndSort:
    """Tests for search and sort functionality in list_strategies."""

    async def test_list_strategies_with_search(self, mock_db: AsyncMock, tenant_id: UUID) -> None:
        """Test listing strategies with search filter."""
        service = StrategyService(mock_db)

        # Mock count returns 1
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        # Mock list returns matching strategy
        mock_strategy = make_mock_strategy(
            id=uuid4(),
            tenant_id=tenant_id,
            name="RSI Strategy",
        )
        mock_list_result = MagicMock()
        mock_list_result.all.return_value = [(mock_strategy, ["SPY"], "1D")]

        mock_db.execute.side_effect = [mock_count_result, mock_list_result]

        strategies, total = await service.list_strategies(
            tenant_id=tenant_id,
            search="RSI",
            page=1,
            page_size=20,
        )

        assert total == 1
        assert len(strategies) == 1

    async def test_list_strategies_with_sort(self, mock_db: AsyncMock, tenant_id: UUID) -> None:
        """Test listing strategies with sort options."""
        service = StrategyService(mock_db)

        # Mock count returns 2
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 2

        # Mock list returns strategies
        mock_strategies = [
            make_mock_strategy(id=uuid4(), tenant_id=tenant_id, name="A Strategy"),
            make_mock_strategy(id=uuid4(), tenant_id=tenant_id, name="B Strategy"),
        ]
        mock_list_result = MagicMock()
        mock_list_result.all.return_value = [(s, ["SPY"], "1D") for s in mock_strategies]

        mock_db.execute.side_effect = [mock_count_result, mock_list_result]

        strategies, total = await service.list_strategies(
            tenant_id=tenant_id,
            sort_field="name",
            sort_direction="asc",
            page=1,
            page_size=20,
        )

        assert total == 2
        assert len(strategies) == 2


# ===================
# Template Tests
# ===================


class TestCreateFromTemplate:
    """Tests for create_from_template."""

    async def test_create_from_template_success(
        self, mock_db: AsyncMock, tenant_id: UUID, user_id: UUID
    ) -> None:
        """Test creating strategy from template."""
        service = StrategyService(mock_db)

        with patch.object(service, "create_strategy") as mock_create:
            mock_create.return_value = MagicMock(
                name="Moving Average Crossover",
            )

            result = await service.create_from_template(
                tenant_id=tenant_id,
                user_id=user_id,
                template_id="ma-crossover",
            )

        mock_create.assert_called_once()
        assert result is not None

    async def test_create_from_template_with_custom_name(
        self, mock_db: AsyncMock, tenant_id: UUID, user_id: UUID
    ) -> None:
        """Test creating strategy from template with custom name."""
        service = StrategyService(mock_db)

        with patch.object(service, "create_strategy") as mock_create:
            mock_create.return_value = MagicMock(name="My Custom Strategy")

            await service.create_from_template(
                tenant_id=tenant_id,
                user_id=user_id,
                template_id="rsi-mean-reversion",
                name="My Custom Strategy",
                description="Custom description",
            )

        # Verify create_strategy was called with custom name
        call_args = mock_create.call_args
        assert call_args.kwargs["data"].name == "My Custom Strategy"
        assert call_args.kwargs["data"].description == "Custom description"

    async def test_create_from_template_not_found(
        self, mock_db: AsyncMock, tenant_id: UUID, user_id: UUID
    ) -> None:
        """Test creating strategy from non-existent template."""
        service = StrategyService(mock_db)

        with pytest.raises(ValueError, match="Template not found"):
            await service.create_from_template(
                tenant_id=tenant_id,
                user_id=user_id,
                template_id="non_existent_template",
            )

    async def test_create_from_template_rejects_unknown_param(
        self, mock_db: AsyncMock, tenant_id: UUID, user_id: UUID
    ) -> None:
        """An unknown template parameter is rejected, not silently ignored."""
        service = StrategyService(mock_db)

        with pytest.raises(ValueError, match="Unknown template parameter"):
            await service.create_from_template(
                tenant_id=tenant_id,
                user_id=user_id,
                template_id="ma-crossover",
                template_params={"bogus": "x"},
            )

    async def test_create_from_template_rejects_injection_value(
        self, mock_db: AsyncMock, tenant_id: UUID, user_id: UUID
    ) -> None:
        """A value that could inject S-expression text is rejected before substitution."""
        service = StrategyService(mock_db)

        with pytest.raises(ValueError, match="Invalid value"):
            await service.create_from_template(
                tenant_id=tenant_id,
                user_id=user_id,
                template_id="ma-crossover",
                template_params={"symbols": '"AAPL") (evil'},
            )

    async def test_create_from_template_rejects_unmatched_param(
        self, mock_db: AsyncMock, tenant_id: UUID, user_id: UUID
    ) -> None:
        """A valid override matching no field raises rather than silently no-op."""
        service = StrategyService(mock_db)

        with pytest.raises(ValueError, match="no 'symbols' field"):
            await service.create_from_template(
                tenant_id=tenant_id,
                user_id=user_id,
                template_id="ma-crossover",
                template_params={"symbols": '["AAPL" "MSFT"]'},
            )


# ===================
# Detected Indicators Tests
# ===================


class TestDetectedIndicators:
    """Tests for detected_indicators in validation."""

    async def test_validate_returns_detected_indicators(self, mock_db: AsyncMock) -> None:
        """Test that validation returns detected indicators."""
        service = StrategyService(mock_db)

        result = await service.validate_config(VALID_RSI_STRATEGY)

        assert result.valid is True
        assert len(result.detected_indicators) > 0
        # Should detect RSI indicator
        assert any("rsi" in ind.lower() for ind in result.detected_indicators)

    async def test_validate_returns_detected_symbols(self, mock_db: AsyncMock) -> None:
        """Test that validation returns detected symbols."""
        service = StrategyService(mock_db)

        result = await service.validate_config(VALID_RSI_STRATEGY)

        assert result.valid is True
        assert len(result.detected_symbols) > 0
        assert "SPY" in result.detected_symbols

    async def test_validate_multiple_indicators(self, mock_db: AsyncMock) -> None:
        """Test validation with multiple indicators."""
        service = StrategyService(mock_db)

        multi_indicator_config = """(strategy "Multi Indicator"
  :rebalance daily
  :benchmark SPY
  (if (and
    (< (rsi SPY 14) 30)
    (crosses-above (ema SPY 12) (ema SPY 26)))
    (asset SPY :weight 100)
    (else (asset AGG :weight 100))))"""

        result = await service.validate_config(multi_indicator_config)

        assert result.valid is True
        # Should detect both RSI and EMA
        assert len(result.detected_indicators) >= 2


# ===================
# Execution Funding Tests (ledger sleeves)
# ===================


class TestExecutionFunding:
    """Sleeve funding on start_execution."""

    @staticmethod
    def _pending_execution(**overrides: object):
        from llamatrade_db.models.strategy import StrategyExecution
        from llamatrade_proto.generated.common_pb2 import EXECUTION_STATUS_PENDING

        execution = StrategyExecution(
            tenant_id=uuid4(),
            strategy_id=uuid4(),
            version=1,
            mode=EXECUTION_MODE_PAPER,
            status=EXECUTION_STATUS_PENDING,
            config_override=None,
            allocated_capital=Decimal("40000"),
            credentials_id=uuid4(),
        )
        execution.id = uuid4()
        execution.created_at = datetime.now(UTC)
        for key, value in overrides.items():
            setattr(execution, key, value)
        return execution

    @staticmethod
    def _ledger_mock(account_id: UUID, sleeve_id: UUID) -> AsyncMock:
        ledger = AsyncMock()
        ledger.get_or_create_account.return_value = SimpleNamespace(
            account=SimpleNamespace(id=str(account_id)), base_sleeves=[]
        )
        ledger.allocate_capital.return_value = SimpleNamespace(id=str(sleeve_id))
        return ledger

    async def test_create_execution_stores_funding_fields(
        self, mock_db: AsyncMock, tenant_id: UUID, strategy_id: UUID
    ) -> None:
        """allocated_capital + credentials_id persist on the execution row."""
        service = StrategyService(mock_db)
        credentials_id = uuid4()

        mock_strategy = make_mock_strategy(id=strategy_id, tenant_id=tenant_id, current_version=1)
        mock_version = make_mock_version(strategy_id=strategy_id)

        def set_execution_attrs(execution: MagicMock) -> None:
            execution.id = uuid4()
            execution.created_at = datetime.now(UTC)

        mock_db.refresh = AsyncMock(side_effect=set_execution_attrs)

        with (
            patch.object(service, "_get_strategy_by_id", return_value=mock_strategy),
            patch.object(service, "_get_version", return_value=mock_version),
        ):
            result = await service.create_execution(
                tenant_id=tenant_id,
                strategy_id=strategy_id,
                data=ExecutionCreate(
                    mode=EXECUTION_MODE_PAPER,
                    allocated_capital=Decimal("40000"),
                    credentials_id=credentials_id,
                ),
            )

        assert result is not None
        assert result.allocated_capital == Decimal("40000")
        assert result.credentials_id == credentials_id
        assert result.sleeve_id is None  # funded at start, not at create

    async def test_start_execution_funds_sleeve(self, mock_db: AsyncMock) -> None:
        """Start opens+funds the sleeve and persists sleeve_id/account_id."""
        service = StrategyService(mock_db)
        execution = self._pending_execution()
        account_id, sleeve_id = uuid4(), uuid4()
        ledger = self._ledger_mock(account_id, sleeve_id)
        strategy = make_mock_strategy(id=execution.strategy_id, name="Momentum A")

        with (
            patch.object(service, "_get_execution_by_id", return_value=execution),
            patch.object(service, "_get_strategy_by_id", return_value=strategy),
        ):
            result = await service.start_execution(
                execution.tenant_id, execution.id, ledger=ledger, user_id=uuid4()
            )

        assert result is not None
        assert execution.sleeve_id == sleeve_id
        assert execution.account_id == account_id
        ledger.get_or_create_account.assert_awaited_once()
        allocate_kwargs = ledger.allocate_capital.await_args.kwargs
        assert allocate_kwargs["strategy_execution_id"] == str(execution.id)
        assert allocate_kwargs["sleeve_name"] == "Momentum A"
        mock_db.commit.assert_called()

    async def test_start_execution_skips_funding_without_intent(self, mock_db: AsyncMock) -> None:
        """No allocated_capital/credentials_id → legacy unfunded start."""
        service = StrategyService(mock_db)
        execution = self._pending_execution(allocated_capital=None, credentials_id=None)
        ledger = self._ledger_mock(uuid4(), uuid4())

        with patch.object(service, "_get_execution_by_id", return_value=execution):
            result = await service.start_execution(execution.tenant_id, execution.id, ledger=ledger)

        assert result is not None
        ledger.allocate_capital.assert_not_awaited()

    async def test_start_execution_already_funded_does_not_refund(self, mock_db: AsyncMock) -> None:
        """A sleeve_id already on the row means funding is skipped (restart)."""
        service = StrategyService(mock_db)
        existing_sleeve = uuid4()
        execution = self._pending_execution(sleeve_id=existing_sleeve, account_id=uuid4())
        ledger = self._ledger_mock(uuid4(), uuid4())

        with patch.object(service, "_get_execution_by_id", return_value=execution):
            await service.start_execution(execution.tenant_id, execution.id, ledger=ledger)

        assert execution.sleeve_id == existing_sleeve
        ledger.allocate_capital.assert_not_awaited()

    async def test_start_execution_funding_failure_blocks_start(self, mock_db: AsyncMock) -> None:
        """A funding RPC failure surfaces as ValueError and start aborts."""
        from connectrpc.code import Code
        from connectrpc.errors import ConnectError

        service = StrategyService(mock_db)
        execution = self._pending_execution()
        strategy = make_mock_strategy(id=execution.strategy_id)
        ledger = self._ledger_mock(uuid4(), uuid4())
        ledger.allocate_capital.side_effect = ConnectError(Code.INVALID_ARGUMENT, "insufficient free cash")

        with (
            patch.object(service, "_get_execution_by_id", return_value=execution),
            patch.object(service, "_get_strategy_by_id", return_value=strategy),
            pytest.raises(ValueError, match="sleeve funding failed"),
        ):
            await service.start_execution(execution.tenant_id, execution.id, ledger=ledger)

        assert execution.sleeve_id is None
        mock_db.commit.assert_not_called()


class TestExecutionStopRelease:
    """stop_execution + archive release the execution's ledger sleeve."""

    @staticmethod
    def _running_execution(**overrides: object):
        from llamatrade_db.models.strategy import StrategyExecution
        from llamatrade_proto.generated.common_pb2 import EXECUTION_STATUS_RUNNING

        execution = StrategyExecution(
            tenant_id=uuid4(),
            strategy_id=uuid4(),
            version=1,
            mode=EXECUTION_MODE_PAPER,
            status=EXECUTION_STATUS_RUNNING,
            config_override=None,
            allocated_capital=Decimal("40000"),
            credentials_id=uuid4(),
            sleeve_id=uuid4(),
            account_id=uuid4(),
        )
        execution.id = uuid4()
        execution.created_at = datetime.now(UTC)
        for key, value in overrides.items():
            setattr(execution, key, value)
        return execution

    async def test_stop_closes_sleeve(self, mock_db: AsyncMock) -> None:
        """A funded execution's sleeve is closed (re-homed) on stop."""
        from llamatrade_proto.generated.common_pb2 import EXECUTION_STATUS_STOPPED

        service = StrategyService(mock_db)
        execution = self._running_execution()
        original_sleeve, original_account = execution.sleeve_id, execution.account_id
        ledger = AsyncMock()

        with patch.object(service, "_get_execution_by_id", return_value=execution):
            result = await service.stop_execution(
                execution.tenant_id, execution.id, reason="done", ledger=ledger, user_id=uuid4()
            )

        assert result is not None
        assert execution.status == EXECUTION_STATUS_STOPPED
        ledger.close_sleeve.assert_awaited_once()
        args = ledger.close_sleeve.await_args.args
        assert args[2] == str(original_account)  # account_id
        assert args[3] == str(original_sleeve)  # sleeve_id
        # On a successful close the sleeve identity is cleared (3A: marks released).
        assert execution.sleeve_id is None

    async def test_stop_without_sleeve_skips_close(self, mock_db: AsyncMock) -> None:
        """An unfunded (legacy) execution has no sleeve to release."""
        service = StrategyService(mock_db)
        execution = self._running_execution(sleeve_id=None, account_id=None)
        ledger = AsyncMock()

        with patch.object(service, "_get_execution_by_id", return_value=execution):
            await service.stop_execution(execution.tenant_id, execution.id, ledger=ledger)

        ledger.close_sleeve.assert_not_awaited()

    async def test_stop_without_ledger_still_stops(self, mock_db: AsyncMock) -> None:
        """No ledger wired → stop succeeds, close is a no-op."""
        service = StrategyService(mock_db)
        execution = self._running_execution()

        with patch.object(service, "_get_execution_by_id", return_value=execution):
            result = await service.stop_execution(execution.tenant_id, execution.id)

        assert result is not None

    async def test_stop_close_failure_is_best_effort(self, mock_db: AsyncMock) -> None:
        """A close RPC failure (e.g. in-flight order) never fails the stop."""
        from connectrpc.code import Code
        from connectrpc.errors import ConnectError

        from llamatrade_proto.generated.common_pb2 import EXECUTION_STATUS_STOPPED

        service = StrategyService(mock_db)
        execution = self._running_execution()
        ledger = AsyncMock()
        ledger.close_sleeve.side_effect = ConnectError(Code.FAILED_PRECONDITION, "sleeve has reserved cash for in-flight orders")

        with patch.object(service, "_get_execution_by_id", return_value=execution):
            result = await service.stop_execution(execution.tenant_id, execution.id, ledger=ledger)

        assert result is not None  # stop still succeeds
        assert execution.status == EXECUTION_STATUS_STOPPED
        # Close failed -> sleeve_id stays set as the "needs release" marker (3A).
        assert execution.sleeve_id is not None

    async def test_reconcile_stranded_sleeves(self, mock_db: AsyncMock) -> None:
        """The sweeper retries close for terminal executions whose sleeve is still set."""
        from llamatrade_proto.generated.common_pb2 import EXECUTION_STATUS_STOPPED

        service = StrategyService(mock_db)
        e1 = self._running_execution(status=EXECUTION_STATUS_STOPPED)
        e2 = self._running_execution(status=EXECUTION_STATUS_STOPPED)

        result = MagicMock()
        result.scalars.return_value.all.return_value = [e1, e2]
        mock_db.execute = AsyncMock(return_value=result)
        ledger = AsyncMock()

        released = await service.reconcile_stranded_sleeves(ledger=ledger, user_id=uuid4())

        assert released == 2
        assert e1.sleeve_id is None
        assert e2.sleeve_id is None
        assert ledger.close_sleeve.await_count == 2

    async def test_reconcile_skips_when_close_fails(self, mock_db: AsyncMock) -> None:
        """A still-failing close leaves the sleeve marked for the next sweep."""
        from connectrpc.code import Code
        from connectrpc.errors import ConnectError

        from llamatrade_proto.generated.common_pb2 import EXECUTION_STATUS_STOPPED

        service = StrategyService(mock_db)
        execution = self._running_execution(status=EXECUTION_STATUS_STOPPED)

        result = MagicMock()
        result.scalars.return_value.all.return_value = [execution]
        mock_db.execute = AsyncMock(return_value=result)
        ledger = AsyncMock()
        ledger.close_sleeve.side_effect = ConnectError(Code.UNAVAILABLE, "ledger down")

        released = await service.reconcile_stranded_sleeves(ledger=ledger)

        assert released == 0
        assert execution.sleeve_id is not None  # still marked for retry

    async def test_archive_blocked_by_active_execution(
        self, mock_db: AsyncMock, tenant_id: UUID, strategy_id: UUID
    ) -> None:
        """Archiving is refused while a RUNNING/PAUSED execution exists."""
        service = StrategyService(mock_db)
        strategy = make_mock_strategy(id=strategy_id, tenant_id=tenant_id, status="active")

        active_count = MagicMock()
        active_count.scalar_one.return_value = 1  # one active execution
        mock_db.execute = AsyncMock(return_value=active_count)

        with (
            patch.object(service, "_get_strategy_by_id", return_value=strategy),
            pytest.raises(ValueError, match="active execution"),
        ):
            await service.delete_strategy(tenant_id, strategy_id)

        assert strategy.status != 4  # not archived
        mock_db.commit.assert_not_called()

    async def test_archive_cancels_pending_executions(
        self, mock_db: AsyncMock, tenant_id: UUID, strategy_id: UUID
    ) -> None:
        """Archiving cancels never-started PENDING executions (unfunded — no sleeve)."""
        from llamatrade_proto.generated.common_pb2 import (
            EXECUTION_STATUS_PENDING,
            EXECUTION_STATUS_STOPPED,
        )

        service = StrategyService(mock_db)
        strategy = make_mock_strategy(id=strategy_id, tenant_id=tenant_id, status="draft")
        pending = self._running_execution(
            tenant_id=tenant_id,
            strategy_id=strategy_id,
            status=EXECUTION_STATUS_PENDING,
            sleeve_id=None,
            account_id=None,
        )

        result = MagicMock()
        result.scalar_one.return_value = 0  # no active executions
        result.scalars.return_value.all.return_value = [pending]
        mock_db.execute = AsyncMock(return_value=result)

        with patch.object(service, "_get_strategy_by_id", return_value=strategy):
            ok = await service.delete_strategy(tenant_id, strategy_id)

        assert ok is True
        assert strategy.status == 4  # STRATEGY_STATUS_ARCHIVED
        assert pending.status == EXECUTION_STATUS_STOPPED
        mock_db.commit.assert_called()
