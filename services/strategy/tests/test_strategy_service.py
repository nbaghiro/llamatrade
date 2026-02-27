"""Unit tests for StrategyService with DSL support."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from src.models import (
    DeploymentCreate,
    DeploymentEnvironment,
    StrategyCreate,
    StrategyStatus,
    StrategyUpdate,
)
from src.services.strategy_service import StrategyService

# ===================
# Sample S-expressions
# ===================

VALID_RSI_STRATEGY = """(strategy
  :name "RSI Mean Reversion"
  :type mean_reversion
  :symbols ["AAPL" "MSFT"]
  :timeframe "1D"
  :entry (< (rsi close 14) 30)
  :exit (> (rsi close 14) 70)
  :stop-loss-pct 2.0
  :take-profit-pct 6.0)"""

VALID_MA_CROSSOVER = """(strategy
  :name "MA Crossover"
  :type trend_following
  :symbols ["SPY"]
  :timeframe "4H"
  :entry (cross-above (sma close 20) (sma close 50))
  :exit (cross-below (sma close 20) (sma close 50))
  :position-size-pct 5.0)"""

VALID_MOMENTUM_STRATEGY = """(strategy
  :name "Momentum Strategy"
  :type momentum
  :symbols ["QQQ" "IWM"]
  :timeframe "1H"
  :entry (and (> (rsi close 14) 50) (> close (sma close 20)))
  :exit (or (< (rsi close 14) 40) (< close (sma close 20))))"""

INVALID_SYNTAX = '(strategy :name "broken'  # Missing closing quotes and paren

INVALID_MISSING_ENTRY = """(strategy
  :name "No Entry"
  :symbols ["AAPL"]
  :timeframe "1D"
  :exit true)"""


def make_mock_strategy(
    id=None,
    tenant_id=None,
    name="Test Strategy",
    description=None,
    strategy_type="mean_reversion",
    status="draft",
    current_version=1,
    created_by=None,
    created_at=None,
    updated_at=None,
):
    """Create a mock Strategy object."""
    from llamatrade_db.models.strategy import (
        StrategyStatus as DBStrategyStatus,
    )
    from llamatrade_db.models.strategy import (
        StrategyType as DBStrategyType,
    )

    now = datetime.now()
    strategy = MagicMock()
    strategy.id = id or uuid4()
    strategy.tenant_id = tenant_id or uuid4()
    strategy.name = name
    strategy.description = description
    strategy.strategy_type = DBStrategyType(strategy_type)
    strategy.status = DBStrategyStatus(status)
    strategy.current_version = current_version
    strategy.created_by = created_by or uuid4()
    strategy.created_at = created_at or now
    strategy.updated_at = updated_at or now
    return strategy


def make_mock_version(
    id=None,
    strategy_id=None,
    version=1,
    config_sexpr=None,
    config_json=None,
    symbols=None,
    timeframe="1D",
    changelog=None,
    created_by=None,
    created_at=None,
):
    """Create a mock StrategyVersion object."""
    ver = MagicMock()
    ver.id = id or uuid4()
    ver.strategy_id = strategy_id or uuid4()
    ver.version = version
    ver.config_sexpr = config_sexpr or VALID_RSI_STRATEGY
    ver.config_json = config_json or {"name": "Test Strategy"}
    ver.symbols = symbols or ["AAPL", "MSFT"]
    ver.timeframe = timeframe
    ver.changelog = changelog
    ver.created_by = created_by or uuid4()
    ver.created_at = created_at or datetime.utcnow()
    return ver


# ===================
# Fixtures
# ===================


@pytest.fixture
def tenant_id():
    """Generate a test tenant ID."""
    return uuid4()


@pytest.fixture
def user_id():
    """Generate a test user ID."""
    return uuid4()


@pytest.fixture
def strategy_id():
    """Generate a test strategy ID."""
    return uuid4()


@pytest.fixture
def mock_db():
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

    async def test_create_strategy_success(self, mock_db, tenant_id, user_id):
        """Test creating a strategy with valid S-expression."""
        service = StrategyService(mock_db)

        # Setup mock to return the created strategy
        mock_strategy = make_mock_strategy(tenant_id=tenant_id, created_by=user_id)
        mock_version = make_mock_version(
            strategy_id=mock_strategy.id,
            config_sexpr=VALID_RSI_STRATEGY,
            symbols=["AAPL", "MSFT"],
            timeframe="1D",
        )

        # Mock refresh to set required attributes
        def set_strategy_attrs(obj):
            obj.id = mock_strategy.id
            obj.created_at = datetime.now()
            obj.updated_at = datetime.now()

        mock_db.refresh = AsyncMock(side_effect=set_strategy_attrs)

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

    async def test_create_strategy_invalid_syntax(self, mock_db, tenant_id, user_id):
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

    async def test_create_strategy_missing_entry(self, mock_db, tenant_id, user_id):
        """Test creating a strategy without :entry raises validation error."""
        service = StrategyService(mock_db)

        data = StrategyCreate(
            name="No Entry Strategy",
            config_sexpr=INVALID_MISSING_ENTRY,
        )

        with pytest.raises(ValueError) as exc_info:
            await service.create_strategy(
                tenant_id=tenant_id,
                user_id=user_id,
                data=data,
            )
        assert "Invalid strategy" in str(exc_info.value)

    async def test_create_strategy_extracts_type(self, mock_db, tenant_id, user_id):
        """Test that strategy type is extracted from S-expression."""
        StrategyService(mock_db)

        StrategyCreate(
            name="Trend Following Strategy",
            config_sexpr=VALID_MA_CROSSOVER,
        )

        # Verify the AST parsing extracts the correct type
        from llamatrade_dsl import parse_strategy

        ast = parse_strategy(VALID_MA_CROSSOVER)
        assert ast.strategy_type == "trend_following"


# ===================
# Get Strategy Tests
# ===================


class TestGetStrategy:
    """Tests for StrategyService.get_strategy."""

    async def test_get_strategy_found(self, mock_db, tenant_id, strategy_id):
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

    async def test_get_strategy_not_found(self, mock_db, tenant_id):
        """Test getting a non-existent strategy returns None."""
        service = StrategyService(mock_db)
        non_existent_id = uuid4()

        with patch.object(service, "_get_strategy_by_id", return_value=None):
            result = await service.get_strategy(
                tenant_id=tenant_id,
                strategy_id=non_existent_id,
            )

        assert result is None

    async def test_get_strategy_tenant_isolation(self, mock_db, strategy_id):
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
        async def tenant_scoped_lookup(tid, sid):
            if tid == tenant_a:
                return mock_strategy
            return None

        async def get_version_mock(sid, version):
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

    async def test_list_strategies_empty(self, mock_db, tenant_id):
        """Test listing strategies when none exist."""
        service = StrategyService(mock_db)

        # Mock count returns 0
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        # Mock list returns empty
        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [mock_count_result, mock_list_result]

        strategies, total = await service.list_strategies(
            tenant_id=tenant_id,
            page=1,
            page_size=20,
        )

        assert strategies == []
        assert total == 0

    async def test_list_strategies_with_results(self, mock_db, tenant_id, user_id):
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

        # Mock list returns strategies
        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = mock_strategies

        mock_db.execute.side_effect = [mock_count_result, mock_list_result]

        strategies, total = await service.list_strategies(
            tenant_id=tenant_id,
            page=1,
            page_size=20,
        )

        assert len(strategies) == 3
        assert total == 3

    async def test_list_strategies_filter_by_status(self, mock_db, tenant_id):
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
        mock_list_result.scalars.return_value.all.return_value = [mock_active_strategy]

        mock_db.execute.side_effect = [mock_count_result, mock_list_result]

        strategies, total = await service.list_strategies(
            tenant_id=tenant_id,
            status=StrategyStatus.ACTIVE,
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

    async def test_update_strategy_metadata_only(self, mock_db, tenant_id, user_id, strategy_id):
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
        self, mock_db, tenant_id, user_id, strategy_id
    ):
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

    async def test_update_strategy_not_found(self, mock_db, tenant_id, user_id):
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

    async def test_update_strategy_invalid_config(self, mock_db, tenant_id, user_id, strategy_id):
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

    async def test_delete_strategy_archives(self, mock_db, tenant_id, strategy_id):
        """Test deleting a strategy archives it (soft delete)."""
        service = StrategyService(mock_db)

        mock_strategy = make_mock_strategy(
            id=strategy_id,
            tenant_id=tenant_id,
            status="draft",
        )

        with patch.object(service, "_get_strategy_by_id", return_value=mock_strategy):
            result = await service.delete_strategy(
                tenant_id=tenant_id,
                strategy_id=strategy_id,
            )

        assert result is True
        from llamatrade_db.models.strategy import StrategyStatus as DBStatus

        assert mock_strategy.status == DBStatus.ARCHIVED
        mock_db.commit.assert_called()

    async def test_delete_strategy_not_found(self, mock_db, tenant_id):
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

    async def test_activate_strategy(self, mock_db, tenant_id, strategy_id):
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

        from llamatrade_db.models.strategy import StrategyStatus as DBStatus

        assert mock_strategy.status == DBStatus.ACTIVE
        mock_db.commit.assert_called()

    async def test_pause_strategy(self, mock_db, tenant_id, strategy_id):
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

        from llamatrade_db.models.strategy import StrategyStatus as DBStatus

        assert mock_strategy.status == DBStatus.PAUSED
        mock_db.commit.assert_called()


# ===================
# Version Management Tests
# ===================


class TestVersionManagement:
    """Tests for version listing and retrieval."""

    async def test_list_versions(self, mock_db, tenant_id, strategy_id, user_id):
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

    async def test_get_version(self, mock_db, tenant_id, strategy_id):
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

    async def test_list_versions_strategy_not_found(self, mock_db, tenant_id):
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

    async def test_clone_strategy_success(self, mock_db, tenant_id, user_id, strategy_id):
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

    async def test_clone_strategy_not_found(self, mock_db, tenant_id, user_id):
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

    async def test_validate_valid_config(self, mock_db):
        """Test validating a valid S-expression."""
        service = StrategyService(mock_db)

        result = await service.validate_config(VALID_RSI_STRATEGY)

        assert result.valid is True
        assert result.errors == []

    async def test_validate_invalid_syntax(self, mock_db):
        """Test validating invalid syntax returns error."""
        service = StrategyService(mock_db)

        result = await service.validate_config(INVALID_SYNTAX)

        assert result.valid is False
        assert len(result.errors) > 0

    async def test_validate_missing_required_fields(self, mock_db):
        """Test validating config with missing fields."""
        service = StrategyService(mock_db)

        result = await service.validate_config(INVALID_MISSING_ENTRY)

        assert result.valid is False
        assert any("entry" in e.lower() for e in result.errors)

    async def test_validate_warnings_for_high_risk(self, mock_db):
        """Test validation adds warnings for high-risk settings."""
        service = StrategyService(mock_db)

        high_risk_config = """(strategy
          :name "High Risk"
          :symbols ["AAPL"]
          :timeframe "1D"
          :entry true
          :exit true
          :stop-loss-pct 15.0)"""

        result = await service.validate_config(high_risk_config)

        assert result.valid is True
        assert any("stop loss" in w.lower() for w in result.warnings)


# ===================
# Deployment Tests
# ===================


class TestDeployments:
    """Tests for deployment operations."""

    async def test_create_deployment_paper(self, mock_db, tenant_id, strategy_id):
        """Test creating a paper trading deployment."""
        service = StrategyService(mock_db)

        mock_strategy = make_mock_strategy(
            id=strategy_id,
            tenant_id=tenant_id,
            current_version=1,
        )
        mock_version = make_mock_version(strategy_id=strategy_id)

        # Setup mock refresh to set deployment attributes
        def set_deployment_attrs(deployment):
            deployment.id = uuid4()
            deployment.created_at = datetime.now()
            deployment.updated_at = datetime.now()

        mock_db.refresh = AsyncMock(side_effect=set_deployment_attrs)

        with (
            patch.object(service, "_get_strategy_by_id", return_value=mock_strategy),
            patch.object(service, "_get_version", return_value=mock_version),
        ):
            data = DeploymentCreate(
                environment=DeploymentEnvironment.PAPER,
            )

            result = await service.create_deployment(
                tenant_id=tenant_id,
                strategy_id=strategy_id,
                data=data,
            )

        mock_db.add.assert_called()
        mock_db.commit.assert_called()
        assert result is not None
        assert result.status.value == "pending"

    async def test_create_deployment_strategy_not_found(self, mock_db, tenant_id):
        """Test creating deployment for non-existent strategy."""
        service = StrategyService(mock_db)

        with patch.object(service, "_get_strategy_by_id", return_value=None):
            data = DeploymentCreate(environment=DeploymentEnvironment.PAPER)

            result = await service.create_deployment(
                tenant_id=tenant_id,
                strategy_id=uuid4(),
                data=data,
            )

        assert result is None

    async def test_create_deployment_invalid_version(self, mock_db, tenant_id, strategy_id):
        """Test creating deployment with non-existent version."""
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
            data = DeploymentCreate(
                version=999,  # Non-existent version
                environment=DeploymentEnvironment.PAPER,
            )

            with pytest.raises(ValueError) as exc_info:
                await service.create_deployment(
                    tenant_id=tenant_id,
                    strategy_id=strategy_id,
                    data=data,
                )
            assert "not found" in str(exc_info.value)

    async def test_list_deployments(self, mock_db, tenant_id, strategy_id):
        """Test listing deployments for a strategy."""
        service = StrategyService(mock_db)

        from llamatrade_db.models.strategy import (
            DeploymentEnvironment as DBEnv,
        )
        from llamatrade_db.models.strategy import (
            DeploymentStatus as DBStatus,
        )

        mock_deployment = MagicMock()
        mock_deployment.id = uuid4()
        mock_deployment.strategy_id = strategy_id
        mock_deployment.tenant_id = tenant_id
        mock_deployment.version = 1
        mock_deployment.environment = DBEnv.PAPER
        mock_deployment.status = DBStatus.PENDING
        mock_deployment.started_at = None
        mock_deployment.stopped_at = None
        mock_deployment.config_override = None
        mock_deployment.error_message = None
        mock_deployment.created_at = datetime.now()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_deployment]
        mock_db.execute.return_value = mock_result

        deployments = await service.list_deployments(
            tenant_id=tenant_id,
            strategy_id=strategy_id,
        )

        assert len(deployments) == 1
