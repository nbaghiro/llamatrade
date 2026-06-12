"""Tests for webhook handler functions.

Handlers take typed stripe-python 15 resources; payloads here are built via
``construct_from`` with the current (dahlia) API shapes — billing periods on
subscription items, invoice→subscription linkage under ``parent``.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from stripe import Invoice, PaymentMethod, Subscription

from llamatrade_proto.generated import billing_pb2

from src.routers.webhooks import (
    _handle_invoice_paid,
    _handle_payment_failed,
    _handle_payment_method_attached,
    _handle_payment_method_detached,
    _handle_subscription_created,
    _handle_subscription_deleted,
    _handle_subscription_updated,
)


def _stripe_subscription(**overrides: Any) -> Subscription:
    data: dict[str, Any] = {
        "id": "sub_123",
        "object": "subscription",
        "status": "active",
        "cancel_at_period_end": False,
        "canceled_at": None,
        "trial_start": None,
        "trial_end": None,
        "items": {
            "object": "list",
            "data": [
                {
                    "id": "si_1",
                    "object": "subscription_item",
                    "current_period_start": 1700000000,
                    "current_period_end": 1702592000,
                }
            ],
            "has_more": False,
        },
    }
    data.update(overrides)
    return Subscription.construct_from(data, "sk_test")


def _stripe_invoice(subscription: str | None = "sub_123", **overrides: Any) -> Invoice:
    parent: dict[str, Any] | None = None
    if subscription is not None:
        parent = {
            "type": "subscription_details",
            "subscription_details": {
                "subscription": subscription,
                "metadata": {},
                "subscription_proration_date": None,
            },
            "quote_details": None,
        }
    data: dict[str, Any] = {
        "id": "in_123",
        "object": "invoice",
        "number": "INV-001",
        "amount_due": 2900,
        "amount_paid": 2900,
        "currency": "usd",
        "period_start": 1700000000,
        "period_end": 1702592000,
        "hosted_invoice_url": None,
        "invoice_pdf": None,
        "parent": parent,
    }
    data.update(overrides)
    return Invoice.construct_from(data, "sk_test")


def _stripe_payment_method(**overrides: Any) -> PaymentMethod:
    data: dict[str, Any] = {
        "id": "pm_123",
        "object": "payment_method",
        "type": "card",
        "customer": "cus_123",
        "card": {
            "brand": "visa",
            "last4": "4242",
            "exp_month": 12,
            "exp_year": 2030,
        },
    }
    data.update(overrides)
    return PaymentMethod.construct_from(data, "sk_test")


class TestHandleSubscriptionCreated:
    """Tests for _handle_subscription_created."""

    async def test_updates_subscription_when_exists(self) -> None:
        """Test updating subscription from webhook when it exists locally."""
        mock_sub = MagicMock()
        mock_sub.status = "incomplete"

        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_sub)

        await _handle_subscription_created(mock_db, _stripe_subscription())

        # Should have updated status, period (from the item), and committed
        assert mock_sub.status == billing_pb2.SUBSCRIPTION_STATUS_ACTIVE
        assert mock_sub.current_period_start.timestamp() == 1700000000
        assert mock_sub.current_period_end.timestamp() == 1702592000
        mock_db.commit.assert_called()

    async def test_does_nothing_when_not_exists(self) -> None:
        """Test that nothing happens when subscription not found locally."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        await _handle_subscription_created(mock_db, _stripe_subscription(id="sub_new_123"))

        # Should not commit if subscription not found
        mock_db.commit.assert_not_called()


class TestHandleSubscriptionUpdated:
    """Tests for _handle_subscription_updated."""

    async def test_updates_existing_subscription(self) -> None:
        """Test updating existing subscription status."""
        mock_subscription = MagicMock()
        mock_subscription.status = "active"

        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_subscription)

        await _handle_subscription_updated(
            mock_db, _stripe_subscription(status="past_due", cancel_at_period_end=True)
        )

        assert mock_subscription.status == billing_pb2.SUBSCRIPTION_STATUS_PAST_DUE
        assert mock_subscription.cancel_at_period_end is True
        mock_db.commit.assert_called()


class TestHandleSubscriptionDeleted:
    """Tests for _handle_subscription_deleted."""

    async def test_marks_subscription_as_cancelled(self) -> None:
        """Test marking subscription as cancelled."""
        mock_subscription = MagicMock()
        mock_subscription.status = "active"

        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_subscription)

        await _handle_subscription_deleted(mock_db, _stripe_subscription(status="canceled"))

        assert mock_subscription.status == billing_pb2.SUBSCRIPTION_STATUS_CANCELED
        mock_db.commit.assert_called()


class TestHandleInvoicePaid:
    """Tests for _handle_invoice_paid."""

    async def test_creates_invoice_record_when_subscription_exists(self) -> None:
        """Test creating invoice record from webhook when subscription exists."""
        mock_subscription = MagicMock()
        mock_subscription.tenant_id = uuid4()
        mock_subscription.id = uuid4()

        # First call returns subscription, second returns None (no existing invoice)
        call_count = 0

        def mock_scalar():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_subscription  # Subscription found
            return None  # No existing invoice

        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=mock_scalar)

        await _handle_invoice_paid(mock_db, _stripe_invoice())

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called()

    async def test_does_nothing_when_subscription_not_found(self) -> None:
        """Test that nothing happens when subscription not found."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        await _handle_invoice_paid(mock_db, _stripe_invoice(subscription="sub_nonexistent"))

        # Should not commit if subscription not found
        mock_db.commit.assert_not_called()


class TestHandlePaymentFailed:
    """Tests for _handle_payment_failed."""

    async def test_updates_subscription_to_past_due(self) -> None:
        """Test updating subscription to past_due on payment failure."""
        mock_subscription = MagicMock()
        mock_subscription.status = "active"

        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_subscription)

        await _handle_payment_failed(mock_db, _stripe_invoice())

        assert mock_subscription.status == billing_pb2.SUBSCRIPTION_STATUS_PAST_DUE
        mock_db.commit.assert_called()

    async def test_does_nothing_when_subscription_not_found(self) -> None:
        """Test that nothing happens when subscription not found."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        await _handle_payment_failed(mock_db, _stripe_invoice(subscription="sub_nonexistent"))

        mock_db.commit.assert_not_called()

    async def test_does_nothing_for_non_subscription_invoice(self) -> None:
        """An invoice with no subscription parent is a no-op."""
        mock_db = AsyncMock()

        await _handle_payment_failed(mock_db, _stripe_invoice(subscription=None))

        mock_db.execute.assert_not_called()


class TestHandlePaymentMethodAttached:
    """Tests for _handle_payment_method_attached."""

    async def test_ignores_without_tenant(self) -> None:
        """Test that attachment is ignored without tenant mapping."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=lambda: None  # No customer found
        )

        await _handle_payment_method_attached(
            mock_db, _stripe_payment_method(customer="cus_unknown")
        )

        # Should not add anything if tenant not found
        mock_db.add.assert_not_called()


class TestHandlePaymentMethodDetached:
    """Tests for _handle_payment_method_detached."""

    async def test_removes_payment_method(self) -> None:
        """Test removing payment method from database."""
        mock_db = AsyncMock()

        await _handle_payment_method_detached(mock_db, _stripe_payment_method())

        # Should have executed delete query
        mock_db.execute.assert_called()
        mock_db.commit.assert_called()
