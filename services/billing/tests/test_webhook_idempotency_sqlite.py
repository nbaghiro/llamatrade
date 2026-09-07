"""Cross-replica Stripe webhook idempotency over real SQL on SQLite (I10).

The in-process dedup LRU only protects one replica; across replicas the
backstop is the unique index on the synced Stripe row (``stripe_invoice_id``
/ ``stripe_payment_method_id``). These tests drive the real route (signature
verification, dispatch, error classification) against a schema whose UNIQUE
constraints are honored, proving a replayed event id is a no-op that returns
200 with no double side effects — including the race where both replicas pass
the existence check and the loser's insert dies on the unique index.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Callable, Iterator
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from llamatrade_db import get_db
from llamatrade_db.models import Invoice, PaymentMethod
from llamatrade_events import EventEnvelope
from llamatrade_events.catalog import notifications as notifications_module
from llamatrade_events.testing import FakeTransport
from llamatrade_telemetry import metrics
from tests.conftest import (
    SqliteSessionAdapter,
    make_stripe_invoice,
    make_stripe_payment_method,
    seed_invoice,
    seed_plan,
    seed_subscription,
    sign_stripe_payload,
)

from src.main import app
from src.routers import webhooks

pytestmark = pytest.mark.asyncio

WEBHOOK_SECRET = "whsec_test_secret"
WEBHOOK_PATH = "/webhooks/stripe"
TENANT = UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture(autouse=True)
def _verified_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.delenv("ENVIRONMENT", raising=False)


@pytest.fixture(autouse=True)
def _reset_dedup() -> Iterator[None]:
    """Isolate the in-process dedup LRU between tests."""
    webhooks._seen_event_ids.clear()
    yield
    webhooks._seen_event_ids.clear()


def _db_override(
    sqlite_sessions: sessionmaker[Session],
    adapter_factory: Callable[[Session], SqliteSessionAdapter] = SqliteSessionAdapter,
) -> Callable[[], AsyncGenerator[SqliteSessionAdapter]]:
    async def _get_db() -> AsyncGenerator[SqliteSessionAdapter]:
        adapter = adapter_factory(sqlite_sessions())
        try:
            yield adapter
        finally:
            await adapter.rollback()
            await adapter.close()

    return _get_db


@pytest.fixture
async def sqlite_client(
    sqlite_sessions: sessionmaker[Session],
) -> AsyncGenerator[AsyncClient]:
    """Webhook client whose ``get_db`` runs real SQL on the SQLite schema."""
    app.dependency_overrides[get_db] = _db_override(sqlite_sessions)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


def _seed_subscription(sqlite_sessions: sessionmaker[Session]) -> None:
    """Seed the subscription the invoice/payment-method events resolve against."""
    with sqlite_sessions() as session:
        plan = seed_plan(session)
        seed_subscription(
            session,
            tenant_id=TENANT,
            plan=plan,
            stripe_subscription_id="sub_123",
            stripe_customer_id="cus_123",
        )


def _event_bytes(event_id: str, event_type: str, data_object: dict[str, object]) -> bytes:
    return json.dumps(
        {"id": event_id, "object": "event", "type": event_type, "data": {"object": data_object}}
    ).encode()


async def _post(client: AsyncClient, payload: bytes) -> Response:
    return await client.post(
        WEBHOOK_PATH,
        content=payload,
        headers={"stripe-signature": sign_stripe_payload(payload, WEBHOOK_SECRET)},
    )


def _published_notification_ids() -> list[str]:
    shared = notifications_module._shared
    assert shared is not None
    transport = shared.bus.transport
    assert isinstance(transport, FakeTransport)
    return [EventEnvelope.FromString(value).id for _, value in transport.published]


# === invoice.paid ===


async def test_invoice_paid_replay_on_second_replica_is_noop(
    sqlite_client: AsyncClient, sqlite_sessions: sessionmaker[Session]
) -> None:
    """A replica with a cold dedup LRU lands on the row guard: 200, one row."""
    _seed_subscription(sqlite_sessions)
    payload = _event_bytes("evt_inv_1", "invoice.paid", make_stripe_invoice().to_dict())

    first = await _post(sqlite_client, payload)
    assert first.status_code == 200

    webhooks._seen_event_ids.clear()
    with patch.object(metrics.billing, "webhook_duplicate") as duplicate_metric:
        second = await _post(sqlite_client, payload)

    assert second.status_code == 200
    assert second.json() == {"received": True}
    duplicate_metric.assert_called_once_with()
    with sqlite_sessions() as session:
        row = session.scalars(select(Invoice)).one()
        assert row.stripe_invoice_id == "in_123"
        assert row.tenant_id == TENANT
        assert row.amount_paid == Decimal("29.00")
    # Both deliveries publish under one deterministic dedup id, collapsing downstream.
    ids = _published_notification_ids()
    assert len(ids) == 2
    assert len(set(ids)) == 1


class _RaceCommitAdapter(SqliteSessionAdapter):
    """Adapter whose first commit lets a competing replica write the row first."""

    def __init__(self, session: Session, before_commit: Callable[[], None]) -> None:
        super().__init__(session)
        self._before_commit: Callable[[], None] | None = before_commit

    async def commit(self) -> None:
        hook, self._before_commit = self._before_commit, None
        if hook is not None:
            hook()
        await super().commit()


async def test_racing_duplicate_insert_dies_on_unique_index_with_200(
    sqlite_sessions: sessionmaker[Session],
) -> None:
    """Both replicas pass the existence check; the loser's IntegrityError is a 200."""
    _seed_subscription(sqlite_sessions)

    def other_replica_wins() -> None:
        with sqlite_sessions() as session:
            seed_invoice(session, tenant_id=TENANT, stripe_invoice_id="in_123")

    app.dependency_overrides[get_db] = _db_override(
        sqlite_sessions, lambda session: _RaceCommitAdapter(session, other_replica_wins)
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            payload = _event_bytes("evt_inv_race", "invoice.paid", make_stripe_invoice().to_dict())
            response = await _post(client, payload)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"received": True}
    # The failed processing is not marked seen and publishes nothing.
    assert "evt_inv_race" not in webhooks._seen_event_ids
    assert _published_notification_ids() == []
    with sqlite_sessions() as session:
        assert len(session.scalars(select(Invoice)).all()) == 1


# === payment_method.attached ===


async def test_payment_method_attached_creates_default_card(
    sqlite_client: AsyncClient, sqlite_sessions: sessionmaker[Session]
) -> None:
    """The happy path: the tenant is resolved via the Stripe customer, first card is default."""
    _seed_subscription(sqlite_sessions)
    payload = _event_bytes(
        "evt_pm_1", "payment_method.attached", make_stripe_payment_method().to_dict()
    )

    response = await _post(sqlite_client, payload)

    assert response.status_code == 200
    with sqlite_sessions() as session:
        row = session.scalars(select(PaymentMethod)).one()
        assert row.tenant_id == TENANT
        assert row.stripe_payment_method_id == "pm_123"
        assert row.card_brand == "visa"
        assert row.card_last4 == "4242"
        assert row.is_default is True


async def test_payment_method_attached_replay_on_second_replica_is_noop(
    sqlite_client: AsyncClient, sqlite_sessions: sessionmaker[Session]
) -> None:
    """A cold-LRU replay lands on the stripe_payment_method_id guard: 200, one row."""
    _seed_subscription(sqlite_sessions)
    payload = _event_bytes(
        "evt_pm_2", "payment_method.attached", make_stripe_payment_method().to_dict()
    )

    first = await _post(sqlite_client, payload)
    assert first.status_code == 200

    webhooks._seen_event_ids.clear()
    with patch.object(metrics.billing, "webhook_duplicate") as duplicate_metric:
        second = await _post(sqlite_client, payload)

    assert second.status_code == 200
    duplicate_metric.assert_called_once_with()
    with sqlite_sessions() as session:
        rows = session.scalars(select(PaymentMethod)).all()
        assert len(rows) == 1
        assert rows[0].is_default is True
