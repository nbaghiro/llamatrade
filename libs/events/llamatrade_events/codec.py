"""Proto codec: domain message ⇄ EventEnvelope ⇄ bytes.

Proto is the source of truth for event data. The envelope carries the serialized
domain message in ``payload`` and an :class:`EventType` discriminator; the codec
keeps a registry of ``EventType → message class`` so consumers parse the payload
without ``Any``/type-url machinery. The transport only ever sees the resulting
bytes — that separation is what keeps the backend swappable.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import cast
from uuid import uuid4

from google.protobuf.message import Message

from llamatrade_proto.generated import events_pb2

EventEnvelope = events_pb2.EventEnvelope
_EventTypeValue = events_pb2.EventType.ValueType


class UnknownEventTypeError(Exception):
    """No payload class is registered for an envelope's ``EventType``.

    Signals schema skew — e.g. a newer producer emitting a type this (older)
    consumer doesn't know. Distinct so a consumer can route it to a DLQ instead
    of treating it as a transient failure to retry forever.
    """


# EventType (int) → the proto message class carried in payload.
_PAYLOAD_REGISTRY: dict[int, type[Message]] = {}


def register_payload(event_type: int, message_cls: type[Message]) -> None:
    """Register the payload message class for an EventType (idempotent)."""
    existing = _PAYLOAD_REGISTRY.get(event_type)
    if existing is not None and existing is not message_cls:
        raise ValueError(
            f"EventType {event_type} already registered to {existing.__name__}, "
            f"cannot re-register to {message_cls.__name__}"
        )
    _PAYLOAD_REGISTRY[event_type] = message_cls


def _now_ms() -> int:
    return int(time.time() * 1000)


def make_envelope(
    event_type: int,
    payload: Message,
    *,
    event_id: str | None = None,
    tenant_id: str = "",
    user_id: str = "",
    metadata: Mapping[str, str] | None = None,
    created_at_unix_ms: int | None = None,
) -> EventEnvelope:
    """Wrap a domain message in an EventEnvelope. ``event_id`` defaults to a uuid4."""
    env = EventEnvelope(
        id=event_id or uuid4().hex,
        # The discriminator is an int in our API; proto stubs type the field as the
        # enum's ValueType (an int subtype) — narrow at this one boundary.
        type=cast("_EventTypeValue", event_type),
        tenant_id=tenant_id,
        user_id=user_id,
        created_at_unix_ms=created_at_unix_ms if created_at_unix_ms is not None else _now_ms(),
        payload=payload.SerializeToString(),
    )
    if metadata:
        env.metadata.update(metadata)
    return env


def parse_payload(envelope: EventEnvelope) -> Message:
    """Parse ``envelope.payload`` into its registered domain message."""
    cls = _PAYLOAD_REGISTRY.get(envelope.type)
    if cls is None:
        raise UnknownEventTypeError(f"No payload registered for EventType {envelope.type}")
    return cls.FromString(envelope.payload)


def encode_envelope(envelope: EventEnvelope) -> bytes:
    return envelope.SerializeToString()


def decode_envelope(data: bytes) -> EventEnvelope:
    return EventEnvelope.FromString(data)
