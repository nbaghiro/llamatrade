"""Event serialization round-trip tests.

Pins the fix for the old ``.strip('{"data":')`` serialization, which stripped
*characters* (not a prefix) and corrupted any payload beginning or ending with
those characters.
"""

from datetime import UTC, datetime
from uuid import uuid4

from llamatrade_common.events import Event, EventType


def _round_trip(event: Event) -> Event:
    return Event.from_redis_stream(event.to_redis_stream())


def test_round_trip_basic_fields() -> None:
    event = Event(
        type=EventType.ORDER_FILLED,
        tenant_id=uuid4(),
        user_id=uuid4(),
        data={"order_id": "abc", "symbol": "SPY", "qty": 50.0, "price": 480.0},
        metadata={"source_service": "trading", "correlation_id": "c-1"},
    )
    restored = _round_trip(event)
    assert restored.id == event.id
    assert restored.type == event.type
    assert restored.tenant_id == event.tenant_id
    assert restored.user_id == event.user_id
    assert restored.data == event.data
    assert restored.metadata == event.metadata


def test_round_trip_payload_with_stripped_characters() -> None:
    """The old strip-based codec corrupted exactly this shape of payload."""
    event = Event(
        type=EventType.BACKTEST_PROGRESS,
        # '{', '"', 'd', 'a', 't', ':' at the boundaries were eaten by .strip()
        data={"message": '{"data": nested-looking string}', "symbol": "data"},
    )
    restored = _round_trip(event)
    assert restored.data["message"] == '{"data": nested-looking string}'
    assert restored.data["symbol"] == "data"


def test_round_trip_unicode_and_empty_maps() -> None:
    event = Event(type=EventType.ALERT_TRIGGERED, data={"message": "résumé — 利益 ✓"})
    restored = _round_trip(event)
    assert restored.data["message"] == "résumé — 利益 ✓"
    assert restored.metadata == {}

    empty = _round_trip(Event(type=EventType.USER_CREATED))
    assert empty.data == {}
    assert empty.metadata == {}


def test_round_trip_optional_ids_absent() -> None:
    event = Event(type=EventType.PRICE_UPDATE)
    fields = event.to_redis_stream()
    assert fields["tenant_id"] == ""
    assert fields["user_id"] == ""
    restored = Event.from_redis_stream(fields)
    assert restored.tenant_id is None
    assert restored.user_id is None


def test_stream_fields_are_flat_strings() -> None:
    """XADD requires flat string fields — no nested values may leak through."""
    event = Event(
        type=EventType.ORDER_SUBMITTED,
        timestamp=datetime(2026, 6, 12, 14, 30, tzinfo=UTC),
        data={"qty": 1.5, "total_trades": 3},
    )
    fields = event.to_redis_stream()
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in fields.items())
    assert fields["timestamp"] == "2026-06-12T14:30:00+00:00"
