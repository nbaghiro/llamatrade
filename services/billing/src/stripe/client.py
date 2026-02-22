"""Stripe API client wrapper."""

import os
from typing import Any

# In production, install and use stripe library
# import stripe


class StripeClient:
    """Wrapper for Stripe API operations."""

    def __init__(self):
        self.api_key = os.getenv("STRIPE_SECRET_KEY", "")
        # stripe.api_key = self.api_key

    async def create_customer(self, email: str, name: str) -> str:
        """Create a Stripe customer."""
        # customer = stripe.Customer.create(email=email, name=name)
        # return customer.id
        return "cus_placeholder"

    async def create_subscription(
        self,
        customer_id: str,
        price_id: str,
        payment_method_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a subscription."""
        # subscription = stripe.Subscription.create(
        #     customer=customer_id,
        #     items=[{"price": price_id}],
        #     default_payment_method=payment_method_id,
        # )
        # return {"id": subscription.id, "status": subscription.status}
        return {"id": "sub_placeholder", "status": "active"}

    async def cancel_subscription(self, subscription_id: str) -> bool:
        """Cancel a subscription at period end."""
        # stripe.Subscription.modify(subscription_id, cancel_at_period_end=True)
        return True

    async def create_portal_session(self, customer_id: str, return_url: str) -> str:
        """Create a billing portal session."""
        # session = stripe.billing_portal.Session.create(
        #     customer=customer_id,
        #     return_url=return_url,
        # )
        # return session.url
        return "https://billing.stripe.com/session/placeholder"

    async def get_invoices(self, customer_id: str, limit: int = 10) -> list[dict]:
        """Get customer invoices."""
        # invoices = stripe.Invoice.list(customer=customer_id, limit=limit)
        # return [invoice.to_dict() for invoice in invoices.data]
        return []
