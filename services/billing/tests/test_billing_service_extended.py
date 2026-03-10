"""Extended tests for BillingService to improve coverage."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from llamatrade_proto.generated import billing_pb2

from src.services.billing_service import DEFAULT_PLANS, BillingService

# === Test Fixtures ===


@pytest.fixture
def mock_db() -> MagicMock:
    """Create a mock database session."""
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def mock_stripe() -> MagicMock:
    """Create a mock Stripe client."""
    stripe = MagicMock()
    stripe.get_or_create_customer = AsyncMock(return_value="cus_123")
    stripe.create_subscription = AsyncMock()
    stripe.update_subscription = AsyncMock()
    stripe.cancel_subscription = AsyncMock()
    stripe.reactivate_subscription = AsyncMock()
    return stripe


@pytest.fixture
def billing_service(mock_db: MagicMock, mock_stripe: MagicMock) -> BillingService:
    """Create a BillingService instance."""
    return BillingService(mock_db, mock_stripe)


@pytest.fixture
def test_tenant_id() -> UUID:
    return uuid4()


# === list_plans Tests ===


class TestListPlans:
    """Tests for list_plans method."""

    async def test_list_plans_returns_defaults_when_db_empty(
        self, billing_service: BillingService, mock_db: MagicMock
    ) -> None:
        """Test listing plans returns defaults when DB is empty."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        plans = await billing_service.list_plans()

        assert len(plans) == len(DEFAULT_PLANS)
        assert plans[0].id == "free"

    async def test_list_plans_returns_db_plans(
        self, billing_service: BillingService, mock_db: MagicMock
    ) -> None:
        """Test listing plans returns plans from database."""
        mock_plan = MagicMock()
        mock_plan.name = "starter"
        mock_plan.display_name = "Starter"
        mock_plan.tier = billing_pb2.PLAN_TIER_STARTER
        mock_plan.price_monthly = Decimal("29.00")
        mock_plan.price_yearly = Decimal("290.00")
        mock_plan.features = {"backtests": True}
        mock_plan.limits = {"backtests_per_month": 50}
        mock_plan.trial_days = 14

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_plan]
        mock_db.execute.return_value = mock_result

        plans = await billing_service.list_plans()

        assert len(plans) == 1
        assert plans[0].name == "Starter"


# === get_plan Tests ===


class TestGetPlan:
    """Tests for get_plan method."""

    async def test_get_plan_from_defaults(
        self, billing_service: BillingService, mock_db: MagicMock
    ) -> None:
        """Test getting plan from defaults when not in DB."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        plan = await billing_service.get_plan("free")

        assert plan is not None
        assert plan.id == "free"

    async def test_get_plan_not_found(
        self, billing_service: BillingService, mock_db: MagicMock
    ) -> None:
        """Test getting non-existent plan."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        plan = await billing_service.get_plan("nonexistent")

        assert plan is None


# === get_subscription Tests ===


class TestGetSubscription:
    """Tests for get_subscription method."""

    async def test_get_subscription_not_found(
        self, billing_service: BillingService, mock_db: MagicMock, test_tenant_id: UUID
    ) -> None:
        """Test getting subscription when none exists."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await billing_service.get_subscription(test_tenant_id)

        assert result is None

    async def test_get_subscription_found(
        self, billing_service: BillingService, mock_db: MagicMock, test_tenant_id: UUID
    ) -> None:
        """Test getting existing subscription."""
        now = datetime.now(UTC)
        mock_plan = MagicMock()
        mock_plan.name = "starter"
        mock_plan.display_name = "Starter"
        mock_plan.tier = billing_pb2.PLAN_TIER_STARTER
        mock_plan.price_monthly = Decimal("29.00")
        mock_plan.price_yearly = Decimal("290.00")
        mock_plan.features = {}
        mock_plan.limits = {}
        mock_plan.trial_days = 14

        mock_sub = MagicMock()
        mock_sub.id = uuid4()
        mock_sub.tenant_id = test_tenant_id
        mock_sub.plan = mock_plan
        mock_sub.status = billing_pb2.SUBSCRIPTION_STATUS_ACTIVE
        mock_sub.billing_cycle = billing_pb2.BILLING_INTERVAL_MONTHLY
        mock_sub.current_period_start = now
        mock_sub.current_period_end = now + timedelta(days=30)
        mock_sub.cancel_at_period_end = False
        mock_sub.trial_start = None
        mock_sub.trial_end = None
        mock_sub.stripe_subscription_id = "sub_123"
        mock_sub.created_at = now

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_sub
        mock_db.execute.return_value = mock_result

        result = await billing_service.get_subscription(test_tenant_id)

        assert result is not None
        assert result.status == billing_pb2.SUBSCRIPTION_STATUS_ACTIVE


# === create_subscription Tests ===


class TestCreateSubscription:
    """Tests for create_subscription method."""

    def test_default_plans_contains_free(self) -> None:
        """Test DEFAULT_PLANS contains free tier."""
        free_plan = next((p for p in DEFAULT_PLANS if p.id == "free"), None)

        assert free_plan is not None
        assert free_plan.tier == billing_pb2.PLAN_TIER_FREE
        assert free_plan.price_monthly == 0

    def test_default_plans_contains_pro(self) -> None:
        """Test DEFAULT_PLANS contains pro tier."""
        pro_plan = next((p for p in DEFAULT_PLANS if p.id == "pro"), None)

        assert pro_plan is not None
        assert pro_plan.tier == billing_pb2.PLAN_TIER_PRO
        assert pro_plan.price_monthly > 0


# === update_subscription Tests ===


class TestUpdateSubscription:
    """Tests for update_subscription method."""

    async def test_update_subscription_no_active(
        self, billing_service: BillingService, mock_db: MagicMock, test_tenant_id: UUID
    ) -> None:
        """Test updating subscription when none active."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="No active subscription found"):
            await billing_service.update_subscription(test_tenant_id, "pro")


# === cancel_subscription Tests ===


class TestCancelSubscription:
    """Tests for cancel_subscription method."""

    async def test_cancel_subscription_no_active(
        self, billing_service: BillingService, mock_db: MagicMock, test_tenant_id: UUID
    ) -> None:
        """Test cancelling subscription when none active."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="No active subscription found"):
            await billing_service.cancel_subscription(test_tenant_id)


# === reactivate_subscription Tests ===


class TestReactivateSubscription:
    """Tests for reactivate_subscription method."""

    async def test_reactivate_subscription_not_pending_cancel(
        self, billing_service: BillingService, mock_db: MagicMock, test_tenant_id: UUID
    ) -> None:
        """Test reactivating when no subscription pending cancellation."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="No subscription pending cancellation"):
            await billing_service.reactivate_subscription(test_tenant_id)


# === sync_subscription_from_stripe Tests ===


class TestSyncSubscriptionFromStripe:
    """Tests for sync_subscription_from_stripe method."""

    async def test_sync_updates_status(
        self, billing_service: BillingService, mock_db: MagicMock
    ) -> None:
        """Test syncing subscription status from Stripe."""
        mock_sub = MagicMock()
        mock_sub.status = billing_pb2.SUBSCRIPTION_STATUS_ACTIVE

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_sub
        mock_db.execute.return_value = mock_result

        await billing_service.sync_subscription_from_stripe("sub_123", "cancelled")

        assert mock_sub.status == billing_pb2.SUBSCRIPTION_STATUS_CANCELED
        mock_db.commit.assert_called_once()

    async def test_sync_no_subscription_found(
        self, billing_service: BillingService, mock_db: MagicMock
    ) -> None:
        """Test syncing when subscription not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Should not raise
        await billing_service.sync_subscription_from_stripe("sub_nonexistent", "active")


# === _is_uuid Tests ===


class TestIsUuid:
    """Tests for _is_uuid helper method."""

    def test_is_uuid_valid(self, billing_service: BillingService) -> None:
        """Test valid UUID detection."""
        assert billing_service._is_uuid(str(uuid4())) is True

    def test_is_uuid_invalid(self, billing_service: BillingService) -> None:
        """Test invalid UUID detection."""
        assert billing_service._is_uuid("not-a-uuid") is False
        assert billing_service._is_uuid("free") is False
