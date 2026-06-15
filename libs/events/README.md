# llamatrade_events

The one library that owns **every event in the system** — the proto envelope, the
streaming transport, the codec, the bus, the typed catalog, the durable-consumer
runtime, and the gRPC fan-out. Services import from here and nothing else for
events; there is no per-service event wrapper.

## Layers

```
proto (events.proto)   EventEnvelope + EventType — the source of truth for event data
   │
transport/             EventTransport: opaque bytes ⇄ backend (Redis Streams adapter;
   │                   swap to Kafka by writing one more adapter)
codec.py               domain proto ⇄ EventEnvelope ⇄ bytes (registry keyed by EventType)
   │
bus.py                 EventBus: publish / tail / consume (codec + transport)
   │
catalog/               typed produce/consume surface services call directly
   │                   OrderEvents · PositionEvents · ProgressEvents · FillEvents · BarEvents
runtime                StreamConsumer (durable consume + dedupe + DLQ + lag)
                       StreamFanout   (one stream → many gRPC client streams)
idempotency.py         derive_event_id + DedupStore (effective-once)
```

Two design rules are load-bearing:

1. **Proto is the source of truth for event data.** Every event is an
   `EventEnvelope` carrying a serialized domain proto in `payload` plus an
   `EventType` discriminator — the same messages the gRPC edge streams. No
   `google.protobuf.Any`; a plain bytes + discriminator pair is simpler and the
   most transport-portable shape.
2. **The transport is pluggable.** `EventTransport` moves opaque bytes with an
   opaque cursor and an optional partition key. Nothing above it knows the
   backend, so replacing Redis Streams with Kafka is a single new adapter.

## Usage

```python
from llamatrade_events import OrderEvents, FillEvents, ProgressEvents, BarEvents

# Producer — trading order update → per-session UI stream
orders = OrderEvents()
await orders.publish(session_id, order_update, tenant_id=ctx.tenant_id)

# Consumer — trading gRPC servicer fans out to a browser, replaying the gap
async for cursor, update in orders.tail(session_id, from_cursor=client_cursor):
    yield to_grpc(update, cursor)

# Durable — trading → portfolio ledger (idempotent on client_order_id)
fills = FillEvents()
await fills.publish_fill(ledger_fill)

# Durable consume — portfolio ingestion (dedupe + DLQ + lag, all owned by the runtime)
consumer = fills.consumer(consumer_name="portfolio-1", dedup=pg_dedup_store)
await consumer.run(handle_envelope, stop_event=stop)
```

Channels (keys, retention, delivery) are declared once in `channels.py`; the
catalog wraps them with typed publish/tail/consume. The codec registry is wired by
importing the catalog, so `parse_payload(envelope)` returns the right message type.

## Testing

Unit tests run without Docker via an in-memory `FakeTransport` (see
`tests/conftest.py`). Integration tests against real Redis are marked and gated.

```bash
cd libs/events && pytest                 # unit (FakeTransport)
cd libs/events && pytest -m integration  # real Redis (Docker)
```
