"""Proto codec: register / make_envelope / parse / encode-decode."""

from __future__ import annotations

import pytest

from llamatrade_events.codec import (
    decode_envelope,
    encode_envelope,
    make_envelope,
    parse_payload,
    register_payload,
)
from llamatrade_proto.generated import events_pb2, trading_pb2

ORDER_FILLED = events_pb2.EVENT_TYPE_ORDER_FILLED


def test_make_envelope_sets_fields() -> None:
    upd = trading_pb2.OrderUpdate(event_type="filled")
    env = make_envelope(
        ORDER_FILLED, upd, tenant_id="t1", user_id="u1", metadata={"trace_id": "abc"}
    )
    assert env.type == ORDER_FILLED
    assert env.tenant_id == "t1"
    assert env.user_id == "u1"
    assert env.metadata["trace_id"] == "abc"
    assert env.id  # defaulted uuid4
    assert env.created_at_unix_ms > 0
    assert env.payload == upd.SerializeToString()


def test_explicit_event_id_and_timestamp_preserved() -> None:
    env = make_envelope(
        ORDER_FILLED,
        trading_pb2.OrderUpdate(),
        event_id="fixed-id",
        created_at_unix_ms=123,
    )
    assert env.id == "fixed-id"
    assert env.created_at_unix_ms == 123


def test_encode_decode_round_trip() -> None:
    upd = trading_pb2.OrderUpdate(event_type="filled")
    env = make_envelope(ORDER_FILLED, upd, tenant_id="t9")
    back = decode_envelope(encode_envelope(env))
    assert back.tenant_id == "t9"
    assert back.type == ORDER_FILLED


def test_parse_payload_returns_registered_type() -> None:
    # Importing any llamatrade_events module runs the package __init__, which
    # imports the catalog and registers OrderUpdate for the order EventTypes.
    upd = trading_pb2.OrderUpdate(event_type="filled")
    env = make_envelope(ORDER_FILLED, upd)
    parsed = parse_payload(env)
    assert isinstance(parsed, trading_pb2.OrderUpdate)
    assert parsed.event_type == "filled"


def test_parse_unregistered_raises() -> None:
    env = make_envelope(events_pb2.EVENT_TYPE_UNSPECIFIED, trading_pb2.OrderUpdate())
    with pytest.raises(KeyError):
        parse_payload(env)


def test_register_conflict_raises() -> None:
    register_payload(ORDER_FILLED, trading_pb2.OrderUpdate)  # idempotent re-register
    with pytest.raises(ValueError, match="already registered"):
        register_payload(ORDER_FILLED, trading_pb2.PositionUpdate)
