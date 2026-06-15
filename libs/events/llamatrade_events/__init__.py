"""llamatrade_events — the one library that owns every event in the system.

Layers, bottom to top:

- **proto** (``events.proto``) is the source of truth for event data: the
  ``EventEnvelope`` and the ``EventType`` discriminator.
- **transport** (:class:`EventTransport`) moves opaque bytes; the Redis Streams
  adapter is the default, and the seam is what makes a Kafka swap a one-file job.
- **codec** turns a domain proto ⇄ envelope ⇄ bytes (registry keyed by EventType).
- **bus** (:class:`EventBus`) ties codec to transport: publish / tail / consume.
- **catalog** is the typed, public produce/consume surface services call directly
  (``OrderEvents``, ``PositionEvents``, ``ProgressEvents``, ``FillEvents``,
  ``BarEvents``).
- **runtime**: :class:`StreamConsumer` (durable consume + dedupe + DLQ + lag) and
  :class:`StreamFanout` (one stream → many gRPC client streams).
- **idempotency**: :func:`derive_event_id` + :class:`DedupStore` for effective-once.

Services import from here and nothing else for events.
"""

from __future__ import annotations

from llamatrade_events.bus import EventBus
from llamatrade_events.catalog import (
    BarEvents,
    FillEvents,
    OrderEvents,
    PositionEvents,
    ProgressEvents,
)
from llamatrade_events.channels import (
    BACKTEST_PROGRESS,
    BARS,
    LEDGER_FILLS,
    ORDERS,
    POSITIONS,
    Channel,
    Delivery,
)
from llamatrade_events.codec import (
    decode_envelope,
    encode_envelope,
    make_envelope,
    parse_payload,
    register_payload,
)
from llamatrade_events.consumer import StreamConsumer
from llamatrade_events.fanout import StreamFanout
from llamatrade_events.idempotency import (
    DedupStore,
    InMemoryDedupStore,
    derive_event_id,
)
from llamatrade_events.transport import (
    CURSOR_BEGIN,
    CURSOR_NEW,
    Cursor,
    EventTransport,
    RedisStreamsTransport,
)
from llamatrade_proto.generated import events_pb2

# Proto aliases so callers reference the envelope/type without a second import.
EventEnvelope = events_pb2.EventEnvelope
EventType = events_pb2.EventType

__all__ = [
    # channels
    "BACKTEST_PROGRESS",
    "BARS",
    "CURSOR_BEGIN",
    "CURSOR_NEW",
    "LEDGER_FILLS",
    "ORDERS",
    "POSITIONS",
    # catalog
    "BarEvents",
    "Channel",
    "Cursor",
    "DedupStore",
    "Delivery",
    # bus / transport
    "EventBus",
    "EventEnvelope",
    "EventTransport",
    "EventType",
    "FillEvents",
    "InMemoryDedupStore",
    "OrderEvents",
    "PositionEvents",
    "ProgressEvents",
    "RedisStreamsTransport",
    # runtime
    "StreamConsumer",
    "StreamFanout",
    # codec / idempotency
    "decode_envelope",
    "derive_event_id",
    "encode_envelope",
    "make_envelope",
    "parse_payload",
    "register_payload",
]
