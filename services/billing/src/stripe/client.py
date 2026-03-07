"""Stripe API client wrapper."""

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import stripe
from stripe import Customer, Event, Invoice, PaymentMethod, SetupIntent, Subscription

logger = logging.getLogger(__name__)


@dataclass
class SetupIntentResult:
    """Result from creating a SetupIntent."""

    client_secret: str
    customer_id: str


@dataclass
class PaymentMethodResult:
    """Result from payment method operations."""

    id: str
    type: str
    card_brand: str | None = None
    card_last4: str | None = None
    card_exp_month: int | None = None
    card_exp_year: int | None = None


@dataclass
class SubscriptionResult:
    """Result from subscription operations."""

    id: str
    status: str
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    trial_start: datetime | None = None
    trial_end: datetime | None = None


@dataclass
class InvoiceResult:
    """Result from invoice operations."""

    id: str
    amount_due: int
    amount_paid: int
    currency: str
    status: str
    period_start: datetime
    period_end: datetime
    paid_at: datetime | None = None
    invoice_pdf: str | None = None
    hosted_invoice_url: str | None = None


class StripeError(Exception):
    """Custom exception for Stripe API errors."""

    def __init__(self, message: str, code: str | None = None):
        self.message = message
        self.code = code
        super().__init__(message)


class StripeClient:
    """Wrapper for Stripe API operations."""

    def __init__(self) -> None:
        self.api_key = os.getenv("STRIPE_SECRET_KEY", "")
        if self.api_key:
            stripe.api_key = self.api_key
        else:
            logger.warning("STRIPE_SECRET_KEY not set")

    def _timestamp_to_datetime(self, ts: int | None) -> datetime | None:
        """Convert Unix timestamp to datetime."""
        if ts is None:
            return None
        return datetime.fromtimestamp(ts, tz=UTC)

    # ===================
    # Customer Management
    # ===================

    async def get_or_create_customer(
        self, tenant_id: str, email: str, name: str | None = None
    ) -> str:
        """Get existing customer by metadata or create new one."""
        try:
            # Search for existing customer with this tenant_id
            # pyright: ignore[reportUnknownMemberType] - stripe library has incomplete type stubs
            customers = Customer.search(  # pyright: ignore[reportUnknownMemberType]
                query=f"metadata['tenant_id']:'{tenant_id}'"
            )
            if customers.data:
                return str(customers.data[0].id)

            # Create new customer
            customer = Customer.create(
                email=email,
                name=name or "",
                metadata={"tenant_id": tenant_id},
            )
            logger.info(f"Created Stripe customer {customer.id} for tenant {tenant_id}")
            return str(customer.id)
        except stripe.StripeError as e:
            logger.error(f"Stripe error creating customer: {e}")
            raise StripeError(str(e), getattr(e, "code", None))

    async def get_customer(self, customer_id: str) -> Customer | None:
        """Get customer by ID."""
        try:
            return Customer.retrieve(customer_id)
        except stripe.InvalidRequestError:
            return None
        except stripe.StripeError as e:
            logger.error(f"Stripe error getting customer: {e}")
            raise StripeError(str(e), getattr(e, "code", None))

    # ===================
    # Payment Methods
    # ===================

    async def create_setup_intent(self, customer_id: str) -> SetupIntentResult:
        """Create a SetupIntent for collecting card details."""
        try:
            setup_intent = SetupIntent.create(
                customer=customer_id,
                payment_method_types=["card"],
                usage="off_session",
            )
            return SetupIntentResult(
                client_secret=setup_intent.client_secret or "",
                customer_id=customer_id,
            )
        except stripe.StripeError as e:
            logger.error(f"Stripe error creating setup intent: {e}")
            raise StripeError(str(e), getattr(e, "code", None))

    async def attach_payment_method(
        self, customer_id: str, payment_method_id: str
    ) -> PaymentMethodResult:
        """Attach a payment method to a customer."""
        try:
            pm = PaymentMethod.attach(payment_method_id, customer=customer_id)
            return self._payment_method_to_result(pm)
        except stripe.StripeError as e:
            logger.error(f"Stripe error attaching payment method: {e}")
            raise StripeError(str(e), getattr(e, "code", None))

    async def detach_payment_method(self, payment_method_id: str) -> bool:
        """Detach a payment method from its customer."""
        try:
            PaymentMethod.detach(payment_method_id)
            return True
        except stripe.StripeError as e:
            logger.error(f"Stripe error detaching payment method: {e}")
            raise StripeError(str(e), getattr(e, "code", None))

    async def list_payment_methods(self, customer_id: str) -> list[PaymentMethodResult]:
        """List payment methods for a customer."""
        try:
            methods = PaymentMethod.list(customer=customer_id, type="card")
            return [self._payment_method_to_result(pm) for pm in methods.data]
        except stripe.StripeError as e:
            logger.error(f"Stripe error listing payment methods: {e}")
            raise StripeError(str(e), getattr(e, "code", None))

    async def set_default_payment_method(self, customer_id: str, payment_method_id: str) -> bool:
        """Set a payment method as the default for a customer."""
        try:
            Customer.modify(
                customer_id,
                invoice_settings={"default_payment_method": payment_method_id},
            )
            return True
        except stripe.StripeError as e:
            logger.error(f"Stripe error setting default payment method: {e}")
            raise StripeError(str(e), getattr(e, "code", None))

    async def get_default_payment_method(self, customer_id: str) -> str | None:
        """Get the default payment method ID for a customer."""
        try:
            customer = Customer.retrieve(customer_id)
            invoice_settings = customer.get("invoice_settings", {})
            default_pm = invoice_settings.get("default_payment_method")
            if default_pm is None:
                return None
            # default_payment_method can be a string or an expanded PaymentMethod object
            if isinstance(default_pm, str):
                return default_pm
            # If expanded, extract the id
            return str(default_pm.get("id", "")) if hasattr(default_pm, "get") else str(default_pm)
        except stripe.StripeError as e:
            logger.error(f"Stripe error getting default payment method: {e}")
            raise StripeError(str(e), getattr(e, "code", None))

    def _payment_method_to_result(self, pm: PaymentMethod) -> PaymentMethodResult:
        """Convert Stripe PaymentMethod to result dataclass."""
        card = pm.get("card", {})
        return PaymentMethodResult(
            id=pm.id,
            type=pm.type or "card",
            card_brand=card.get("brand") if card else None,
            card_last4=card.get("last4") if card else None,
            card_exp_month=card.get("exp_month") if card else None,
            card_exp_year=card.get("exp_year") if card else None,
        )

    # ===================
    # Subscriptions
    # ===================

    async def create_subscription(
        self,
        customer_id: str,
        price_id: str,
        payment_method_id: str,
        trial_days: int = 0,
    ) -> SubscriptionResult:
        """Create a subscription for a customer."""
        try:
            params: dict[str, Any] = {
                "customer": customer_id,
                "items": [{"price": price_id}],
                "default_payment_method": payment_method_id,
                "payment_behavior": "default_incomplete",
                "expand": ["latest_invoice.payment_intent"],
            }

            if trial_days > 0:
                params["trial_period_days"] = trial_days

            subscription = Subscription.create(**params)  # pyright: ignore[reportUnknownArgumentType]
            return self._subscription_to_result(subscription)
        except stripe.StripeError as e:
            logger.error(f"Stripe error creating subscription: {e}")
            raise StripeError(str(e), getattr(e, "code", None))

    async def update_subscription(
        self,
        subscription_id: str,
        price_id: str,
        proration_behavior: Literal[
            "always_invoice", "create_prorations", "none"
        ] = "create_prorations",
    ) -> SubscriptionResult:
        """Update a subscription to a new price (plan change)."""
        try:
            # Get current subscription to find the item ID
            subscription = Subscription.retrieve(subscription_id)
            item_id = subscription["items"]["data"][0]["id"]

            # Update subscription
            updated = Subscription.modify(
                subscription_id,
                items=[{"id": item_id, "price": price_id}],
                proration_behavior=proration_behavior,
            )
            return self._subscription_to_result(updated)
        except stripe.StripeError as e:
            logger.error(f"Stripe error updating subscription: {e}")
            raise StripeError(str(e), getattr(e, "code", None))

    async def cancel_subscription(self, subscription_id: str, at_period_end: bool = True) -> bool:
        """Cancel a subscription."""
        try:
            if at_period_end:
                Subscription.modify(subscription_id, cancel_at_period_end=True)
            else:
                Subscription.cancel(subscription_id)
            return True
        except stripe.StripeError as e:
            logger.error(f"Stripe error canceling subscription: {e}")
            raise StripeError(str(e), getattr(e, "code", None))

    async def reactivate_subscription(self, subscription_id: str) -> SubscriptionResult:
        """Reactivate a subscription that was set to cancel at period end."""
        try:
            subscription = Subscription.modify(
                subscription_id,
                cancel_at_period_end=False,
            )
            return self._subscription_to_result(subscription)
        except stripe.StripeError as e:
            logger.error(f"Stripe error reactivating subscription: {e}")
            raise StripeError(str(e), getattr(e, "code", None))

    async def get_subscription(self, subscription_id: str) -> SubscriptionResult | None:
        """Get a subscription by ID."""
        try:
            subscription = Subscription.retrieve(subscription_id)
            return self._subscription_to_result(subscription)
        except stripe.InvalidRequestError:
            return None
        except stripe.StripeError as e:
            logger.error(f"Stripe error getting subscription: {e}")
            raise StripeError(str(e), getattr(e, "code", None))

    def _subscription_to_result(self, sub: Subscription) -> SubscriptionResult:
        """Convert Stripe Subscription to result dataclass."""
        # Access subscription fields via dict-like access for proper typing
        current_period_start = sub.get("current_period_start")
        current_period_end = sub.get("current_period_end")
        return SubscriptionResult(
            id=sub.id,
            status=sub.status,
            current_period_start=self._timestamp_to_datetime(current_period_start)
            or datetime.now(UTC),
            current_period_end=self._timestamp_to_datetime(current_period_end) or datetime.now(UTC),
            cancel_at_period_end=sub.cancel_at_period_end,
            trial_start=self._timestamp_to_datetime(sub.trial_start),
            trial_end=self._timestamp_to_datetime(sub.trial_end),
        )

    # ===================
    # Invoices
    # ===================

    async def list_invoices(self, customer_id: str, limit: int = 10) -> list[InvoiceResult]:
        """List invoices for a customer."""
        try:
            invoices = Invoice.list(customer=customer_id, limit=limit)
            return [self._invoice_to_result(inv) for inv in invoices.data]
        except stripe.StripeError as e:
            logger.error(f"Stripe error listing invoices: {e}")
            raise StripeError(str(e), getattr(e, "code", None))

    def _invoice_to_result(self, inv: Invoice) -> InvoiceResult:
        """Convert Stripe Invoice to result dataclass."""
        return InvoiceResult(
            id=inv.id,
            amount_due=inv.amount_due or 0,
            amount_paid=inv.amount_paid or 0,
            currency=inv.currency or "usd",
            status=inv.status or "unknown",
            period_start=self._timestamp_to_datetime(inv.period_start) or datetime.now(UTC),
            period_end=self._timestamp_to_datetime(inv.period_end) or datetime.now(UTC),
            paid_at=self._timestamp_to_datetime(inv.status_transitions.paid_at)
            if inv.status_transitions
            else None,
            invoice_pdf=inv.invoice_pdf,
            hosted_invoice_url=inv.hosted_invoice_url,
        )

    # ===================
    # Webhooks
    # ===================

    def verify_webhook_signature(
        self, payload: bytes, sig_header: str, webhook_secret: str
    ) -> Event:
        """Verify webhook signature and return the event."""
        try:
            # stripe.Webhook.construct_event is not fully typed in stripe-python
            # pyright: ignore[reportUnknownMemberType] - stripe library has incomplete type stubs
            event: Event = stripe.Webhook.construct_event(  # pyright: ignore[reportUnknownMemberType]
                payload, sig_header, webhook_secret
            )
            return event
        except stripe.SignatureVerificationError as e:
            logger.error(f"Webhook signature verification failed: {e}")
            raise StripeError("Invalid webhook signature", "signature_verification_error")
        except ValueError as e:
            logger.error(f"Invalid webhook payload: {e}")
            raise StripeError("Invalid webhook payload", "invalid_payload")


# Singleton instance
_stripe_client: StripeClient | None = None


def get_stripe_client() -> StripeClient:
    """Get or create the Stripe client singleton."""
    global _stripe_client
    if _stripe_client is None:
        _stripe_client = StripeClient()
    return _stripe_client
