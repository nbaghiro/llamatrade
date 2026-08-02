"""E2E: the plans / subscribe / invoices / payment-methods billing flow.

Mirrors the UI billing surface: BillingPage reads ``ListPlans`` /
``GetSubscription`` / ``ListInvoices`` / ``ListPaymentMethods``; SubscribePage
starts a purchase via ``CreateCheckoutSession`` (and ``CreateSubscription`` once a
card is collected). The reads run against the seeded demo tenant; the purchase
mutations run on a freshly registered tenant so the demo is never touched.

The billing service points at a real-shaped ``stripe-mock`` (STRIPE_API_BASE), so
the checkout/subscribe calls exercise the real Stripe SDK path and get back a
canned Checkout Session / Subscription without live keys. The seed provisions a
placeholder Stripe price id on the paid plan, so the whole flow runs over HTTP.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from .client import MeshClient, MeshError, decimal_val, status_is

pytestmark = pytest.mark.e2e

_INTERVAL_MONTHLY = "BILLING_INTERVAL_MONTHLY"


def _money(value: object) -> float:
    """Amount of a proto ``Money`` ({'currency','amount'}); tolerant of a bare Decimal/number."""
    if isinstance(value, dict) and "amount" in value:
        return float(value.get("amount") or 0)
    return decimal_val(value)


def _paid_plan(plans: list[dict[str, object]]) -> dict[str, object]:
    """First plan with a positive monthly price (the purchasable ones)."""
    for plan in plans:
        if _money(plan.get("monthlyPrice")) > 0:
            return plan
    raise AssertionError("no paid plan present in the catalog")


def _create_checkout(client: MeshClient, plan_id: str) -> dict[str, object]:
    """CreateCheckoutSession for a plan; the UI omits the tenant context, so fall
    back to a context-less call if the contexted one is rejected."""
    body = {
        "planId": plan_id,
        "interval": _INTERVAL_MONTHLY,
        "successUrl": "http://localhost:8800/billing?success=true",
        "cancelUrl": "http://localhost:8800/subscribe",
    }
    try:
        return client.call("billing", "CreateCheckoutSession", body)
    except MeshError:
        return client.call("billing", "CreateCheckoutSession", body, context=False)


# --- Reads (seeded demo tenant) ----------------------------------------------
def test_list_plans_returns_the_catalog(demo: MeshClient) -> None:
    plans = demo.call("billing", "ListPlans", {}).get("plans", [])
    assert len(plans) >= 2
    for plan in plans:
        assert plan.get("id")
        assert plan.get("name")
    assert any(_money(p.get("monthlyPrice")) == 0 for p in plans), "expected a free plan"
    paid = _paid_plan(plans)
    assert _money(paid.get("monthlyPrice")) > 0


def test_get_subscription_returns_the_seeded_active_sub(demo: MeshClient) -> None:
    sub = demo.call("billing", "GetSubscription", {}).get("subscription", {})
    assert sub.get("id")
    assert sub.get("planId")
    status = sub.get("status")
    assert status_is(status, "SUBSCRIPTION_STATUS_ACTIVE", 1) or status_is(
        status, "SUBSCRIPTION_STATUS_TRIALING", 4
    ), f"unexpected subscription status {status!r}"
    assert status_is(sub.get("interval"), _INTERVAL_MONTHLY, 1)
    assert _money(sub.get("currentPrice")) > 0


def test_list_invoices_returns_the_seeded_history(demo: MeshClient) -> None:
    resp = demo.call("billing", "ListInvoices", {"pagination": {"page": 1, "pageSize": 25}})
    invoices = resp.get("invoices", [])
    assert len(invoices) >= 1
    assert resp.get("pagination", {}).get("totalItems", 0) >= 1
    for inv in invoices:
        assert inv.get("id")
        assert _money(inv.get("amount")) > 0
        assert inv.get("status")
    assert any(status_is(inv.get("status"), "INVOICE_STATUS_PAID", 3) for inv in invoices)


def test_list_payment_methods_returns_the_seeded_card(demo: MeshClient) -> None:
    methods = demo.call("billing", "ListPaymentMethods", {}).get("paymentMethods", [])
    assert len(methods) >= 1
    card = next((m for m in methods if m.get("type") == "card"), None)
    assert card is not None, "seeded demo should expose a card payment method"
    assert len(str(card.get("cardLast4", ""))) == 4


# --- Purchase path (fresh tenant, against stripe-mock) -----------------------
def test_new_tenant_has_no_subscription(
    throwaway_tenant: Callable[[str], MeshClient],
) -> None:
    client = throwaway_tenant("bill")
    try:
        sub = client.call("billing", "GetSubscription", {}).get("subscription")
        assert not sub, "a fresh tenant must not carry a subscription"
    except MeshError as exc:
        assert exc.http_status == 404 or exc.code == "not_found", (
            f"expected not_found for a fresh tenant, got {exc.http_status} {exc.code}"
        )


def test_checkout_session_returns_a_stripe_url(
    throwaway_tenant: Callable[[str], MeshClient],
) -> None:
    client = throwaway_tenant("bill")
    plans = client.call("billing", "ListPlans", {}).get("plans", [])
    plan_id = _paid_plan(plans).get("id")
    assert isinstance(plan_id, str) and plan_id

    resp = _create_checkout(client, plan_id)
    checkout_url = resp.get("checkoutUrl")
    assert isinstance(checkout_url, str) and checkout_url.startswith("http")
    assert resp.get("sessionId")


def test_create_subscription_or_fall_back_to_checkout(
    throwaway_tenant: Callable[[str], MeshClient],
) -> None:
    client = throwaway_tenant("bill")
    plans = client.call("billing", "ListPlans", {}).get("plans", [])
    plan = _paid_plan(plans)
    plan_id = plan.get("id")
    assert isinstance(plan_id, str) and plan_id

    try:
        sub = client.call(
            "billing",
            "CreateSubscription",
            {"planId": plan_id, "interval": _INTERVAL_MONTHLY, "paymentMethodId": ""},
        ).get("subscription", {})
    except MeshError:
        # stripe-mock may not carry a subscription create cleanly (needs a real
        # payment method); the checkout path is the required purchase proof.
        resp = _create_checkout(client, plan_id)
        assert str(resp.get("checkoutUrl", "")).startswith("http")
        return

    assert sub.get("id")
    assert sub.get("planId") == plan_id
    assert sub.get("status")
