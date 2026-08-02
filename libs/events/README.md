# llamatrade_events

The one library that owns **every event in the system** — the proto envelope, the
streaming transport, the codec, the bus, the typed catalog, the durable-consumer
runtime, and the gRPC fan-out. Services import from here and nothing else for
events; there is no per-service event wrapper.

## Layers

```
proto (events.proto)   EventEnvelope + EventType — the source of truth for event data
   │
transport/             EventTransport: opaque bytes ⇄ backend (Kafka adapter via
   │                   aiokafka; swap backends by writing one more adapter)
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
   backend, so swapping Kafka for another broker is a single new adapter.

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

Channels (keys, topics, delivery) are declared once in `channels.py`; the catalog
wraps them with typed publish/tail/consume. Topic retention and partition counts
are provisioned in Terraform, not declared in code. The codec registry is wired by
importing the catalog, so `parse_payload(envelope)` returns the right message type.

## Transport reliability

Every aiokafka client the transport builds is started under a bounded wait and
then proven live with one metadata round-trip. A broker answers a rejected
OAUTHBEARER token in band (KIP-255: `error_code=0` with `status=invalid_token`)
and aiokafka reads that as a successful handshake, so without the bound `publish`
and `consume` hang forever with no exception, no reconnect and no metric (the
wrong-audience and clock-skew failure modes of Workload Identity). A client that
misses either phase raises `TransportAuthError` and increments
`llamatrade_events_client_start_failures_total{kind,reason}`.

Readers keep their retry-forever contract: `tail` and `consume` treat that error
as any other reconnectable fault, so the money path never gives up. The operator
signal for a permanently broken credential is a run of consecutive failures to
start, logged at ERROR with the failure class named and counted by
`llamatrade_events_broken_credentials_total{stream,mode}`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `KAFKA_CLIENT_START_TIMEOUT_SECONDS` | `30` | Budget for a client's connect + auth phase, and separately for its liveness probe |
| `KAFKA_AUTH_FAILURE_ALERT_THRESHOLD` | `5` | Consecutive reader start failures before the broken-credentials signal |

## Testing

Unit tests run without Docker via an in-memory `FakeTransport` (see
`tests/conftest.py`). Integration tests run against a real Kafka broker — either
one provided via `KAFKA_BOOTSTRAP_SERVERS` or a throwaway testcontainers broker —
and are marked and gated.

```bash
cd libs/events && pytest                 # unit (FakeTransport)
cd libs/events && pytest -m integration  # real Kafka (Docker / KAFKA_BOOTSTRAP_SERVERS)
```
