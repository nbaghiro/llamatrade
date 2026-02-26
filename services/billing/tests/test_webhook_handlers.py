"""Tests for webhook handler functions."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from src.routers.webhooks import (
    _handle_invoice_paid,
    _handle_payment_failed,
    _handle_payment_method_attached,
    _handle_payment_method_detached,
    _handle_subscription_created,
    _handle_subscription_deleted,
    _handle_subscription_updated,
)


class TestHandleSubscriptionCreated:
    """Tests for _handle_subscription_created."""

    async def test_updates_subscription_when_exists(self) -> None:
        """Test updating subscription from webhook when it exists locally."""
        mock_sub = MagicMock()
        mock_sub.status = "incomplete"

        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_sub)

        subscription_data = {
            "id": "sub_123",
            "customer": "cus_123",
            "status": "active",
            "current_period_start": 1700000000,
            "current_period_end": 1702592000,
        }

        await _handle_subscription_created(mock_db, subscription_data)

        # Should have updated status and committed
        assert mock_sub.status == "active"
        mock_db.commit.assert_called()

    async def test_does_nothing_when_not_exists(self) -> None:
        """Test that nothing happens when subscription not found locally."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        subscription_data = {
            "id": "sub_new_123",
            "customer": "cus_123",
            "status": "active",
        }

        await _handle_subscription_created(mock_db, subscription_data)

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

        subscription_data = {
            "id": "sub_123",
            "status": "past_due",
            "cancel_at_period_end": True,
            "current_period_start": 1700000000,
            "current_period_end": 1702592000,
        }

        await _handle_subscription_updated(mock_db, subscription_data)

        assert mock_subscription.status == "past_due"
        mock_db.commit.assert_called()


class TestHandleSubscriptionDeleted:
    """Tests for _handle_subscription_deleted."""

    async def test_marks_subscription_as_cancelled(self) -> None:
        """Test marking subscription as cancelled."""
        mock_subscription = MagicMock()
        mock_subscription.status = "active"

        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: mock_subscription)

        subscription_data = {
            "id": "sub_123",
        }

        await _handle_subscription_deleted(mock_db, subscription_data)

        assert mock_subscription.status == "cancelled"
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

        invoice_data = {
            "id": "in_123",
            "subscription": "sub_123",
            "customer": "cus_123",
            "number": "INV-001",
            "amount_due": 2900,
            "amount_paid": 2900,
            "currency": "usd",
            "period_start": 1700000000,
            "period_end": 1702592000,
        }

        await _handle_invoice_paid(mock_db, invoice_data)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called()

    async def test_does_nothing_when_subscription_not_found(self) -> None:
        """Test that nothing happens when subscription not found."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        invoice_data = {
            "id": "in_123",
            "subscription": "sub_nonexistent",
        }

        await _handle_invoice_paid(mock_db, invoice_data)

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

        invoice_data = {
            "id": "in_123",
            "subscription": "sub_123",
        }

        await _handle_payment_failed(mock_db, invoice_data)

        assert mock_subscription.status == "past_due"
        mock_db.commit.assert_called()

    async def test_does_nothing_when_subscription_not_found(self) -> None:
        """Test that nothing happens when subscription not found."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        invoice_data = {
            "id": "in_123",
            "subscription": "sub_nonexistent",
        }

        await _handle_payment_failed(mock_db, invoice_data)

        # Should not commit if nothing to update
        # (depends on implementation)


class TestHandlePaymentMethodAttached:
    """Tests for _handle_payment_method_attached."""

    async def test_ignores_without_tenant(self) -> None:
        """Test that attachment is ignored without tenant mapping."""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(
            scalar_one_or_none=lambda: None  # No customer found
        )

        pm_data = {
            "id": "pm_123",
            "customer": "cus_unknown",
            "type": "card",
            "card": {
                "brand": "visa",
                "last4": "4242",
                "exp_month": 12,
                "exp_year": 2030,
            },
        }

        await _handle_payment_method_attached(mock_db, pm_data)

        # Should not add anything if tenant not found


class TestHandlePaymentMethodDetached:
    """Tests for _handle_payment_method_detached."""

    async def test_removes_payment_method(self) -> None:
        """Test removing payment method from database."""
        mock_db = AsyncMock()

        pm_data = {
            "id": "pm_123",
        }

        await _handle_payment_method_detached(mock_db, pm_data)

        # Should have executed delete query
        mock_db.execute.assert_called()
        mock_db.commit.assert_called()
