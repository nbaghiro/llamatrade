"""Canonical DB-row → proto mappers for billing reads.

Proto is the single source of truth for the read/wire shape (decision 1A): these
functions map the persisted ``Plan``/``Subscription``/``PaymentMethod``/``Invoice``
rows straight to the generated proto messages in one pass, with no intermediate
Pydantic layer. Money is kept as ``Decimal`` end-to-end (5A) — every amount is
emitted as a proto ``Money`` carrying the Decimal's string form, never via float.

Proto field names are authoritative (7A): DB ``billing_cycle`` → proto ``interval``,
DB ``amount_due`` → proto ``amount``, and the plan slug (``Plan.name``) is the
plan identity exposed on the wire (proto ``Plan.id`` / ``Subscription.plan_id``),
matching the slug callers pass back to CreateSubscription.

Enum columns are stored as proto ints via TypeDecorators (see
libs/db/.../_enum_types.py), so a row's enum field is already the proto int and is
assigned straight through — no string conversion on read.
"""

from datetime import datetime
from decimal import Decimal
from typing import cast

from llamatrade_db.models import Invoice, PaymentMethod, Plan, Subscription
from llamatrade_proto.generated import billing_pb2, common_pb2

_USD = "USD"


def _ts(value: datetime) -> common_pb2.Timestamp:
    return common_pb2.Timestamp(seconds=int(value.timestamp()))


def _money(amount: Decimal, currency: str = _USD) -> common_pb2.Money:
    """Proto Money from a Decimal (str form preserves scale; never via float)."""
    return common_pb2.Money(currency=currency, amount=str(amount))


def _effective_yearly_price(plan: Plan) -> Decimal:
    """Yearly price, defaulting to 10x monthly (2 months free) when the column is unset."""
    return plan.price_yearly if plan.price_yearly is not None else plan.price_monthly * 10


def _limit(limits: dict[str, object], key: str) -> int:
    """Integer plan limit; a missing/None (``unlimited``) value maps to 0, as the proto has no sentinel."""
    value = limits.get(key)
    return value if isinstance(value, int) else 0


def _feature(features: dict[str, object], key: str) -> bool:
    return bool(features.get(key, False))


def plan_to_proto(plan: Plan) -> billing_pb2.Plan:
    """Map a persisted (or default catalog) Plan row to a proto Plan.

    ``id`` carries the plan slug (``name``); ``name`` carries the human ``display_name``.
    ``data_retention_days`` has no DB column and is a fixed 90.
    """
    features: dict[str, object] = plan.features or {}
    limits: dict[str, object] = plan.limits or {}
    return billing_pb2.Plan(
        id=plan.name,
        name=plan.display_name,
        tier=plan.tier,
        description=plan.description or "",
        monthly_price=_money(plan.price_monthly),
        yearly_price=_money(_effective_yearly_price(plan)),
        max_strategies=_limit(limits, "live_strategies"),
        max_backtests_per_month=_limit(limits, "backtests_per_month"),
        max_live_sessions=_limit(limits, "live_strategies"),
        data_retention_days=90,
        features=[k for k, v in features.items() if v],
        api_access=_feature(features, "api_access"),
        priority_support=_feature(features, "priority_support"),
    )


def subscription_to_proto(sub: Subscription) -> billing_pb2.Subscription:
    """Map a persisted Subscription row (with its ``plan`` loaded) to a proto Subscription.

    Fully populates fields the old Pydantic layer dropped (``stripe_customer_id``,
    ``canceled_at``, ``updated_at``). ``current_price`` reflects the plan price for the
    subscription's billing interval. ``cancellation_reason`` has no DB column and is left
    at its scalar default.
    """
    plan = sub.plan
    current_price = (
        plan.price_monthly
        if sub.billing_cycle == billing_pb2.BILLING_INTERVAL_MONTHLY
        else _effective_yearly_price(plan)
    )
    proto = billing_pb2.Subscription(
        id=str(sub.id),
        tenant_id=str(sub.tenant_id),
        plan_id=plan.name,
        plan=plan_to_proto(plan),
        status=sub.status,
        interval=sub.billing_cycle,
        current_price=_money(current_price),
        current_period_start=_ts(sub.current_period_start),
        current_period_end=_ts(sub.current_period_end),
        is_trial=sub.trial_end is not None,
        cancel_at_period_end=sub.cancel_at_period_end,
        stripe_subscription_id=sub.stripe_subscription_id or "",
        stripe_customer_id=sub.stripe_customer_id or "",
        created_at=_ts(sub.created_at),
        updated_at=_ts(sub.updated_at),
    )
    if sub.trial_end is not None:
        proto.trial_end.CopyFrom(_ts(sub.trial_end))
    if sub.canceled_at is not None:
        proto.canceled_at.CopyFrom(_ts(sub.canceled_at))
    return proto


def payment_method_to_proto(pm: PaymentMethod) -> billing_pb2.PaymentMethod:
    """Map a persisted PaymentMethod row to a proto PaymentMethod (``created_at`` included)."""
    return billing_pb2.PaymentMethod(
        id=str(pm.id),
        type=pm.type,
        is_default=pm.is_default,
        card_brand=pm.card_brand or "",
        card_last4=pm.card_last4 or "",
        card_exp_month=pm.card_exp_month or 0,
        card_exp_year=pm.card_exp_year or 0,
        created_at=_ts(pm.created_at),
    )


def invoice_to_proto(inv: Invoice) -> billing_pb2.Invoice:
    """Map a persisted Invoice row to a proto Invoice.

    Proto ``amount`` ← DB ``amount_due``; ``amount_remaining`` is the unpaid balance.
    Line-item amounts come from a trusted JSONB blob and carry no ``quantity``/``unit_price``.
    """
    currency = (inv.currency or "usd").upper()
    items = [
        billing_pb2.InvoiceItem(
            description=str(li.get("description", "")),
            amount=common_pb2.Money(currency=currency, amount=str(li.get("amount", "0"))),
        )
        for li in (inv.line_items or [])
    ]
    proto = billing_pb2.Invoice(
        id=str(inv.id),
        tenant_id=str(inv.tenant_id),
        subscription_id=str(inv.subscription_id) if inv.subscription_id else "",
        amount=_money(inv.amount_due, currency),
        amount_paid=_money(inv.amount_paid, currency),
        amount_remaining=_money(inv.amount_due - inv.amount_paid, currency),
        status=cast("billing_pb2.InvoiceStatus.ValueType", inv.status),
        period_start=_ts(inv.period_start),
        period_end=_ts(inv.period_end),
        pdf_url=inv.invoice_pdf or "",
        stripe_invoice_id=inv.stripe_invoice_id,
        items=items,
    )
    if inv.due_date is not None:
        proto.due_date.CopyFrom(_ts(inv.due_date))
    if inv.paid_at is not None:
        proto.paid_at.CopyFrom(_ts(inv.paid_at))
    return proto
