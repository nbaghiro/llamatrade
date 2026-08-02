"""Ledger alert dispatcher tests — publish assertions over a FakeTransport.

Covers the incident-to-category mapping, field threading, deterministic
incident dedup, and the best-effort guarantee: a broker fault never raises
out of ``dispatch``.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from llamatrade_events import EventBus, EventEnvelope
from llamatrade_events.catalog.notifications import NotificationEvents
from llamatrade_events.testing import FakeTransport
from llamatrade_proto.generated import events_pb2

from src.alerts import (
    LedgerAlertDispatcher,
    LedgerIncident,
    get_ledger_alert_dispatcher,
)

TENANT = uuid4()
_E = events_pb2

pytestmark = pytest.mark.asyncio


@pytest.fixture
def transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def dispatcher(transport: FakeTransport) -> LedgerAlertDispatcher:
    return LedgerAlertDispatcher(events=NotificationEvents(bus=EventBus(transport)))


def _events(transport: FakeTransport) -> list[events_pb2.NotificationEvent]:
    return [
        NotificationEvents.payload(EventEnvelope.FromString(value))
        for _, value in transport.published
    ]


async def test_sleeve_frozen_maps_to_category(
    dispatcher: LedgerAlertDispatcher, transport: FakeTransport
) -> None:
    await dispatcher.dispatch(
        TENANT,
        LedgerIncident(
            kind="sleeve_frozen",
            message="negative cash after fill",
            context={"sleeve_id": "sl-1", "account_id": "acct-1"},
        ),
    )
    event = _events(transport)[0]
    assert event.category == _E.NOTIFICATION_CATEGORY_SLEEVE_FROZEN
    assert event.severity == _E.NOTIFICATION_SEVERITY_CRITICAL
    assert event.sleeve_id == "sl-1"
    assert event.account_id == "acct-1"
    assert event.reason == "negative cash after fill"


async def test_quarantine_maps_and_keys_by_tenant(
    dispatcher: LedgerAlertDispatcher, transport: FakeTransport
) -> None:
    await dispatcher.dispatch(
        TENANT,
        LedgerIncident(
            kind="fill_quarantined",
            message="unresolvable cost basis",
            context={"client_order_id": "lt-abc"},
        ),
    )
    assert transport.records[0].key == str(TENANT)
    event = _events(transport)[0]
    assert event.category == _E.NOTIFICATION_CATEGORY_FILL_QUARANTINED
    assert event.extra["client_order_id"] == "lt-abc"


async def test_same_incident_collapses_to_one_id(
    dispatcher: LedgerAlertDispatcher, transport: FakeTransport
) -> None:
    incident = LedgerIncident(kind="sleeve_frozen", message="drift", context={"sleeve_id": "sl-9"})
    await dispatcher.dispatch(TENANT, incident)
    await dispatcher.dispatch(TENANT, incident)
    ids = {EventEnvelope.FromString(v).id for _, v in transport.published}
    assert len(ids) == 1


async def test_distinct_sleeves_do_not_collapse(
    dispatcher: LedgerAlertDispatcher, transport: FakeTransport
) -> None:
    for sleeve in ("sl-1", "sl-2"):
        await dispatcher.dispatch(
            TENANT,
            LedgerIncident(kind="sleeve_frozen", message="d", context={"sleeve_id": sleeve}),
        )
    ids = {EventEnvelope.FromString(v).id for _, v in transport.published}
    assert len(ids) == 2


async def test_publish_fault_never_raises(
    transport: FakeTransport, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = NotificationEvents(bus=EventBus(transport))

    async def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("broker down")

    monkeypatch.setattr(events.bus, "publish_envelope", boom)
    dispatcher = LedgerAlertDispatcher(events=events)
    await dispatcher.dispatch(TENANT, LedgerIncident(kind="sleeve_frozen", message="d", context={}))


async def test_contextless_incident_dedups_on_message(
    dispatcher: LedgerAlertDispatcher, transport: FakeTransport
) -> None:
    await dispatcher.dispatch(TENANT, LedgerIncident(kind="dlq_backlog", message="depth 5"))
    await dispatcher.dispatch(TENANT, LedgerIncident(kind="dlq_backlog", message="depth 9"))
    ids = {EventEnvelope.FromString(v).id for _, v in transport.published}
    assert len(ids) == 2


def test_get_ledger_alert_dispatcher_returns_singleton() -> None:
    assert get_ledger_alert_dispatcher() is get_ledger_alert_dispatcher()
