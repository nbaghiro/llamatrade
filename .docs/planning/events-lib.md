# `libs/events` (`llamatrade_events`) — The Single Event System

Status: **IMPLEMENTED** (2026-06-16). `llamatrade_events` is the system's **sole**
event library — proto schemas, pluggable transport, the typed produce/consume
catalog, the consumer runtime, and the gRPC stream fan-out. Services call it
**directly** (like `init_telemetry`), with **no per-service
publisher/subscriber/bridge wrapper**. The predecessor `llamatrade_common.events`
(`Event`/`EventBus`/`EventType`) has been **deleted**, and so has the telemetry
`instrumentation/eventbus.py` shim (event metrics now live in the lib's
`observability.py`, surfaced as `events_*`).

All streams are migrated: `ledger:fills` (`FillEvents`, proto, durable consumer
group), `trading:orders/positions:*` (`OrderEvents`/`PositionEvents`),
`backtest:progress:*` (`ProgressEvents`), `market:bars:1m` (`BarEvents`).
Successor to the completed [redis-streams-migration](redis-streams-migration.md).

## Three principles
1. **Proto is the source of truth for event data.** Every payload is a proto
   message (reusing the ones the streaming RPCs already define); the bus and the
   gRPC edge share one typed contract — Python + TS codegen, `buf` breaking
   checks. Nothing's locked, so even the ledger fill contract becomes proto (the
   old flat-fields exception is gone).
2. **The transport is pluggable.** Redis Streams sits behind one `EventTransport`
   interface; a Kafka swap is one adapter and **zero** changes elsewhere.
3. **One home, used directly.** All event code lives here. A producer calls
   `OrderEvents().publish_filled(...)`; a consumer calls
   `FillEvents().consume(group, handler)`. No service writes a wrapper class.

---

## 1. What moves OUT of services and INTO the lib

The whole point: services keep **domain logic** (what an event *means*), the lib
owns **everything about moving events**.

| Today (per-service, bespoke) | Moves into `libs/events` as |
|---|---|
| trading `streaming/publisher.py` (`TradingEventPublisher`, `OrderUpdate`/`PositionUpdate`) | `catalog.OrderEvents` / `PositionEvents` (typed publish/tail) |
| trading `streaming/subscriber.py` (`TradingEventSubscriber`) | the same catalog's `tail()` helpers |
| trading `ledger_events.py` payload builders + publish_ledger_fill | `catalog.FillEvents` (publish fill/reservation) |
| backtest `progress.py` (`ProgressPublisher`/`Subscriber`) | `catalog.ProgressEvents` (the rate-limit/ETA stays in backtest) |
| market-data `bar_events.py` + `bus_bridge.py` | `catalog.BarEvents` + `fanout` |
| market-data `streaming/manager.py` (`StreamManager`) | `fanout.StreamFanout` (generic gRPC client fan-out) |
| portfolio `tasks/fill_ingestion.py` consume loop + lag monitor | `consumer.StreamConsumer` (the handler stays in portfolio) |
| `llamatrade_common.events` (`Event`/`EventType` Pydantic + `EventBus`) | proto `EventEnvelope` + `bus.py` |
| duplicated `LEDGER_FILLS_STREAM`, stream-key constants | `channels.py` (one registry) |

What **stays** in services: the domain handlers (append-to-ledger, send-email,
meter-usage), the rate-limit/ETA policy, and the gRPC servicer shells (they just
forward the lib's proto).

---

## 2. Lib structure

```
libs/events/llamatrade_events/
  __init__.py            # public API: the catalog + consumer + fanout + channels
  bus.py                 # EventBus: proto<->bytes (codec) over a Transport (internal-ish)
  codec.py               # EventEnvelope proto <-> bytes; Any pack/unpack; raw-payload mode
  channels.py            # registry: name · delivery mode · maxlen · partition key · envelope|raw
  catalog/               # THE typed produce/consume API per event family
    orders.py            #   OrderEvents.publish_*(), .tail(session_id) -> OrderUpdate
    positions.py
    fills.py             #   FillEvents.publish_fill/reservation(), .consume(group, handler)
    progress.py          #   ProgressEvents.publish(), .tail(backtest_id)
    bars.py              #   BarEvents.publish(), .tail()
    notifications.py     #   (new) NotificationEvents
    billing.py / users.py / strategy.py   # (new, as the taxonomy lights up)
  consumer.py            # StreamConsumer runtime: group, ack, retry, DLQ, lag, drain
  fanout.py              # StreamFanout: one bus stream -> N gRPC client queues
  idempotency.py         # derive_event_id() + DedupStore Protocol
  observability.py       # registers lag/published/DLQ via llamatrade_telemetry
  transport/
    base.py              # EventTransport Protocol  ← the swap seam
    redis_streams.py     # current behavior, behind the Protocol
    # kafka.py           # future, no other changes
libs/proto/protos/events/
  envelope.proto         # EventEnvelope + EventType
  trading_events.proto   # OrderUpdate, PositionUpdate, FillEvent, ReservationEvent
  backtest_events.proto  # BacktestProgressUpdate (reuse existing)
  market_events.proto    # Bar (reuse existing)
  # notification/billing/user events as added
```

`bus.py` ties codec+transport; the **catalog is the public face** — services
import `OrderEvents`, `FillEvents`, etc., never `EventBus` directly.

---

## 3. Seam #1 — proto schemas (source of truth)

```proto
message EventEnvelope {
  string id = 1;                       // uuid — correlation + idempotency seed
  EventType type = 2;
  string tenant_id = 3;
  string user_id = 4;
  google.protobuf.Timestamp timestamp = 5;
  google.protobuf.Any payload = 6;     // a reused domain message
  map<string, string> metadata = 7;    // correlation_id / trace_id / source_service
}
```
- Payloads **reuse** `OrderUpdate` / `Bar` / `BacktestProgressUpdate` (already in
  the service protos) via `Any`; new families add messages. One definition per
  event, used on the bus **and** at the gRPC edge → the servicer stops mapping
  and just `yield env.payload.unpack(OrderUpdate)`.
- **Envelope is optional per channel:** high-volume **bars ride as bare `Bar`
  proto bytes** (no envelope overhead) — proto is still the schema. Everything
  else rides the full `EventEnvelope`.
- Browser gets typed TS event payloads from the same `make proto`; `buf`
  breaking-change checks now cover events.

---

## 4. Seam #2 — pluggable transport

```python
class EventTransport(Protocol):
    async def publish(self, stream, value: bytes, *, key=None, maxlen=None) -> str: ...
    def tail(self, stream, *, from_cursor) -> AsyncIterator[tuple[str, bytes]]: ...   # fan-out
    async def ensure_group(self, stream, group) -> None: ...
    def consume(self, stream, group, consumer) -> AsyncIterator[tuple[str, bytes]]: ...# durable
    async def ack(self, stream, group, cursor) -> None: ...
    async def pending(self, stream, group) -> int: ...
    async def trim(self, stream, maxlen) -> None: ...
    async def close(self) -> None: ...
```
- Carries **opaque `bytes`** + **opaque `cursor`** + a partition **`key`**. The
  codec owns proto; the transport never sees it.
- Mode mapping: **fan-out = own group, durable = shared group.** Redis specifics
  (`XAUTOCLAIM` reclaim, per-publish `MAXLEN`) vs Kafka (auto-rebalance, retention
  config) are **absorbed inside each adapter** — nothing above notices.
- **Swap test:** add `KafkaTransport`, set `EVENTS_TRANSPORT=kafka`, done.

| | Redis | Kafka |
|---|---|---|
| fan-out / durable | own group / shared group | own group / shared group |
| failover | `XAUTOCLAIM` | rebalance |
| trim | per-publish `MAXLEN` | topic retention |
| cursor | `1697-0` | `partition:offset` |

---

## 5. The catalog — how services use it (the "no wrapper" payoff)

Each event family is a thin, typed facade over `EventBus`. Examples:

```python
# trading — producer (no TradingEventPublisher anymore)
from llamatrade_events import OrderEvents
await OrderEvents().publish_filled(session_id, order)        # builds proto + envelope + publishes

# trading servicer — StreamOrderUpdates (no subscriber wrapper)
async for cursor, order in OrderEvents().tail(session_id, from_cursor=req.cursor):
    yield order                                              # already the proto payload

# portfolio — durable fill consumer (no fill_ingestion loop)
await FillEvents().consume(group="portfolio-ledger", consumer=pod_id, handler=ingest_fill)
#   StreamConsumer owns group/ack/retry/DLQ/lag; ingest_fill is the only service code

# market-data — bars + gRPC fan-out (no bar_events / bus_bridge / StreamManager)
await BarEvents().publish(bar)
fan = StreamFanout(BarEvents().tail())                       # one bus stream -> many clients
async for bar in fan.subscribe(symbols): yield bar

# notification — the new second consumer, trivially
await OrderEvents().consume(group="notifications", consumer=pod, handler=email_on_fill)
```

`StreamFanout` generalizes market-data's `StreamManager` (per-client queues,
backpressure-drop) so trading order/position streaming and market-data bar
streaming use **one** fan-out, not two.

---

## 6. Per-service result

| Service | Before | After |
|---|---|---|
| trading | `streaming/{publisher,subscriber}.py`, `ledger_events.py` | `OrderEvents`/`PositionEvents`/`FillEvents` calls; files deleted |
| portfolio | `tasks/fill_ingestion.py` consume+lag plumbing | `FillEvents().consume(handler=...)`; handler stays |
| market-data | `bar_events.py`, `bus_bridge.py`, `streaming/manager.py` | `BarEvents` + `StreamFanout` |
| backtest | `progress.py` pub/sub classes | `ProgressEvents`; rate-limit/ETA stays |
| notification ⭐ | (stub) | `OrderEvents/AlertEvents.consume(...)` → email/SMS/webhook |
| billing ⭐ | (stub) | `UsageEvents.consume(...)` → meter `UsageRecord` |
| auth / strategy | — | `UserEvents/StrategyEvents.publish(...)` |
| agent | in-process LLM stream | unchanged (not on the bus) |

---

## 7. Cross-cutting
- **Idempotency**: `derive_event_id(*parts)` (the five hand-rolled `sha256` sites)
  + `DedupStore`; the catalog sets `envelope.id` deterministically where needed.
- **Tenancy**: `tenant_id` in the envelope; consumers re-enforce it (mandatory
  tenant-isolation tests, per the migration doc).
- **Tracing**: consumer spans link to the producer via `metadata.trace_id`,
  registered through `llamatrade_telemetry` (a fill is one trace: gRPC
  `SubmitOrder` → publish → consume → ledger append). Lib metrics
  (`events_published_total`, group lag, DLQ depth) go through telemetry too.

---

## 8. Build sequence
1. **Proto:** `events/envelope.proto` + reuse/add payload messages; regen Py + TS.
2. **Lib core:** `transport/base.py` + `redis_streams.py`, `codec.py`,
   `channels.py`, `bus.py`. Port the existing bus tests.
3. **Catalog:** move trading/backtest/market-data publishers+subscribers in as
   `OrderEvents`/`PositionEvents`/`FillEvents`/`ProgressEvents`/`BarEvents`;
   delete the service files; services call the catalog. `consumer.StreamConsumer`
   + `fanout.StreamFanout`.
4. **Repoint + shim:** drop `llamatrade_common.events`; leave a back-compat
   re-export (mirrors `llamatrade_telemetry`). Update pyproject/workspace/Docker.
5. **Idempotency + observability**; port portfolio's ledger consumer onto
   `StreamConsumer`.
6. **Light up notification** (second consumer) → validates generality.
7. **Outbox** in trading (collapse the three emission paths); billing + auth/
   strategy producers.
8. **`KafkaTransport`** only if a migration-doc §9 trigger fires — the seam is the
   insurance, not a task.

## 9. Non-goals
- Persisted domain enums (`LedgerEventType`/`AuditEventType`) stay in `libs/db`
  (they're stored columns, not messages).
- The ledger's projector/snapshot kernel stays bespoke until a **second**
  event-sourced aggregate exists (N=1 → no framework).
- Kafka adapter now. The transport seam is the commitment.
