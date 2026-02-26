"""Webhooks router - Stripe webhook handling."""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.database import get_db
from src.stripe.client import StripeError, get_stripe_client

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


async def _handle_subscription_created(db: AsyncSession, subscription: dict) -> None:
    """Handle customer.subscription.created event."""
    from datetime import UTC, datetime

    from llamatrade_db.models import Subscription
    from sqlalchemy import select

    stripe_sub_id = subscription.get("id")
    sub_status = subscription.get("status")

    logger.info(f"Subscription created: {stripe_sub_id}, status: {sub_status}")

    # Find subscription in our database
    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
    )
    local_sub = result.scalar_one_or_none()

    if local_sub:
        # Update status
        local_sub.status = sub_status
        local_sub.current_period_start = datetime.fromtimestamp(
            subscription.get("current_period_start", 0), tz=UTC
        )
        local_sub.current_period_end = datetime.fromtimestamp(
            subscription.get("current_period_end", 0), tz=UTC
        )
        if subscription.get("trial_start"):
            local_sub.trial_start = datetime.fromtimestamp(subscription["trial_start"], tz=UTC)
        if subscription.get("trial_end"):
            local_sub.trial_end = datetime.fromtimestamp(subscription["trial_end"], tz=UTC)
        await db.commit()


async def _handle_subscription_updated(db: AsyncSession, subscription: dict) -> None:
    """Handle customer.subscription.updated event."""
    from datetime import UTC, datetime

    from llamatrade_db.models import Subscription
    from sqlalchemy import select

    stripe_sub_id = subscription.get("id")
    sub_status = subscription.get("status")
    cancel_at_period_end = subscription.get("cancel_at_period_end", False)

    logger.info(f"Subscription updated: {stripe_sub_id}, status: {sub_status}")

    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
    )
    local_sub = result.scalar_one_or_none()

    if local_sub:
        local_sub.status = sub_status
        local_sub.cancel_at_period_end = cancel_at_period_end
        local_sub.current_period_start = datetime.fromtimestamp(
            subscription.get("current_period_start", 0), tz=UTC
        )
        local_sub.current_period_end = datetime.fromtimestamp(
            subscription.get("current_period_end", 0), tz=UTC
        )
        if subscription.get("canceled_at"):
            local_sub.canceled_at = datetime.fromtimestamp(subscription["canceled_at"], tz=UTC)
        await db.commit()


async def _handle_subscription_deleted(db: AsyncSession, subscription: dict) -> None:
    """Handle customer.subscription.deleted event."""
    from datetime import UTC, datetime

    from llamatrade_db.models import Subscription
    from sqlalchemy import select

    stripe_sub_id = subscription.get("id")

    logger.info(f"Subscription deleted: {stripe_sub_id}")

    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
    )
    local_sub = result.scalar_one_or_none()

    if local_sub:
        local_sub.status = "cancelled"
        local_sub.canceled_at = datetime.now(UTC)
        await db.commit()


async def _handle_invoice_paid(db: AsyncSession, invoice: dict) -> None:
    """Handle invoice.paid event."""
    from datetime import UTC, datetime
    from decimal import Decimal

    from llamatrade_db.models import Invoice, Subscription
    from sqlalchemy import select

    stripe_invoice_id = invoice.get("id")
    stripe_sub_id = invoice.get("subscription")

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

    if existing:
        # Update status
        existing.status = "paid"
        existing.amount_paid = Decimal(str(invoice.get("amount_paid", 0) / 100))
        existing.paid_at = datetime.now(UTC)
    else:
        # Create new invoice record
        new_invoice = Invoice(
            tenant_id=subscription.tenant_id,
            subscription_id=subscription.id,
            stripe_invoice_id=stripe_invoice_id,
            invoice_number=invoice.get("number"),
            status="paid",
            amount_due=Decimal(str(invoice.get("amount_due", 0) / 100)),
            amount_paid=Decimal(str(invoice.get("amount_paid", 0) / 100)),
            currency=invoice.get("currency", "usd"),
            period_start=datetime.fromtimestamp(invoice.get("period_start", 0), tz=UTC),
            period_end=datetime.fromtimestamp(invoice.get("period_end", 0), tz=UTC),
            paid_at=datetime.now(UTC),
            hosted_invoice_url=invoice.get("hosted_invoice_url"),
            invoice_pdf=invoice.get("invoice_pdf"),
        )
        db.add(new_invoice)

    await db.commit()


async def _handle_payment_failed(db: AsyncSession, invoice: dict) -> None:
    """Handle invoice.payment_failed event."""
    from llamatrade_db.models import Subscription
    from sqlalchemy import select

    stripe_sub_id = invoice.get("subscription")

    logger.warning(f"Payment failed for subscription: {stripe_sub_id}")

    if not stripe_sub_id:
        return

    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
    )
    subscription = result.scalar_one_or_none()

    if subscription:
        subscription.status = "past_due"
        await db.commit()


async def _handle_payment_method_attached(db: AsyncSession, payment_method: dict) -> None:
    """Handle payment_method.attached event."""
    from llamatrade_db.models import PaymentMethod, Subscription
    from sqlalchemy import select

    stripe_pm_id = payment_method.get("id")
    customer_id = payment_method.get("customer")
    pm_type = payment_method.get("type", "card")
    card = payment_method.get("card", {})

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

    new_pm = PaymentMethod(
        tenant_id=tenant_id,
        stripe_payment_method_id=stripe_pm_id,
        stripe_customer_id=customer_id,
        type=pm_type,
        card_brand=card.get("brand"),
        card_last4=card.get("last4"),
        card_exp_month=card.get("exp_month"),
        card_exp_year=card.get("exp_year"),
        is_default=is_default,
    )

    db.add(new_pm)
    await db.commit()


async def _handle_payment_method_detached(db: AsyncSession, payment_method: dict) -> None:
    """Handle payment_method.detached event."""
    from llamatrade_db.models import PaymentMethod
    from sqlalchemy import delete

    stripe_pm_id = payment_method.get("id")

    logger.info(f"Payment method detached: {stripe_pm_id}")

    await db.execute(
        delete(PaymentMethod).where(PaymentMethod.stripe_payment_method_id == stripe_pm_id)
    )
    await db.commit()
