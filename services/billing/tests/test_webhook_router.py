"""Router-level tests for the Stripe webhook endpoint.

These drive the real route (signature verification, dedup, error
classification) over ASGI; handler internals are covered separately in
test_webhook_handlers.py.
"""

import hashlib
import hmac
import json
import time
from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import OperationalError

from llamatrade_telemetry import metrics

from src.routers import webhooks

WEBHOOK_SECRET = "whsec_test_secret"
WEBHOOK_PATH = "/webhooks/stripe"


def _sign(payload: bytes, secret: str, timestamp: int | None = None) -> str:
    """Build a real Stripe-Signature header for the payload."""
    ts = timestamp if timestamp is not None else int(time.time())
    signed = f"{ts}.".encode() + payload
    mac = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def _event_payload(
    event_id: str = "evt_test_1",
    event_type: str = "customer.subscription.updated",
) -> bytes:
    return json.dumps(
        {
            "id": event_id,
            "object": "event",
            "type": event_type,
            "data": {"object": {"id": "sub_123", "object": "subscription", "status": "active"}},
        }
    ).encode()


@pytest.fixture(autouse=True)
def _reset_dedup() -> Iterator[None]:
    """Isolate the in-process dedup LRU between tests."""
    webhooks._seen_event_ids.clear()
    yield
    webhooks._seen_event_ids.clear()


@pytest.fixture
def _verified_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.delenv("ENVIRONMENT", raising=False)


async def test_missing_signature_header_returns_400(
    client: AsyncClient, _verified_env: None
) -> None:
    """A request without a stripe-signature header is rejected."""
    response = await client.post(WEBHOOK_PATH, content=_event_payload())
    assert response.status_code == 400
    assert "stripe-signature" in response.json()["detail"]


async def test_bad_signature_returns_400_and_records_metric(
    client: AsyncClient, _verified_env: None
) -> None:
    """A forged signature is rejected and counted."""
    payload = _event_payload()
    with patch.object(metrics.billing, "webhook_signature_failure") as failure_metric:
        response = await client.post(
            WEBHOOK_PATH,
            content=payload,
            headers={"stripe-signature": _sign(payload, "whsec_wrong_secret")},
        )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid webhook signature"
    failure_metric.assert_called_once_with()


async def test_valid_signature_dispatches_handler(client: AsyncClient, _verified_env: None) -> None:
    """A correctly signed handled event reaches its handler exactly once."""
    payload = _event_payload()
    handler = AsyncMock()
    with patch.object(webhooks, "_handle_subscription_updated", handler):
        response = await client.post(
            WEBHOOK_PATH,
            content=payload,
            headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET)},
        )
    assert response.status_code == 200
    assert response.json() == {"received": True}
    handler.assert_awaited_once()


async def test_duplicate_event_is_noop_second_time(
    client: AsyncClient, _verified_env: None
) -> None:
    """Redelivery of an already-processed event id skips the handler."""
    payload = _event_payload(event_id="evt_dup_1")
    headers = {"stripe-signature": _sign(payload, WEBHOOK_SECRET)}
    handler = AsyncMock()
    with (
        patch.object(webhooks, "_handle_subscription_updated", handler),
        patch.object(metrics.billing, "webhook_duplicate") as duplicate_metric,
    ):
        first = await client.post(WEBHOOK_PATH, content=payload, headers=headers)
        second = await client.post(WEBHOOK_PATH, content=payload, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    handler.assert_awaited_once()
    duplicate_metric.assert_called_once_with()


async def test_distinct_event_ids_both_dispatch(client: AsyncClient, _verified_env: None) -> None:
    """Dedup keys on event id, not event type."""
    handler = AsyncMock()
    with patch.object(webhooks, "_handle_subscription_updated", handler):
        for event_id in ("evt_a", "evt_b"):
            payload = _event_payload(event_id=event_id)
            response = await client.post(
                WEBHOOK_PATH,
                content=payload,
                headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET)},
            )
            assert response.status_code == 200
    assert handler.await_count == 2


async def test_transient_handler_failure_returns_500_and_is_retryable(
    client: AsyncClient, _verified_env: None
) -> None:
    """A DB outage yields 500 (Stripe retries) and the retry is not deduped."""
    payload = _event_payload(event_id="evt_transient_1")
    headers = {"stripe-signature": _sign(payload, WEBHOOK_SECRET)}
    failing = AsyncMock(side_effect=OperationalError("SELECT 1", {}, Exception("db down")))
    with patch.object(webhooks, "_handle_subscription_updated", failing):
        response = await client.post(WEBHOOK_PATH, content=payload, headers=headers)
    assert response.status_code == 500

    succeeding = AsyncMock()
    with patch.object(webhooks, "_handle_subscription_updated", succeeding):
        retry = await client.post(WEBHOOK_PATH, content=payload, headers=headers)
    assert retry.status_code == 200
    succeeding.assert_awaited_once()


async def test_permanent_handler_failure_returns_200(
    client: AsyncClient, _verified_env: None
) -> None:
    """A logic error is swallowed with a 200 so Stripe stops redelivering."""
    payload = _event_payload(event_id="evt_permanent_1")
    handler = AsyncMock(side_effect=ValueError("bad payload shape"))
    with patch.object(webhooks, "_handle_subscription_updated", handler):
        response = await client.post(
            WEBHOOK_PATH,
            content=payload,
            headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET)},
        )
    assert response.status_code == 200
    assert response.json() == {"received": True}


async def test_unhandled_event_type_is_noop(client: AsyncClient, _verified_env: None) -> None:
    """Event types we don't subscribe to are acknowledged without dispatch."""
    payload = _event_payload(event_type="charge.succeeded")
    with patch.object(metrics.billing, "webhook_received") as received_metric:
        response = await client.post(
            WEBHOOK_PATH,
            content=payload,
            headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET)},
        )
    assert response.status_code == 200
    received_metric.assert_not_called()


async def test_missing_secret_in_production_returns_503(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Production with no webhook secret fails closed."""
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    payload = _event_payload()
    handler = AsyncMock()
    with patch.object(webhooks, "_handle_subscription_updated", handler):
        response = await client.post(
            WEBHOOK_PATH,
            content=payload,
            headers={"stripe-signature": _sign(payload, WEBHOOK_SECRET)},
        )
    assert response.status_code == 503
    handler.assert_not_awaited()


async def test_missing_secret_in_staging_returns_503(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Staging is held to the same fail-closed bar as production."""
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "staging")
    response = await client.post(WEBHOOK_PATH, content=_event_payload())
    assert response.status_code == 503


async def test_missing_secret_in_dev_dispatches_unverified(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Dev without a secret still dispatches, with a loud warning."""
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    payload = _event_payload(event_id="evt_dev_1")
    handler = AsyncMock()
    with (
        patch.object(webhooks, "_handle_subscription_updated", handler),
        caplog.at_level("WARNING", logger="src.routers.webhooks"),
    ):
        response = await client.post(
            WEBHOOK_PATH,
            content=payload,
            headers={"stripe-signature": "t=0,v1=unverified"},
        )
    assert response.status_code == 200
    handler.assert_awaited_once()
    assert any("skipping signature verification" in r.message for r in caplog.records)


async def test_missing_secret_in_dev_invalid_json_returns_400(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dev unverified path still rejects malformed payloads."""
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    response = await client.post(
        WEBHOOK_PATH,
        content=b"not-json{",
        headers={"stripe-signature": "t=0,v1=unverified"},
    )
    assert response.status_code == 400


def test_dedup_lru_is_bounded() -> None:
    """The seen-event set evicts oldest ids at its cap."""
    webhooks._seen_event_ids.clear()
    for i in range(webhooks._SEEN_EVENTS_MAX + 10):
        webhooks._mark_event_seen(f"evt_{i}")
    assert len(webhooks._seen_event_ids) == webhooks._SEEN_EVENTS_MAX
    assert not webhooks._event_seen("evt_0")
    assert webhooks._event_seen(f"evt_{webhooks._SEEN_EVENTS_MAX + 9}")


def test_transient_classification_excludes_logic_errors() -> None:
    """Only infra-shaped exceptions are classified as retryable."""
    assert OperationalError("SELECT 1", {}, Exception("x")).__class__ in webhooks._TRANSIENT_ERRORS
    assert ValueError not in webhooks._TRANSIENT_ERRORS
    assert KeyError not in webhooks._TRANSIENT_ERRORS
