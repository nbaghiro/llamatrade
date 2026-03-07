"""Test fixtures for billing service tests."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from llamatrade_proto.generated import billing_pb2

from src.main import app
from src.models import PlanResponse
from src.services.database import get_db
from src.stripe.client import (
    InvoiceResult,
    PaymentMethodResult,
    SetupIntentResult,
    SubscriptionResult,
    get_stripe_client,
)

# ===================
# Mock Stripe Client
# ===================


class MockStripeClient:
    """Mock Stripe client for testing."""

    def __init__(self) -> None:
        self.customers: dict[str, dict[str, Any]] = {}
        self.subscriptions: dict[str, dict[str, Any]] = {}
        self.payment_methods: dict[str, dict[str, Any]] = {}
        self.setup_intents: dict[str, dict[str, Any]] = {}

    async def get_or_create_customer(
        self, tenant_id: str, email: str, name: str | None = None
    ) -> str:
        """Get or create a mock customer."""
        for cid, customer in self.customers.items():
            metadata = customer.get("metadata", {})
            if isinstance(metadata, dict) and metadata.get("tenant_id") == tenant_id:
                return cid

        customer_id = f"cus_test_{len(self.customers)}"
        self.customers[customer_id] = {
            "id": customer_id,
            "email": email,
            "name": name,
            "metadata": {"tenant_id": tenant_id},
        }
        return customer_id

    async def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        """Get a mock customer."""
        return self.customers.get(customer_id)

    async def create_setup_intent(self, customer_id: str) -> SetupIntentResult:
        """Create a mock SetupIntent."""
        intent_id = f"seti_test_{len(self.setup_intents)}"
        self.setup_intents[intent_id] = {
            "id": intent_id,
            "customer": customer_id,
            "client_secret": f"{intent_id}_secret_test",
        }
        return SetupIntentResult(
            client_secret=f"{intent_id}_secret_test",
            customer_id=customer_id,
        )

    async def attach_payment_method(
        self, customer_id: str, payment_method_id: str
    ) -> PaymentMethodResult:
        """Attach a mock payment method."""
        pm = self.payment_methods.get(payment_method_id, {})
        pm["customer"] = customer_id
        self.payment_methods[payment_method_id] = pm
        return PaymentMethodResult(
            id=payment_method_id,
            type="card",
            card_brand="visa",
            card_last4="4242",
            card_exp_month=12,
            card_exp_year=2030,
        )

    async def detach_payment_method(self, payment_method_id: str) -> bool:
        """Detach a mock payment method."""
        if payment_method_id in self.payment_methods:
            del self.payment_methods[payment_method_id]
        return True

    async def list_payment_methods(self, customer_id: str) -> list[PaymentMethodResult]:
        """List mock payment methods."""
        return [
            PaymentMethodResult(
                id=pm_id,
                type=str(pm.get("type", "card")),
                card_brand=str(pm.get("card_brand", "visa")),
                card_last4=str(pm.get("card_last4", "4242")),
                card_exp_month=int(pm.get("card_exp_month", 12)),
                card_exp_year=int(pm.get("card_exp_year", 2030)),
            )
            for pm_id, pm in self.payment_methods.items()
            if pm.get("customer") == customer_id
        ]

    async def set_default_payment_method(self, customer_id: str, payment_method_id: str) -> bool:
        """Set default payment method."""
        customer = self.customers.get(customer_id)
        if customer:
            customer["default_payment_method"] = payment_method_id
        return True

    async def get_default_payment_method(self, customer_id: str) -> str | None:
        """Get default payment method."""
        customer = self.customers.get(customer_id)
        if customer:
            result = customer.get("default_payment_method")
            return str(result) if result else None
        return None

    async def create_subscription(
        self,
        customer_id: str,
        price_id: str,
        payment_method_id: str,
        trial_days: int = 0,
    ) -> SubscriptionResult:
        """Create a mock subscription."""
        sub_id = f"sub_test_{len(self.subscriptions)}"
        now = datetime.now(UTC)

        status = "trialing" if trial_days > 0 else "active"
        trial_start = now if trial_days > 0 else None
        trial_end = now + timedelta(days=trial_days) if trial_days > 0 else None

        self.subscriptions[sub_id] = {
            "id": sub_id,
            "customer": customer_id,
            "price_id": price_id,
            "status": status,
            "trial_start": trial_start,
            "trial_end": trial_end,
        }

        return SubscriptionResult(
            id=sub_id,
            status=status,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            cancel_at_period_end=False,
            trial_start=trial_start,
            trial_end=trial_end,
        )

    async def update_subscription(
        self,
        subscription_id: str,
        price_id: str,
        proration_behavior: str = "create_prorations",
    ) -> SubscriptionResult:
        """Update a mock subscription."""
        sub = self.subscriptions.get(subscription_id, {})
        sub["price_id"] = price_id
        now = datetime.now(UTC)

        return SubscriptionResult(
            id=subscription_id,
            status=str(sub.get("status", "active")),
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            cancel_at_period_end=False,
        )

    async def cancel_subscription(self, subscription_id: str, at_period_end: bool = True) -> bool:
        """Cancel a mock subscription."""
        sub = self.subscriptions.get(subscription_id)
        if sub:
            if at_period_end:
                sub["cancel_at_period_end"] = True
            else:
                sub["status"] = "cancelled"
        return True

    async def reactivate_subscription(self, subscription_id: str) -> SubscriptionResult:
        """Reactivate a mock subscription."""
        sub = self.subscriptions.get(subscription_id, {})
        sub["cancel_at_period_end"] = False
        now = datetime.now(UTC)

        return SubscriptionResult(
            id=subscription_id,
            status="active",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            cancel_at_period_end=False,
        )

    async def get_subscription(self, subscription_id: str) -> SubscriptionResult | None:
        """Get a mock subscription."""
        sub = self.subscriptions.get(subscription_id)
        if not sub:
            return None

        now = datetime.now(UTC)
        trial_start_val = sub.get("trial_start")
        trial_end_val = sub.get("trial_end")

        return SubscriptionResult(
            id=subscription_id,
            status=str(sub.get("status", "active")),
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            cancel_at_period_end=bool(sub.get("cancel_at_period_end", False)),
            trial_start=trial_start_val if isinstance(trial_start_val, datetime) else None,
            trial_end=trial_end_val if isinstance(trial_end_val, datetime) else None,
        )

    async def list_invoices(self, customer_id: str, limit: int = 10) -> list[InvoiceResult]:
        """List mock invoices."""
        now = datetime.now(UTC)
        return [
            InvoiceResult(
                id="in_test_1",
                amount_due=2900,
                amount_paid=2900,
                currency="usd",
                status="paid",
                period_start=now - timedelta(days=30),
                period_end=now,
                paid_at=now - timedelta(days=29),
            )
        ]

    def verify_webhook_signature(
        self, payload: bytes, sig_header: str, webhook_secret: str
    ) -> dict[str, Any]:
        """Mock webhook verification."""
        import json

        return json.loads(payload)  # type: ignore[no-any-return]


# ===================
# Mock Database Session
# ===================


class MockPlan:
    """Mock Plan object for testing."""

    def __init__(
        self,
        id: UUID | None = None,
        name: str = "starter",
        display_name: str = "Starter",
        tier: int = billing_pb2.PLAN_TIER_STARTER,
        price_monthly: float = 29.0,
        price_yearly: float = 290.0,
        features: dict[str, Any] | None = None,
        limits: dict[str, Any] | None = None,
        trial_days: int = 14,
        stripe_price_id_monthly: str = "price_monthly_test",
        stripe_price_id_yearly: str = "price_yearly_test",
        is_active: bool = True,
        sort_order: int = 1,
    ) -> None:
        self.id = id or uuid4()
        self.name = name
        self.display_name = display_name
        self.tier = tier
        self.price_monthly = price_monthly
        self.price_yearly = price_yearly
        self.features = features or {"backtests": True}
        self.limits = limits or {"backtests_per_month": 50}
        self.trial_days = trial_days
        self.stripe_price_id_monthly = stripe_price_id_monthly
        self.stripe_price_id_yearly = stripe_price_id_yearly
        self.is_active = is_active
        self.sort_order = sort_order


class MockSubscription:
    """Mock Subscription object for testing."""

    def __init__(
        self,
        id: UUID | None = None,
        tenant_id: UUID | None = None,
        plan: MockPlan | None = None,
        status: int = billing_pb2.SUBSCRIPTION_STATUS_ACTIVE,
        billing_cycle: int = billing_pb2.BILLING_INTERVAL_MONTHLY,
        stripe_subscription_id: str | None = "sub_test_123",
        stripe_customer_id: str | None = "cus_test_123",
        current_period_start: datetime | None = None,
        current_period_end: datetime | None = None,
        cancel_at_period_end: bool = False,
        trial_start: datetime | None = None,
        trial_end: datetime | None = None,
        created_at: datetime | None = None,
    ) -> None:
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
        self.created_at = created_at or now
        self.canceled_at: datetime | None = None


class MockPaymentMethodModel:
    """Mock PaymentMethod database model for testing."""

    def __init__(
        self,
        id: UUID | None = None,
        tenant_id: UUID | None = None,
        stripe_payment_method_id: str = "pm_test_123",
        stripe_customer_id: str = "cus_test_123",
        type: str = "card",
        card_brand: str = "visa",
        card_last4: str = "4242",
        card_exp_month: int = 12,
        card_exp_year: int = 2030,
        is_default: bool = False,
    ) -> None:
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


class MockAsyncSession:
    """Mock async database session."""

    def __init__(self) -> None:
        self._data: dict[str, list[Any]] = {
            "plans": [],
            "subscriptions": [],
            "payment_methods": [],
            "invoices": [],
        }
        self._committed = False
        self._return_subscription: MockSubscription | None = None
        self._return_payment_method: MockPaymentMethodModel | None = None

    def set_subscription(self, subscription: MockSubscription | None) -> None:
        """Set subscription to return from queries."""
        self._return_subscription = subscription

    def set_payment_method(self, pm: MockPaymentMethodModel | None) -> None:
        """Set payment method to return from queries."""
        self._return_payment_method = pm

    async def execute(self, query: object) -> MagicMock:
        """Mock execute - returns configured results."""
        result = MagicMock()

        # Check if this is a subscription query and we have one configured
        if self._return_subscription:
            result.scalars.return_value.all.return_value = [self._return_subscription]
            result.scalar_one_or_none.return_value = self._return_subscription
            result.scalar.return_value = self._return_subscription.stripe_customer_id
        elif self._return_payment_method:
            result.scalars.return_value.all.return_value = [self._return_payment_method]
            result.scalar_one_or_none.return_value = self._return_payment_method
            result.scalar.return_value = None
        else:
            result.scalars.return_value.all.return_value = []
            result.scalar_one_or_none.return_value = None
            result.scalar.return_value = None

        return result

    async def commit(self) -> None:
        """Mock commit."""
        self._committed = True

    async def flush(self) -> None:
        """Mock flush."""
        pass

    async def refresh(self, obj: object, attrs: list[str] | None = None) -> None:
        """Mock refresh - set up required attributes."""
        # Ensure subscription has a plan
        if hasattr(obj, "plan") and getattr(obj, "plan") is None:
            setattr(obj, "plan", MockPlan())
        # Ensure objects have an ID
        if hasattr(obj, "id") and getattr(obj, "id") is None:
            setattr(obj, "id", uuid4())
        # Ensure created_at is set
        if hasattr(obj, "created_at") and getattr(obj, "created_at") is None:
            setattr(obj, "created_at", datetime.now(UTC))

    def add(self, obj: object) -> None:
        """Mock add."""
        pass

    async def rollback(self) -> None:
        """Mock rollback."""
        pass


@pytest.fixture
def mock_stripe_client() -> MockStripeClient:
    """Create a mock Stripe client."""
    return MockStripeClient()


@pytest.fixture
def mock_db() -> MockAsyncSession:
    """Create a mock database session."""
    return MockAsyncSession()


@pytest.fixture
def mock_db_with_subscription() -> MockAsyncSession:
    """Create a mock database session with an existing subscription."""
    db = MockAsyncSession()
    plan = MockPlan(name="starter", tier=billing_pb2.PLAN_TIER_STARTER)
    subscription = MockSubscription(plan=plan, status=billing_pb2.SUBSCRIPTION_STATUS_ACTIVE)
    db.set_subscription(subscription)
    return db


@pytest.fixture
def mock_db_with_cancelled_subscription() -> MockAsyncSession:
    """Create a mock database session with a subscription pending cancellation."""
    db = MockAsyncSession()
    plan = MockPlan(name="starter", tier=billing_pb2.PLAN_TIER_STARTER)
    subscription = MockSubscription(
        plan=plan,
        status=billing_pb2.SUBSCRIPTION_STATUS_ACTIVE,
        cancel_at_period_end=True,
    )
    db.set_subscription(subscription)
    return db


@pytest.fixture
def mock_db_with_payment_method() -> MockAsyncSession:
    """Create a mock database session with an existing payment method."""
    db = MockAsyncSession()
    pm = MockPaymentMethodModel()
    db.set_payment_method(pm)
    return db


# ===================
# Test Client
# ===================


@pytest.fixture
async def client(
    mock_stripe_client: MockStripeClient, mock_db: MockAsyncSession
) -> AsyncGenerator[AsyncClient]:
    """Create async test client with mocked dependencies."""

    async def get_mock_db() -> AsyncGenerator[MockAsyncSession]:
        yield mock_db

    # Override dependencies
    app.dependency_overrides[get_stripe_client] = lambda: mock_stripe_client
    app.dependency_overrides[get_db] = get_mock_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
async def client_with_subscription(
    mock_stripe_client: MockStripeClient, mock_db_with_subscription: MockAsyncSession
) -> AsyncGenerator[AsyncClient]:
    """Create async test client with an existing subscription."""

    async def get_mock_db() -> AsyncGenerator[MockAsyncSession]:
        yield mock_db_with_subscription

    app.dependency_overrides[get_stripe_client] = lambda: mock_stripe_client
    app.dependency_overrides[get_db] = get_mock_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
async def client_with_cancelled_subscription(
    mock_stripe_client: MockStripeClient, mock_db_with_cancelled_subscription: MockAsyncSession
) -> AsyncGenerator[AsyncClient]:
    """Create async test client with a subscription pending cancellation."""

    async def get_mock_db() -> AsyncGenerator[MockAsyncSession]:
        yield mock_db_with_cancelled_subscription

    app.dependency_overrides[get_stripe_client] = lambda: mock_stripe_client
    app.dependency_overrides[get_db] = get_mock_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
async def client_with_payment_method(
    mock_stripe_client: MockStripeClient, mock_db_with_payment_method: MockAsyncSession
) -> AsyncGenerator[AsyncClient]:
    """Create async test client with an existing payment method."""

    async def get_mock_db() -> AsyncGenerator[MockAsyncSession]:
        yield mock_db_with_payment_method

    app.dependency_overrides[get_stripe_client] = lambda: mock_stripe_client
    app.dependency_overrides[get_db] = get_mock_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()


# ===================
# Test Data Factories
# ===================


def make_plan(
    id: str = "test_plan",
    name: str = "Test Plan",
    tier: int = billing_pb2.PLAN_TIER_STARTER,
    price_monthly: float = 29.0,
    price_yearly: float = 290.0,
    trial_days: int = 14,
) -> PlanResponse:
    """Create a test plan."""
    return PlanResponse(
        id=id,
        name=name,
        tier=tier,
        price_monthly=price_monthly,
        price_yearly=price_yearly,
        features={
            "backtests": True,
            "paper_trading": True,
            "live_trading": tier == billing_pb2.PLAN_TIER_PRO,
        },
        limits={
            "backtests_per_month": 50 if tier != billing_pb2.PLAN_TIER_PRO else None,
            "live_strategies": 1 if tier == billing_pb2.PLAN_TIER_STARTER else 5,
        },
        trial_days=trial_days,
    )


def make_tenant_id() -> str:
    """Generate a test tenant ID."""
    return str(uuid4())


def make_auth_header(
    tenant_id: str | None = None, email: str = "test@example.com"
) -> dict[str, str]:
    """Create auth headers with a test JWT token."""
    import jwt

    if tenant_id is None:
        tenant_id = make_tenant_id()

    payload = {
        "sub": str(uuid4()),
        "tenant_id": tenant_id,
        "email": email,
        "roles": ["admin"],
        "type": "access",
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    # Use the default dev secret
    token = jwt.encode(payload, "dev-secret-change-in-production", algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}
