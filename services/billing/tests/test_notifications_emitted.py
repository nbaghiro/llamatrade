"""Billing webhook handlers land their notifications on the stream.

Every ``_notify_billing`` category is asserted over the in-memory
FakeTransport (the autouse conftest fixture), including the deterministic
dedup ids that make a Stripe redelivery collapse to one notification.
"""

from __future__ import annotations

import pytest

from llamatrade_events import EventEnvelope
from llamatrade_events.catalog import notifications as notifications_module
from llamatrade_events.catalog.notifications import NotificationEvents
from llamatrade_events.testing import FakeTransport
from llamatrade_proto.generated import billing_pb2, events_pb2
from tests.conftest import (
    MockAsyncSession,
    MockSubscription,
    make_stripe_invoice,
    make_stripe_subscription,
)

from src.routers.webhooks import (
    _handle_invoice_paid,
    _handle_payment_failed,
    _handle_subscription_deleted,
    _handle_subscription_updated,
    _handle_trial_will_end,
)

_E = events_pb2

pytestmark = pytest.mark.asyncio


def _transport() -> FakeTransport:
    shared = notifications_module._shared
    assert shared is not None
    transport = shared.bus.transport
    assert isinstance(transport, FakeTransport)
    return transport


def _published() -> list[events_pb2.NotificationEvent]:
    return [
        NotificationEvents.payload(EventEnvelope.FromString(value))
        for _, value in _transport().published
    ]


def _event_ids() -> set[str]:
    return {EventEnvelope.FromString(value).id for _, value in _transport().published}


@pytest.fixture
def db() -> MockAsyncSession:
    return MockAsyncSession()


@pytest.fixture
def local_sub(db: MockAsyncSession) -> MockSubscription:
    sub = MockSubscription()
    db.subscriptions.append(sub)
    return sub


# === SUBSCRIPTION_UPDATED ===


async def test_subscription_updated_emits_subscription_updated(
    db: MockAsyncSession, local_sub: MockSubscription
) -> None:
    await _handle_subscription_updated(db, make_stripe_subscription(cancel_at_period_end=True))

    events = _published()
    assert [e.category for e in events] == [_E.NOTIFICATION_CATEGORY_SUBSCRIPTION_UPDATED]
    assert events[0].reason == "cancels at period end"
    envelope = EventEnvelope.FromString(_transport().published[0][1])
    assert envelope.tenant_id == str(local_sub.tenant_id)


async def test_subscription_updated_redelivery_collapses(
    db: MockAsyncSession, local_sub: MockSubscription
) -> None:
    payload = make_stripe_subscription(status="past_due")

    await _handle_subscription_updated(db, payload)
    await _handle_subscription_updated(db, payload)

    assert len(_transport().published) == 2
    assert len(_event_ids()) == 1


async def test_distinct_subscription_transitions_do_not_collapse(
    db: MockAsyncSession, local_sub: MockSubscription
) -> None:
    """A real state change (not a redelivery) keeps its own dedup identity."""
    await _handle_subscription_updated(db, make_stripe_subscription(status="active"))
    await _handle_subscription_updated(db, make_stripe_subscription(status="past_due"))

    assert len(_event_ids()) == 2


# === SUBSCRIPTION_CANCELED ===


async def test_subscription_deleted_emits_and_collapses(
    db: MockAsyncSession, local_sub: MockSubscription
) -> None:
    payload = make_stripe_subscription(status="canceled")

    await _handle_subscription_deleted(db, payload)
    await _handle_subscription_deleted(db, payload)

    events = _published()
    assert {e.category for e in events} == {_E.NOTIFICATION_CATEGORY_SUBSCRIPTION_CANCELED}
    assert len(_event_ids()) == 1
    assert local_sub.status == billing_pb2.SUBSCRIPTION_STATUS_CANCELED


# === PAYMENT_SUCCEEDED ===


async def test_invoice_paid_emits_payment_succeeded_with_amount(
    db: MockAsyncSession, local_sub: MockSubscription
) -> None:
    await _handle_invoice_paid(db, make_stripe_invoice())

    events = _published()
    assert [e.category for e in events] == [_E.NOTIFICATION_CATEGORY_PAYMENT_SUCCEEDED]
    assert events[0].amount == "29"
    assert "INV-001" in events[0].reason


async def test_invoice_paid_redelivery_collapses(
    db: MockAsyncSession, local_sub: MockSubscription
) -> None:
    """The second delivery hits the recorded-invoice replay path, same dedup id."""
    payload = make_stripe_invoice()

    await _handle_invoice_paid(db, payload)
    await _handle_invoice_paid(db, payload)

    assert len(db.invoices) == 1
    assert len(_transport().published) == 2
    assert len(_event_ids()) == 1


# === PAYMENT_FAILED ===


async def test_payment_failed_emits_and_collapses(
    db: MockAsyncSession, local_sub: MockSubscription
) -> None:
    payload = make_stripe_invoice()

    await _handle_payment_failed(db, payload)
    await _handle_payment_failed(db, payload)

    events = _published()
    assert {e.category for e in events} == {_E.NOTIFICATION_CATEGORY_PAYMENT_FAILED}
    assert "starter" in events[0].reason
    assert len(_event_ids()) == 1
    assert local_sub.status == billing_pb2.SUBSCRIPTION_STATUS_PAST_DUE


async def test_paid_and_failed_for_same_invoice_do_not_collapse(
    db: MockAsyncSession, local_sub: MockSubscription
) -> None:
    payload = make_stripe_invoice()

    await _handle_invoice_paid(db, payload)
    await _handle_payment_failed(db, payload)

    assert len(_event_ids()) == 2


# === TRIAL_ENDING ===


async def test_trial_will_end_emits_trial_ending(
    db: MockAsyncSession, local_sub: MockSubscription
) -> None:
    await _handle_trial_will_end(db, make_stripe_subscription(trial_end=1702592000))

    events = _published()
    assert [e.category for e in events] == [_E.NOTIFICATION_CATEGORY_TRIAL_ENDING]
    assert "2023-12-14" in events[0].reason


async def test_trial_will_end_without_trial_end_uses_fallback_reason(
    db: MockAsyncSession, local_sub: MockSubscription
) -> None:
    await _handle_trial_will_end(db, make_stripe_subscription())

    assert _published()[0].reason == "trial ending soon"


async def test_trial_will_end_redelivery_collapses(
    db: MockAsyncSession, local_sub: MockSubscription
) -> None:
    payload = make_stripe_subscription(trial_end=1702592000)

    await _handle_trial_will_end(db, payload)
    await _handle_trial_will_end(db, payload)

    assert len(_transport().published) == 2
    assert len(_event_ids()) == 1


async def test_trial_will_end_without_local_subscription_publishes_nothing(
    db: MockAsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("WARNING", logger="src.routers.webhooks"):
        await _handle_trial_will_end(db, make_stripe_subscription(id="sub_unknown"))

    assert _published() == []
    assert "No subscription found for trial_will_end" in caplog.text
