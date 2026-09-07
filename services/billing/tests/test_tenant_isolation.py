"""Cross-tenant denial across the billing servicer surface.

Tenant B's subscription, payment method, and invoice are seeded through the
real schema (real SQL on SQLite), so every RPC issued as tenant A must deny
or come back empty purely through the tenant_id predicates — a dropped
filter fails here instead of being mirrored by a mock. The token-vs-wire
tests exercise resolve_identity's middleware-populated branch.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from llamatrade_common import TenantContext, reset_context, set_context
from llamatrade_db.models import PaymentMethod, Subscription
from llamatrade_proto.generated import billing_pb2, common_pb2
from tests.conftest import (
    MockStripeClient,
    seed_invoice,
    seed_payment_method,
    seed_plan,
    seed_subscription,
)

from src.grpc.servicer import BillingServicer

pytestmark = pytest.mark.asyncio

TENANT_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TENANT_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
USER = UUID("33333333-3333-3333-3333-333333333333")


def _wire(tenant_id: UUID) -> common_pb2.TenantContext:
    return common_pb2.TenantContext(tenant_id=str(tenant_id), user_id=str(USER))


@pytest.fixture
def stripe() -> Iterator[MockStripeClient]:
    client = MockStripeClient()
    with patch("src.grpc.servicer.get_stripe_client", return_value=client):
        yield client


@pytest.fixture
def seeded_b(sqlite_sessions: sessionmaker[Session]) -> dict[str, UUID]:
    """Tenant B's pending-cancel subscription, default card, and invoice."""
    with sqlite_sessions() as session:
        plan = seed_plan(session)
        subscription = seed_subscription(
            session,
            tenant_id=TENANT_B,
            plan=plan,
            cancel_at_period_end=True,
            stripe_subscription_id="sub_b_1",
        )
        payment_method = seed_payment_method(
            session, tenant_id=TENANT_B, stripe_payment_method_id="pm_b_1", is_default=True
        )
        invoice = seed_invoice(session, tenant_id=TENANT_B)
        return {
            "subscription_id": subscription.id,
            "payment_method_id": payment_method.id,
            "invoice_id": invoice.id,
        }


# === Reads ===


async def test_get_subscription_does_not_leak_across_tenants(
    sqlite_servicer: BillingServicer, seeded_b: dict[str, UUID], stripe: MockStripeClient
) -> None:
    with pytest.raises(ConnectError) as exc_info:
        await sqlite_servicer.get_subscription(
            billing_pb2.GetSubscriptionRequest(context=_wire(TENANT_A)), MagicMock()
        )
    assert exc_info.value.code == Code.NOT_FOUND

    # Positive control: the seeded row is visible to its own tenant.
    response = await sqlite_servicer.get_subscription(
        billing_pb2.GetSubscriptionRequest(context=_wire(TENANT_B)), MagicMock()
    )
    assert response.subscription.tenant_id == str(TENANT_B)


async def test_list_payment_methods_is_tenant_scoped(
    sqlite_servicer: BillingServicer, seeded_b: dict[str, UUID], stripe: MockStripeClient
) -> None:
    as_a = await sqlite_servicer.list_payment_methods(
        billing_pb2.ListPaymentMethodsRequest(context=_wire(TENANT_A)), MagicMock()
    )
    assert list(as_a.payment_methods) == []

    as_b = await sqlite_servicer.list_payment_methods(
        billing_pb2.ListPaymentMethodsRequest(context=_wire(TENANT_B)), MagicMock()
    )
    assert len(as_b.payment_methods) == 1


async def test_get_invoice_is_tenant_scoped(
    sqlite_servicer: BillingServicer, seeded_b: dict[str, UUID], stripe: MockStripeClient
) -> None:
    request_a = billing_pb2.GetInvoiceRequest(
        context=_wire(TENANT_A), invoice_id=str(seeded_b["invoice_id"])
    )
    with pytest.raises(ConnectError) as exc_info:
        await sqlite_servicer.get_invoice(request_a, MagicMock())
    assert exc_info.value.code == Code.NOT_FOUND

    request_b = billing_pb2.GetInvoiceRequest(
        context=_wire(TENANT_B), invoice_id=str(seeded_b["invoice_id"])
    )
    response = await sqlite_servicer.get_invoice(request_b, MagicMock())
    assert response.invoice.tenant_id == str(TENANT_B)


async def test_list_invoices_is_tenant_scoped(
    sqlite_servicer: BillingServicer, seeded_b: dict[str, UUID], stripe: MockStripeClient
) -> None:
    as_a = await sqlite_servicer.list_invoices(
        billing_pb2.ListInvoicesRequest(context=_wire(TENANT_A)), MagicMock()
    )
    assert list(as_a.invoices) == []
    assert as_a.pagination.total_items == 0

    as_b = await sqlite_servicer.list_invoices(
        billing_pb2.ListInvoicesRequest(context=_wire(TENANT_B)), MagicMock()
    )
    assert len(as_b.invoices) == 1


# === Mutations ===


async def test_remove_payment_method_cannot_cross_tenants(
    sqlite_servicer: BillingServicer,
    sqlite_sessions: sessionmaker[Session],
    seeded_b: dict[str, UUID],
    stripe: MockStripeClient,
) -> None:
    request = billing_pb2.RemovePaymentMethodRequest(
        context=_wire(TENANT_A), payment_method_id=str(seeded_b["payment_method_id"])
    )
    with pytest.raises(ConnectError) as exc_info:
        await sqlite_servicer.remove_payment_method(request, MagicMock())

    assert exc_info.value.code == Code.NOT_FOUND
    assert stripe.detached == []
    with sqlite_sessions() as session:
        assert session.scalars(select(PaymentMethod)).one().tenant_id == TENANT_B


async def test_resume_subscription_cannot_cross_tenants(
    sqlite_servicer: BillingServicer,
    sqlite_sessions: sessionmaker[Session],
    seeded_b: dict[str, UUID],
    stripe: MockStripeClient,
) -> None:
    with pytest.raises(ConnectError) as exc_info:
        await sqlite_servicer.resume_subscription(
            billing_pb2.ResumeSubscriptionRequest(context=_wire(TENANT_A)), MagicMock()
        )

    assert exc_info.value.code == Code.INVALID_ARGUMENT
    assert stripe.reactivated == []
    with sqlite_sessions() as session:
        assert session.scalars(select(Subscription)).one().cancel_at_period_end is True


async def test_cancel_subscription_cannot_cross_tenants(
    sqlite_servicer: BillingServicer,
    sqlite_sessions: sessionmaker[Session],
    seeded_b: dict[str, UUID],
    stripe: MockStripeClient,
) -> None:
    with pytest.raises(ConnectError) as exc_info:
        await sqlite_servicer.cancel_subscription(
            billing_pb2.CancelSubscriptionRequest(context=_wire(TENANT_A), cancel_immediately=True),
            MagicMock(),
        )

    assert exc_info.value.code == Code.INVALID_ARGUMENT
    assert stripe.cancel_calls == []
    with sqlite_sessions() as session:
        row = session.scalars(select(Subscription)).one()
        assert row.status == billing_pb2.SUBSCRIPTION_STATUS_ACTIVE
        assert row.canceled_at is None


# === Token vs wire (middleware-populated branch of resolve_identity) ===


async def test_wire_tenant_mismatch_is_denied_for_authenticated_user(
    sqlite_servicer: BillingServicer, seeded_b: dict[str, UUID], stripe: MockStripeClient
) -> None:
    """A tenant-A principal (AuthMiddleware context) cannot claim tenant B on the wire."""
    token = set_context(TenantContext(tenant_id=TENANT_A, user_id=USER))
    try:
        with pytest.raises(ConnectError) as exc_info:
            await sqlite_servicer.get_subscription(
                billing_pb2.GetSubscriptionRequest(context=_wire(TENANT_B)), MagicMock()
            )
    finally:
        reset_context(token)
    assert exc_info.value.code == Code.PERMISSION_DENIED


async def test_matching_wire_tenant_proceeds_for_authenticated_user(
    sqlite_servicer: BillingServicer, seeded_b: dict[str, UUID], stripe: MockStripeClient
) -> None:
    """The same principal with a matching wire context reaches the tenant-scoped read."""
    token = set_context(TenantContext(tenant_id=TENANT_B, user_id=USER))
    try:
        response = await sqlite_servicer.get_subscription(
            billing_pb2.GetSubscriptionRequest(context=_wire(TENANT_B)), MagicMock()
        )
    finally:
        reset_context(token)
    assert response.subscription.tenant_id == str(TENANT_B)
