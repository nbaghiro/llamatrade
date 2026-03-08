"""Webhooks router - Stripe webhook handling."""

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from llamatrade_proto.generated import billing_pb2

from src.services.billing_service import stripe_status_to_proto
from src.services.database import get_db
from src.stripe.client import StripeError, get_stripe_client

# Invoice status constants (DB-only, no proto)
INVOICE_STATUS_DRAFT = 1
INVOICE_STATUS_OPEN = 2
INVOICE_STATUS_PAID = 3
INVOICE_STATUS_VOID = 4
INVOICE_STATUS_UNCOLLECTIBLE = 5

router = APIRouter()
logger = logging.getLogger(__name__)

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")


@router.post("/stripe")
async def handle_stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Handle Stripe webhook events."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing stripe-signature header",
        )

    if not STRIPE_WEBHOOK_SECRET:
        logger.warning("STRIPE_WEBHOOK_SECRET not configured, skipping signature verification")
        # In development, we might skip verification
        import json

        try:
            event_data = json.loads(payload)
            event_type = event_data.get("type", "")
            event_object = event_data.get("data", {}).get("object", {})
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload",
            )
    else:
        # Verify signature
        stripe_client = get_stripe_client()
        try:
            event = stripe_client.verify_webhook_signature(
                payload=payload,
                sig_header=sig_header,
                webhook_secret=STRIPE_WEBHOOK_SECRET,
            )
            event_type = event.type
            event_object = event.data.object
        except StripeError as e:
            logger.error(f"Webhook signature verification failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid webhook signature",
            )

    # Log the event
    logger.info(f"Processing Stripe webhook: {event_type}")

    # Handle different event types
    try:
        if event_type == "customer.subscription.created":
            await _handle_subscription_created(db, event_object)
        elif event_type == "customer.subscription.updated":
            await _handle_subscription_updated(db, event_object)
        elif event_type == "customer.subscription.deleted":
            await _handle_subscription_deleted(db, event_object)
        elif event_type == "invoice.paid":
            await _handle_invoice_paid(db, event_object)
        elif event_type == "invoice.payment_failed":
            await _handle_payment_failed(db, event_object)
        elif event_type == "payment_method.attached":
            await _handle_payment_method_attached(db, event_object)
        elif event_type == "payment_method.detached":
            await _handle_payment_method_detached(db, event_object)
        else:
            logger.debug(f"Unhandled webhook event type: {event_type}")
    except Exception as e:
        logger.error(f"Error processing webhook {event_type}: {e}")
        # Don't raise - return 200 so Stripe doesn't retry
        # We'll investigate failed events through logs

    return {"received": True}


async def _handle_subscription_created(db: AsyncSession, subscription: dict[str, Any]) -> None:
    """Handle customer.subscription.created event."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    from llamatrade_db.models import Subscription

    stripe_sub_id: str | None = subscription.get("id")
    sub_status: str | None = subscription.get("status")

    logger.info(f"Subscription created: {stripe_sub_id}, status: {sub_status}")

    # Find subscription in our database
    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
    )
    local_sub = result.scalar_one_or_none()

    if local_sub:
        # Update status
        if sub_status is not None:
            local_sub.status = stripe_status_to_proto(sub_status)
        current_period_start: int = subscription.get("current_period_start", 0)
        current_period_end: int = subscription.get("current_period_end", 0)
        local_sub.current_period_start = datetime.fromtimestamp(current_period_start, tz=UTC)
        local_sub.current_period_end = datetime.fromtimestamp(current_period_end, tz=UTC)
        trial_start: int | None = subscription.get("trial_start")
        trial_end: int | None = subscription.get("trial_end")
        if trial_start:
            local_sub.trial_start = datetime.fromtimestamp(trial_start, tz=UTC)
        if trial_end:
            local_sub.trial_end = datetime.fromtimestamp(trial_end, tz=UTC)
        await db.commit()


async def _handle_subscription_updated(db: AsyncSession, subscription: dict[str, Any]) -> None:
    """Handle customer.subscription.updated event."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    from llamatrade_db.models import Subscription

    stripe_sub_id: str | None = subscription.get("id")
    sub_status: str | None = subscription.get("status")
    cancel_at_period_end: bool = subscription.get("cancel_at_period_end", False)

    logger.info(f"Subscription updated: {stripe_sub_id}, status: {sub_status}")

    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
    )
    local_sub = result.scalar_one_or_none()

    if local_sub:
        if sub_status is not None:
            local_sub.status = stripe_status_to_proto(sub_status)
        local_sub.cancel_at_period_end = cancel_at_period_end
        current_period_start: int = subscription.get("current_period_start", 0)
        current_period_end: int = subscription.get("current_period_end", 0)
        local_sub.current_period_start = datetime.fromtimestamp(current_period_start, tz=UTC)
        local_sub.current_period_end = datetime.fromtimestamp(current_period_end, tz=UTC)
        canceled_at: int | None = subscription.get("canceled_at")
        if canceled_at:
            local_sub.canceled_at = datetime.fromtimestamp(canceled_at, tz=UTC)
        await db.commit()


async def _handle_subscription_deleted(db: AsyncSession, subscription: dict[str, Any]) -> None:
    """Handle customer.subscription.deleted event."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    from llamatrade_db.models import Subscription

    stripe_sub_id: str | None = subscription.get("id")

    logger.info(f"Subscription deleted: {stripe_sub_id}")

    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
    )
    local_sub = result.scalar_one_or_none()

    if local_sub:
        local_sub.status = billing_pb2.SUBSCRIPTION_STATUS_CANCELED
        local_sub.canceled_at = datetime.now(UTC)
        await db.commit()


async def _handle_invoice_paid(db: AsyncSession, invoice: dict[str, Any]) -> None:
    """Handle invoice.paid event."""
    from datetime import UTC, datetime
    from decimal import Decimal

    from sqlalchemy import select

    from llamatrade_db.models import Invoice, Subscription

    stripe_invoice_id: str | None = invoice.get("id")
    stripe_sub_id: str | None = invoice.get("subscription")

    logger.info(f"Invoice paid: {stripe_invoice_id}")

    # Find the subscription to get tenant_id
    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        logger.warning(f"No subscription found for invoice {stripe_invoice_id}")
        return

    # Check if invoice already exists
    result = await db.execute(select(Invoice).where(Invoice.stripe_invoice_id == stripe_invoice_id))
    existing = result.scalar_one_or_none()

    amount_paid_cents: int = invoice.get("amount_paid", 0)
    amount_due_cents: int = invoice.get("amount_due", 0)
    period_start: int = invoice.get("period_start", 0)
    period_end: int = invoice.get("period_end", 0)
    invoice_number: str | None = invoice.get("number")
    currency: str = invoice.get("currency", "usd")
    hosted_invoice_url: str | None = invoice.get("hosted_invoice_url")
    invoice_pdf: str | None = invoice.get("invoice_pdf")

    if existing:
        # Update status
        existing.status = INVOICE_STATUS_PAID
        existing.amount_paid = Decimal(str(amount_paid_cents / 100))
        existing.paid_at = datetime.now(UTC)
    else:
        # Create new invoice record
        new_invoice = Invoice(
            tenant_id=subscription.tenant_id,
            subscription_id=subscription.id,
            stripe_invoice_id=stripe_invoice_id,
            invoice_number=invoice_number,
            status=INVOICE_STATUS_PAID,
            amount_due=Decimal(str(amount_due_cents / 100)),
            amount_paid=Decimal(str(amount_paid_cents / 100)),
            currency=currency,
            period_start=datetime.fromtimestamp(period_start, tz=UTC),
            period_end=datetime.fromtimestamp(period_end, tz=UTC),
            paid_at=datetime.now(UTC),
            hosted_invoice_url=hosted_invoice_url,
            invoice_pdf=invoice_pdf,
        )
        db.add(new_invoice)

    await db.commit()


async def _handle_payment_failed(db: AsyncSession, invoice: dict[str, Any]) -> None:
    """Handle invoice.payment_failed event."""
    from sqlalchemy import select

    from llamatrade_db.models import Subscription

    stripe_sub_id: str | None = invoice.get("subscription")

    logger.warning(f"Payment failed for subscription: {stripe_sub_id}")

    if not stripe_sub_id:
        return

    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
    )
    subscription = result.scalar_one_or_none()

    if subscription:
        subscription.status = billing_pb2.SUBSCRIPTION_STATUS_PAST_DUE
        await db.commit()


async def _handle_payment_method_attached(db: AsyncSession, payment_method: dict[str, Any]) -> None:
    """Handle payment_method.attached event."""
    from sqlalchemy import select

    from llamatrade_db.models import PaymentMethod, Subscription

    stripe_pm_id: str | None = payment_method.get("id")
    customer_id: str | None = payment_method.get("customer")
    pm_type: str = payment_method.get("type", "card")
    card: dict[str, Any] = payment_method.get("card", {})

    logger.info(f"Payment method attached: {stripe_pm_id}")

    # Check if already exists
    result = await db.execute(
        select(PaymentMethod).where(PaymentMethod.stripe_payment_method_id == stripe_pm_id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        return  # Already synced

    # Find tenant by customer ID
    result = await db.execute(
        select(Subscription.tenant_id).where(Subscription.stripe_customer_id == customer_id)
    )
    tenant_id = result.scalar_one_or_none()

    if not tenant_id:
        logger.warning(f"No tenant found for customer {customer_id}")
        return

    # Check if this is the first payment method
    result = await db.execute(select(PaymentMethod).where(PaymentMethod.tenant_id == tenant_id))
    existing_methods = result.scalars().all()
    is_default = len(existing_methods) == 0

    card_brand: str | None = card.get("brand")
    card_last4: str | None = card.get("last4")
    card_exp_month: int | None = card.get("exp_month")
    card_exp_year: int | None = card.get("exp_year")

    new_pm = PaymentMethod(
        tenant_id=tenant_id,
        stripe_payment_method_id=stripe_pm_id,
        stripe_customer_id=customer_id,
        type=pm_type,
        card_brand=card_brand,
        card_last4=card_last4,
        card_exp_month=card_exp_month,
        card_exp_year=card_exp_year,
        is_default=is_default,
    )

    db.add(new_pm)
    await db.commit()


async def _handle_payment_method_detached(db: AsyncSession, payment_method: dict[str, Any]) -> None:
    """Handle payment_method.detached event."""
    from sqlalchemy import delete

    from llamatrade_db.models import PaymentMethod

    stripe_pm_id: str | None = payment_method.get("id")

    logger.info(f"Payment method detached: {stripe_pm_id}")

    await db.execute(
        delete(PaymentMethod).where(PaymentMethod.stripe_payment_method_id == stripe_pm_id)
    )
    await db.commit()
