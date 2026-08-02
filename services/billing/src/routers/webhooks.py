"""Webhooks router - Stripe webhook handling.

Written against stripe-python 15 (dahlia API): handlers receive **typed**
Stripe resources, materialized from the event payload via ``construct_from``.
Field relocations in the current API that this code relies on:

- Subscription billing periods live on the subscription **items**
  (``items.data[].current_period_*``), not the subscription.
- An invoice's owning subscription lives under
  ``invoice.parent.subscription_details.subscription``.

The webhook endpoint in the Stripe dashboard must be configured on the same
API generation, or payloads will not match these shapes.
"""

from __future__ import annotations

import json
import logging
from collections import OrderedDict
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from stripe import Event, Invoice, PaymentMethod, StripeObject, Subscription

if TYPE_CHECKING:
    from llamatrade_db.models import Subscription as DbSubscription

from llamatrade_common.utils import require_secret
from llamatrade_db import get_db
from llamatrade_events.catalog.notifications import NotificationEvent, shared_notification_events
from llamatrade_proto.generated import billing_pb2, events_pb2
from llamatrade_telemetry import metrics

from src.services.billing_service import stripe_status_to_proto
from src.stripe.client import StripeError, get_stripe_client

# Invoice status constant (DB-only, no proto)
INVOICE_STATUS_PAID = 3

router = APIRouter()
logger = logging.getLogger(__name__)

# Handler failures worth a Stripe retry (infra outages), vs. permanent logic errors.
_TRANSIENT_ERRORS: tuple[type[BaseException], ...] = (
    OperationalError,
    InterfaceError,
    ConnectionError,
    TimeoutError,
)

# Best-effort in-process event dedup; cross-replica duplicates ride the natural
# per-row guards (stripe_invoice_id / stripe_payment_method_id existence checks).
_SEEN_EVENTS_MAX = 4096
_seen_event_ids: OrderedDict[str, None] = OrderedDict()


def _event_seen(event_id: str) -> bool:
    if event_id in _seen_event_ids:
        _seen_event_ids.move_to_end(event_id)
        return True
    return False


def _mark_event_seen(event_id: str) -> None:
    _seen_event_ids[event_id] = None
    _seen_event_ids.move_to_end(event_id)
    while len(_seen_event_ids) > _SEEN_EVENTS_MAX:
        _seen_event_ids.popitem(last=False)


# Stripe event types this service dispatches; everything else is a no-op.
_HANDLED_EVENT_TYPES = frozenset(
    {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "customer.subscription.trial_will_end",
        "invoice.paid",
        "invoice.payment_failed",
        "payment_method.attached",
        "payment_method.detached",
    }
)

# Bounded fallback plan label for revenue metrics when the plan is unknown.
_UNKNOWN_PLAN = "unknown"


def _payload_as[T: StripeObject](resource: type[T], event: Event) -> T:
    """Materialize ``event.data.object`` as its concrete typed resource.

    ``Event.data.object`` is untyped in stripe-python 15; rebuilding it
    through the resource's ``construct_from`` gives real typed attribute
    access (including fields like ``items`` that dict-shadowing would hide).
    """
    return resource.construct_from(event.data.object.to_dict(), stripe.api_key)


def _ts(epoch: int | None) -> datetime | None:
    """Unix timestamp → aware datetime."""
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=UTC)


def _subscription_period(sub: Subscription) -> tuple[datetime | None, datetime | None]:
    """Billing period from the first subscription item."""
    try:
        item = sub.items.data[0]
    except AttributeError, KeyError, IndexError:
        return None, None
    return _ts(item.current_period_start), _ts(item.current_period_end)


def _invoice_subscription_id(invoice: Invoice) -> str | None:
    """The owning subscription id, if this invoice bills a subscription."""
    parent = invoice.parent
    details = parent.subscription_details if parent is not None else None
    if details is None:
        return None
    sub = details.subscription
    return sub if isinstance(sub, str) else sub.id


def _apply_stripe_status(local_sub: DbSubscription, subscription: Subscription) -> None:
    """Set the local status from the Stripe status, unchanged on an unknown value.

    An unrecognized Stripe status leaves the stored status as-is (logged) rather
    than storing UNSPECIFIED or defaulting to a live status.
    """
    new_status = stripe_status_to_proto(subscription.status)
    if new_status is not None:
        local_sub.status = new_status
    else:
        logger.warning(
            "Unknown Stripe subscription status %r for %s; keeping stored status",
            subscription.status,
            subscription.id,
        )


@router.post("/stripe")
async def handle_stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Handle Stripe webhook events."""
    # Fail closed in production/staging: no secret means no verifiable webhooks.
    try:
        webhook_secret = require_secret("STRIPE_WEBHOOK_SECRET", dev_default="")
    except RuntimeError:
        logger.error("STRIPE_WEBHOOK_SECRET is not set; refusing to process webhooks")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook secret not configured",
        )

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing stripe-signature header",
        )

    if not webhook_secret:
        logger.warning("STRIPE_WEBHOOK_SECRET not configured, skipping signature verification")
        # In development, parse the unverified payload into a typed Event so
        # the same dispatch path runs as in production.
        try:
            event = Event.construct_from(json.loads(payload), stripe.api_key)
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
                webhook_secret=webhook_secret,
            )
        except StripeError as e:
            metrics.billing.webhook_signature_failure()
            logger.error(f"Webhook signature verification failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid webhook signature",
            )

    event_type = event.type if hasattr(event, "type") else ""

    logger.info(f"Processing Stripe webhook: {event_type}")

    # Map of handled event types to their dispatch coroutines. Only handled
    # types are counted/timed; unrecognized events are no-ops (Stripe sends
    # many we don't subscribe to).
    handled = event_type in _HANDLED_EVENT_TYPES
    if not handled:
        logger.debug(f"Unhandled webhook event type: {event_type}")
        return {"received": True}

    event_id = str(getattr(event, "id", "") or "")
    if event_id and _event_seen(event_id):
        metrics.billing.webhook_duplicate()
        logger.info(f"Duplicate Stripe webhook {event_id} ({event_type}); skipping")
        return {"received": True}

    metrics.billing.webhook_received(event_type=event_type)

    # Handle different event types
    try:
        with metrics.billing.webhook_handler_duration.time(event_type=event_type):
            if event_type == "customer.subscription.created":
                await _handle_subscription_created(db, _payload_as(Subscription, event))
            elif event_type == "customer.subscription.updated":
                await _handle_subscription_updated(db, _payload_as(Subscription, event))
            elif event_type == "customer.subscription.deleted":
                await _handle_subscription_deleted(db, _payload_as(Subscription, event))
            elif event_type == "customer.subscription.trial_will_end":
                await _handle_trial_will_end(db, _payload_as(Subscription, event))
            elif event_type == "invoice.paid":
                await _handle_invoice_paid(db, _payload_as(Invoice, event))
            elif event_type == "invoice.payment_failed":
                await _handle_payment_failed(db, _payload_as(Invoice, event))
            elif event_type == "payment_method.attached":
                await _handle_payment_method_attached(db, _payload_as(PaymentMethod, event))
            elif event_type == "payment_method.detached":
                await _handle_payment_method_detached(db, _payload_as(PaymentMethod, event))
    except _TRANSIENT_ERRORS as e:
        # 500 so Stripe redelivers; the event is not marked seen.
        logger.error(f"Transient error processing webhook {event_type}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transient error processing webhook",
        )
    except Exception as e:
        # Permanent/logic failure: 200 so Stripe doesn't retry a poison event.
        logger.error(f"Error processing webhook {event_type}: {e}")
    else:
        if event_id:
            _mark_event_seen(event_id)

    return {"received": True}


async def _notify_billing(
    tenant_id: object,
    category: events_pb2.NotificationCategory.ValueType,
    *,
    reason: str = "",
    amount: str = "",
    dedup_parts: tuple[str, ...],
) -> None:
    """Fire-and-forget billing notification; Stripe redelivery collapses on the id."""
    await shared_notification_events().publish_safe(
        NotificationEvent(category=category, reason=reason, amount=amount),
        tenant_id=str(tenant_id),
        dedup_parts=dedup_parts,
    )


async def _handle_subscription_created(db: AsyncSession, subscription: Subscription) -> None:
    """Handle customer.subscription.created event."""
    from sqlalchemy import select

    from llamatrade_db.models import Subscription as DbSubscription

    logger.info(f"Subscription created: {subscription.id}, status: {subscription.status}")

    # Find subscription in our database
    result = await db.execute(
        select(DbSubscription).where(DbSubscription.stripe_subscription_id == subscription.id)
    )
    local_sub = result.scalar_one_or_none()

    if local_sub:
        _apply_stripe_status(local_sub, subscription)
        period_start, period_end = _subscription_period(subscription)
        if period_start is not None:
            local_sub.current_period_start = period_start
        if period_end is not None:
            local_sub.current_period_end = period_end
        trial_start = _ts(subscription.trial_start)
        trial_end = _ts(subscription.trial_end)
        if trial_start is not None:
            local_sub.trial_start = trial_start
        if trial_end is not None:
            local_sub.trial_end = trial_end
        await db.commit()


async def _handle_subscription_updated(db: AsyncSession, subscription: Subscription) -> None:
    """Handle customer.subscription.updated event."""
    from sqlalchemy import select

    from llamatrade_db.models import Subscription as DbSubscription

    logger.info(f"Subscription updated: {subscription.id}, status: {subscription.status}")

    result = await db.execute(
        select(DbSubscription).where(DbSubscription.stripe_subscription_id == subscription.id)
    )
    local_sub = result.scalar_one_or_none()

    if local_sub:
        _apply_stripe_status(local_sub, subscription)
        local_sub.cancel_at_period_end = subscription.cancel_at_period_end
        period_start, period_end = _subscription_period(subscription)
        if period_start is not None:
            local_sub.current_period_start = period_start
        if period_end is not None:
            local_sub.current_period_end = period_end
        canceled_at = _ts(subscription.canceled_at)
        if canceled_at is not None:
            local_sub.canceled_at = canceled_at
        await db.commit()
        reason = (
            "cancels at period end"
            if subscription.cancel_at_period_end
            else f"status: {subscription.status}"
        )
        await _notify_billing(
            local_sub.tenant_id,
            events_pb2.NOTIFICATION_CATEGORY_SUBSCRIPTION_UPDATED,
            reason=reason,
            dedup_parts=(
                str(subscription.id),
                "updated",
                str(subscription.status),
                str(subscription.cancel_at_period_end),
            ),
        )


async def _handle_subscription_deleted(db: AsyncSession, subscription: Subscription) -> None:
    """Handle customer.subscription.deleted event."""
    from sqlalchemy import select

    from llamatrade_db.models import Subscription as DbSubscription

    logger.info(f"Subscription deleted: {subscription.id}")

    result = await db.execute(
        select(DbSubscription).where(DbSubscription.stripe_subscription_id == subscription.id)
    )
    local_sub = result.scalar_one_or_none()

    if local_sub:
        local_sub.status = billing_pb2.SUBSCRIPTION_STATUS_CANCELED
        local_sub.canceled_at = datetime.now(UTC)
        await db.commit()
        await _notify_billing(
            local_sub.tenant_id,
            events_pb2.NOTIFICATION_CATEGORY_SUBSCRIPTION_CANCELED,
            dedup_parts=(str(subscription.id), "deleted"),
        )


async def _handle_invoice_paid(db: AsyncSession, invoice: Invoice) -> None:
    """Handle invoice.paid event."""
    from decimal import Decimal

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from llamatrade_db.models import Invoice as DbInvoice
    from llamatrade_db.models import Subscription as DbSubscription

    stripe_sub_id = _invoice_subscription_id(invoice)

    logger.info(f"Invoice paid: {invoice.id}")

    # Find the subscription to get tenant_id (eager-load plan for revenue metric)
    result = await db.execute(
        select(DbSubscription)
        .options(selectinload(DbSubscription.plan))
        .where(DbSubscription.stripe_subscription_id == stripe_sub_id)
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        logger.warning(f"No subscription found for invoice {invoice.id}")
        return

    plan_name = subscription.plan.name
    metrics.billing.invoice_paid(plan=plan_name)

    # Check if invoice already exists
    result = await db.execute(select(DbInvoice).where(DbInvoice.stripe_invoice_id == invoice.id))
    existing = result.scalar_one_or_none()

    if existing:
        # An invoice we've already recorded is being re-delivered: idempotent replay.
        metrics.billing.webhook_duplicate()
        # Update status
        existing.status = INVOICE_STATUS_PAID
        existing.amount_paid = Decimal(invoice.amount_paid) / 100
        existing.paid_at = datetime.now(UTC)
    else:
        # Create new invoice record
        new_invoice = DbInvoice(
            tenant_id=subscription.tenant_id,
            subscription_id=subscription.id,
            stripe_invoice_id=invoice.id,
            invoice_number=invoice.number,
            status=INVOICE_STATUS_PAID,
            amount_due=Decimal(invoice.amount_due) / 100,
            amount_paid=Decimal(invoice.amount_paid) / 100,
            currency=invoice.currency,
            period_start=_ts(invoice.period_start) or datetime.now(UTC),
            period_end=_ts(invoice.period_end) or datetime.now(UTC),
            paid_at=datetime.now(UTC),
            hosted_invoice_url=invoice.hosted_invoice_url,
            invoice_pdf=invoice.invoice_pdf,
        )
        db.add(new_invoice)

    await db.commit()
    await _notify_billing(
        subscription.tenant_id,
        events_pb2.NOTIFICATION_CATEGORY_PAYMENT_SUCCEEDED,
        reason=f"invoice {invoice.number or invoice.id} ({plan_name})",
        amount=str(Decimal(invoice.amount_paid) / 100),
        dedup_parts=(str(invoice.id), "paid"),
    )


async def _handle_payment_failed(db: AsyncSession, invoice: Invoice) -> None:
    """Handle invoice.payment_failed event."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from llamatrade_db.models import Subscription as DbSubscription

    stripe_sub_id = _invoice_subscription_id(invoice)

    logger.warning(f"Payment failed for subscription: {stripe_sub_id}")

    if not stripe_sub_id:
        metrics.billing.invoice_payment_failed(plan=_UNKNOWN_PLAN)
        return

    result = await db.execute(
        select(DbSubscription)
        .options(selectinload(DbSubscription.plan))
        .where(DbSubscription.stripe_subscription_id == stripe_sub_id)
    )
    subscription = result.scalar_one_or_none()

    plan_name = subscription.plan.name if subscription is not None else _UNKNOWN_PLAN
    metrics.billing.invoice_payment_failed(plan=plan_name)

    if subscription:
        subscription.status = billing_pb2.SUBSCRIPTION_STATUS_PAST_DUE
        await db.commit()
        await _notify_billing(
            subscription.tenant_id,
            events_pb2.NOTIFICATION_CATEGORY_PAYMENT_FAILED,
            reason=f"plan {plan_name}",
            dedup_parts=(str(invoice.id), "failed"),
        )


async def _handle_trial_will_end(db: AsyncSession, subscription: Subscription) -> None:
    """Handle customer.subscription.trial_will_end (fires ~3 days before)."""
    from sqlalchemy import select

    from llamatrade_db.models import Subscription as DbSubscription

    result = await db.execute(
        select(DbSubscription).where(DbSubscription.stripe_subscription_id == subscription.id)
    )
    local_sub = result.scalar_one_or_none()
    if local_sub is None:
        logger.warning(f"No subscription found for trial_will_end: {subscription.id}")
        return
    trial_end = _ts(subscription.trial_end)
    await _notify_billing(
        local_sub.tenant_id,
        events_pb2.NOTIFICATION_CATEGORY_TRIAL_ENDING,
        reason=f"trial ends {trial_end.date().isoformat()}" if trial_end else "trial ending soon",
        dedup_parts=(str(subscription.id), "trial_will_end"),
    )


async def _handle_payment_method_attached(db: AsyncSession, payment_method: PaymentMethod) -> None:
    """Handle payment_method.attached event."""
    from sqlalchemy import select

    from llamatrade_db.models import PaymentMethod as DbPaymentMethod
    from llamatrade_db.models import Subscription as DbSubscription

    customer = payment_method.customer
    customer_id = customer if isinstance(customer, str) or customer is None else customer.id
    card = payment_method.card

    logger.info(f"Payment method attached: {payment_method.id}")

    # Check if already exists
    result = await db.execute(
        select(DbPaymentMethod).where(DbPaymentMethod.stripe_payment_method_id == payment_method.id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Payment method already recorded: re-delivered webhook (idempotent replay).
        metrics.billing.webhook_duplicate()
        return  # Already synced

    # Find tenant by customer ID
    result = await db.execute(
        select(DbSubscription.tenant_id).where(DbSubscription.stripe_customer_id == customer_id)
    )
    tenant_id = result.scalar_one_or_none()

    if not tenant_id:
        logger.warning(f"No tenant found for customer {customer_id}")
        return

    # Check if this is the first payment method
    result = await db.execute(select(DbPaymentMethod).where(DbPaymentMethod.tenant_id == tenant_id))
    existing_methods = result.scalars().all()
    is_default = len(existing_methods) == 0

    new_pm = DbPaymentMethod(
        tenant_id=tenant_id,
        stripe_payment_method_id=payment_method.id,
        stripe_customer_id=customer_id,
        type=payment_method.type,
        card_brand=card.brand if card else None,
        card_last4=card.last4 if card else None,
        card_exp_month=card.exp_month if card else None,
        card_exp_year=card.exp_year if card else None,
        is_default=is_default,
    )

    db.add(new_pm)
    await db.commit()


async def _handle_payment_method_detached(db: AsyncSession, payment_method: PaymentMethod) -> None:
    """Handle payment_method.detached event."""
    from sqlalchemy import delete

    from llamatrade_db.models import PaymentMethod as DbPaymentMethod

    logger.info(f"Payment method detached: {payment_method.id}")

    await db.execute(
        delete(DbPaymentMethod).where(DbPaymentMethod.stripe_payment_method_id == payment_method.id)
    )
    await db.commit()
