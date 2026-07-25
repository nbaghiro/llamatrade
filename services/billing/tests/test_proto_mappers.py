"""Golden round-trip tests for the DB-row -> proto billing mappers (1A).

Validates the canonical mappers in isolation: DB row in, proto out, with
(1) money precision preserved through Decimal->Money strings (no float hop, 5A),
(2) proto field names / value semantics correct (7A) — DB ``billing_cycle`` ->
proto ``interval``, DB ``amount_due`` -> proto ``amount``, plan slug -> proto id —
and (3) no proto sub-message (Money / Timestamp / Plan) field left unset outside an
explicit allowlist.

Allowlist note: every proto message-typed field on Plan/Subscription/PaymentMethod/
Invoice maps to a DB column, so the completeness allowlists below are all empty. The
only proto fields without a DB source are scalars that fall back to their proto3
defaults and are therefore outside this message-field invariant:
Subscription.cancellation_reason (""), Plan.data_retention_days (fixed 90), and
InvoiceItem.quantity / unit_price (line-item JSONB carries only description+amount).
Nullable message fields (trial_end, canceled_at, due_date, paid_at) get their own
unset-when-None tests.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from google.protobuf.message import Message

from llamatrade_db.models import Invoice, PaymentMethod, Plan, Subscription
from llamatrade_proto.generated import billing_pb2

from src.proto_mappers import (
    invoice_to_proto,
    payment_method_to_proto,
    plan_to_proto,
    subscription_to_proto,
)

_TENANT = UUID("11111111-1111-1111-1111-111111111111")
_SUB_ID = UUID("22222222-2222-2222-2222-222222222222")
_PLAN_ID = UUID("33333333-3333-3333-3333-333333333333")
_PM_ID = UUID("44444444-4444-4444-4444-444444444444")
_INV_ID = UUID("55555555-5555-5555-5555-555555555555")

_NOW = datetime(2026, 7, 1, tzinfo=UTC)

# All four mappers populate every proto message-typed field the DB exposes.
_PLAN_UNSET_ALLOWLIST: set[str] = set()
_SUBSCRIPTION_UNSET_ALLOWLIST: set[str] = set()
_PAYMENT_METHOD_UNSET_ALLOWLIST: set[str] = set()
_INVOICE_UNSET_ALLOWLIST: set[str] = set()


def _singular_message_fields(message: Message) -> list[str]:
    """Names of non-repeated, message-typed fields (Money/Timestamp/Plan/...) on a proto."""
    return [
        f.name
        for f in message.DESCRIPTOR.fields
        if f.message_type is not None and not f.is_repeated
    ]


def _make_plan(*, yearly: Decimal | None = Decimal("290.00")) -> Plan:
    return Plan(
        id=_PLAN_ID,
        name="pro",
        display_name="Pro",
        description="Everything unlimited",
        tier=billing_pb2.PLAN_TIER_PRO,
        price_monthly=Decimal("29.00"),
        price_yearly=yearly,
        features={"backtests": True, "api_access": True, "priority_support": True, "off": False},
        limits={"backtests_per_month": 50, "live_strategies": 5},
        trial_days=14,
        is_active=True,
        sort_order=2,
    )


def _make_subscription(
    *,
    billing_cycle: int = billing_pb2.BILLING_INTERVAL_MONTHLY,
    trial_end: datetime | None = _NOW + timedelta(days=14),
    canceled_at: datetime | None = _NOW + timedelta(days=1),
) -> Subscription:
    sub = Subscription(
        id=_SUB_ID,
        tenant_id=_TENANT,
        plan_id=_PLAN_ID,
        status=billing_pb2.SUBSCRIPTION_STATUS_ACTIVE,
        billing_cycle=billing_cycle,
        stripe_subscription_id="sub_live_1",
        stripe_customer_id="cus_live_1",
        current_period_start=_NOW,
        current_period_end=_NOW + timedelta(days=30),
        canceled_at=canceled_at,
        cancel_at_period_end=True,
        trial_start=_NOW if trial_end else None,
        trial_end=trial_end,
        created_at=_NOW,
        updated_at=_NOW + timedelta(hours=1),
    )
    sub.plan = _make_plan()
    return sub


def _make_payment_method(*, cardless: bool = False) -> PaymentMethod:
    return PaymentMethod(
        id=_PM_ID,
        tenant_id=_TENANT,
        stripe_payment_method_id="pm_1",
        stripe_customer_id="cus_live_1",
        type="card",
        card_brand=None if cardless else "visa",
        card_last4=None if cardless else "4242",
        card_exp_month=None if cardless else 12,
        card_exp_year=None if cardless else 2030,
        is_default=True,
        created_at=_NOW,
    )


def _make_invoice(*, due_date: datetime | None = _NOW, paid_at: datetime | None = _NOW) -> Invoice:
    return Invoice(
        id=_INV_ID,
        tenant_id=_TENANT,
        subscription_id=_SUB_ID,
        stripe_invoice_id="in_1",
        status=billing_pb2.INVOICE_STATUS_PAID,
        amount_due=Decimal("49.00"),
        amount_paid=Decimal("49.00"),
        currency="usd",
        period_start=_NOW - timedelta(days=30),
        period_end=_NOW,
        due_date=due_date,
        paid_at=paid_at,
        invoice_pdf="https://pdf.example/inv.pdf",
        line_items=[{"description": "Pro plan", "amount": "49.00"}],
    )


# === plan_to_proto ===


def test_plan_precision_and_field_names() -> None:
    proto = plan_to_proto(_make_plan())

    # slug -> id, display_name -> name (7A value semantics).
    assert proto.id == "pro"
    assert proto.name == "Pro"
    assert proto.description == "Everything unlimited"
    assert proto.tier == billing_pb2.PLAN_TIER_PRO

    # 5A: Decimal preserved through the Money string, no float hop.
    assert proto.monthly_price.amount == "29.00"
    assert Decimal(proto.monthly_price.amount) == Decimal("29")
    assert proto.monthly_price.currency == "USD"
    assert Decimal(proto.yearly_price.amount) == Decimal("290")

    assert proto.max_backtests_per_month == 50
    assert proto.max_live_sessions == 5
    assert proto.max_strategies == 5
    assert set(proto.features) == {"backtests", "api_access", "priority_support"}
    assert proto.api_access is True
    assert proto.priority_support is True
    assert proto.data_retention_days == 90


def test_plan_yearly_defaults_to_ten_times_monthly() -> None:
    proto = plan_to_proto(_make_plan(yearly=None))
    assert Decimal(proto.yearly_price.amount) == Decimal("290")  # 29 * 10 (2 months free)


def test_plan_completeness_no_unexpected_default() -> None:
    proto = plan_to_proto(_make_plan())
    for name in _singular_message_fields(proto):
        if name in _PLAN_UNSET_ALLOWLIST:
            assert not proto.HasField(name), f"{name} should be unset"
        else:
            assert proto.HasField(name), f"{name} unexpectedly left at default"


# === subscription_to_proto ===


def test_subscription_precision_and_dropped_fields_populated() -> None:
    proto = subscription_to_proto(_make_subscription())

    assert proto.id == str(_SUB_ID)
    assert proto.tenant_id == str(_TENANT)
    assert proto.plan_id == "pro"  # slug, matching the embedded plan id
    assert proto.plan.id == "pro"
    assert proto.status == billing_pb2.SUBSCRIPTION_STATUS_ACTIVE
    assert (
        proto.interval == billing_pb2.BILLING_INTERVAL_MONTHLY
    )  # DB billing_cycle -> proto interval

    # current_price follows the interval; monthly here.
    assert Decimal(proto.current_price.amount) == Decimal("29")

    # Fields the old Pydantic layer dropped are now populated directly from the row.
    assert proto.stripe_customer_id == "cus_live_1"
    assert proto.canceled_at.seconds == int((_NOW + timedelta(days=1)).timestamp())
    assert proto.updated_at.seconds == int((_NOW + timedelta(hours=1)).timestamp())

    assert proto.is_trial is True
    assert proto.trial_end.seconds == int((_NOW + timedelta(days=14)).timestamp())
    assert proto.cancel_at_period_end is True


def test_subscription_current_price_uses_yearly_for_yearly_interval() -> None:
    proto = subscription_to_proto(
        _make_subscription(billing_cycle=billing_pb2.BILLING_INTERVAL_YEARLY)
    )
    assert proto.interval == billing_pb2.BILLING_INTERVAL_YEARLY
    assert Decimal(proto.current_price.amount) == Decimal("290")


def test_subscription_completeness_no_unexpected_default() -> None:
    proto = subscription_to_proto(_make_subscription())
    for name in _singular_message_fields(proto):
        if name in _SUBSCRIPTION_UNSET_ALLOWLIST:
            assert not proto.HasField(name), f"{name} should be unset"
        else:
            assert proto.HasField(name), f"{name} unexpectedly left at default"


def test_subscription_nullable_timestamps_unset_when_none() -> None:
    proto = subscription_to_proto(_make_subscription(trial_end=None, canceled_at=None))
    assert proto.is_trial is False
    assert not proto.HasField("trial_end")
    assert not proto.HasField("canceled_at")
    # Non-nullable timestamps still populated.
    assert proto.HasField("current_period_start")
    assert proto.HasField("updated_at")


# === payment_method_to_proto ===


def test_payment_method_maps_all_fields_including_created_at() -> None:
    proto = payment_method_to_proto(_make_payment_method())
    assert proto.id == str(_PM_ID)
    assert proto.type == "card"
    assert proto.is_default is True
    assert proto.card_brand == "visa"
    assert proto.card_last4 == "4242"
    assert proto.card_exp_month == 12
    assert proto.card_exp_year == 2030
    assert proto.created_at.seconds == int(_NOW.timestamp())  # previously dropped


def test_payment_method_null_card_fields_become_empty() -> None:
    proto = payment_method_to_proto(_make_payment_method(cardless=True))
    assert proto.card_brand == ""
    assert proto.card_last4 == ""
    assert proto.card_exp_month == 0
    assert proto.card_exp_year == 0


def test_payment_method_completeness_no_unexpected_default() -> None:
    proto = payment_method_to_proto(_make_payment_method())
    for name in _singular_message_fields(proto):
        if name in _PAYMENT_METHOD_UNSET_ALLOWLIST:
            assert not proto.HasField(name), f"{name} should be unset"
        else:
            assert proto.HasField(name), f"{name} unexpectedly left at default"


# === invoice_to_proto ===


def test_invoice_precision_names_and_remaining() -> None:
    proto = invoice_to_proto(_make_invoice())
    assert proto.id == str(_INV_ID)
    assert proto.tenant_id == str(_TENANT)
    assert proto.subscription_id == str(_SUB_ID)
    assert proto.status == billing_pb2.INVOICE_STATUS_PAID  # proto int carried straight through

    # DB amount_due -> proto amount (7A); amounts preserved as Decimal strings.
    assert proto.amount.amount == "49.00"
    assert proto.amount.currency == "USD"
    assert Decimal(proto.amount_paid.amount) == Decimal("49")
    assert Decimal(proto.amount_remaining.amount) == Decimal("0")  # 49 - 49

    assert len(proto.items) == 1
    assert proto.items[0].description == "Pro plan"
    assert proto.items[0].amount.amount == "49.00"


def test_invoice_nullable_timestamps_unset_when_none() -> None:
    proto = invoice_to_proto(_make_invoice(due_date=None, paid_at=None))
    assert not proto.HasField("due_date")
    assert not proto.HasField("paid_at")
    assert proto.HasField("period_start")
    assert proto.HasField("period_end")


def test_invoice_completeness_no_unexpected_default() -> None:
    proto = invoice_to_proto(_make_invoice())
    for name in _singular_message_fields(proto):
        if name in _INVOICE_UNSET_ALLOWLIST:
            assert not proto.HasField(name), f"{name} should be unset"
        else:
            assert proto.HasField(name), f"{name} unexpectedly left at default"
