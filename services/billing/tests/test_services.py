"""Unit tests for billing services."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_proto.generated import billing_pb2
from tests.conftest import MockAsyncSession, MockPlan, MockStripeClient, MockSubscription

from src.models import SubscriptionCreateRequest
from src.services.billing_service import (
    DEFAULT_PLANS,
    BillingService,
    stripe_status_to_proto,
)
from src.services.payment_method_service import PaymentMethodService
from src.stripe.client import StripeClient, StripeError, SubscriptionResult


class _DownStripe(MockStripeClient):
    """Stripe double whose subscription mutations all fail."""

    async def create_subscription(
        self, customer_id: str, price_id: str, payment_method_id: str, trial_days: int = 0
    ) -> SubscriptionResult:
        raise StripeError("stripe down", "api_error")

    async def update_subscription(
        self, subscription_id: str, price_id: str, proration_behavior: str = "create_prorations"
    ) -> SubscriptionResult:
        raise StripeError("stripe down", "api_error")

    async def cancel_subscription(self, subscription_id: str, at_period_end: bool = True) -> bool:
        raise StripeError("stripe down", "api_error")

    async def reactivate_subscription(self, subscription_id: str) -> SubscriptionResult:
        raise StripeError("stripe down", "api_error")


class _WeirdStatusStripe(MockStripeClient):
    """Stripe double whose subscription mutations return an unrecognized status."""

    async def create_subscription(
        self, customer_id: str, price_id: str, payment_method_id: str, trial_days: int = 0
    ) -> SubscriptionResult:
        result = await super().create_subscription(
            customer_id, price_id, payment_method_id, trial_days
        )
        return replace(result, status="brand_new_status")

    async def update_subscription(
        self, subscription_id: str, price_id: str, proration_behavior: str = "create_prorations"
    ) -> SubscriptionResult:
        result = await super().update_subscription(subscription_id, price_id)
        return replace(result, status="brand_new_status")


def _stripe(client: MockStripeClient) -> StripeClient:
    return cast(StripeClient, client)


def _db(session: MockAsyncSession) -> AsyncSession:
    return cast(AsyncSession, session)


class TestBillingServicePlans:
    """Tests for BillingService plan methods."""

    async def test_list_plans_returns_defaults_when_db_empty(self) -> None:
        """Test listing plans returns defaults when database is empty."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: []))

        service = BillingService(mock_db, cast(Any, MockStripeClient()))
        plans = await service.list_plans()

        assert len(plans) == 3
        assert plans[0].name == "free"
        assert plans[1].name == "starter"
        assert plans[2].name == "pro"

    async def test_list_plans_returns_db_plans_when_available(self) -> None:
        """Test listing plans returns database plans when available."""
        mock_plan = MockPlan(name="custom", display_name="Custom Plan")
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: [mock_plan]))

        service = BillingService(mock_db, cast(Any, MockStripeClient()))
        plans = await service.list_plans()

        assert len(plans) == 1
        assert plans[0].display_name == "Custom Plan"

    async def test_get_plan_from_defaults(self) -> None:
        """Test getting plan from defaults."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        service = BillingService(mock_db, cast(Any, MockStripeClient()))
        plan = await service.get_plan("starter")

        assert plan is not None
        assert plan.name == "starter"

    async def test_get_plan_not_found(self) -> None:
        """Test getting non-existent plan."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        service = BillingService(mock_db, cast(Any, MockStripeClient()))
        plan = await service.get_plan("nonexistent")

        assert plan is None


class TestBillingServiceSubscriptions:
    """Tests for BillingService subscription methods."""

    async def test_get_subscription_not_found(self) -> None:
        """Test getting subscription when none exists."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        service = BillingService(mock_db, cast(Any, MockStripeClient()))
        subscription = await service.get_subscription(uuid4())

        assert subscription is None

    async def test_get_subscription_found(self) -> None:
        """Test getting subscription when one exists."""
        mock_sub = MockSubscription()
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_sub)

        service = BillingService(mock_db, cast(Any, MockStripeClient()))
        subscription = await service.get_subscription(mock_sub.tenant_id)

        assert subscription is not None
        assert subscription.status == billing_pb2.SUBSCRIPTION_STATUS_ACTIVE

    async def test_cancel_subscription_not_found(self) -> None:
        """Test canceling subscription when none exists."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        service = BillingService(mock_db, cast(Any, MockStripeClient()))

        with pytest.raises(ValueError, match="No active subscription found"):
            await service.cancel_subscription(uuid4())

    async def test_cancel_subscription_at_period_end(self) -> None:
        """Test canceling subscription at period end."""
        mock_sub = MockSubscription()
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_sub)

        service = BillingService(mock_db, cast(Any, MockStripeClient()))
        result = await service.cancel_subscription(mock_sub.tenant_id, at_period_end=True)

        assert result.cancel_at_period_end is True

    async def test_cancel_subscription_immediately(self) -> None:
        """Test canceling subscription immediately."""
        mock_sub = MockSubscription()
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_sub)

        service = BillingService(mock_db, cast(Any, MockStripeClient()))
        await service.cancel_subscription(mock_sub.tenant_id, at_period_end=False)

        assert mock_sub.status == billing_pb2.SUBSCRIPTION_STATUS_CANCELED

    async def test_reactivate_subscription_not_found(self) -> None:
        """Test reactivating subscription when none pending cancellation."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        service = BillingService(mock_db, cast(Any, MockStripeClient()))

        with pytest.raises(ValueError, match="No subscription pending cancellation found"):
            await service.reactivate_subscription(uuid4())

    async def test_reactivate_subscription_success(self) -> None:
        """Test reactivating subscription successfully."""
        mock_sub = MockSubscription(cancel_at_period_end=True)
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_sub)

        service = BillingService(mock_db, cast(Any, MockStripeClient()))
        result = await service.reactivate_subscription(mock_sub.tenant_id)

        assert result.cancel_at_period_end is False

    async def test_ensure_stripe_customer(self) -> None:
        """Test ensuring Stripe customer exists."""
        mock_db = AsyncMock()
        stripe_client = MockStripeClient()

        service = BillingService(mock_db, cast(Any, stripe_client))
        customer_id = await service.ensure_stripe_customer(uuid4(), "test@example.com")

        assert customer_id.startswith("cus_test_")


class MockPaymentMethod:
    """Mock PaymentMethod model."""

    def __init__(self, **kwargs: Any) -> None:
        self.id = kwargs.get("id", uuid4())
        self.tenant_id = kwargs.get("tenant_id", uuid4())
        self.stripe_payment_method_id = kwargs.get("stripe_payment_method_id", "pm_test_123")
        self.stripe_customer_id = kwargs.get("stripe_customer_id", "cus_test_123")
        self.type = kwargs.get("type", "card")
        self.card_brand = kwargs.get("card_brand", "visa")
        self.card_last4 = kwargs.get("card_last4", "4242")
        self.card_exp_month = kwargs.get("card_exp_month", 12)
        self.card_exp_year = kwargs.get("card_exp_year", 2030)
        self.is_default = kwargs.get("is_default", False)
        self.created_at = kwargs.get("created_at", datetime.now(UTC))


class TestPaymentMethodService:
    """Tests for PaymentMethodService."""

    async def test_create_setup_intent(self) -> None:
        """Test creating setup intent."""
        mock_db = AsyncMock()
        stripe_client = MockStripeClient()
        billing_service = BillingService(mock_db, cast(Any, stripe_client))

        service = PaymentMethodService(mock_db, cast(Any, stripe_client), billing_service)
        result = await service.create_setup_intent(uuid4(), "test@example.com")

        assert result.client_secret == "seti_test_0_secret_test"

    async def test_list_payment_methods_empty(self) -> None:
        """Test listing payment methods when none exist."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: []))
        stripe_client = MockStripeClient()
        billing_service = BillingService(mock_db, cast(Any, stripe_client))

        service = PaymentMethodService(mock_db, cast(Any, stripe_client), billing_service)
        methods = await service.list_payment_methods(uuid4())

        assert methods == []

    async def test_list_payment_methods_with_data(self) -> None:
        """Test listing payment methods when some exist."""
        mock_pm = MockPaymentMethod()
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: [mock_pm]))
        stripe_client = MockStripeClient()
        billing_service = BillingService(mock_db, cast(Any, stripe_client))

        service = PaymentMethodService(mock_db, cast(Any, stripe_client), billing_service)
        methods = await service.list_payment_methods(mock_pm.tenant_id)

        assert len(methods) == 1
        assert methods[0].card_brand == "visa"

    async def test_get_payment_method_found(self) -> None:
        """Test getting a payment method that exists."""
        mock_pm = MockPaymentMethod()
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_pm)
        stripe_client = MockStripeClient()
        billing_service = BillingService(mock_db, cast(Any, stripe_client))

        service = PaymentMethodService(mock_db, cast(Any, stripe_client), billing_service)
        result = await service.get_payment_method(mock_pm.tenant_id, mock_pm.id)

        assert result is not None
        assert result.id == mock_pm.id

    async def test_get_payment_method_not_found(self) -> None:
        """Test getting a payment method that doesn't exist."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)
        stripe_client = MockStripeClient()
        billing_service = BillingService(mock_db, cast(Any, stripe_client))

        service = PaymentMethodService(mock_db, cast(Any, stripe_client), billing_service)
        result = await service.get_payment_method(uuid4(), uuid4())

        assert result is None

    async def test_delete_payment_method_not_found(self) -> None:
        """Test deleting payment method that doesn't exist."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)
        stripe_client = MockStripeClient()
        billing_service = BillingService(mock_db, cast(Any, stripe_client))

        service = PaymentMethodService(mock_db, cast(Any, stripe_client), billing_service)
        result = await service.delete_payment_method(uuid4(), uuid4())

        assert result is False

    async def test_set_default_payment_method_not_found(self) -> None:
        """Test setting default on non-existent payment method."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)
        stripe_client = MockStripeClient()
        billing_service = BillingService(mock_db, cast(Any, stripe_client))

        service = PaymentMethodService(mock_db, cast(Any, stripe_client), billing_service)

        with pytest.raises(ValueError, match="Payment method not found"):
            await service.set_default_payment_method(uuid4(), uuid4())


class TestBillingServiceUpdate:
    """Tests for BillingService update methods."""

    async def test_update_subscription_not_found(self) -> None:
        """Test updating subscription when none exists."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        service = BillingService(mock_db, cast(Any, MockStripeClient()))

        with pytest.raises(ValueError, match="No active subscription found"):
            await service.update_subscription(uuid4(), "pro")

    async def test_update_subscription_plan_not_found(self) -> None:
        """Test updating subscription with non-existent plan."""
        mock_sub = MockSubscription()

        # First call returns subscription, second returns None for plan
        call_count = 0

        def mock_scalar():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_sub
            return None

        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=mock_scalar)

        service = BillingService(mock_db, cast(Any, MockStripeClient()))

        with pytest.raises(ValueError, match="not found"):
            await service.update_subscription(mock_sub.tenant_id, "nonexistent")


class TestPaymentMethodServiceDelete:
    """Tests for PaymentMethodService delete operations."""

    async def test_delete_payment_method_success(self) -> None:
        """Test successful payment method deletion."""
        mock_pm = MockPaymentMethod(is_default=False)

        # Return mock_pm on first call, then None for other checks
        call_count = 0

        def mock_scalar():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_pm
            return None

        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=mock_scalar, scalars=lambda: MagicMock(all=lambda: [])
        )
        stripe_client = MockStripeClient()
        billing_service = BillingService(mock_db, cast(Any, stripe_client))

        service = PaymentMethodService(mock_db, cast(Any, stripe_client), billing_service)
        result = await service.delete_payment_method(mock_pm.tenant_id, mock_pm.id)

        assert result is True


class TestBillingServiceCreateSubscription:
    """Tests for BillingService create subscription."""

    async def test_create_subscription_plan_not_found(self) -> None:
        """Test creating subscription with non-existent plan."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=lambda: None, scalars=lambda: MagicMock(all=lambda: [])
        )

        service = BillingService(mock_db, cast(Any, MockStripeClient()))

        with pytest.raises(ValueError, match="not found"):
            await service.create_subscription(
                tenant_id=uuid4(),
                email="test@example.com",
                request=SubscriptionCreateRequest(
                    plan_id="nonexistent",
                    payment_method_id="pm_test",
                    billing_cycle=billing_pb2.BILLING_INTERVAL_MONTHLY,
                ),
            )


class TestDefaultPlans:
    """Cross-field invariants of the default catalog (values pinned by plan-limit parity)."""

    def test_all_plans_have_features(self) -> None:
        """Test that all plans have features defined."""
        for plan in DEFAULT_PLANS:
            assert plan.features is not None
            assert "backtests" in plan.features

    def test_all_plans_have_limits(self) -> None:
        """Test that all plans have limits defined."""
        for plan in DEFAULT_PLANS:
            assert plan.limits is not None
            assert "backtests_per_month" in plan.limits

    def test_plan_id_matches_tier(self) -> None:
        """Test that plan IDs match their tiers."""
        tier_to_id = {
            billing_pb2.PLAN_TIER_FREE: "free",
            billing_pb2.PLAN_TIER_STARTER: "starter",
            billing_pb2.PLAN_TIER_PRO: "pro",
        }
        for plan in DEFAULT_PLANS:
            assert plan.name == tier_to_id[plan.tier]

    def test_yearly_price_has_discount(self) -> None:
        """Test that yearly prices have discount."""
        for plan in DEFAULT_PLANS:
            if plan.price_monthly > 0:
                # Yearly should be less than 12x monthly (2 months free)
                assert plan.price_yearly < plan.price_monthly * 12


class TestCreateFreeSubscription:
    """Tests for creating free subscriptions."""

    async def test_get_free_plan_from_defaults(self) -> None:
        """Test getting free plan from defaults when not in DB."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = BillingService(mock_db, cast(Any, MockStripeClient()))

        # Get the free plan from defaults
        plan = await service.get_plan("free")
        assert plan is not None
        assert plan.name == "free"
        assert plan.tier == billing_pb2.PLAN_TIER_FREE
        assert plan.price_monthly == 0


class TestPaymentMethodSetDefault:
    """Tests for setting default payment method."""

    async def test_set_default_updates_stripe_and_db(self) -> None:
        """Test that set_default updates both Stripe and DB."""
        mock_pm = MockPaymentMethod(is_default=False)
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_pm)
        stripe_client = MockStripeClient()
        billing_service = BillingService(mock_db, cast(Any, stripe_client))

        service = PaymentMethodService(mock_db, cast(Any, stripe_client), billing_service)
        result = await service.set_default_payment_method(mock_pm.tenant_id, mock_pm.id)

        # Verify result
        assert result.id == mock_pm.id
        # Verify DB operations happened
        assert mock_db.commit.called


class TestListPlansFromDB:
    """Tests for listing plans from database."""

    async def test_list_plans_from_db(self) -> None:
        """Test listing plans when they exist in the database."""
        mock_plans = [
            MockPlan(name="db_free", display_name="DB Free", tier=billing_pb2.PLAN_TIER_FREE),
            MockPlan(name="db_pro", display_name="DB Pro", tier=billing_pb2.PLAN_TIER_PRO),
        ]
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: mock_plans))

        service = BillingService(mock_db, cast(Any, MockStripeClient()))
        plans = await service.list_plans()

        assert len(plans) == 2
        assert plans[0].name == "db_free"
        assert plans[1].name == "db_pro"


class TestGetPlanDB:
    """Tests for getting plan from database."""

    async def test_get_plan_db_found(self) -> None:
        """Test getting plan from DB when it exists."""
        mock_plan = MockPlan()
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_plan)

        service = BillingService(mock_db, cast(Any, MockStripeClient()))
        plan = await service.get_plan_db("starter")

        assert plan is not None
        assert plan.name == "starter"

    async def test_get_plan_db_not_found(self) -> None:
        """Test getting plan from DB when it doesn't exist."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        service = BillingService(mock_db, cast(Any, MockStripeClient()))
        plan = await service.get_plan_db("nonexistent")

        assert plan is None


class TestIsUuid:
    """Tests for _is_uuid helper."""

    def test_is_uuid_valid(self) -> None:
        """Test with valid UUID string."""
        from src.services.billing_service import BillingService

        service = BillingService(AsyncMock(), cast(Any, MockStripeClient()))
        assert service._is_uuid("12345678-1234-5678-1234-567812345678") is True

    def test_is_uuid_invalid(self) -> None:
        """Test with invalid UUID string."""
        from src.services.billing_service import BillingService

        service = BillingService(AsyncMock(), cast(Any, MockStripeClient()))
        assert service._is_uuid("not-a-uuid") is False

    def test_is_uuid_empty(self) -> None:
        """Test with empty string."""
        from src.services.billing_service import BillingService

        service = BillingService(AsyncMock(), cast(Any, MockStripeClient()))
        assert service._is_uuid("") is False


class TestGetPlanByName:
    """Tests for getting plan by name variations."""

    async def test_get_plan_case_insensitive(self) -> None:
        """Test getting plan by name is case-insensitive."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=lambda: None, scalars=lambda: MagicMock(all=lambda: [])
        )

        service = BillingService(mock_db, cast(Any, MockStripeClient()))

        # Get starter plan with different case
        plan = await service.get_plan("Starter")
        assert plan is not None
        assert plan.tier == billing_pb2.PLAN_TIER_STARTER

    async def test_get_plan_by_tier(self) -> None:
        """Test getting plan by tier name."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=lambda: None, scalars=lambda: MagicMock(all=lambda: [])
        )

        service = BillingService(mock_db, cast(Any, MockStripeClient()))

        # Get pro plan
        plan = await service.get_plan("pro")
        assert plan is not None
        assert plan.tier == billing_pb2.PLAN_TIER_PRO
        assert plan.price_monthly == 99


class TestDefaultPlanFeatures:
    """Cross-plan invariants of the default feature/limit configurations."""

    def test_free_plan_has_lowest_limits(self) -> None:
        """Test that free plan has the lowest limits."""
        free_plan = next((p for p in DEFAULT_PLANS if p.tier == billing_pb2.PLAN_TIER_FREE), None)
        pro_plan = next((p for p in DEFAULT_PLANS if p.tier == billing_pb2.PLAN_TIER_PRO), None)

        assert free_plan is not None
        assert pro_plan is not None

        # Free should have lower backtest limit than pro
        free_limit = free_plan.limits.get("backtests_per_month") or 0
        pro_limit = pro_plan.limits.get("backtests_per_month") or float("inf")

        assert free_limit < pro_limit


class TestBillingServiceEnsureCustomer:
    """Tests for ensure_stripe_customer."""

    async def test_ensure_customer_creates_new(self) -> None:
        """Test ensuring customer when none exists."""
        mock_db = AsyncMock()
        stripe_client = MockStripeClient()

        service = BillingService(mock_db, cast(Any, stripe_client))
        tenant_id = uuid4()
        email = "new@example.com"

        customer_id = await service.ensure_stripe_customer(tenant_id, email)

        assert customer_id.startswith("cus_test_")

    async def test_ensure_customer_returns_existing(self) -> None:
        """Test ensuring customer when one already exists."""
        mock_db = AsyncMock()
        stripe_client = MockStripeClient()

        service = BillingService(mock_db, cast(Any, stripe_client))
        tenant_id = uuid4()
        email = "existing@example.com"

        # Create first time
        customer_id1 = await service.ensure_stripe_customer(tenant_id, email)
        # Get again
        customer_id2 = await service.ensure_stripe_customer(tenant_id, email)

        assert customer_id1 == customer_id2


class TestStripeStatusToProto:
    """Tests for the Stripe-status to proto-status converter."""

    @pytest.mark.parametrize(
        ("stripe_status", "expected"),
        [
            ("active", billing_pb2.SUBSCRIPTION_STATUS_ACTIVE),
            ("ACTIVE", billing_pb2.SUBSCRIPTION_STATUS_ACTIVE),
            ("past_due", billing_pb2.SUBSCRIPTION_STATUS_PAST_DUE),
            ("canceled", billing_pb2.SUBSCRIPTION_STATUS_CANCELED),
            ("cancelled", billing_pb2.SUBSCRIPTION_STATUS_CANCELED),
            ("trialing", billing_pb2.SUBSCRIPTION_STATUS_TRIALING),
            ("paused", billing_pb2.SUBSCRIPTION_STATUS_PAUSED),
            ("incomplete", billing_pb2.SUBSCRIPTION_STATUS_PAST_DUE),
            ("incomplete_expired", billing_pb2.SUBSCRIPTION_STATUS_CANCELED),
            ("unpaid", billing_pb2.SUBSCRIPTION_STATUS_PAST_DUE),
        ],
    )
    def test_known_statuses_map(self, stripe_status: str, expected: int) -> None:
        assert stripe_status_to_proto(stripe_status) == expected

    def test_unknown_status_returns_none(self) -> None:
        """An unrecognized status returns None (never UNSPECIFIED or active)."""
        assert stripe_status_to_proto("brand_new_status") is None


class TestCreateSubscriptionBranches:
    """create_subscription error and fallback branches over the statement-aware session."""

    def _service(self, db: MockAsyncSession, stripe: MockStripeClient) -> BillingService:
        return BillingService(_db(db), _stripe(stripe))

    def _request(self) -> SubscriptionCreateRequest:
        return SubscriptionCreateRequest(
            plan_id="starter",
            payment_method_id="pm_test",
            billing_cycle=billing_pb2.BILLING_INTERVAL_MONTHLY,
        )

    async def test_paid_plan_missing_from_db_is_rejected(self) -> None:
        """A catalog-only paid plan cannot be subscribed (no Stripe price rows)."""
        db = MockAsyncSession()

        with pytest.raises(ValueError, match="not found in database"):
            await self._service(db, MockStripeClient()).create_subscription(
                uuid4(), "test@example.com", self._request()
            )

    async def test_plan_without_price_for_cycle_is_rejected(self) -> None:
        """A DB plan with no Stripe price for the requested cycle fails before Stripe."""
        db = MockAsyncSession()
        db.plans.append(MockPlan(stripe_price_id_monthly=""))
        stripe = MockStripeClient()

        with pytest.raises(ValueError, match="No Stripe price configured"):
            await self._service(db, stripe).create_subscription(
                uuid4(), "test@example.com", self._request()
            )

        assert stripe.subscriptions == {}

    async def test_stripe_failure_surfaces_payment_error(self) -> None:
        """A Stripe subscription failure maps to a payment ValueError, nothing persisted."""
        db = MockAsyncSession()
        db.plans.append(MockPlan())

        with pytest.raises(ValueError, match="Payment failed"):
            await self._service(db, _DownStripe()).create_subscription(
                uuid4(), "test@example.com", self._request()
            )

        assert db.added == []

    async def test_unknown_stripe_status_stored_as_past_due(self) -> None:
        """An unrecognized status on create is stored as PAST_DUE pending review."""
        db = MockAsyncSession()
        db.plans.append(MockPlan())

        subscription = await self._service(db, _WeirdStatusStripe()).create_subscription(
            uuid4(), "test@example.com", self._request()
        )

        assert subscription.status == billing_pb2.SUBSCRIPTION_STATUS_PAST_DUE


class TestUpdateSubscriptionBranches:
    """update_subscription error and fallback branches."""

    def _seed(
        self, db: MockAsyncSession, *, stripe_subscription_id: str | None = "sub_live_1"
    ) -> MockSubscription:
        subscription = MockSubscription(stripe_subscription_id=stripe_subscription_id)
        db.subscriptions.append(subscription)
        return subscription

    async def test_plan_missing_from_db_is_rejected(self) -> None:
        """A catalog-only target plan cannot be switched to."""
        db = MockAsyncSession()
        self._seed(db)
        service = BillingService(_db(db), _stripe(MockStripeClient()))

        with pytest.raises(ValueError, match="not found in database"):
            await service.update_subscription(uuid4(), "pro")

    async def test_plan_without_price_is_rejected(self) -> None:
        """A target plan with no Stripe price for the current cycle is rejected."""
        db = MockAsyncSession()
        self._seed(db)
        db.plans.append(MockPlan(name="pro", stripe_price_id_monthly=""))
        service = BillingService(_db(db), _stripe(MockStripeClient()))

        with pytest.raises(ValueError, match="No Stripe price configured"):
            await service.update_subscription(uuid4(), "pro")

    async def test_non_stripe_subscription_is_rejected(self) -> None:
        """A subscription with no Stripe id (free tier) cannot be plan-changed."""
        db = MockAsyncSession()
        self._seed(db, stripe_subscription_id=None)
        db.plans.append(MockPlan(name="pro"))
        service = BillingService(_db(db), _stripe(MockStripeClient()))

        with pytest.raises(ValueError, match="Cannot update non-Stripe subscription"):
            await service.update_subscription(uuid4(), "pro")

    async def test_stripe_failure_surfaces_update_error(self) -> None:
        """A Stripe update failure maps to a ValueError; the local plan is unchanged."""
        db = MockAsyncSession()
        subscription = self._seed(db)
        original_plan_id = subscription.plan_id
        db.plans.append(MockPlan(name="pro"))
        service = BillingService(_db(db), _stripe(_DownStripe()))

        with pytest.raises(ValueError, match="Subscription update failed"):
            await service.update_subscription(uuid4(), "pro")

        assert subscription.plan_id == original_plan_id

    async def test_unknown_stripe_status_keeps_stored_status(self) -> None:
        """An unrecognized status on update leaves the stored status unchanged."""
        db = MockAsyncSession()
        self._seed(db)
        new_plan = MockPlan(name="pro")
        db.plans.append(new_plan)
        service = BillingService(_db(db), _stripe(_WeirdStatusStripe()))

        result = await service.update_subscription(uuid4(), "pro")

        assert result.status == billing_pb2.SUBSCRIPTION_STATUS_ACTIVE
        assert result.plan_id == new_plan.id


class TestCancelReactivateStripeFailures:
    """Stripe failures on cancel/reactivate surface as ValueErrors, state unchanged."""

    async def test_cancel_stripe_failure_keeps_subscription_active(self) -> None:
        db = MockAsyncSession()
        subscription = MockSubscription()
        db.subscriptions.append(subscription)
        service = BillingService(_db(db), _stripe(_DownStripe()))

        with pytest.raises(ValueError, match="Cancellation failed"):
            await service.cancel_subscription(uuid4())

        assert subscription.cancel_at_period_end is False
        assert subscription.status == billing_pb2.SUBSCRIPTION_STATUS_ACTIVE

    async def test_reactivate_stripe_failure_keeps_pending_cancellation(self) -> None:
        db = MockAsyncSession()
        subscription = MockSubscription(cancel_at_period_end=True)
        db.subscriptions.append(subscription)
        service = BillingService(_db(db), _stripe(_DownStripe()))

        with pytest.raises(ValueError, match="Reactivation failed"):
            await service.reactivate_subscription(uuid4())

        assert subscription.cancel_at_period_end is True
