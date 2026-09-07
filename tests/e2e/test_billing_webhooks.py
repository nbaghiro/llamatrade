"""E2E: Stripe-webhook-driven billing transitions against the real endpoint.

stripe-mock cannot EMIT webhooks, so the suite plays Stripe itself: it POSTs
synthetic events to billing's public ``/webhooks/stripe`` route, signed exactly
the way ``stripe.Webhook.construct_event`` verifies them (``t=<ts>,v1=<hmac>``
over ``{t}.{raw_body}``). The signing secret comes from ``STRIPE_WEBHOOK_SECRET``
in the environment; the dev mesh leaves it unset, in which case billing skips
verification (dev-only branch) but still requires the header — the forged
signature is correct either way. Everything downstream (handler dispatch, the
subscription row transition, the notification publish) runs for real.

Each mutating flow runs on a throwaway tenant whose subscription is created
against stripe-mock via the real ``CreateSubscription`` RPC, which stores the
``stripe_subscription_id`` the webhook handlers correlate on.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable

import pytest

from .client import HOSTS, JSON, MeshClient, MeshError, status_is

pytestmark = pytest.mark.e2e

_WEBHOOK_URL = f"{HOSTS['billing']}/webhooks/stripe"
# Used verbatim when the mesh has a secret configured; otherwise billing's dev
# branch skips verification and only requires the header to be present.
_SIGNING_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_e2e_unconfigured")


def _post_signed_event(event: JSON) -> int:
    """POST a synthetic Stripe event with a genuine v1 signature; returns HTTP status."""
    payload = json.dumps(event).encode()
    ts = int(time.time())
    mac = hmac.new(_SIGNING_SECRET.encode(), f"{ts}.".encode() + payload, hashlib.sha256)
    req = urllib.request.Request(
        _WEBHOOK_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "stripe-signature": f"t={ts},v1={mac.hexdigest()}",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status


def _subscribed_tenant(
    throwaway_tenant: Callable[[str], MeshClient], label: str
) -> tuple[MeshClient, str]:
    """A throwaway tenant holding a real (stripe-mock backed) paid subscription."""
    client = throwaway_tenant(label)
    plans = client.call("billing", "ListPlans", {}).get("plans", [])
    paid = next(p for p in plans if float((p.get("monthlyPrice") or {}).get("amount", 0) or 0) > 0)
    sub = client.call(
        "billing",
        "CreateSubscription",
        {"planId": paid["id"], "interval": "BILLING_INTERVAL_MONTHLY", "paymentMethodId": ""},
    ).get("subscription", {})
    stripe_sub_id = sub.get("stripeSubscriptionId", "")
    assert stripe_sub_id, f"CreateSubscription stored no stripe_subscription_id: {sub}"
    return client, stripe_sub_id


def _subscription_event(
    event_id: str, event_type: str, stripe_sub_id: str, **overrides: object
) -> JSON:
    """A dahlia-shaped customer.subscription.* event (periods live on the items)."""
    obj: JSON = {
        "id": stripe_sub_id,
        "object": "subscription",
        "status": "active",
        "cancel_at_period_end": False,
        "canceled_at": None,
        "trial_start": None,
        "trial_end": None,
        "items": {
            "object": "list",
            "has_more": False,
            "data": [
                {
                    "id": "si_e2e",
                    "object": "subscription_item",
                    "current_period_start": 1700000000,
                    "current_period_end": 1702592000,
                }
            ],
        },
    }
    obj.update(overrides)
    return {"id": event_id, "object": "event", "type": event_type, "data": {"object": obj}}


def _poll_subscription(
    client: MeshClient, predicate: Callable[[JSON], bool], *, timeout: float = 20.0
) -> JSON:
    deadline = time.monotonic() + timeout
    sub: JSON = {}
    while time.monotonic() < deadline:
        sub = client.call("billing", "GetSubscription", {}).get("subscription", {})
        if predicate(sub):
            return sub
        time.sleep(1)
    return sub


def _poll_inbox_title(client: MeshClient, title: str, *, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        rows = client.call("notification", "ListNotifications", {}).get("notifications", [])
        if any(r.get("title") == title for r in rows):
            return True
        time.sleep(2)
    return False


def test_missing_signature_header_is_rejected() -> None:
    req = urllib.request.Request(
        _WEBHOOK_URL, data=b"{}", headers={"Content-Type": "application/json"}
    )
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(req, timeout=10)
    assert excinfo.value.code == 400


def test_subscription_updated_event_transitions_state_and_notifies(
    throwaway_tenant: Callable[[str], MeshClient],
) -> None:
    client, stripe_sub_id = _subscribed_tenant(throwaway_tenant, "hook-upd")
    uniq = f"{int(time.time() * 1000)}"

    status = _post_signed_event(
        _subscription_event(
            f"evt_e2e_upd_{uniq}",
            "customer.subscription.updated",
            stripe_sub_id,
            cancel_at_period_end=True,
        )
    )
    assert status == 200

    sub = _poll_subscription(client, lambda s: s.get("cancelAtPeriodEnd") is True)
    assert sub.get("cancelAtPeriodEnd") is True, f"webhook did not flip cancelAtPeriodEnd: {sub}"
    assert _poll_inbox_title(client, "Subscription updated"), (
        "SUBSCRIPTION_UPDATED notification never surfaced"
    )


def test_payment_failed_event_marks_past_due_and_notifies(
    throwaway_tenant: Callable[[str], MeshClient],
) -> None:
    client, stripe_sub_id = _subscribed_tenant(throwaway_tenant, "hook-pf")
    uniq = f"{int(time.time() * 1000)}"

    status = _post_signed_event(
        {
            "id": f"evt_e2e_pf_{uniq}",
            "object": "event",
            "type": "invoice.payment_failed",
            "data": {
                "object": {
                    "id": f"in_e2e_{uniq}",
                    "object": "invoice",
                    "number": f"INV-E2E-{uniq}",
                    "amount_due": 4900,
                    "amount_paid": 0,
                    "currency": "usd",
                    "period_start": 1700000000,
                    "period_end": 1702592000,
                    "hosted_invoice_url": None,
                    "invoice_pdf": None,
                    "parent": {
                        "type": "subscription_details",
                        "quote_details": None,
                        "subscription_details": {
                            "subscription": stripe_sub_id,
                            "metadata": {},
                            "subscription_proration_date": None,
                        },
                    },
                }
            },
        }
    )
    assert status == 200

    sub = _poll_subscription(
        client, lambda s: status_is(s.get("status"), "SUBSCRIPTION_STATUS_PAST_DUE", 2)
    )
    assert status_is(sub.get("status"), "SUBSCRIPTION_STATUS_PAST_DUE", 2), (
        f"invoice.payment_failed did not mark the subscription PAST_DUE: {sub.get('status')}"
    )
    assert _poll_inbox_title(client, "Payment failed"), "PAYMENT_FAILED notification never surfaced"


def test_subscription_deleted_event_cancels_and_notifies(
    throwaway_tenant: Callable[[str], MeshClient],
) -> None:
    client, stripe_sub_id = _subscribed_tenant(throwaway_tenant, "hook-del")
    uniq = f"{int(time.time() * 1000)}"

    status = _post_signed_event(
        _subscription_event(
            f"evt_e2e_del_{uniq}",
            "customer.subscription.deleted",
            stripe_sub_id,
            status="canceled",
        )
    )
    assert status == 200

    # A canceled subscription stops resolving: GetSubscription reports
    # not_found ("No active subscription found") once the row is CANCELED.
    def _gone() -> bool:
        try:
            client.call("billing", "GetSubscription", {})
        except MeshError as exc:
            return exc.code == "not_found"
        return False

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and not _gone():
        time.sleep(1)
    assert _gone(), "subscription.deleted did not cancel the subscription"
    assert _poll_inbox_title(client, "Subscription canceled"), (
        "SUBSCRIPTION_CANCELED notification never surfaced"
    )
