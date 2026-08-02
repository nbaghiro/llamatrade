"""Shared strategy test fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _fake_notification_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the shared notification publisher at an in-memory stream."""
    from llamatrade_events import EventBus
    from llamatrade_events.catalog import notifications as notifications_module
    from llamatrade_events.catalog.notifications import NotificationEvents
    from llamatrade_events.testing import FakeTransport

    monkeypatch.setattr(
        notifications_module,
        "_shared",
        NotificationEvents(bus=EventBus(FakeTransport())),
    )
