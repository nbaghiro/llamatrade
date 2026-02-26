"""Billing webhook integration tests with real database.

These tests verify that Stripe webhook events are correctly processed
and persist changes to PostgreSQL. This is critical for:
1. Subscription lifecycle management
2. Invoice tracking
3. Payment method management
4. Revenue integrity

IMPORTANT: These tests use a real database to verify data persistence.
"""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_db.models import Invoice, PaymentMethod, Subscription, Tenant
from tests.factories import (
    InvoiceFactory,
    PaymentMethodFactory,
    PlanFactory,
    SubscriptionFactory,
    TenantFactory,
)

pytestmark = [pytest.mark.integration, pytest.mark.billing]


def _get_billing_app_and_deps():
    """Import the billing app and dependencies.

    Multiple services use 'src.main' as their module name.
    We need to clear all service paths and modules to ensure
    we import from the billing service specifically.
    """
    import sys
    from pathlib import Path

    billing_path = Path(__file__).parents[3] / "services" / "billing"

    # Remove all other service paths to avoid conflicts
    service_paths = [
        str(Path(__file__).parents[3] / "services" / svc)
        for svc in ["auth", "strategy", "backtest", "market-data", "trading", "portfolio"]
    ]
    for svc_path in service_paths:
        if svc_path in sys.path:
            sys.path.remove(svc_path)

    # Clear any cached src modules (which might be from other services)
    # Must include bare 'src' module as well as all submodules
    modules_to_remove = [
        k for k in list(sys.modules.keys())
        if k == "src" or k.startswith("src.")
    ]
    for mod in modules_to_remove:
        del sys.modules[mod]

    # Add billing service path at the beginning
    billing_path_str = str(billing_path)
    if billing_path_str in sys.path:
        sys.path.remove(billing_path_str)
    sys.path.insert(0, billing_path_str)

    # Now import - should get billing service's src.main
    from src.main import app
    from src.services.database import get_db

    return app, get_db


@pytest.fixture
async def billing_client(
    db_session: AsyncSession,
) -> AsyncClient:
    """Create async client with real database session for billing tests."""
    try:
        billing_app, get_db = _get_billing_app_and_deps()
    except ImportError as e:
        pytest.skip(f"Billing service not installed: {e}")

    async def override_get_db():
        yield db_session

    billing_app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=billing_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    billing_app.dependency_overrides.clear()


@pytest.fixture
async def test_plan(db_session: AsyncSession):
    """Create a test plan."""
    plan = PlanFactory.create(
        name=f"test-plan-{uuid4().hex[:8]}",
        tier="starter",
    )
    db_session.add(plan)
    await db_session.flush()
    return plan


@pytest.fixture
async def test_subscription(
    db_session: AsyncSession,
    test_tenant: Tenant,
    test_plan,
):
    """Create a test subscription."""
    subscription = SubscriptionFactory.create(
        tenant_id=test_tenant.id,
        plan_id=test_plan.id,
        stripe_subscription_id=f"sub_{uuid4().hex[:24]}",
        stripe_customer_id=f"cus_{uuid4().hex[:24]}",
        status="active",
    )
    db_session.add(subscription)
    await db_session.flush()
    return subscription


class TestWebhookEndpoint:
    """Tests for webhook endpoint behavior."""

    async def test_webhook_requires_signature_header(self, billing_client: AsyncClient):
        """Test webhook rejects requests without stripe-signature header."""
        response = await billing_client.post(
            "/webhooks/stripe",
            content=json.dumps({"type": "test.event", "data": {}}),
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 400
        assert "signature" in response.json()["detail"].lower()

    async def test_webhook_rejects_invalid_json(self, billing_client: AsyncClient):
        """Test webhook rejects invalid JSON payload."""
        response = await billing_client.post(
            "/webhooks/stripe",
            content="not valid json",
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "test_sig",
            },
        )

        assert response.status_code == 400

    async def test_webhook_accepts_unknown_events(self, billing_client: AsyncClient):
        """Test webhook returns 200 for unknown event types.

        This is important - we don't want Stripe to retry for events we don't handle.
        """
        event = {
            "type": "some.unknown.event.type",
            "data": {"object": {}},
        }

        response = await billing_client.post(
            "/webhooks/stripe",
            content=json.dumps(event),
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "test_sig",
            },
        )

        assert response.status_code == 200
        assert response.json() == {"received": True}


class TestSubscriptionWebhooks:
    """Tests for subscription-related webhook events."""

    async def test_subscription_created_updates_database(
        self,
        billing_client: AsyncClient,
        db_session: AsyncSession,
        test_subscription: Subscription,
    ):
        """Test subscription.created webhook updates subscription status."""
        # Use the existing subscription's stripe_subscription_id
        event = {
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "id": test_subscription.stripe_subscription_id,
                    "customer": test_subscription.stripe_customer_id,
                    "status": "trialing",
                    "current_period_start": int(datetime.now(UTC).timestamp()),
                    "current_period_end": int((datetime.now(UTC) + timedelta(days=14)).timestamp()),
                    "trial_start": int(datetime.now(UTC).timestamp()),
                    "trial_end": int((datetime.now(UTC) + timedelta(days=14)).timestamp()),
                }
            },
        }

        response = await billing_client.post(
            "/webhooks/stripe",
            content=json.dumps(event),
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "test_sig",
            },
        )

        assert response.status_code == 200

        # Verify database was updated
        await db_session.refresh(test_subscription)
        assert test_subscription.status == "trialing"
        assert test_subscription.trial_start is not None
        assert test_subscription.trial_end is not None

    async def test_subscription_updated_changes_status(
        self,
        billing_client: AsyncClient,
        db_session: AsyncSession,
        test_subscription: Subscription,
    ):
        """Test subscription.updated webhook changes subscription status."""
        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": test_subscription.stripe_subscription_id,
                    "status": "past_due",
                    "cancel_at_period_end": True,
                    "current_period_start": int(datetime.now(UTC).timestamp()),
                    "current_period_end": int((datetime.now(UTC) + timedelta(days=30)).timestamp()),
                }
            },
        }

        response = await billing_client.post(
            "/webhooks/stripe",
            content=json.dumps(event),
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "test_sig",
            },
        )

        assert response.status_code == 200

        # Verify database was updated
        await db_session.refresh(test_subscription)
        assert test_subscription.status == "past_due"
        assert test_subscription.cancel_at_period_end is True

    async def test_subscription_deleted_marks_cancelled(
        self,
        billing_client: AsyncClient,
        db_session: AsyncSession,
        test_subscription: Subscription,
    ):
        """Test subscription.deleted webhook marks subscription as cancelled."""
        event = {
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "id": test_subscription.stripe_subscription_id,
                }
            },
        }

        response = await billing_client.post(
            "/webhooks/stripe",
            content=json.dumps(event),
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "test_sig",
            },
        )

        assert response.status_code == 200

        # Verify database was updated
        await db_session.refresh(test_subscription)
        assert test_subscription.status == "cancelled"
        assert test_subscription.canceled_at is not None

    async def test_subscription_webhook_for_unknown_subscription(
        self,
        billing_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test webhook for non-existent subscription doesn't error.

        Webhooks should always return 200 - we don't want Stripe retrying.
        """
        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "id": "sub_nonexistent_12345",
                    "status": "active",
                    "cancel_at_period_end": False,
                    "current_period_start": int(datetime.now(UTC).timestamp()),
                    "current_period_end": int((datetime.now(UTC) + timedelta(days=30)).timestamp()),
                }
            },
        }

        response = await billing_client.post(
            "/webhooks/stripe",
            content=json.dumps(event),
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "test_sig",
            },
        )

        # Should still return 200, just won't update anything
        assert response.status_code == 200


class TestInvoiceWebhooks:
    """Tests for invoice-related webhook events."""

    async def test_invoice_paid_creates_invoice_record(
        self,
        billing_client: AsyncClient,
        db_session: AsyncSession,
        test_subscription: Subscription,
    ):
        """Test invoice.paid webhook creates invoice record in database."""
        stripe_invoice_id = f"in_{uuid4().hex[:24]}"
        now = datetime.now(UTC)

        event = {
            "type": "invoice.paid",
            "data": {
                "object": {
                    "id": stripe_invoice_id,
                    "subscription": test_subscription.stripe_subscription_id,
                    "customer": test_subscription.stripe_customer_id,
                    "number": "INV-0001",
                    "amount_due": 2900,  # $29.00 in cents
                    "amount_paid": 2900,
                    "currency": "usd",
                    "period_start": int(now.timestamp()),
                    "period_end": int((now + timedelta(days=30)).timestamp()),
                    "hosted_invoice_url": "https://invoice.stripe.com/test",
                    "invoice_pdf": "https://invoice.stripe.com/test.pdf",
                }
            },
        }

        response = await billing_client.post(
            "/webhooks/stripe",
            content=json.dumps(event),
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "test_sig",
            },
        )

        assert response.status_code == 200

        # Verify invoice was created in database
        result = await db_session.execute(
            select(Invoice).where(Invoice.stripe_invoice_id == stripe_invoice_id)
        )
        invoice = result.scalar_one_or_none()

        assert invoice is not None
        assert invoice.status == "paid"
        assert invoice.amount_due == Decimal("29.00")
        assert invoice.amount_paid == Decimal("29.00")
        assert invoice.tenant_id == test_subscription.tenant_id
        assert invoice.paid_at is not None

    async def test_invoice_paid_updates_existing_invoice(
        self,
        billing_client: AsyncClient,
        db_session: AsyncSession,
        test_subscription: Subscription,
    ):
        """Test invoice.paid updates existing invoice record."""
        # Create existing invoice with "open" status
        existing_invoice = InvoiceFactory.create(
            tenant_id=test_subscription.tenant_id,
            subscription_id=test_subscription.id,
            status="open",
            amount_due=Decimal("29.00"),
            amount_paid=Decimal("0.00"),
        )
        db_session.add(existing_invoice)
        await db_session.flush()

        event = {
            "type": "invoice.paid",
            "data": {
                "object": {
                    "id": existing_invoice.stripe_invoice_id,
                    "subscription": test_subscription.stripe_subscription_id,
                    "customer": test_subscription.stripe_customer_id,
                    "amount_due": 2900,
                    "amount_paid": 2900,
                    "currency": "usd",
                    "period_start": int(datetime.now(UTC).timestamp()),
                    "period_end": int((datetime.now(UTC) + timedelta(days=30)).timestamp()),
                }
            },
        }

        response = await billing_client.post(
            "/webhooks/stripe",
            content=json.dumps(event),
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "test_sig",
            },
        )

        assert response.status_code == 200

        # Verify invoice was updated
        await db_session.refresh(existing_invoice)
        assert existing_invoice.status == "paid"
        assert existing_invoice.amount_paid == Decimal("29.00")
        assert existing_invoice.paid_at is not None

    async def test_payment_failed_marks_subscription_past_due(
        self,
        billing_client: AsyncClient,
        db_session: AsyncSession,
        test_subscription: Subscription,
    ):
        """Test invoice.payment_failed marks subscription as past_due."""
        event = {
            "type": "invoice.payment_failed",
            "data": {
                "object": {
                    "id": f"in_{uuid4().hex[:24]}",
                    "subscription": test_subscription.stripe_subscription_id,
                }
            },
        }

        response = await billing_client.post(
            "/webhooks/stripe",
            content=json.dumps(event),
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "test_sig",
            },
        )

        assert response.status_code == 200

        # Verify subscription was marked past_due
        await db_session.refresh(test_subscription)
        assert test_subscription.status == "past_due"


class TestPaymentMethodWebhooks:
    """Tests for payment method webhook events."""

    async def test_payment_method_attached_creates_record(
        self,
        billing_client: AsyncClient,
        db_session: AsyncSession,
        test_subscription: Subscription,
    ):
        """Test payment_method.attached creates payment method record."""
        stripe_pm_id = f"pm_{uuid4().hex[:24]}"

        event = {
            "type": "payment_method.attached",
            "data": {
                "object": {
                    "id": stripe_pm_id,
                    "customer": test_subscription.stripe_customer_id,
                    "type": "card",
                    "card": {
                        "brand": "visa",
                        "last4": "4242",
                        "exp_month": 12,
                        "exp_year": 2030,
                    },
                }
            },
        }

        response = await billing_client.post(
            "/webhooks/stripe",
            content=json.dumps(event),
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "test_sig",
            },
        )

        assert response.status_code == 200

        # Verify payment method was created
        result = await db_session.execute(
            select(PaymentMethod).where(PaymentMethod.stripe_payment_method_id == stripe_pm_id)
        )
        pm = result.scalar_one_or_none()

        assert pm is not None
        assert pm.type == "card"
        assert pm.card_brand == "visa"
        assert pm.card_last4 == "4242"
        assert pm.card_exp_month == 12
        assert pm.card_exp_year == 2030
        assert pm.tenant_id == test_subscription.tenant_id

    async def test_first_payment_method_is_default(
        self,
        billing_client: AsyncClient,
        db_session: AsyncSession,
        test_subscription: Subscription,
    ):
        """Test first attached payment method is set as default."""
        stripe_pm_id = f"pm_{uuid4().hex[:24]}"

        event = {
            "type": "payment_method.attached",
            "data": {
                "object": {
                    "id": stripe_pm_id,
                    "customer": test_subscription.stripe_customer_id,
                    "type": "card",
                    "card": {
                        "brand": "mastercard",
                        "last4": "5555",
                        "exp_month": 6,
                        "exp_year": 2028,
                    },
                }
            },
        }

        response = await billing_client.post(
            "/webhooks/stripe",
            content=json.dumps(event),
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "test_sig",
            },
        )

        assert response.status_code == 200

        # Verify it's set as default (first method)
        result = await db_session.execute(
            select(PaymentMethod).where(PaymentMethod.stripe_payment_method_id == stripe_pm_id)
        )
        pm = result.scalar_one_or_none()

        assert pm is not None
        assert pm.is_default is True

    async def test_payment_method_detached_deletes_record(
        self,
        billing_client: AsyncClient,
        db_session: AsyncSession,
        test_subscription: Subscription,
    ):
        """Test payment_method.detached deletes the payment method."""
        # Create existing payment method
        pm = PaymentMethodFactory.create(
            tenant_id=test_subscription.tenant_id,
            stripe_customer_id=test_subscription.stripe_customer_id,
        )
        db_session.add(pm)
        await db_session.flush()

        event = {
            "type": "payment_method.detached",
            "data": {
                "object": {
                    "id": pm.stripe_payment_method_id,
                }
            },
        }

        response = await billing_client.post(
            "/webhooks/stripe",
            content=json.dumps(event),
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "test_sig",
            },
        )

        assert response.status_code == 200

        # Verify payment method was deleted
        result = await db_session.execute(
            select(PaymentMethod).where(PaymentMethod.stripe_payment_method_id == pm.stripe_payment_method_id)
        )
        assert result.scalar_one_or_none() is None


class TestWebhookIdempotency:
    """Tests for webhook idempotency."""

    async def test_duplicate_invoice_webhook_is_idempotent(
        self,
        billing_client: AsyncClient,
        db_session: AsyncSession,
        test_subscription: Subscription,
    ):
        """Test sending same invoice.paid webhook twice doesn't create duplicates."""
        stripe_invoice_id = f"in_{uuid4().hex[:24]}"

        event = {
            "type": "invoice.paid",
            "data": {
                "object": {
                    "id": stripe_invoice_id,
                    "subscription": test_subscription.stripe_subscription_id,
                    "customer": test_subscription.stripe_customer_id,
                    "number": "INV-IDEM-001",
                    "amount_due": 2900,
                    "amount_paid": 2900,
                    "currency": "usd",
                    "period_start": int(datetime.now(UTC).timestamp()),
                    "period_end": int((datetime.now(UTC) + timedelta(days=30)).timestamp()),
                }
            },
        }

        # Send webhook twice
        for _ in range(2):
            response = await billing_client.post(
                "/webhooks/stripe",
                content=json.dumps(event),
                headers={
                    "Content-Type": "application/json",
                    "stripe-signature": "test_sig",
                },
            )
            assert response.status_code == 200

        # Verify only one invoice exists
        result = await db_session.execute(
            select(Invoice).where(Invoice.stripe_invoice_id == stripe_invoice_id)
        )
        invoices = result.scalars().all()

        assert len(invoices) == 1

    async def test_duplicate_payment_method_webhook_is_idempotent(
        self,
        billing_client: AsyncClient,
        db_session: AsyncSession,
        test_subscription: Subscription,
    ):
        """Test sending same payment_method.attached webhook twice doesn't duplicate."""
        stripe_pm_id = f"pm_{uuid4().hex[:24]}"

        event = {
            "type": "payment_method.attached",
            "data": {
                "object": {
                    "id": stripe_pm_id,
                    "customer": test_subscription.stripe_customer_id,
                    "type": "card",
                    "card": {
                        "brand": "amex",
                        "last4": "1234",
                        "exp_month": 3,
                        "exp_year": 2027,
                    },
                }
            },
        }

        # Send webhook twice
        for _ in range(2):
            response = await billing_client.post(
                "/webhooks/stripe",
                content=json.dumps(event),
                headers={
                    "Content-Type": "application/json",
                    "stripe-signature": "test_sig",
                },
            )
            assert response.status_code == 200

        # Verify only one payment method exists
        result = await db_session.execute(
            select(PaymentMethod).where(PaymentMethod.stripe_payment_method_id == stripe_pm_id)
        )
        pms = result.scalars().all()

        assert len(pms) == 1


class TestWebhookTenantIsolation:
    """Tests for tenant isolation in webhook processing."""

    async def test_invoice_created_for_correct_tenant(
        self,
        billing_client: AsyncClient,
        db_session: AsyncSession,
        test_subscription: Subscription,
        second_tenant: Tenant,
    ):
        """Test invoice is created for the correct tenant based on subscription."""
        stripe_invoice_id = f"in_{uuid4().hex[:24]}"

        event = {
            "type": "invoice.paid",
            "data": {
                "object": {
                    "id": stripe_invoice_id,
                    "subscription": test_subscription.stripe_subscription_id,
                    "customer": test_subscription.stripe_customer_id,
                    "number": "INV-TENANT-001",
                    "amount_due": 2900,
                    "amount_paid": 2900,
                    "currency": "usd",
                    "period_start": int(datetime.now(UTC).timestamp()),
                    "period_end": int((datetime.now(UTC) + timedelta(days=30)).timestamp()),
                }
            },
        }

        response = await billing_client.post(
            "/webhooks/stripe",
            content=json.dumps(event),
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "test_sig",
            },
        )

        assert response.status_code == 200

        # Verify invoice belongs to correct tenant
        result = await db_session.execute(
            select(Invoice).where(Invoice.stripe_invoice_id == stripe_invoice_id)
        )
        invoice = result.scalar_one_or_none()

        assert invoice is not None
        assert invoice.tenant_id == test_subscription.tenant_id
        assert invoice.tenant_id != second_tenant.id

    async def test_payment_method_created_for_correct_tenant(
        self,
        billing_client: AsyncClient,
        db_session: AsyncSession,
        test_subscription: Subscription,
        second_tenant: Tenant,
    ):
        """Test payment method is created for the correct tenant."""
        stripe_pm_id = f"pm_{uuid4().hex[:24]}"

        event = {
            "type": "payment_method.attached",
            "data": {
                "object": {
                    "id": stripe_pm_id,
                    "customer": test_subscription.stripe_customer_id,
                    "type": "card",
                    "card": {
                        "brand": "visa",
                        "last4": "9999",
                        "exp_month": 9,
                        "exp_year": 2029,
                    },
                }
            },
        }

        response = await billing_client.post(
            "/webhooks/stripe",
            content=json.dumps(event),
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "test_sig",
            },
        )

        assert response.status_code == 200

        # Verify payment method belongs to correct tenant
        result = await db_session.execute(
            select(PaymentMethod).where(PaymentMethod.stripe_payment_method_id == stripe_pm_id)
        )
        pm = result.scalar_one_or_none()

        assert pm is not None
        assert pm.tenant_id == test_subscription.tenant_id
        assert pm.tenant_id != second_tenant.id
