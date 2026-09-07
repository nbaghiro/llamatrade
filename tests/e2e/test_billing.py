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
    """CreateCheckoutSession for a plan, exactly as SubscribePage calls it."""
    return client.call(
        "billing",
        "CreateCheckoutSession",
        {
            "planId": plan_id,
            "interval": _INTERVAL_MONTHLY,
            "successUrl": "http://localhost:8800/billing?success=true",
            "cancelUrl": "http://localhost:8800/subscribe",
        },
    )


def test_checkout_works_without_a_tenant_context(
    throwaway_tenant: Callable[[str], MeshClient],
) -> None:
    """The RPC derives the tenant from the JWT, so the context arg is optional.

    Pinned separately because the helper above used to retry context-less on any
    error, which would have masked a real failure of the contexted call.
    """
    client = throwaway_tenant("bill-ctx")
    plan_id = _paid_plan(client.call("billing", "ListPlans", {}).get("plans", [])).get("id")

    resp = client.call(
        "billing",
        "CreateCheckoutSession",
        {
            "planId": plan_id,
            "interval": _INTERVAL_MONTHLY,
            "successUrl": "http://localhost:8800/billing?success=true",
            "cancelUrl": "http://localhost:8800/subscribe",
        },
        context=False,
    )

    assert str(resp.get("checkoutUrl", "")).startswith("http")


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


def test_create_subscription_subscribes_the_tenant(
    throwaway_tenant: Callable[[str], MeshClient],
) -> None:
    """Subscribing must succeed outright.

    This previously fell back to the checkout path on any error, which swallowed
    a real 500: the create maps the new row to proto with ``plan`` still unloaded.
    """
    client = throwaway_tenant("bill")
    plans = client.call("billing", "ListPlans", {}).get("plans", [])
    plan = _paid_plan(plans)
    plan_id = plan.get("id")
    assert isinstance(plan_id, str) and plan_id

    sub = client.call(
        "billing",
        "CreateSubscription",
        {"planId": plan_id, "interval": _INTERVAL_MONTHLY, "paymentMethodId": ""},
    ).get("subscription", {})

    assert sub.get("id")
    assert sub.get("planId") == plan_id
    assert status_is(sub.get("status"), "SUBSCRIPTION_STATUS_ACTIVE", 1)

    # The subscription must be readable back, with its plan resolved.
    read_back = client.call("billing", "GetSubscription", {}).get("subscription", {})
    assert read_back.get("id") == sub.get("id")
    assert read_back.get("plan", {}).get("name")


# --- Cancel / resume (round trip on the seeded demo subscription) -------------
def test_cancel_then_resume_round_trips_the_demo_subscription(demo: MeshClient) -> None:
    """Cancel-at-period-end and resume, the two controls on the billing page.

    Both mutate then map the row back to proto, which is where they used to fail:
    the UPDATE expires the server-side timestamps and the mapper read them after
    only the plan had been refreshed, so both returned an opaque 500. The demo
    subscription is restored either way, so the leg is repeatable.
    """
    before = demo.call("billing", "GetSubscription", {}).get("subscription", {})
    assert status_is(before.get("status"), "SUBSCRIPTION_STATUS_ACTIVE", 1), (
        "this leg needs the seeded active subscription"
    )
    assert not before.get("cancelAtPeriodEnd")

    resumed = False
    try:
        canceled = demo.call(
            "billing", "CancelSubscription", {"cancelImmediately": False, "reason": "e2e"}
        ).get("subscription", {})

        assert canceled.get("cancelAtPeriodEnd") is True
        # Cancelling at period end leaves access intact until the period closes.
        assert status_is(canceled.get("status"), "SUBSCRIPTION_STATUS_ACTIVE", 1)
        assert (
            demo.call("billing", "GetSubscription", {})
            .get("subscription", {})
            .get("cancelAtPeriodEnd")
        ), "the pending cancellation must survive a re-read"

        restored = demo.call("billing", "ResumeSubscription", {}).get("subscription", {})
        resumed = True
        assert not restored.get("cancelAtPeriodEnd")
        assert status_is(restored.get("status"), "SUBSCRIPTION_STATUS_ACTIVE", 1)
    finally:
        if not resumed:
            demo.try_call("billing", "ResumeSubscription", {})


def test_resume_without_a_pending_cancellation_is_refused(demo: MeshClient) -> None:
    """Nothing to resume is a client error, not a 500."""
    assert (
        not demo.call("billing", "GetSubscription", {})
        .get("subscription", {})
        .get("cancelAtPeriodEnd")
    ), "the demo subscription must not be pending cancellation here"

    with pytest.raises(MeshError) as exc:
        demo.call("billing", "ResumeSubscription", {})
    assert exc.value.http_status < 500, f"expected a client error, got {exc.value}"


def test_cancel_on_a_tenant_without_a_subscription_is_refused(
    throwaway_tenant: Callable[[str], MeshClient],
) -> None:
    client = throwaway_tenant("bill-cancel")

    with pytest.raises(MeshError) as exc:
        client.call("billing", "CancelSubscription", {"cancelImmediately": False, "reason": "e2e"})
    assert exc.value.http_status < 500, f"expected a client error, got {exc.value}"


def test_plan_change_to_an_unknown_plan_is_refused(demo: MeshClient) -> None:
    """UpdateSubscription shares the mutate-then-map path; pin its refusal shape."""
    with pytest.raises(MeshError) as exc:
        demo.call(
            "billing",
            "UpdateSubscription",
            {"planId": "no-such-plan", "interval": _INTERVAL_MONTHLY, "prorate": True},
        )
    assert exc.value.http_status < 500, f"expected a client error, got {exc.value}"
