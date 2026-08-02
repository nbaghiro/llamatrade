"""Template rendering: every category renders non-empty, fields interpolate."""

from __future__ import annotations

import pytest

from llamatrade_proto.generated import events_pb2

from src.preferences import CATEGORY_SPECS
from src.templates import render

_E = events_pb2


@pytest.mark.parametrize("category", sorted(CATEGORY_SPECS))
def test_every_category_renders(category: int) -> None:
    rendered = render(events_pb2.NotificationEvent(category=category))
    assert rendered.title
    assert rendered.message
    assert rendered.subject.startswith("LlamaTrade: ")


def test_unknown_category_renders_fallback(self_category: int = 9999) -> None:
    rendered = render(events_pb2.NotificationEvent(category=self_category, reason="odd"))
    assert rendered.title == "Notification"
    assert rendered.message == "odd"


def test_symbol_interpolates() -> None:
    event = events_pb2.NotificationEvent(
        category=_E.NOTIFICATION_CATEGORY_ORDER_FILLED, symbol="AAPL", amount="1500.25"
    )
    rendered = render(event)
    assert "AAPL" in rendered.message
    assert "$1500.25" in rendered.message


def test_reason_interpolates() -> None:
    event = events_pb2.NotificationEvent(
        category=_E.NOTIFICATION_CATEGORY_SLEEVE_FROZEN, reason="quantity mismatch on TLT"
    )
    rendered = render(event)
    assert "quantity mismatch on TLT" in rendered.message


def test_missing_fields_degrade_readably() -> None:
    rendered = render(
        events_pb2.NotificationEvent(category=_E.NOTIFICATION_CATEGORY_ORDER_REJECTED)
    )
    assert "  " not in rendered.message
    assert rendered.message.endswith(".")
