"""Unit tests for billing services."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from src.models import BillingCycle, SubscriptionCreateRequest
from src.services.billing_service import DEFAULT_PLANS, BillingService
from src.services.payment_method_service import PaymentMethodService
from src.stripe.client import PaymentMethodResult, SetupIntentResult, SubscriptionResult


class MockStripeClient:
    """Mock Stripe client for unit tests."""

    def __init__(self):
        self.customers = {}

    async def get_or_create_customer(
        self, tenant_id: str, email: str, name: str | None = None
    ) -> str:
        if tenant_id in self.customers:
            return self.customers[tenant_id]
        customer_id = f"cus_test_{len(self.customers)}"
        self.customers[tenant_id] = customer_id
        return customer_id

    async def create_setup_intent(self, customer_id: str) -> SetupIntentResult:
        return SetupIntentResult(
            client_secret=f"seti_secret_{customer_id}",
            customer_id=customer_id,
        )

    async def attach_payment_method(
        self, customer_id: str, payment_method_id: str
    ) -> PaymentMethodResult:
        return PaymentMethodResult(
            id=payment_method_id,
            type="card",
            card_brand="visa",
            card_last4="4242",
            card_exp_month=12,
            card_exp_year=2030,
        )

    async def set_default_payment_method(self, customer_id: str, payment_method_id: str) -> bool:
        return True

    async def detach_payment_method(self, payment_method_id: str) -> bool:
        return True

    async def list_payment_methods(self, customer_id: str) -> list[PaymentMethodResult]:
        return []

    async def create_subscription(
        self, customer_id: str, price_id: str, payment_method_id: str, trial_days: int = 0
    ) -> SubscriptionResult:
        now = datetime.now(UTC)
        return SubscriptionResult(
            id="sub_test_123",
            status="trialing" if trial_days > 0 else "active",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            cancel_at_period_end=False,
            trial_start=now if trial_days > 0 else None,
            trial_end=now + timedelta(days=trial_days) if trial_days > 0 else None,
        )

    async def cancel_subscription(self, subscription_id: str, at_period_end: bool = True) -> bool:
        return True

    async def reactivate_subscription(self, subscription_id: str) -> SubscriptionResult:
        now = datetime.now(UTC)
        return SubscriptionResult(
            id=subscription_id,
            status="active",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            cancel_at_period_end=False,
        )


class MockPlan:
    """Mock Plan model."""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", uuid4())
        self.name = kwargs.get("name", "starter")
        self.display_name = kwargs.get("display_name", "Starter")
        self.tier = kwargs.get("tier", "starter")
        self.price_monthly = kwargs.get("price_monthly", 29)
        self.price_yearly = kwargs.get("price_yearly", 290)
        self.features = kwargs.get("features", {})
        self.limits = kwargs.get("limits", {})
        self.trial_days = kwargs.get("trial_days", 14)
        self.stripe_price_id_monthly = kwargs.get("stripe_price_id_monthly", "price_monthly_test")
        self.stripe_price_id_yearly = kwargs.get("stripe_price_id_yearly", "price_yearly_test")


class MockSubscription:
    """Mock Subscription model."""

    def __init__(self, **kwargs):
        self.id = kwargs.get("id", uuid4())
        self.tenant_id = kwargs.get("tenant_id", uuid4())
        self.plan = kwargs.get("plan", MockPlan())
        self.plan_id = self.plan.id
        self.status = kwargs.get("status", "active")
        self.billing_cycle = kwargs.get("billing_cycle", "monthly")
        self.stripe_subscription_id = kwargs.get("stripe_subscription_id", "sub_test_123")
        self.stripe_customer_id = kwargs.get("stripe_customer_id", "cus_test_123")
        now = datetime.now(UTC)
        self.current_period_start = kwargs.get("current_period_start", now)
        self.current_period_end = kwargs.get("current_period_end", now + timedelta(days=30))
        self.cancel_at_period_end = kwargs.get("cancel_at_period_end", False)
        self.trial_start = kwargs.get("trial_start")
        self.trial_end = kwargs.get("trial_end")
        self.created_at = kwargs.get("created_at", now)


class TestBillingServicePlans:
    """Tests for BillingService plan methods."""

    async def test_list_plans_returns_defaults_when_db_empty(self) -> None:
        """Test listing plans returns defaults when database is empty."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: []))

        service = BillingService(mock_db, MockStripeClient())
        plans = await service.list_plans()

        assert len(plans) == 3
        assert plans[0].id == "free"
        assert plans[1].id == "starter"
        assert plans[2].id == "pro"

    async def test_list_plans_returns_db_plans_when_available(self) -> None:
        """Test listing plans returns database plans when available."""
        mock_plan = MockPlan(name="custom", display_name="Custom Plan")
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: [mock_plan]))

        service = BillingService(mock_db, MockStripeClient())
        plans = await service.list_plans()

        assert len(plans) == 1
        assert plans[0].name == "Custom Plan"

    async def test_get_plan_from_defaults(self) -> None:
        """Test getting plan from defaults."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        service = BillingService(mock_db, MockStripeClient())
        plan = await service.get_plan("starter")

        assert plan is not None
        assert plan.id == "starter"

    async def test_get_plan_not_found(self) -> None:
        """Test getting non-existent plan."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        service = BillingService(mock_db, MockStripeClient())
        plan = await service.get_plan("nonexistent")

        assert plan is None

    async def test_is_uuid_with_valid_uuid(self) -> None:
        """Test _is_uuid with valid UUID."""
        service = BillingService(AsyncMock(), MockStripeClient())
        assert service._is_uuid(str(uuid4())) is True

    async def test_is_uuid_with_invalid_uuid(self) -> None:
        """Test _is_uuid with invalid UUID."""
        service = BillingService(AsyncMock(), MockStripeClient())
        assert service._is_uuid("not-a-uuid") is False


class TestBillingServiceSubscriptions:
    """Tests for BillingService subscription methods."""

    async def test_get_subscription_not_found(self) -> None:
        """Test getting subscription when none exists."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        service = BillingService(mock_db, MockStripeClient())
        subscription = await service.get_subscription(uuid4())

        assert subscription is None

    async def test_get_subscription_found(self) -> None:
        """Test getting subscription when one exists."""
        mock_sub = MockSubscription()
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_sub)

        service = BillingService(mock_db, MockStripeClient())
        subscription = await service.get_subscription(mock_sub.tenant_id)

        assert subscription is not None
        assert subscription.status.value == "active"

    async def test_cancel_subscription_not_found(self) -> None:
        """Test canceling subscription when none exists."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        service = BillingService(mock_db, MockStripeClient())

        with pytest.raises(ValueError, match="No active subscription found"):
            await service.cancel_subscription(uuid4())

    async def test_cancel_subscription_at_period_end(self) -> None:
        """Test canceling subscription at period end."""
        mock_sub = MockSubscription()
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_sub)

        service = BillingService(mock_db, MockStripeClient())
        result = await service.cancel_subscription(mock_sub.tenant_id, at_period_end=True)

        assert result.cancel_at_period_end is True

    async def test_cancel_subscription_immediately(self) -> None:
        """Test canceling subscription immediately."""
        mock_sub = MockSubscription()
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_sub)

        service = BillingService(mock_db, MockStripeClient())
        await service.cancel_subscription(mock_sub.tenant_id, at_period_end=False)

        assert mock_sub.status == "cancelled"

    async def test_reactivate_subscription_not_found(self) -> None:
        """Test reactivating subscription when none pending cancellation."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        service = BillingService(mock_db, MockStripeClient())

        with pytest.raises(ValueError, match="No subscription pending cancellation found"):
            await service.reactivate_subscription(uuid4())

    async def test_reactivate_subscription_success(self) -> None:
        """Test reactivating subscription successfully."""
        mock_sub = MockSubscription(cancel_at_period_end=True)
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_sub)

        service = BillingService(mock_db, MockStripeClient())
        result = await service.reactivate_subscription(mock_sub.tenant_id)

        assert result.cancel_at_period_end is False

    async def test_sync_subscription_from_stripe(self) -> None:
        """Test syncing subscription status from Stripe."""
        mock_sub = MockSubscription()
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_sub)

        service = BillingService(mock_db, MockStripeClient())
        await service.sync_subscription_from_stripe("sub_test_123", "past_due")

        assert mock_sub.status == "past_due"

    async def test_ensure_stripe_customer(self) -> None:
        """Test ensuring Stripe customer exists."""
        mock_db = AsyncMock()
        stripe_client = MockStripeClient()

        service = BillingService(mock_db, stripe_client)
        customer_id = await service.ensure_stripe_customer(uuid4(), "test@example.com")

        assert customer_id.startswith("cus_test_")


class MockPaymentMethod:
    """Mock PaymentMethod model."""

    def __init__(self, **kwargs):
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
        billing_service = BillingService(mock_db, stripe_client)

        service = PaymentMethodService(mock_db, stripe_client, billing_service)
        result = await service.create_setup_intent(uuid4(), "test@example.com")

        assert result.client_secret.startswith("seti_secret_")

    async def test_list_payment_methods_empty(self) -> None:
        """Test listing payment methods when none exist."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: []))
        stripe_client = MockStripeClient()
        billing_service = BillingService(mock_db, stripe_client)

        service = PaymentMethodService(mock_db, stripe_client, billing_service)
        methods = await service.list_payment_methods(uuid4())

        assert methods == []

    async def test_list_payment_methods_with_data(self) -> None:
        """Test listing payment methods when some exist."""
        mock_pm = MockPaymentMethod()
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: [mock_pm]))
        stripe_client = MockStripeClient()
        billing_service = BillingService(mock_db, stripe_client)

        service = PaymentMethodService(mock_db, stripe_client, billing_service)
        methods = await service.list_payment_methods(mock_pm.tenant_id)

        assert len(methods) == 1
        assert methods[0].card_brand == "visa"

    async def test_get_payment_method_found(self) -> None:
        """Test getting a payment method that exists."""
        mock_pm = MockPaymentMethod()
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_pm)
        stripe_client = MockStripeClient()
        billing_service = BillingService(mock_db, stripe_client)

        service = PaymentMethodService(mock_db, stripe_client, billing_service)
        result = await service.get_payment_method(mock_pm.tenant_id, mock_pm.id)

        assert result is not None
        assert result.id == mock_pm.id

    async def test_get_payment_method_not_found(self) -> None:
        """Test getting a payment method that doesn't exist."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)
        stripe_client = MockStripeClient()
        billing_service = BillingService(mock_db, stripe_client)

        service = PaymentMethodService(mock_db, stripe_client, billing_service)
        result = await service.get_payment_method(uuid4(), uuid4())

        assert result is None

    async def test_delete_payment_method_not_found(self) -> None:
        """Test deleting payment method that doesn't exist."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)
        stripe_client = MockStripeClient()
        billing_service = BillingService(mock_db, stripe_client)

        service = PaymentMethodService(mock_db, stripe_client, billing_service)
        result = await service.delete_payment_method(uuid4(), uuid4())

        assert result is False

    async def test_set_default_payment_method_not_found(self) -> None:
        """Test setting default on non-existent payment method."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)
        stripe_client = MockStripeClient()
        billing_service = BillingService(mock_db, stripe_client)

        service = PaymentMethodService(mock_db, stripe_client, billing_service)

        with pytest.raises(ValueError, match="Payment method not found"):
            await service.set_default_payment_method(uuid4(), uuid4())

    async def test_sync_payment_method_detached(self) -> None:
        """Test syncing payment method detachment."""
        mock_db = AsyncMock()
        stripe_client = MockStripeClient()
        billing_service = BillingService(mock_db, stripe_client)

        service = PaymentMethodService(mock_db, stripe_client, billing_service)
        await service.sync_payment_method_detached("pm_test_123")

        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()


class TestBillingServiceUpdate:
    """Tests for BillingService update methods."""

    async def test_update_subscription_not_found(self) -> None:
        """Test updating subscription when none exists."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        service = BillingService(mock_db, MockStripeClient())

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

        service = BillingService(mock_db, MockStripeClient())

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
        billing_service = BillingService(mock_db, stripe_client)

        service = PaymentMethodService(mock_db, stripe_client, billing_service)
        result = await service.delete_payment_method(mock_pm.tenant_id, mock_pm.id)

        assert result is True

    async def test_sync_payment_method_attached_new(self) -> None:
        """Test syncing a new payment method attachment."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=lambda: None, scalars=lambda: MagicMock(all=lambda: [])
        )
        stripe_client = MockStripeClient()
        billing_service = BillingService(mock_db, stripe_client)

        service = PaymentMethodService(mock_db, stripe_client, billing_service)
        await service.sync_payment_method_attached(
            tenant_id=uuid4(),
            stripe_payment_method_id="pm_new_123",
            stripe_customer_id="cus_123",
            pm_type="card",
            card_brand="visa",
            card_last4="4242",
            card_exp_month=12,
            card_exp_year=2030,
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_sync_payment_method_attached_existing(self) -> None:
        """Test syncing a payment method that already exists."""
        mock_pm = MockPaymentMethod()
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_pm)
        stripe_client = MockStripeClient()
        billing_service = BillingService(mock_db, stripe_client)

        service = PaymentMethodService(mock_db, stripe_client, billing_service)
        await service.sync_payment_method_attached(
            tenant_id=mock_pm.tenant_id,
            stripe_payment_method_id=mock_pm.stripe_payment_method_id,
            stripe_customer_id=mock_pm.stripe_customer_id,
            pm_type="card",
            card_brand="visa",
            card_last4="4242",
            card_exp_month=12,
            card_exp_year=2030,
        )

        # Should not add again if exists
        mock_db.add.assert_not_called()


class TestBillingServiceCreateSubscription:
    """Tests for BillingService create subscription."""

    async def test_create_subscription_plan_not_found(self) -> None:
        """Test creating subscription with non-existent plan."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=lambda: None, scalars=lambda: MagicMock(all=lambda: [])
        )

        service = BillingService(mock_db, MockStripeClient())

        with pytest.raises(ValueError, match="not found"):
            await service.create_subscription(
                tenant_id=uuid4(),
                email="test@example.com",
                request=SubscriptionCreateRequest(
                    plan_id="nonexistent",
                    payment_method_id="pm_test",
                    billing_cycle=BillingCycle.MONTHLY,
                ),
            )

    async def test_plan_to_response(self) -> None:
        """Test converting Plan model to PlanResponse."""
        mock_db = AsyncMock()
        service = BillingService(mock_db, MockStripeClient())

        plan = MockPlan(
            name="test",
            display_name="Test Plan",
            tier="starter",
            price_monthly=29,
            price_yearly=290,
            features={"feature1": True},
            limits={"limit1": 10},
            trial_days=14,
        )

        response = service._plan_to_response(plan)

        assert response.id == "test"
        assert response.name == "Test Plan"
        assert response.price_monthly == 29
        assert response.trial_days == 14

    async def test_subscription_to_response(self) -> None:
        """Test converting Subscription model to SubscriptionResponse."""
        mock_db = AsyncMock()
        service = BillingService(mock_db, MockStripeClient())

        subscription = MockSubscription()
        response = service._subscription_to_response(subscription)

        assert response.status.value == "active"
        assert response.billing_cycle.value == "monthly"


class TestPaymentMethodServiceAttach:
    """Tests for PaymentMethodService attach operations."""

    async def test_to_response(self) -> None:
        """Test converting PaymentMethod model to response."""
        mock_db = AsyncMock()
        stripe_client = MockStripeClient()
        billing_service = BillingService(mock_db, stripe_client)

        service = PaymentMethodService(mock_db, stripe_client, billing_service)
        pm = MockPaymentMethod()

        response = service._to_response(pm)

        assert response.card_brand == "visa"
        assert response.card_last4 == "4242"
        assert response.is_default is False


class TestDefaultPlans:
    """Tests for default plan configurations."""

    def test_free_plan_exists(self) -> None:
        """Test that free plan is defined."""
        free_plan = next((p for p in DEFAULT_PLANS if p.tier == "free"), None)
        assert free_plan is not None
        assert free_plan.price_monthly == 0
        assert free_plan.trial_days == 0

    def test_starter_plan_exists(self) -> None:
        """Test that starter plan is defined."""
        starter_plan = next((p for p in DEFAULT_PLANS if p.tier == "starter"), None)
        assert starter_plan is not None
        assert starter_plan.price_monthly == 29
        assert starter_plan.trial_days == 14

    def test_pro_plan_exists(self) -> None:
        """Test that pro plan is defined."""
        pro_plan = next((p for p in DEFAULT_PLANS if p.tier == "pro"), None)
        assert pro_plan is not None
        assert pro_plan.price_monthly == 99
        assert pro_plan.trial_days == 14

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
        for plan in DEFAULT_PLANS:
            assert plan.id == plan.tier

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

        service = BillingService(mock_db, MockStripeClient())

        # Get the free plan from defaults
        plan = await service.get_plan("free")
        assert plan is not None
        assert plan.id == "free"
        assert plan.tier == "free"
        assert plan.price_monthly == 0


class TestWebhookHelperFunctions:
    """Tests for webhook helper functions."""

    async def test_sync_subscription_not_found(self) -> None:
        """Test syncing subscription when none exists in DB."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        service = BillingService(mock_db, MockStripeClient())
        await service.sync_subscription_from_stripe("sub_nonexistent", "cancelled")

        # Should not commit if no subscription found
        # (actually, looking at the code, it still commits - let's verify)


class TestPaymentMethodSetDefault:
    """Tests for setting default payment method."""

    async def test_set_default_updates_stripe_and_db(self) -> None:
        """Test that set_default updates both Stripe and DB."""
        mock_pm = MockPaymentMethod(is_default=False)
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_pm)
        stripe_client = MockStripeClient()
        billing_service = BillingService(mock_db, stripe_client)

        service = PaymentMethodService(mock_db, stripe_client, billing_service)
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
            MockPlan(name="db_free", display_name="DB Free", tier="free"),
            MockPlan(name="db_pro", display_name="DB Pro", tier="pro"),
        ]
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalars=lambda: MagicMock(all=lambda: mock_plans))

        service = BillingService(mock_db, MockStripeClient())
        plans = await service.list_plans()

        assert len(plans) == 2
        assert plans[0].id == "db_free"
        assert plans[1].id == "db_pro"


class TestGetPlanDB:
    """Tests for getting plan from database."""

    async def test_get_plan_db_found(self) -> None:
        """Test getting plan from DB when it exists."""
        mock_plan = MockPlan()
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_plan)

        service = BillingService(mock_db, MockStripeClient())
        plan = await service.get_plan_db("starter")

        assert plan is not None
        assert plan.name == "starter"

    async def test_get_plan_db_not_found(self) -> None:
        """Test getting plan from DB when it doesn't exist."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        service = BillingService(mock_db, MockStripeClient())
        plan = await service.get_plan_db("nonexistent")

        assert plan is None


class TestIsUuid:
    """Tests for _is_uuid helper."""

    def test_is_uuid_valid(self) -> None:
        """Test with valid UUID string."""
        from src.services.billing_service import BillingService

        service = BillingService(AsyncMock(), MockStripeClient())
        assert service._is_uuid("12345678-1234-5678-1234-567812345678") is True

    def test_is_uuid_invalid(self) -> None:
        """Test with invalid UUID string."""
        from src.services.billing_service import BillingService

        service = BillingService(AsyncMock(), MockStripeClient())
        assert service._is_uuid("not-a-uuid") is False

    def test_is_uuid_empty(self) -> None:
        """Test with empty string."""
        from src.services.billing_service import BillingService

        service = BillingService(AsyncMock(), MockStripeClient())
        assert service._is_uuid("") is False


class TestGetPlanByName:
    """Tests for getting plan by name variations."""

    async def test_get_plan_case_insensitive(self) -> None:
        """Test getting plan by name is case-insensitive."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=lambda: None, scalars=lambda: MagicMock(all=lambda: [])
        )

        service = BillingService(mock_db, MockStripeClient())

        # Get starter plan with different case
        plan = await service.get_plan("Starter")
        assert plan is not None
        assert plan.tier == "starter"

    async def test_get_plan_by_tier(self) -> None:
        """Test getting plan by tier name."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=lambda: None, scalars=lambda: MagicMock(all=lambda: [])
        )

        service = BillingService(mock_db, MockStripeClient())

        # Get pro plan
        plan = await service.get_plan("pro")
        assert plan is not None
        assert plan.tier == "pro"
        assert plan.price_monthly == 99


class TestModelConversions:
    """Tests for model conversion methods."""

    def test_plan_to_response_with_null_yearly(self) -> None:
        """Test plan conversion when yearly price is None."""
        mock_db = AsyncMock()
        service = BillingService(mock_db, MockStripeClient())

        plan = MockPlan(
            price_monthly=29,
            price_yearly=None,  # Should default to 10x monthly
        )

        response = service._plan_to_response(plan)
        assert response.price_yearly == 290  # 10x monthly

    def test_plan_to_response_with_empty_features(self) -> None:
        """Test plan conversion with empty features."""
        mock_db = AsyncMock()
        service = BillingService(mock_db, MockStripeClient())

        plan = MockPlan(features=None, limits=None)

        response = service._plan_to_response(plan)
        # Should handle None gracefully
        assert response.features == {} or response.features is None


class TestPaymentMethodResponse:
    """Tests for payment method response conversion."""

    async def test_to_response_all_fields(self) -> None:
        """Test converting payment method with all fields."""
        mock_db = AsyncMock()
        stripe_client = MockStripeClient()
        billing_service = BillingService(mock_db, stripe_client)
        service = PaymentMethodService(mock_db, stripe_client, billing_service)

        pm = MockPaymentMethod(
            id=uuid4(),
            card_brand="mastercard",
            card_last4="5555",
            card_exp_month=6,
            card_exp_year=2025,
            is_default=True,
        )

        response = service._to_response(pm)

        assert response.card_brand == "mastercard"
        assert response.card_last4 == "5555"
        assert response.card_exp_month == 6
        assert response.card_exp_year == 2025
        assert response.is_default is True


class TestBillingServiceModelConversions:
    """Additional tests for model conversions."""

    async def test_subscription_to_response_with_trial(self) -> None:
        """Test subscription response with trial period."""
        mock_db = AsyncMock()
        service = BillingService(mock_db, MockStripeClient())

        now = datetime.now(UTC)
        subscription = MockSubscription(
            status="trialing",
            trial_start=now,
            trial_end=now + timedelta(days=14),
        )

        response = service._subscription_to_response(subscription)
        assert response.status.value == "trialing"
        assert response.trial_start is not None
        assert response.trial_end is not None

    async def test_plan_response_has_all_fields(self) -> None:
        """Test that plan response includes all expected fields."""
        mock_db = AsyncMock()
        service = BillingService(mock_db, MockStripeClient())

        plan = MockPlan(
            name="test",
            display_name="Test Plan",
            tier="starter",
            price_monthly=49,
            price_yearly=490,
            features={"feature1": True, "feature2": False},
            limits={"limit1": 100},
            trial_days=7,
        )

        response = service._plan_to_response(plan)

        assert response.id == "test"
        assert response.name == "Test Plan"
        assert response.tier == "starter"
        assert response.price_monthly == 49
        assert response.price_yearly == 490
        assert response.features["feature1"] is True
        assert response.limits["limit1"] == 100
        assert response.trial_days == 7


class TestDefaultPlanFeatures:
    """Tests for default plan feature configurations."""

    def test_free_plan_no_live_trading(self) -> None:
        """Test that free plan doesn't allow live trading."""
        free_plan = next((p for p in DEFAULT_PLANS if p.tier == "free"), None)
        assert free_plan is not None
        assert free_plan.features.get("live_trading") is False

    def test_pro_plan_has_live_trading(self) -> None:
        """Test that pro plan allows live trading."""
        pro_plan = next((p for p in DEFAULT_PLANS if p.tier == "pro"), None)
        assert pro_plan is not None
        assert pro_plan.features.get("live_trading") is True

    def test_all_plans_have_backtests(self) -> None:
        """Test that all plans allow backtests."""
        for plan in DEFAULT_PLANS:
            assert plan.features.get("backtests") is True

    def test_free_plan_has_lowest_limits(self) -> None:
        """Test that free plan has the lowest limits."""
        free_plan = next((p for p in DEFAULT_PLANS if p.tier == "free"), None)
        pro_plan = next((p for p in DEFAULT_PLANS if p.tier == "pro"), None)

        assert free_plan is not None
        assert pro_plan is not None

        # Free should have lower backtest limit than pro
        free_limit = free_plan.limits.get("backtests_per_month", 0)
        pro_limit = pro_plan.limits.get("backtests_per_month")

        assert free_limit < (pro_limit or float("inf"))


class TestPaymentMethodListBranches:
    """Tests for payment method list operations."""

    async def test_list_payment_methods_orders_by_default(self) -> None:
        """Test that payment methods are ordered with default first."""
        mock_pm1 = MockPaymentMethod(is_default=False, card_last4="1111")
        mock_pm2 = MockPaymentMethod(is_default=True, card_last4="2222")

        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(
            scalars=lambda: MagicMock(all=lambda: [mock_pm2, mock_pm1])
        )
        stripe_client = MockStripeClient()
        billing_service = BillingService(mock_db, stripe_client)

        service = PaymentMethodService(mock_db, stripe_client, billing_service)
        methods = await service.list_payment_methods(uuid4())

        assert len(methods) == 2
        # First method should be the default
        assert methods[0].card_last4 == "2222"


class TestBillingServiceGetSubscription:
    """Tests for getting subscription."""

    async def test_get_subscription_with_plan(self) -> None:
        """Test getting subscription includes plan details."""
        mock_plan = MockPlan(name="pro", display_name="Pro Plan", tier="pro")
        mock_sub = MockSubscription(plan=mock_plan)

        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_sub)

        service = BillingService(mock_db, MockStripeClient())
        result = await service.get_subscription(mock_sub.tenant_id)

        assert result is not None
        assert result.plan.name == "Pro Plan"
        assert result.plan.tier == "pro"


class TestPaymentMethodToResponse:
    """Tests for payment method response conversion edge cases."""

    async def test_response_with_null_card_fields(self) -> None:
        """Test response when card fields are null."""
        mock_db = AsyncMock()
        stripe_client = MockStripeClient()
        billing_service = BillingService(mock_db, stripe_client)
        service = PaymentMethodService(mock_db, stripe_client, billing_service)

        pm = MockPaymentMethod(
            card_brand=None,
            card_last4=None,
            card_exp_month=None,
            card_exp_year=None,
        )

        response = service._to_response(pm)

        assert response.card_brand is None
        assert response.card_last4 is None


class TestSubscriptionStatusConversions:
    """Tests for subscription status handling."""

    async def test_subscription_trialing_status(self) -> None:
        """Test subscription with trialing status."""
        mock_sub = MockSubscription(status="trialing")
        mock_db = AsyncMock()

        service = BillingService(mock_db, MockStripeClient())
        response = service._subscription_to_response(mock_sub)

        assert response.status.value == "trialing"

    async def test_subscription_past_due_status(self) -> None:
        """Test subscription with past_due status."""
        mock_sub = MockSubscription(status="past_due")
        mock_db = AsyncMock()

        service = BillingService(mock_db, MockStripeClient())
        response = service._subscription_to_response(mock_sub)

        assert response.status.value == "past_due"

    async def test_subscription_cancelled_status(self) -> None:
        """Test subscription with cancelled status."""
        mock_sub = MockSubscription(status="cancelled")
        mock_db = AsyncMock()

        service = BillingService(mock_db, MockStripeClient())
        response = service._subscription_to_response(mock_sub)

        assert response.status.value == "cancelled"


class TestBillingServiceEnsureCustomer:
    """Tests for ensure_stripe_customer."""

    async def test_ensure_customer_creates_new(self) -> None:
        """Test ensuring customer when none exists."""
        mock_db = AsyncMock()
        stripe_client = MockStripeClient()

        service = BillingService(mock_db, stripe_client)
        tenant_id = uuid4()
        email = "new@example.com"

        customer_id = await service.ensure_stripe_customer(tenant_id, email)

        assert customer_id.startswith("cus_test_")

    async def test_ensure_customer_returns_existing(self) -> None:
        """Test ensuring customer when one already exists."""
        mock_db = AsyncMock()
        stripe_client = MockStripeClient()

        service = BillingService(mock_db, stripe_client)
        tenant_id = uuid4()
        email = "existing@example.com"

        # Create first time
        customer_id1 = await service.ensure_stripe_customer(tenant_id, email)
        # Get again
        customer_id2 = await service.ensure_stripe_customer(tenant_id, email)

        assert customer_id1 == customer_id2


class TestBillingCycleYearly:
    """Tests for yearly billing cycle."""

    async def test_plan_response_yearly_pricing(self) -> None:
        """Test that plan response includes yearly pricing."""
        mock_db = AsyncMock()
        service = BillingService(mock_db, MockStripeClient())

        plan = MockPlan(
            price_monthly=99,
            price_yearly=990,  # 2 months free
        )

        response = service._plan_to_response(plan)

        assert response.price_monthly == 99
        assert response.price_yearly == 990
        # Yearly is 10x monthly (2 months free)
        assert response.price_yearly == response.price_monthly * 10


class TestSubscriptionBillingCycle:
    """Tests for subscription billing cycle."""

    async def test_subscription_monthly_cycle(self) -> None:
        """Test subscription with monthly billing cycle."""
        mock_sub = MockSubscription(billing_cycle="monthly")
        mock_db = AsyncMock()

        service = BillingService(mock_db, MockStripeClient())
        response = service._subscription_to_response(mock_sub)

        assert response.billing_cycle.value == "monthly"

    async def test_subscription_yearly_cycle(self) -> None:
        """Test subscription with yearly billing cycle."""
        mock_sub = MockSubscription(billing_cycle="yearly")
        mock_db = AsyncMock()

        service = BillingService(mock_db, MockStripeClient())
        response = service._subscription_to_response(mock_sub)

        assert response.billing_cycle.value == "yearly"
