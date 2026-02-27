"""Tests for Stripe client."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.stripe.client import (
    InvoiceResult,
    PaymentMethodResult,
    SetupIntentResult,
    StripeClient,
    StripeError,
    SubscriptionResult,
)


class TestStripeClientInit:
    """Tests for StripeClient initialization."""

    def test_init_with_api_key(self) -> None:
        """Test client initializes with API key from environment."""
        with patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_123"}):
            client = StripeClient()
            assert client.api_key == "sk_test_123"

    def test_init_without_api_key(self) -> None:
        """Test client handles missing API key gracefully."""
        with patch.dict("os.environ", {"STRIPE_SECRET_KEY": ""}):
            client = StripeClient()
            assert client.api_key == ""


class TestTimestampConversion:
    """Tests for timestamp conversion helper."""

    def test_timestamp_to_datetime(self) -> None:
        """Test converting Unix timestamp to datetime."""
        client = StripeClient()

        # Test with valid timestamp
        result = client._timestamp_to_datetime(1700000000)
        assert result is not None
        assert isinstance(result, datetime)
        assert result.tzinfo == UTC

    def test_timestamp_to_datetime_none(self) -> None:
        """Test converting None timestamp."""
        client = StripeClient()

        result = client._timestamp_to_datetime(None)
        assert result is None


class TestDataclassResults:
    """Tests for result dataclasses."""

    def test_setup_intent_result(self) -> None:
        """Test SetupIntentResult dataclass."""
        result = SetupIntentResult(
            client_secret="seti_secret_123",
            customer_id="cus_123",
        )
        assert result.client_secret == "seti_secret_123"
        assert result.customer_id == "cus_123"

    def test_payment_method_result(self) -> None:
        """Test PaymentMethodResult dataclass."""
        result = PaymentMethodResult(
            id="pm_123",
            type="card",
            card_brand="visa",
            card_last4="4242",
            card_exp_month=12,
            card_exp_year=2030,
        )
        assert result.id == "pm_123"
        assert result.type == "card"
        assert result.card_brand == "visa"
        assert result.card_last4 == "4242"

    def test_subscription_result(self) -> None:
        """Test SubscriptionResult dataclass."""
        now = datetime.now(UTC)
        result = SubscriptionResult(
            id="sub_123",
            status="active",
            current_period_start=now,
            current_period_end=now,
            cancel_at_period_end=False,
        )
        assert result.id == "sub_123"
        assert result.status == "active"
        assert result.cancel_at_period_end is False

    def test_invoice_result(self) -> None:
        """Test InvoiceResult dataclass."""
        now = datetime.now(UTC)
        result = InvoiceResult(
            id="in_123",
            amount_due=2900,
            amount_paid=2900,
            currency="usd",
            status="paid",
            period_start=now,
            period_end=now,
        )
        assert result.id == "in_123"
        assert result.amount_due == 2900
        assert result.status == "paid"


class TestStripeError:
    """Tests for StripeError exception."""

    def test_stripe_error_with_code(self) -> None:
        """Test StripeError with error code."""
        error = StripeError("Payment failed", "card_declined")
        assert error.message == "Payment failed"
        assert error.code == "card_declined"
        assert str(error) == "Payment failed"

    def test_stripe_error_without_code(self) -> None:
        """Test StripeError without error code."""
        error = StripeError("Something went wrong")
        assert error.message == "Something went wrong"
        assert error.code is None


class TestStripeClientMethods:
    """Tests for StripeClient API methods with mocked Stripe SDK."""

    @patch("src.stripe.client.Customer")
    async def test_get_or_create_customer_existing(self, mock_customer: MagicMock) -> None:
        """Test getting existing customer."""
        mock_customer.search.return_value = MagicMock(data=[MagicMock(id="cus_existing_123")])

        client = StripeClient()
        result = await client.get_or_create_customer("tenant_123", "test@example.com")

        assert result == "cus_existing_123"
        mock_customer.search.assert_called_once()

    @patch("src.stripe.client.Customer")
    async def test_get_or_create_customer_new(self, mock_customer: MagicMock) -> None:
        """Test creating new customer when none exists."""
        mock_customer.search.return_value = MagicMock(data=[])
        mock_customer.create.return_value = MagicMock(id="cus_new_123")

        client = StripeClient()
        result = await client.get_or_create_customer("tenant_123", "test@example.com", "Test User")

        assert result == "cus_new_123"
        mock_customer.create.assert_called_once()

    @patch("src.stripe.client.Customer")
    async def test_get_customer_found(self, mock_customer: MagicMock) -> None:
        """Test getting existing customer."""
        mock_customer.retrieve.return_value = MagicMock(id="cus_123")

        client = StripeClient()
        result = await client.get_customer("cus_123")

        assert result is not None
        assert result.id == "cus_123"

    @patch("src.stripe.client.Customer")
    async def test_get_customer_not_found(self, mock_customer: MagicMock) -> None:
        """Test getting non-existent customer."""
        import stripe

        mock_customer.retrieve.side_effect = stripe.InvalidRequestError(
            "No such customer", "customer_id"
        )

        client = StripeClient()
        result = await client.get_customer("cus_nonexistent")

        assert result is None

    @patch("src.stripe.client.SetupIntent")
    async def test_create_setup_intent(self, mock_setup_intent: MagicMock) -> None:
        """Test creating setup intent."""
        mock_setup_intent.create.return_value = MagicMock(client_secret="seti_secret_123")

        client = StripeClient()
        result = await client.create_setup_intent("cus_123")

        assert result.client_secret == "seti_secret_123"
        assert result.customer_id == "cus_123"

    @patch("src.stripe.client.PaymentMethod")
    async def test_attach_payment_method(self, mock_pm: MagicMock) -> None:
        """Test attaching payment method."""
        mock_pm.attach.return_value = MagicMock(
            id="pm_123",
            type="card",
            card={"brand": "visa", "last4": "4242", "exp_month": 12, "exp_year": 2030},
            get=lambda key, default=None: (
                {
                    "brand": "visa",
                    "last4": "4242",
                    "exp_month": 12,
                    "exp_year": 2030,
                }
                if key == "card"
                else default
            ),
        )

        client = StripeClient()
        result = await client.attach_payment_method("cus_123", "pm_123")

        assert result.id == "pm_123"
        assert result.type == "card"

    @patch("src.stripe.client.PaymentMethod")
    async def test_detach_payment_method(self, mock_pm: MagicMock) -> None:
        """Test detaching payment method."""
        mock_pm.detach.return_value = MagicMock()

        client = StripeClient()
        result = await client.detach_payment_method("pm_123")

        assert result is True
        mock_pm.detach.assert_called_once_with("pm_123")

    @patch("src.stripe.client.PaymentMethod")
    async def test_list_payment_methods(self, mock_pm: MagicMock) -> None:
        """Test listing payment methods."""
        mock_pm.list.return_value = MagicMock(
            data=[
                MagicMock(
                    id="pm_1",
                    type="card",
                    card={"brand": "visa", "last4": "4242", "exp_month": 12, "exp_year": 2030},
                    get=lambda key, default=None: (
                        {
                            "brand": "visa",
                            "last4": "4242",
                            "exp_month": 12,
                            "exp_year": 2030,
                        }
                        if key == "card"
                        else default
                    ),
                )
            ]
        )

        client = StripeClient()
        result = await client.list_payment_methods("cus_123")

        assert len(result) == 1
        assert result[0].id == "pm_1"

    @patch("src.stripe.client.Customer")
    async def test_set_default_payment_method(self, mock_customer: MagicMock) -> None:
        """Test setting default payment method."""
        mock_customer.modify.return_value = MagicMock()

        client = StripeClient()
        result = await client.set_default_payment_method("cus_123", "pm_123")

        assert result is True
        mock_customer.modify.assert_called_once()

    @patch("src.stripe.client.Customer")
    async def test_get_default_payment_method(self, mock_customer: MagicMock) -> None:
        """Test getting default payment method."""
        mock_customer.retrieve.return_value = MagicMock(
            get=lambda key, default=None: (
                {"default_payment_method": "pm_123"} if key == "invoice_settings" else default
            )
        )

        client = StripeClient()
        result = await client.get_default_payment_method("cus_123")

        assert result == "pm_123"

    @patch("src.stripe.client.Subscription")
    async def test_create_subscription(self, mock_sub: MagicMock) -> None:
        """Test creating subscription."""
        mock_sub.create.return_value = MagicMock(
            id="sub_123",
            status="active",
            current_period_start=1700000000,
            current_period_end=1702678400,
            cancel_at_period_end=False,
            trial_start=None,
            trial_end=None,
        )

        client = StripeClient()
        result = await client.create_subscription("cus_123", "price_123", "pm_123")

        assert result.id == "sub_123"
        assert result.status == "active"

    @patch("src.stripe.client.Subscription")
    async def test_create_subscription_with_trial(self, mock_sub: MagicMock) -> None:
        """Test creating subscription with trial."""
        mock_sub.create.return_value = MagicMock(
            id="sub_123",
            status="trialing",
            current_period_start=1700000000,
            current_period_end=1702678400,
            cancel_at_period_end=False,
            trial_start=1700000000,
            trial_end=1701209600,
        )

        client = StripeClient()
        result = await client.create_subscription("cus_123", "price_123", "pm_123", trial_days=14)

        assert result.id == "sub_123"
        assert result.status == "trialing"

    @patch("src.stripe.client.Subscription")
    async def test_cancel_subscription_at_period_end(self, mock_sub: MagicMock) -> None:
        """Test canceling subscription at period end."""
        mock_sub.modify.return_value = MagicMock()

        client = StripeClient()
        result = await client.cancel_subscription("sub_123", at_period_end=True)

        assert result is True
        mock_sub.modify.assert_called_once_with("sub_123", cancel_at_period_end=True)

    @patch("src.stripe.client.Subscription")
    async def test_cancel_subscription_immediately(self, mock_sub: MagicMock) -> None:
        """Test canceling subscription immediately."""
        mock_sub.cancel.return_value = MagicMock()

        client = StripeClient()
        result = await client.cancel_subscription("sub_123", at_period_end=False)

        assert result is True
        mock_sub.cancel.assert_called_once_with("sub_123")

    @patch("src.stripe.client.Subscription")
    async def test_reactivate_subscription(self, mock_sub: MagicMock) -> None:
        """Test reactivating subscription."""
        mock_sub.modify.return_value = MagicMock(
            id="sub_123",
            status="active",
            current_period_start=1700000000,
            current_period_end=1702678400,
            cancel_at_period_end=False,
            trial_start=None,
            trial_end=None,
        )

        client = StripeClient()
        result = await client.reactivate_subscription("sub_123")

        assert result.id == "sub_123"
        assert result.cancel_at_period_end is False

    @patch("src.stripe.client.Subscription")
    async def test_get_subscription_found(self, mock_sub: MagicMock) -> None:
        """Test getting subscription that exists."""
        mock_sub.retrieve.return_value = MagicMock(
            id="sub_123",
            status="active",
            current_period_start=1700000000,
            current_period_end=1702678400,
            cancel_at_period_end=False,
            trial_start=None,
            trial_end=None,
        )

        client = StripeClient()
        result = await client.get_subscription("sub_123")

        assert result is not None
        assert result.id == "sub_123"

    @patch("src.stripe.client.Subscription")
    async def test_get_subscription_not_found(self, mock_sub: MagicMock) -> None:
        """Test getting non-existent subscription."""
        import stripe

        mock_sub.retrieve.side_effect = stripe.InvalidRequestError(
            "No such subscription", "subscription_id"
        )

        client = StripeClient()
        result = await client.get_subscription("sub_nonexistent")

        assert result is None

    @patch("src.stripe.client.Invoice")
    async def test_list_invoices(self, mock_invoice: MagicMock) -> None:
        """Test listing invoices."""
        mock_invoice.list.return_value = MagicMock(
            data=[
                MagicMock(
                    id="in_123",
                    amount_due=2900,
                    amount_paid=2900,
                    currency="usd",
                    status="paid",
                    period_start=1700000000,
                    period_end=1702678400,
                    status_transitions=MagicMock(paid_at=1700001000),
                    invoice_pdf="https://stripe.com/invoice.pdf",
                    hosted_invoice_url="https://stripe.com/invoice",
                )
            ]
        )

        client = StripeClient()
        result = await client.list_invoices("cus_123")

        assert len(result) == 1
        assert result[0].id == "in_123"
        assert result[0].status == "paid"

    @patch("src.stripe.client.Subscription")
    async def test_update_subscription(self, mock_sub: MagicMock) -> None:
        """Test updating subscription."""
        mock_sub.retrieve.return_value = MagicMock(
            items=MagicMock(data=[MagicMock(id="si_123")]),
            __getitem__=lambda self, key: {"items": {"data": [{"id": "si_123"}]}}[key],
        )
        mock_sub.modify.return_value = MagicMock(
            id="sub_123",
            status="active",
            current_period_start=1700000000,
            current_period_end=1702678400,
            cancel_at_period_end=False,
            trial_start=None,
            trial_end=None,
        )

        client = StripeClient()
        result = await client.update_subscription("sub_123", "price_new")

        assert result.id == "sub_123"


class TestGetStripeClient:
    """Tests for get_stripe_client function."""

    def test_get_stripe_client_singleton(self) -> None:
        """Test that get_stripe_client returns singleton."""
        # Reset the singleton
        import src.stripe.client
        from src.stripe.client import get_stripe_client

        src.stripe.client._stripe_client = None

        client1 = get_stripe_client()
        client2 = get_stripe_client()

        assert client1 is client2


class TestStripeClientErrors:
    """Tests for StripeClient error handling."""

    @patch("src.stripe.client.Customer")
    async def test_get_or_create_customer_stripe_error(self, mock_customer: MagicMock) -> None:
        """Test handling Stripe error in get_or_create_customer."""
        import stripe

        mock_customer.search.side_effect = stripe.StripeError("API error")

        client = StripeClient()

        with pytest.raises(StripeError, match="API error"):
            await client.get_or_create_customer("tenant_123", "test@example.com")

    @patch("src.stripe.client.Customer")
    async def test_get_customer_stripe_error(self, mock_customer: MagicMock) -> None:
        """Test handling Stripe error in get_customer."""
        import stripe

        mock_customer.retrieve.side_effect = stripe.StripeError("API error")

        client = StripeClient()

        with pytest.raises(StripeError, match="API error"):
            await client.get_customer("cus_123")

    @patch("src.stripe.client.SetupIntent")
    async def test_create_setup_intent_stripe_error(self, mock_setup_intent: MagicMock) -> None:
        """Test handling Stripe error in create_setup_intent."""
        import stripe

        mock_setup_intent.create.side_effect = stripe.StripeError("API error")

        client = StripeClient()

        with pytest.raises(StripeError, match="API error"):
            await client.create_setup_intent("cus_123")

    @patch("src.stripe.client.PaymentMethod")
    async def test_attach_payment_method_stripe_error(self, mock_pm: MagicMock) -> None:
        """Test handling Stripe error in attach_payment_method."""
        import stripe

        mock_pm.attach.side_effect = stripe.StripeError("Card declined")

        client = StripeClient()

        with pytest.raises(StripeError, match="Card declined"):
            await client.attach_payment_method("cus_123", "pm_123")

    @patch("src.stripe.client.PaymentMethod")
    async def test_detach_payment_method_stripe_error(self, mock_pm: MagicMock) -> None:
        """Test handling Stripe error in detach_payment_method."""
        import stripe

        mock_pm.detach.side_effect = stripe.StripeError("API error")

        client = StripeClient()

        with pytest.raises(StripeError, match="API error"):
            await client.detach_payment_method("pm_123")

    @patch("src.stripe.client.PaymentMethod")
    async def test_list_payment_methods_stripe_error(self, mock_pm: MagicMock) -> None:
        """Test handling Stripe error in list_payment_methods."""
        import stripe

        mock_pm.list.side_effect = stripe.StripeError("API error")

        client = StripeClient()

        with pytest.raises(StripeError, match="API error"):
            await client.list_payment_methods("cus_123")

    @patch("src.stripe.client.Customer")
    async def test_set_default_payment_method_stripe_error(self, mock_customer: MagicMock) -> None:
        """Test handling Stripe error in set_default_payment_method."""
        import stripe

        mock_customer.modify.side_effect = stripe.StripeError("API error")

        client = StripeClient()

        with pytest.raises(StripeError, match="API error"):
            await client.set_default_payment_method("cus_123", "pm_123")

    @patch("src.stripe.client.Customer")
    async def test_get_default_payment_method_stripe_error(self, mock_customer: MagicMock) -> None:
        """Test handling Stripe error in get_default_payment_method."""
        import stripe

        mock_customer.retrieve.side_effect = stripe.StripeError("API error")

        client = StripeClient()

        with pytest.raises(StripeError, match="API error"):
            await client.get_default_payment_method("cus_123")

    @patch("src.stripe.client.Subscription")
    async def test_create_subscription_stripe_error(self, mock_sub: MagicMock) -> None:
        """Test handling Stripe error in create_subscription."""
        import stripe

        mock_sub.create.side_effect = stripe.StripeError("Payment failed")

        client = StripeClient()

        with pytest.raises(StripeError, match="Payment failed"):
            await client.create_subscription("cus_123", "price_123", "pm_123")

    @patch("src.stripe.client.Subscription")
    async def test_update_subscription_stripe_error(self, mock_sub: MagicMock) -> None:
        """Test handling Stripe error in update_subscription."""
        import stripe

        mock_sub.retrieve.side_effect = stripe.StripeError("API error")

        client = StripeClient()

        with pytest.raises(StripeError, match="API error"):
            await client.update_subscription("sub_123", "price_123")

    @patch("src.stripe.client.Subscription")
    async def test_cancel_subscription_stripe_error(self, mock_sub: MagicMock) -> None:
        """Test handling Stripe error in cancel_subscription."""
        import stripe

        mock_sub.modify.side_effect = stripe.StripeError("API error")

        client = StripeClient()

        with pytest.raises(StripeError, match="API error"):
            await client.cancel_subscription("sub_123")

    @patch("src.stripe.client.Subscription")
    async def test_reactivate_subscription_stripe_error(self, mock_sub: MagicMock) -> None:
        """Test handling Stripe error in reactivate_subscription."""
        import stripe

        mock_sub.modify.side_effect = stripe.StripeError("API error")

        client = StripeClient()

        with pytest.raises(StripeError, match="API error"):
            await client.reactivate_subscription("sub_123")

    @patch("src.stripe.client.Subscription")
    async def test_get_subscription_stripe_error(self, mock_sub: MagicMock) -> None:
        """Test handling Stripe error in get_subscription."""
        import stripe

        mock_sub.retrieve.side_effect = stripe.StripeError("API error")

        client = StripeClient()

        with pytest.raises(StripeError, match="API error"):
            await client.get_subscription("sub_123")

    @patch("src.stripe.client.Invoice")
    async def test_list_invoices_stripe_error(self, mock_invoice: MagicMock) -> None:
        """Test handling Stripe error in list_invoices."""
        import stripe

        mock_invoice.list.side_effect = stripe.StripeError("API error")

        client = StripeClient()

        with pytest.raises(StripeError, match="API error"):
            await client.list_invoices("cus_123")


class TestWebhookVerification:
    """Tests for webhook signature verification."""

    @patch("src.stripe.client.stripe.Webhook")
    def test_verify_webhook_invalid_signature(self, mock_webhook: MagicMock) -> None:
        """Test webhook verification with invalid signature."""
        import stripe

        mock_webhook.construct_event.side_effect = stripe.SignatureVerificationError(
            "Invalid signature", "sig_header"
        )

        client = StripeClient()

        with pytest.raises(StripeError, match="Invalid webhook signature"):
            client.verify_webhook_signature(b"payload", "sig", "secret")

    @patch("src.stripe.client.stripe.Webhook")
    def test_verify_webhook_invalid_payload(self, mock_webhook: MagicMock) -> None:
        """Test webhook verification with invalid payload."""
        mock_webhook.construct_event.side_effect = ValueError("Invalid JSON")

        client = StripeClient()

        with pytest.raises(StripeError, match="Invalid webhook payload"):
            client.verify_webhook_signature(b"not json", "sig", "secret")
