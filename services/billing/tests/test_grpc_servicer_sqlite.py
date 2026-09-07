"""Subscription-lifecycle and payment-method RPCs over real SQL on SQLite.

These drive the servicer end to end (tenant_session, service layer, proto
mappers) against a real schema, so a dropped predicate or a broken write
fails instead of being mirrored by a mock. Cross-tenant denial on the same
plumbing lives in test_tenant_isolation.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from llamatrade_db.models import PaymentMethod, Plan, Subscription
from llamatrade_proto.generated import billing_pb2, common_pb2
from tests.conftest import (
    MockStripeClient,
    seed_payment_method,
    seed_plan,
    seed_subscription,
)

from src.grpc.servicer import BillingServicer
from src.stripe.client import StripeError

pytestmark = pytest.mark.asyncio

TENANT = UUID("11111111-1111-1111-1111-111111111111")
USER = UUID("33333333-3333-3333-3333-333333333333")


def _wire() -> common_pb2.TenantContext:
    return common_pb2.TenantContext(tenant_id=str(TENANT), user_id=str(USER))


@pytest.fixture
def stripe() -> Iterator[MockStripeClient]:
    """The canonical Stripe double, injected at the servicer's factory seam."""
    client = MockStripeClient()
    with patch("src.grpc.servicer.get_stripe_client", return_value=client):
        yield client


# === ResumeSubscription ===


async def test_resume_subscription_clears_pending_cancellation(
    sqlite_servicer: BillingServicer,
    sqlite_sessions: sessionmaker[Session],
    stripe: MockStripeClient,
) -> None:
    with sqlite_sessions() as session:
        plan = seed_plan(session)
        seed_subscription(
            session,
            tenant_id=TENANT,
            plan=plan,
            cancel_at_period_end=True,
            stripe_subscription_id="sub_pending_1",
        )

    response = await sqlite_servicer.resume_subscription(
        billing_pb2.ResumeSubscriptionRequest(context=_wire()), MagicMock()
    )

    assert response.subscription.cancel_at_period_end is False
    assert response.subscription.status == billing_pb2.SUBSCRIPTION_STATUS_ACTIVE
    assert response.subscription.plan_id == "starter"
    assert stripe.reactivated == ["sub_pending_1"]
    with sqlite_sessions() as session:
        row = session.scalars(select(Subscription)).one()
        assert row.cancel_at_period_end is False


async def test_resume_without_pending_cancellation_is_rejected(
    sqlite_servicer: BillingServicer,
    sqlite_sessions: sessionmaker[Session],
    stripe: MockStripeClient,
) -> None:
    with sqlite_sessions() as session:
        plan = seed_plan(session)
        seed_subscription(session, tenant_id=TENANT, plan=plan)

    with pytest.raises(ConnectError) as exc_info:
        await sqlite_servicer.resume_subscription(
            billing_pb2.ResumeSubscriptionRequest(context=_wire()), MagicMock()
        )

    assert exc_info.value.code == Code.INVALID_ARGUMENT
    assert stripe.reactivated == []


# === AddPaymentMethod ===


async def test_add_payment_method_first_card_becomes_default(
    sqlite_servicer: BillingServicer,
    sqlite_sessions: sessionmaker[Session],
    stripe: MockStripeClient,
) -> None:
    response = await sqlite_servicer.add_payment_method(
        billing_pb2.AddPaymentMethodRequest(context=_wire(), setup_intent_id="pm_new_1"),
        MagicMock(),
    )

    pm = response.payment_method
    assert pm.is_default is True
    assert pm.card_brand == "visa"
    assert pm.card_last4 == "4242"
    with sqlite_sessions() as session:
        row = session.scalars(select(PaymentMethod)).one()
        assert row.tenant_id == TENANT
        assert row.stripe_payment_method_id == "pm_new_1"
        assert row.is_default is True
    # The first card is also promoted to the Stripe-side default.
    assert list(stripe.default_payment_methods.values()) == ["pm_new_1"]


async def test_add_payment_method_second_card_is_not_default(
    sqlite_servicer: BillingServicer,
    sqlite_sessions: sessionmaker[Session],
    stripe: MockStripeClient,
) -> None:
    with sqlite_sessions() as session:
        seed_payment_method(
            session, tenant_id=TENANT, stripe_payment_method_id="pm_first", is_default=True
        )

    response = await sqlite_servicer.add_payment_method(
        billing_pb2.AddPaymentMethodRequest(context=_wire(), setup_intent_id="pm_second"),
        MagicMock(),
    )

    assert response.payment_method.is_default is False
    assert stripe.default_payment_methods == {}
    with sqlite_sessions() as session:
        rows = session.scalars(select(PaymentMethod)).all()
        assert {r.stripe_payment_method_id: r.is_default for r in rows} == {
            "pm_first": True,
            "pm_second": False,
        }


# === RemovePaymentMethod ===


async def test_remove_payment_method_deletes_row(
    sqlite_servicer: BillingServicer,
    sqlite_sessions: sessionmaker[Session],
    stripe: MockStripeClient,
) -> None:
    with sqlite_sessions() as session:
        seed_payment_method(
            session, tenant_id=TENANT, stripe_payment_method_id="pm_default", is_default=True
        )
        extra = seed_payment_method(session, tenant_id=TENANT, stripe_payment_method_id="pm_extra")

    response = await sqlite_servicer.remove_payment_method(
        billing_pb2.RemovePaymentMethodRequest(context=_wire(), payment_method_id=str(extra.id)),
        MagicMock(),
    )

    assert response.success is True
    assert stripe.detached == ["pm_extra"]
    with sqlite_sessions() as session:
        remaining = session.scalars(select(PaymentMethod)).all()
        assert [pm.stripe_payment_method_id for pm in remaining] == ["pm_default"]


async def test_remove_default_promotes_remaining_card(
    sqlite_servicer: BillingServicer,
    sqlite_sessions: sessionmaker[Session],
    stripe: MockStripeClient,
) -> None:
    old = datetime(2026, 1, 1, tzinfo=UTC)
    with sqlite_sessions() as session:
        default = seed_payment_method(
            session,
            tenant_id=TENANT,
            stripe_payment_method_id="pm_default",
            is_default=True,
            created_at=old,
        )
        seed_payment_method(
            session,
            tenant_id=TENANT,
            stripe_payment_method_id="pm_survivor",
            created_at=old + timedelta(days=1),
        )

    response = await sqlite_servicer.remove_payment_method(
        billing_pb2.RemovePaymentMethodRequest(context=_wire(), payment_method_id=str(default.id)),
        MagicMock(),
    )

    assert response.success is True
    with sqlite_sessions() as session:
        row = session.scalars(select(PaymentMethod)).one()
        assert row.stripe_payment_method_id == "pm_survivor"
        assert row.is_default is True
    assert stripe.default_payment_methods == {"cus_seeded_1": "pm_survivor"}


async def test_remove_only_default_with_active_subscription_is_rejected(
    sqlite_servicer: BillingServicer,
    sqlite_sessions: sessionmaker[Session],
    stripe: MockStripeClient,
) -> None:
    with sqlite_sessions() as session:
        plan = seed_plan(session)
        seed_subscription(session, tenant_id=TENANT, plan=plan)
        only = seed_payment_method(
            session, tenant_id=TENANT, stripe_payment_method_id="pm_only", is_default=True
        )

    with pytest.raises(ConnectError) as exc_info:
        await sqlite_servicer.remove_payment_method(
            billing_pb2.RemovePaymentMethodRequest(context=_wire(), payment_method_id=str(only.id)),
            MagicMock(),
        )

    assert exc_info.value.code == Code.INVALID_ARGUMENT
    assert "only payment method" in str(exc_info.value)
    assert stripe.detached == []
    with sqlite_sessions() as session:
        assert session.scalars(select(PaymentMethod)).one().stripe_payment_method_id == "pm_only"


async def test_remove_unknown_payment_method_is_not_found(
    sqlite_servicer: BillingServicer, stripe: MockStripeClient
) -> None:
    with pytest.raises(ConnectError) as exc_info:
        await sqlite_servicer.remove_payment_method(
            billing_pb2.RemovePaymentMethodRequest(context=_wire(), payment_method_id=str(uuid4())),
            MagicMock(),
        )

    assert exc_info.value.code == Code.NOT_FOUND


async def test_remove_malformed_payment_method_id_is_invalid(
    sqlite_servicer: BillingServicer, stripe: MockStripeClient
) -> None:
    with pytest.raises(ConnectError) as exc_info:
        await sqlite_servicer.remove_payment_method(
            billing_pb2.RemovePaymentMethodRequest(context=_wire(), payment_method_id="not-a-uuid"),
            MagicMock(),
        )

    assert exc_info.value.code == Code.INVALID_ARGUMENT


# === ListPaymentMethods ===


async def test_list_payment_methods_orders_default_first(
    sqlite_servicer: BillingServicer,
    sqlite_sessions: sessionmaker[Session],
    stripe: MockStripeClient,
) -> None:
    old = datetime(2026, 1, 1, tzinfo=UTC)
    with sqlite_sessions() as session:
        seed_payment_method(
            session,
            tenant_id=TENANT,
            stripe_payment_method_id="pm_newer",
            card_last4="1111",
            created_at=old + timedelta(days=1),
        )
        seed_payment_method(
            session,
            tenant_id=TENANT,
            stripe_payment_method_id="pm_default",
            card_last4="2222",
            is_default=True,
            created_at=old,
        )

    response = await sqlite_servicer.list_payment_methods(
        billing_pb2.ListPaymentMethodsRequest(context=_wire()), MagicMock()
    )

    assert [pm.card_last4 for pm in response.payment_methods] == ["2222", "1111"]
    assert response.payment_methods[0].is_default is True


# === CreateSubscription (free tier) ===


async def test_create_free_subscription_without_stripe(
    sqlite_servicer: BillingServicer,
    sqlite_sessions: sessionmaker[Session],
    stripe: MockStripeClient,
) -> None:
    response = await sqlite_servicer.create_subscription(
        billing_pb2.CreateSubscriptionRequest(
            context=_wire(),
            plan_id="free",
            interval=billing_pb2.BILLING_INTERVAL_MONTHLY,
        ),
        MagicMock(),
    )

    sub = response.subscription
    assert sub.status == billing_pb2.SUBSCRIPTION_STATUS_ACTIVE
    assert sub.plan.tier == billing_pb2.PLAN_TIER_FREE
    assert sub.stripe_subscription_id == ""
    with sqlite_sessions() as session:
        row = session.scalars(select(Subscription)).one()
        assert row.tenant_id == TENANT
        assert row.stripe_subscription_id is None
    # The free tier never touches Stripe.
    assert stripe.subscriptions == {}
    assert stripe.customers == {}


async def test_create_paid_subscription_persists_stripe_identifiers(
    sqlite_servicer: BillingServicer,
    sqlite_sessions: sessionmaker[Session],
    stripe: MockStripeClient,
) -> None:
    with sqlite_sessions() as session:
        seed_plan(session, name="starter")
        session.commit()

    response = await sqlite_servicer.create_subscription(
        billing_pb2.CreateSubscriptionRequest(
            context=_wire(),
            plan_id="starter",
            interval=billing_pb2.BILLING_INTERVAL_MONTHLY,
            payment_method_id="pm_card_1",
        ),
        MagicMock(),
    )

    sub = response.subscription
    assert sub.status == billing_pb2.SUBSCRIPTION_STATUS_TRIALING
    assert sub.is_trial is True
    assert sub.stripe_subscription_id == "sub_test_0"
    with sqlite_sessions() as session:
        row = session.scalars(select(Subscription)).one()
        assert row.tenant_id == TENANT
        assert row.stripe_customer_id == "cus_test_0"
        assert row.status == billing_pb2.SUBSCRIPTION_STATUS_TRIALING
    # The Stripe double received the plan's monthly price and trial window.
    assert stripe.subscriptions["sub_test_0"]["price_id"] == "price_monthly_test"


# === UpdateSubscription ===


async def test_update_subscription_changes_plan(
    sqlite_servicer: BillingServicer,
    sqlite_sessions: sessionmaker[Session],
    stripe: MockStripeClient,
) -> None:
    with sqlite_sessions() as session:
        starter = seed_plan(session, name="starter")
        seed_plan(session, name="pro", stripe_price_id_monthly="price_pro_monthly")
        seed_subscription(
            session, tenant_id=TENANT, plan=starter, stripe_subscription_id="sub_live_1"
        )

    response = await sqlite_servicer.update_subscription(
        billing_pb2.UpdateSubscriptionRequest(context=_wire(), plan_id="pro"), MagicMock()
    )

    assert response.subscription.plan_id == "pro"
    assert stripe.update_calls == [("sub_live_1", "price_pro_monthly")]
    with sqlite_sessions() as session:
        row = session.scalars(select(Subscription)).one()
        assert session.scalar(select(Plan.name).where(Plan.id == row.plan_id)) == "pro"


# === CancelSubscription ===


async def test_cancel_subscription_at_period_end(
    sqlite_servicer: BillingServicer,
    sqlite_sessions: sessionmaker[Session],
    stripe: MockStripeClient,
) -> None:
    with sqlite_sessions() as session:
        plan = seed_plan(session)
        seed_subscription(session, tenant_id=TENANT, plan=plan, stripe_subscription_id="sub_live_2")

    response = await sqlite_servicer.cancel_subscription(
        billing_pb2.CancelSubscriptionRequest(context=_wire(), cancel_immediately=False),
        MagicMock(),
    )

    assert response.subscription.cancel_at_period_end is True
    assert response.subscription.status == billing_pb2.SUBSCRIPTION_STATUS_ACTIVE
    assert stripe.cancel_calls == [("sub_live_2", True)]
    with sqlite_sessions() as session:
        assert session.scalars(select(Subscription)).one().cancel_at_period_end is True


async def test_cancel_subscription_immediately_marks_canceled(
    sqlite_servicer: BillingServicer,
    sqlite_sessions: sessionmaker[Session],
    stripe: MockStripeClient,
) -> None:
    with sqlite_sessions() as session:
        plan = seed_plan(session)
        seed_subscription(session, tenant_id=TENANT, plan=plan, stripe_subscription_id="sub_live_3")

    response = await sqlite_servicer.cancel_subscription(
        billing_pb2.CancelSubscriptionRequest(context=_wire(), cancel_immediately=True),
        MagicMock(),
    )

    assert response.subscription.status == billing_pb2.SUBSCRIPTION_STATUS_CANCELED
    assert response.subscription.HasField("canceled_at")
    assert stripe.cancel_calls == [("sub_live_3", False)]


# === RemovePaymentMethod: Stripe-failure tolerance ===


class _DetachDownStripe(MockStripeClient):
    """Stripe double whose detach fails; the local row must still be deleted."""

    async def detach_payment_method(self, payment_method_id: str) -> bool:
        raise StripeError("stripe down", "api_error")


class _PromoteDownStripe(MockStripeClient):
    """Stripe double whose set-default fails; local promotion must still land."""

    async def set_default_payment_method(self, customer_id: str, payment_method_id: str) -> bool:
        raise StripeError("stripe down", "api_error")


async def test_remove_payment_method_survives_stripe_detach_failure(
    sqlite_servicer: BillingServicer,
    sqlite_sessions: sessionmaker[Session],
) -> None:
    with sqlite_sessions() as session:
        seed_payment_method(
            session, tenant_id=TENANT, stripe_payment_method_id="pm_default", is_default=True
        )
        extra = seed_payment_method(session, tenant_id=TENANT, stripe_payment_method_id="pm_extra")

    with patch("src.grpc.servicer.get_stripe_client", return_value=_DetachDownStripe()):
        response = await sqlite_servicer.remove_payment_method(
            billing_pb2.RemovePaymentMethodRequest(
                context=_wire(), payment_method_id=str(extra.id)
            ),
            MagicMock(),
        )

    assert response.success is True
    with sqlite_sessions() as session:
        remaining = session.scalars(select(PaymentMethod)).all()
        assert [pm.stripe_payment_method_id for pm in remaining] == ["pm_default"]


async def test_remove_default_promotes_locally_when_stripe_promotion_fails(
    sqlite_servicer: BillingServicer,
    sqlite_sessions: sessionmaker[Session],
) -> None:
    old = datetime(2026, 1, 1, tzinfo=UTC)
    with sqlite_sessions() as session:
        default = seed_payment_method(
            session,
            tenant_id=TENANT,
            stripe_payment_method_id="pm_default",
            is_default=True,
            created_at=old,
        )
        seed_payment_method(
            session,
            tenant_id=TENANT,
            stripe_payment_method_id="pm_survivor",
            created_at=old + timedelta(days=1),
        )

    with patch("src.grpc.servicer.get_stripe_client", return_value=_PromoteDownStripe()):
        response = await sqlite_servicer.remove_payment_method(
            billing_pb2.RemovePaymentMethodRequest(
                context=_wire(), payment_method_id=str(default.id)
            ),
            MagicMock(),
        )

    assert response.success is True
    with sqlite_sessions() as session:
        row = session.scalars(select(PaymentMethod)).one()
        assert row.stripe_payment_method_id == "pm_survivor"
        assert row.is_default is True
