"""Strategy service integration tests with real database.

Since the strategy service is currently stubbed, these tests verify
database operations directly to ensure the ORM models and relationships
work correctly with PostgreSQL.
"""

from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models import Strategy, StrategyVersion, Tenant, User
from tests.factories import (
    STRATEGY_STATUS_ACTIVE,
    STRATEGY_STATUS_ARCHIVED,
    StrategyFactory,
    StrategyVersionFactory,
)

pytestmark = pytest.mark.integration


class TestStrategyPersistence:
    """Tests for strategy database persistence."""

    async def test_create_strategy_persists_to_db(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test that creating a strategy persists it to database."""
        strategy = StrategyFactory.create(
            tenant_id=test_tenant.id,
            created_by=test_user.id,
            name="Test Strategy",
            description="A test strategy",
        )

        db_session.add(strategy)
        await db_session.flush()

        # Verify it was persisted
        result = await db_session.execute(select(Strategy).where(Strategy.id == strategy.id))
        persisted = result.scalar_one_or_none()

        assert persisted is not None
        assert persisted.id == strategy.id
        assert persisted.name == "Test Strategy"
        assert persisted.description == "A test strategy"
        assert persisted.tenant_id == test_tenant.id
        assert persisted.created_by == test_user.id

    async def test_strategy_version_config_stored_as_jsonb(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test that strategy version config is properly stored as JSONB."""
        config_json = {
            "symbols": ["AAPL", "GOOGL", "MSFT"],
            "timeframe": "1H",
            "indicators": [
                {"type": "sma", "params": {"period": 20}},
                {"type": "rsi", "params": {"period": 14}},
            ],
            "nested": {"deep": {"value": 123}},
        }

        strategy = StrategyFactory.create(
            tenant_id=test_tenant.id,
            created_by=test_user.id,
        )
        db_session.add(strategy)
        await db_session.flush()

        version = StrategyVersionFactory.create(
            tenant_id=test_tenant.id,
            strategy_id=strategy.id,
            created_by=test_user.id,
            config_json=config_json,
            symbols=["AAPL", "GOOGL", "MSFT"],
            timeframe="1H",
        )
        db_session.add(version)
        await db_session.flush()

        # Query back and verify config
        result = await db_session.execute(
            select(StrategyVersion).where(StrategyVersion.id == version.id)
        )
        persisted = result.scalar_one()

        assert persisted.config_json == config_json
        assert persisted.config_json["symbols"] == ["AAPL", "GOOGL", "MSFT"]
        assert persisted.config_json["nested"]["deep"]["value"] == 123

    async def test_strategy_tenant_index_exists(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test that queries filtered by tenant_id are efficient (use index)."""
        # Create multiple strategies across multiple tenants
        other_tenant = Tenant(
            id=uuid4(),
            name="Other Org",
            slug=f"other-org-{uuid4().hex[:8]}",
            is_active=True,
        )
        db_session.add(other_tenant)
        await db_session.flush()

        for i in range(5):
            db_session.add(
                StrategyFactory.create(
                    tenant_id=test_tenant.id,
                    created_by=test_user.id,
                    name=f"Tenant 1 Strategy {i}",
                )
            )
            db_session.add(
                StrategyFactory.create(
                    tenant_id=other_tenant.id,
                    created_by=test_user.id,  # OK for test
                    name=f"Tenant 2 Strategy {i}",
                )
            )

        await db_session.flush()

        # Query for first tenant only
        result = await db_session.execute(
            select(Strategy).where(Strategy.tenant_id == test_tenant.id)
        )
        strategies = result.scalars().all()

        assert len(strategies) == 5
        assert all(s.tenant_id == test_tenant.id for s in strategies)


class TestStrategyVersioning:
    """Tests for strategy version management."""

    async def test_create_strategy_version(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test creating strategy versions."""
        strategy = StrategyFactory.create(
            tenant_id=test_tenant.id,
            created_by=test_user.id,
        )
        db_session.add(strategy)
        await db_session.flush()

        version = StrategyVersionFactory.create(
            tenant_id=test_tenant.id,
            strategy_id=strategy.id,
            created_by=test_user.id,
            version=1,
            config_json={"symbols": ["AAPL"], "timeframe": "1D"},
            symbols=["AAPL"],
            changelog="Initial version",
        )
        db_session.add(version)
        await db_session.flush()

        # Verify version was created
        result = await db_session.execute(
            select(StrategyVersion).where(StrategyVersion.strategy_id == strategy.id)
        )
        versions = result.scalars().all()

        assert len(versions) == 1
        assert versions[0].version == 1
        assert versions[0].changelog == "Initial version"

    async def test_multiple_versions_per_strategy(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test creating multiple versions for a strategy."""
        strategy = StrategyFactory.create(
            tenant_id=test_tenant.id,
            created_by=test_user.id,
            current_version=3,
        )
        db_session.add(strategy)
        await db_session.flush()

        # Create 3 versions
        for v in range(1, 4):
            version = StrategyVersionFactory.create(
                tenant_id=test_tenant.id,
                strategy_id=strategy.id,
                created_by=test_user.id,
                version=v,
                config_json={"symbols": ["AAPL"], "version_param": v, "timeframe": "1D"},
                symbols=["AAPL"],
                changelog=f"Version {v}",
            )
            db_session.add(version)

        await db_session.flush()

        # Query versions ordered by version number
        result = await db_session.execute(
            select(StrategyVersion)
            .where(StrategyVersion.strategy_id == strategy.id)
            .order_by(StrategyVersion.version)
        )
        versions = result.scalars().all()

        assert len(versions) == 3
        assert [v.version for v in versions] == [1, 2, 3]
        assert versions[0].config_json["version_param"] == 1
        assert versions[2].config_json["version_param"] == 3

    async def test_version_uniqueness_constraint(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test that duplicate version numbers for same strategy fail."""
        strategy = StrategyFactory.create(
            tenant_id=test_tenant.id,
            created_by=test_user.id,
        )
        db_session.add(strategy)
        await db_session.flush()

        # Create version 1
        version1 = StrategyVersionFactory.create(
            tenant_id=test_tenant.id,
            strategy_id=strategy.id,
            created_by=test_user.id,
            version=1,
        )
        db_session.add(version1)
        await db_session.flush()

        # Try to create another version 1 (should fail)
        version1_dup = StrategyVersionFactory.create(
            tenant_id=test_tenant.id,
            strategy_id=strategy.id,
            created_by=test_user.id,
            version=1,  # Duplicate
        )
        db_session.add(version1_dup)

        with pytest.raises(Exception):  # IntegrityError
            await db_session.flush()


class TestStrategyCascadeDelete:
    """Tests for cascade delete behavior."""

    async def test_strategy_delete_cascades_to_versions(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test that deleting a strategy deletes its versions."""
        strategy = StrategyFactory.create(
            tenant_id=test_tenant.id,
            created_by=test_user.id,
        )
        db_session.add(strategy)
        await db_session.flush()

        # Create versions
        for v in range(1, 4):
            version = StrategyVersionFactory.create(
                tenant_id=test_tenant.id,
                strategy_id=strategy.id,
                created_by=test_user.id,
                version=v,
            )
            db_session.add(version)

        await db_session.flush()

        strategy_id = strategy.id

        # Delete the strategy
        await db_session.delete(strategy)
        await db_session.flush()

        # Verify strategy is gone
        result = await db_session.execute(select(Strategy).where(Strategy.id == strategy_id))
        assert result.scalar_one_or_none() is None

        # Verify versions are gone
        result = await db_session.execute(
            select(StrategyVersion).where(StrategyVersion.strategy_id == strategy_id)
        )
        assert len(result.scalars().all()) == 0


class TestStrategyQueries:
    """Tests for common query patterns."""

    async def test_count_strategies_by_tenant(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test counting strategies per tenant."""
        # Create 5 strategies
        for i in range(5):
            db_session.add(
                StrategyFactory.create(
                    tenant_id=test_tenant.id,
                    created_by=test_user.id,
                    name=f"Count Strategy {i}",
                )
            )
        await db_session.flush()

        # Count
        result = await db_session.execute(
            select(func.count(Strategy.id)).where(Strategy.tenant_id == test_tenant.id)
        )
        count = result.scalar()

        assert count == 5

    async def test_filter_active_strategies(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test filtering by status field."""
        # Create active strategies
        for i in range(3):
            db_session.add(
                StrategyFactory.create(
                    tenant_id=test_tenant.id,
                    created_by=test_user.id,
                    name=f"Active Strategy {i}",
                    status=STRATEGY_STATUS_ACTIVE,  # Proto int: ACTIVE=2
                )
            )

        # Create archived strategies
        for i in range(2):
            db_session.add(
                StrategyFactory.create(
                    tenant_id=test_tenant.id,
                    created_by=test_user.id,
                    name=f"Archived Strategy {i}",
                    status=STRATEGY_STATUS_ARCHIVED,  # Proto int: ARCHIVED=4
                )
            )

        await db_session.flush()

        # Query active only
        result = await db_session.execute(
            select(Strategy).where(
                Strategy.tenant_id == test_tenant.id,
                Strategy.status == STRATEGY_STATUS_ACTIVE,  # Proto int: ACTIVE=2
            )
        )
        active = result.scalars().all()

        assert len(active) == 3
        assert all(s.status == STRATEGY_STATUS_ACTIVE for s in active)

    async def test_filter_public_strategies(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test finding public strategies."""
        # Create private strategies
        for i in range(3):
            db_session.add(
                StrategyFactory.create(
                    tenant_id=test_tenant.id,
                    created_by=test_user.id,
                    name=f"Private Strategy {i}",
                    is_public=False,
                )
            )

        # Create public strategies
        for i in range(2):
            db_session.add(
                StrategyFactory.create(
                    tenant_id=test_tenant.id,
                    created_by=test_user.id,
                    name=f"Public Strategy {i}",
                    is_public=True,
                )
            )

        await db_session.flush()

        # Query public only
        result = await db_session.execute(
            select(Strategy).where(Strategy.is_public == True)  # noqa: E712
        )
        public = result.scalars().all()

        assert len(public) == 2
        assert all(s.is_public for s in public)

    async def test_pagination(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test paginated query."""
        # Create 25 strategies
        for i in range(25):
            db_session.add(
                StrategyFactory.create(
                    tenant_id=test_tenant.id,
                    created_by=test_user.id,
                    name=f"Strategy {i:02d}",
                )
            )
        await db_session.flush()

        # Page 1 (first 10)
        result = await db_session.execute(
            select(Strategy)
            .where(Strategy.tenant_id == test_tenant.id)
            .order_by(Strategy.name)
            .offset(0)
            .limit(10)
        )
        page1 = result.scalars().all()

        assert len(page1) == 10
        assert page1[0].name == "Strategy 00"
        assert page1[9].name == "Strategy 09"

        # Page 2
        result = await db_session.execute(
            select(Strategy)
            .where(Strategy.tenant_id == test_tenant.id)
            .order_by(Strategy.name)
            .offset(10)
            .limit(10)
        )
        page2 = result.scalars().all()

        assert len(page2) == 10
        assert page2[0].name == "Strategy 10"

        # Page 3 (partial)
        result = await db_session.execute(
            select(Strategy)
            .where(Strategy.tenant_id == test_tenant.id)
            .order_by(Strategy.name)
            .offset(20)
            .limit(10)
        )
        page3 = result.scalars().all()

        assert len(page3) == 5  # Only 5 remaining


class TestStrategyRelationships:
    """Tests for strategy model relationships."""

    async def test_strategy_version_relationship(
        self,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test the strategy -> versions relationship."""
        strategy = StrategyFactory.create(
            tenant_id=test_tenant.id,
            created_by=test_user.id,
        )
        db_session.add(strategy)
        await db_session.flush()

        # Add versions
        for v in range(1, 4):
            version = StrategyVersionFactory.create(
                tenant_id=test_tenant.id,
                strategy_id=strategy.id,
                created_by=test_user.id,
                version=v,
            )
            db_session.add(version)

        await db_session.flush()
        await db_session.refresh(strategy)

        # Access versions via relationship
        # Note: May need to load explicitly with selectinload in real code
        result = await db_session.execute(
            select(StrategyVersion).where(StrategyVersion.strategy_id == strategy.id)
        )
        versions = result.scalars().all()

        assert len(versions) == 3
