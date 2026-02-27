"""Tests for Billing gRPC servicer.

Tests the BillingServicer directly without HTTP layer.
"""

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import jwt
import pytest
from connectrpc.errors import ConnectError

# Set test environment before imports
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("STRIPE_API_KEY", "sk_test_fake")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test_fake")
os.environ.setdefault("JWT_SECRET", "test-billing-secret-key-12345")
os.environ.setdefault("JWT_ALGORITHM", "HS256")

JWT_SECRET = "test-billing-secret-key-12345"
JWT_ALGORITHM = "HS256"


def create_test_token(tenant_id: str, user_id: str) -> str:
    """Create a test JWT token."""
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "email": "test@example.com",
        "roles": ["admin"],
        "type": "access",
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


# ===================
# Mock Classes
# ===================


class MockPlan:
    """Mock Plan database model."""

    def __init__(
        self,
        id=None,
        name="starter",
        display_name="Starter",
        tier="starter",
        price_monthly=29.0,
        price_yearly=290.0,
        features=None,
        limits=None,
        trial_days=14,
        stripe_price_id_monthly="price_monthly_test",
        stripe_price_id_yearly="price_yearly_test",
    ):
        self.id = id or uuid4()
        self.name = name
        self.display_name = display_name
        self.tier = tier
        self.price_monthly = price_monthly
        self.price_yearly = price_yearly
        self.features = features or {"backtests": True}
        self.limits = limits or {"backtests_per_month": 50, "live_strategies": 5}
        self.trial_days = trial_days
        self.stripe_price_id_monthly = stripe_price_id_monthly
        self.stripe_price_id_yearly = stripe_price_id_yearly
        self.is_active = True
        self.sort_order = 1


class MockSubscription:
    """Mock Subscription database model."""

    def __init__(
        self,
        id=None,
        tenant_id=None,
        plan=None,
        status="active",
        billing_cycle="monthly",
        stripe_subscription_id="sub_test_123",
        stripe_customer_id="cus_test_123",
        current_period_start=None,
        current_period_end=None,
        cancel_at_period_end=False,
        trial_start=None,
        trial_end=None,
    ):
        self.id = id or uuid4()
        self.tenant_id = tenant_id or uuid4()
        self.plan = plan or MockPlan()
        self.plan_id = self.plan.id
        self.status = status
        self.billing_cycle = billing_cycle
        self.stripe_subscription_id = stripe_subscription_id
        self.stripe_customer_id = stripe_customer_id
        now = datetime.now(UTC)
        self.current_period_start = current_period_start or now
        self.current_period_end = current_period_end or (now + timedelta(days=30))
        self.cancel_at_period_end = cancel_at_period_end
        self.trial_start = trial_start
        self.trial_end = trial_end
        self.created_at = now
        self.canceled_at = None


class MockPaymentMethod:
    """Mock PaymentMethod database model."""

    def __init__(
        self,
        id=None,
        tenant_id=None,
        stripe_payment_method_id="pm_test_123",
        stripe_customer_id="cus_test_123",
        type="card",
        card_brand="visa",
        card_last4="4242",
        card_exp_month=12,
        card_exp_year=2030,
        is_default=False,
    ):
        self.id = id or uuid4()
        self.tenant_id = tenant_id or uuid4()
        self.stripe_payment_method_id = stripe_payment_method_id
        self.stripe_customer_id = stripe_customer_id
        self.type = type
        self.card_brand = card_brand
        self.card_last4 = card_last4
        self.card_exp_month = card_exp_month
        self.card_exp_year = card_exp_year
        self.is_default = is_default
        self.created_at = datetime.now(UTC)


class MockServicerContext:
    """Mock ConnectRPC servicer context."""

    def __init__(self, headers=None):
        self.headers = headers or {}


class MockStripeClient:
    """Mock Stripe client for testing."""

    def __init__(self):
        self.customers = {}
        self.subscriptions = {}
        self.payment_methods = {}

    async def get_or_create_customer(self, tenant_id, email, name=None):
        customer_id = f"cus_test_{tenant_id}"
        self.customers[customer_id] = {"id": customer_id, "email": email}
        return customer_id

    async def create_subscription(self, customer_id, price_id, payment_method_id, trial_days=0):
        from src.stripe.client import SubscriptionResult

        sub_id = f"sub_test_{len(self.subscriptions)}"
        now = datetime.now(UTC)
        return SubscriptionResult(
            id=sub_id,
            status="active",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            cancel_at_period_end=False,
        )

    async def cancel_subscription(self, subscription_id, at_period_end=True):
        return True

    async def update_subscription(
        self, subscription_id, price_id, proration_behavior="create_prorations"
    ):
        from src.stripe.client import SubscriptionResult

        now = datetime.now(UTC)
        return SubscriptionResult(
            id=subscription_id,
            status="active",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            cancel_at_period_end=False,
        )

    async def reactivate_subscription(self, subscription_id):
        from src.stripe.client import SubscriptionResult

        now = datetime.now(UTC)
        return SubscriptionResult(
            id=subscription_id,
            status="active",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            cancel_at_period_end=False,
        )

    async def list_payment_methods(self, customer_id):
        from src.stripe.client import PaymentMethodResult

        return [
            PaymentMethodResult(
                id="pm_test_1",
                type="card",
                card_brand="visa",
                card_last4="4242",
                card_exp_month=12,
                card_exp_year=2030,
            )
        ]

    async def attach_payment_method(self, customer_id, payment_method_id):
        from src.stripe.client import PaymentMethodResult

        return PaymentMethodResult(
            id=payment_method_id,
            type="card",
            card_brand="visa",
            card_last4="4242",
            card_exp_month=12,
            card_exp_year=2030,
        )

    async def detach_payment_method(self, payment_method_id):
        return True


class MockBillingService:
    """Mock billing service."""

    def __init__(self, subscription=None, plans=None):
        self._subscription = subscription
        self._plans = plans or []

    async def get_subscription(self, tenant_id):
        return self._subscription

    async def list_plans(self):
        return self._plans

    async def create_subscription(self, tenant_id, email, request):
        from src.models import (
            BillingCycle,
            PlanResponse,
            PlanTier,
            SubscriptionResponse,
            SubscriptionStatus,
        )

        plan = PlanResponse(
            id="plan_starter",
            name="Starter",
            tier=PlanTier.STARTER,
            price_monthly=29.0,
            price_yearly=290.0,
            features={"backtests": True},
            limits={"backtests_per_month": 50},
            trial_days=14,
        )
        return SubscriptionResponse(
            id=uuid4(),
            tenant_id=tenant_id,
            plan=plan,
            status=SubscriptionStatus.ACTIVE,
            billing_cycle=BillingCycle.MONTHLY,
            current_period_start=datetime.now(UTC),
            current_period_end=datetime.now(UTC) + timedelta(days=30),
            cancel_at_period_end=False,
            stripe_subscription_id="sub_test_123",
            created_at=datetime.now(UTC),
        )

    async def cancel_subscription(self, tenant_id, at_period_end=True):
        if not self._subscription:
            raise ValueError("No active subscription")
        return self._subscription

    async def update_subscription(self, tenant_id, plan_id):
        if not self._subscription:
            raise ValueError("No active subscription")
        return self._subscription

    async def reactivate_subscription(self, tenant_id):
        if not self._subscription:
            raise ValueError("No cancelled subscription")
        return self._subscription

    async def get_customer_id(self, tenant_id):
        return f"cus_test_{tenant_id}"


class MockPaymentMethodService:
    """Mock payment method service."""

    def __init__(self, payment_methods=None):
        self._payment_methods = payment_methods or []

    async def list_payment_methods(self, tenant_id):
        return self._payment_methods

    async def attach_payment_method(self, tenant_id, email, payment_method_id):
        from src.models import PaymentMethodResponse

        return PaymentMethodResponse(
            id=uuid4(),
            tenant_id=tenant_id,
            type="card",
            card_brand="visa",
            card_last4="4242",
            card_exp_month=12,
            card_exp_year=2030,
            is_default=True,
        )

    async def delete_payment_method(self, tenant_id, payment_method_id):
        return True


# ===================
# Fixtures
# ===================


@pytest.fixture
def tenant_context():
    """Create a tenant context message."""
    from llamatrade.v1 import common_pb2

    return common_pb2.TenantContext(
        tenant_id=str(uuid4()),
        user_id=str(uuid4()),
        roles=["admin"],
    )


@pytest.fixture
def context(tenant_context):
    """Create mock servicer context with auth token."""
    token = create_test_token(tenant_context.tenant_id, tenant_context.user_id)
    return MockServicerContext(headers={"authorization": f"Bearer {token}"})


@pytest.fixture
def mock_stripe_client():
    """Create mock Stripe client."""
    return MockStripeClient()


@pytest.fixture
def billing_servicer():
    """Create BillingServicer with mocked dependencies."""
    from src.grpc.servicer import BillingServicer

    return BillingServicer()


# ===================
# ListPlans Tests
# ===================


class TestListPlans:
    """Tests for ListPlans RPC."""

    async def test_list_plans_returns_plans(self, context, tenant_context):
        """Test listing available plans by testing helper method directly."""
        from llamatrade.v1 import billing_pb2
        from src.grpc.servicer import BillingServicer
        from src.models import PlanResponse, PlanTier

        servicer = BillingServicer()

        # Test _to_proto_plan helper with different plan types
        plan = PlanResponse(
            id="plan_starter",
            name="Starter",
            tier=PlanTier.STARTER,
            price_monthly=29.0,
            price_yearly=290.0,
            features={"backtests": True, "api_access": True},
            limits={"backtests_per_month": 50, "live_strategies": 5},
            trial_days=14,
        )

        proto_plan = servicer._to_proto_plan(plan)

        assert proto_plan.id == "plan_starter"
        assert proto_plan.name == "Starter"
        assert proto_plan.tier == billing_pb2.PLAN_TIER_STARTER
        assert proto_plan.max_backtests_per_month == 50
        assert proto_plan.max_live_sessions == 5
        assert proto_plan.api_access is True


# ===================
# GetUsage Tests
# ===================


class TestGetUsage:
    """Tests for GetUsage RPC."""

    async def test_get_usage_returns_metrics(self, billing_servicer, context, tenant_context):
        """Test getting usage metrics."""
        from llamatrade.v1 import billing_pb2

        request = billing_pb2.GetUsageRequest(
            context=tenant_context,
            period_id="2024-01",
        )

        response = await billing_servicer.get_usage(request, context)

        assert response.usage.tenant_id == tenant_context.tenant_id
        assert response.usage.period_id == "2024-01"


# ===================
# ListInvoices Tests
# ===================


class TestListInvoices:
    """Tests for ListInvoices RPC."""

    async def test_list_invoices_returns_empty(self, billing_servicer, context, tenant_context):
        """Test listing invoices returns empty list (stub implementation)."""
        from llamatrade.v1 import billing_pb2

        request = billing_pb2.ListInvoicesRequest(context=tenant_context)

        response = await billing_servicer.list_invoices(request, context)

        assert len(response.invoices) == 0
        assert response.pagination.total_items == 0


# ===================
# CreateCheckoutSession Tests
# ===================


class TestCreateCheckoutSession:
    """Tests for CreateCheckoutSession RPC."""

    async def test_create_checkout_session(self, billing_servicer, context, tenant_context):
        """Test creating a checkout session."""
        from llamatrade.v1 import billing_pb2

        request = billing_pb2.CreateCheckoutSessionRequest(
            context=tenant_context,
            plan_id="plan_starter",
            interval=billing_pb2.BILLING_INTERVAL_MONTHLY,
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
        )

        with patch("src.grpc.servicer.get_stripe_client", return_value=MockStripeClient()):
            response = await billing_servicer.create_checkout_session(request, context)

            assert response.checkout_url
            assert (
                "checkout" in response.checkout_url.lower()
                or "placeholder" in response.checkout_url.lower()
            )
            assert response.session_id


# ===================
# CreatePortalSession Tests
# ===================


class TestCreatePortalSession:
    """Tests for CreatePortalSession RPC."""

    async def test_create_portal_session(self, billing_servicer, context, tenant_context):
        """Test creating a customer portal session."""
        from llamatrade.v1 import billing_pb2

        request = billing_pb2.CreatePortalSessionRequest(
            context=tenant_context,
            return_url="https://example.com/billing",
        )

        response = await billing_servicer.create_portal_session(request, context)

        assert response.portal_url
        assert (
            "billing" in response.portal_url.lower() or "placeholder" in response.portal_url.lower()
        )


# ===================
# GetInvoice Tests
# ===================


class TestGetInvoice:
    """Tests for GetInvoice RPC."""

    async def test_get_invoice_not_found(self, billing_servicer, context, tenant_context):
        """Test getting non-existent invoice returns NOT_FOUND."""
        from llamatrade.v1 import billing_pb2

        request = billing_pb2.GetInvoiceRequest(
            context=tenant_context,
            invoice_id="inv_nonexistent",
        )

        with pytest.raises(ConnectError) as exc_info:
            await billing_servicer.get_invoice(request, context)

        assert "NOT_FOUND" in str(exc_info.value.code)


# ===================
# Helper Method Tests
# ===================


class TestHelperMethods:
    """Tests for servicer helper methods."""

    def test_to_proto_tier(self, billing_servicer):
        """Test tier conversion to proto enum."""
        from llamatrade.v1 import billing_pb2
        from src.models import PlanTier

        assert billing_servicer._to_proto_tier(PlanTier.FREE) == billing_pb2.PLAN_TIER_FREE
        assert billing_servicer._to_proto_tier(PlanTier.STARTER) == billing_pb2.PLAN_TIER_STARTER
        assert billing_servicer._to_proto_tier(PlanTier.PRO) == billing_pb2.PLAN_TIER_PROFESSIONAL

    def test_to_proto_interval(self, billing_servicer):
        """Test interval conversion to proto enum."""
        from llamatrade.v1 import billing_pb2
        from src.models import BillingCycle

        assert (
            billing_servicer._to_proto_interval(BillingCycle.MONTHLY)
            == billing_pb2.BILLING_INTERVAL_MONTHLY
        )
        assert (
            billing_servicer._to_proto_interval(BillingCycle.YEARLY)
            == billing_pb2.BILLING_INTERVAL_YEARLY
        )

    def test_from_proto_interval(self, billing_servicer):
        """Test proto interval conversion to internal enum."""
        from llamatrade.v1 import billing_pb2
        from src.models import BillingCycle

        assert (
            billing_servicer._from_proto_interval(billing_pb2.BILLING_INTERVAL_MONTHLY)
            == BillingCycle.MONTHLY
        )
        assert (
            billing_servicer._from_proto_interval(billing_pb2.BILLING_INTERVAL_YEARLY)
            == BillingCycle.YEARLY
        )
        # Default should be monthly
        assert (
            billing_servicer._from_proto_interval(billing_pb2.BILLING_INTERVAL_UNSPECIFIED)
            == BillingCycle.MONTHLY
        )

    def test_to_proto_status(self, billing_servicer):
        """Test status conversion to proto enum."""
        from llamatrade.v1 import billing_pb2
        from src.models import SubscriptionStatus

        assert (
            billing_servicer._to_proto_status(SubscriptionStatus.ACTIVE)
            == billing_pb2.SUBSCRIPTION_STATUS_ACTIVE
        )
        assert (
            billing_servicer._to_proto_status(SubscriptionStatus.TRIALING)
            == billing_pb2.SUBSCRIPTION_STATUS_TRIALING
        )
        assert (
            billing_servicer._to_proto_status(SubscriptionStatus.CANCELLED)
            == billing_pb2.SUBSCRIPTION_STATUS_CANCELED
        )
