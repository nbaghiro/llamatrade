"""Webhook delivery tracking: failure counting, reset, auto-disable."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from llamatrade_db.models.notification import Webhook

from src.channels.webhook import WebhookResult
from src.delivery import WEBHOOK_DISABLE_THRESHOLD, DeliveryDispatcher

_OK = WebhookResult(ok=True, status_code=200, error=None)
_FAIL = WebhookResult(ok=False, status_code=500, error=None)


def _dispatcher(threshold: int = WEBHOOK_DISABLE_THRESHOLD) -> DeliveryDispatcher:
    return DeliveryDispatcher(MagicMock(), disable_threshold=threshold)


def _webhook(failure_count: int = 0) -> Webhook:
    return Webhook(
        id=uuid4(),
        tenant_id=uuid4(),
        name="w",
        url="https://example.test",
        events=[],
        is_active=True,
        failure_count=failure_count,
        created_by=uuid4(),
    )


def test_success_resets_failure_count() -> None:
    webhook = _webhook(failure_count=7)
    disabled = _dispatcher()._track_webhook(webhook, _OK)
    assert not disabled
    assert webhook.failure_count == 0
    assert webhook.last_status_code == 200
    assert webhook.is_active


def test_failure_increments() -> None:
    webhook = _webhook()
    disabled = _dispatcher()._track_webhook(webhook, _FAIL)
    assert not disabled
    assert webhook.failure_count == 1
    assert webhook.is_active


def test_disable_at_threshold_fires_once() -> None:
    webhook = _webhook(failure_count=1)
    dispatcher = _dispatcher(threshold=2)
    disabled = dispatcher._track_webhook(webhook, _FAIL)
    assert disabled
    assert not webhook.is_active
    # Further failures on the (already inactive) endpoint do not re-notify.
    assert not dispatcher._track_webhook(webhook, _FAIL)


def test_default_threshold() -> None:
    assert WEBHOOK_DISABLE_THRESHOLD == 25


def test_recovery_after_reenable() -> None:
    webhook = _webhook(failure_count=1)
    dispatcher = _dispatcher(threshold=2)
    assert dispatcher._track_webhook(webhook, _FAIL)
    # Operator re-enables; a success clears the slate.
    webhook.is_active = True
    assert not dispatcher._track_webhook(webhook, _OK)
    assert webhook.failure_count == 0
