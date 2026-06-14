# Redis Streams Migration — Implementation Plan

Execution plan for replacing Redis **pub/sub** with Redis **Streams** where multiple
consumers, durability, and replay matter — delivered as a shared `EventBus` in
`libs/common` that also becomes the transport substrate for the portfolio ledger's
fill ingestion.

- **Background discussion:** Redis pub/sub vs Kafka vs Postgres-as-ledger (this thread).
- **Ledger spec it feeds:** [Portfolio Ledger & Multi-Strategy Fund Allocation](../portfolio-ledger.md) — resolves its [Open Decision #2](portfolio-ledger-implementation.md) (fill-ingestion transport) toward Streams.
- **Status:** **COMPLETE (Phase 4 done, 2026-06-14)** — Redis Streams is now the
  **sole** transport for all three channels. The dual-write pub/sub paths, the
  `pubsub()` subscriber code, and the `STREAMS_LEDGER_FILLS`/`STREAMS_TRADING`/
  `STREAMS_BACKTEST` flags were all removed (pre-prod, no soak needed). The
  `EventBus` (`publish`/`tail`/`consume`/`ack`) is the only event path; the
  `CancellationFlag` keeps its own key-based Redis usage (not an event channel).
  Below is the original phased plan, retained for context — the per-phase flag
  and dual-write mechanics no longer apply. Implementation deviations decided
  during the build:
  - The bus is **payload-agnostic** (flat `dict[str, str]` fields, Streams' native
    model) rather than `Event`-typed — the locked ledger fill contract crosses
    untranslated; the (fixed) `Event` codec plugs in via `to_redis_stream()`.
  - Ledger fills use **one global stream** `lt:ledger:fills` + consumer group
    `portfolio-ledger` (not per-account): XREADGROUP has no pattern-subscribe, and
    global order preserves per-account FIFO. Single active consumer per group
    (XAUTOCLAIM failover) keeps ordering; shard by account-hash if volume demands.
  - Trading UI streams are **per-session** (`lt:trading:orders:{session_id}`), not
    per-account — the ledger no longer rides the UI stream, so the per-account
    motivation was moot.
  - Flags: `STREAMS_LEDGER_FILLS` (first — the correctness fix), `STREAMS_TRADING`,
    `STREAMS_BACKTEST`. Reconnect cursors: `last_seen_id`/`stream_cursor` on the
    trading stream protos.
  - Observability: `eventbus_published_total` / `eventbus_reconnects_total`
    (prefix-labeled), `portfolio_ledger_stream_pending` (PEL lag gauge).
  - Outbox sweep deferred per kickoff decision: idempotent triple-path emission +
    reconciliation/drift-policy already backstop stream loss.

---

## 1. Goal & Scope

Move the event channels that genuinely need **fan-out to multiple independent
consumers**, **durability across reconnects/restarts**, and **bounded replay** off
fire-and-forget pub/sub and onto Redis Streams, behind a single reusable abstraction.

**In scope**
- A shared `EventBus` (`libs/common/llamatrade_common/eventbus.py`) over Redis Streams: publish, fan-out *tail*, durable *consumer-group* consume, ack, reclaim, trim.
- Fix the existing, buggy `Event.to_redis_stream()` / `from_redis_stream()` serialization in `events.py` and make `EventBus` use the `Event` model.
- Migrate **trading order/position events** (`TradingEventPublisher` / `TradingEventSubscriber`) to the bus.
- Migrate **backtest progress** (`ProgressPublisher` / `ProgressSubscriber`) to the bus.
- Wire the **portfolio ledger fill ingestion** as a durable consumer group on the trading stream (Phase 1 of the ledger plan consumes this).

**Out of scope (deferred)**
- Activating the full dormant inter-service domain-event taxonomy in `events.py` (notifications, billing, auth events). The bus makes this *possible*; lighting up those producers/consumers is separate roadmap work.
- The market-data real-time firehose — it stays on the in-process `StreamManager`/`StreamBridge` path (latency-sensitive, ephemeral, Alpaca is the durable source). **Not migrated.**
- Kafka. Re-evaluated only against the criteria in §9.

---

## 2. Guiding Principles

1. **Incremental & non-breaking.** Every migration ships behind a flag and **dual-writes** (pub/sub + Stream) until consumers are cut over and verified, then pub/sub is removed.
2. **One abstraction, three uses.** The same `EventBus` serves UI streaming, backtest progress, and the ledger — no per-call-site Streams plumbing.
3. **Streams are transport; Postgres is the book of record.** Stream entries are safe to trim after consumers ack because the durable truth lives in Postgres (`trading_events` outbox on the producer side, the ledger `LedgerEvent` table on the consumer side). This is what makes at-least-once + dedupe sufficient.
4. **Right delivery mode per consumer** (the crux — see §4): *competing* durable backends use **consumer groups**; *independent* live clients use **tail reads**.
5. **Well-tested (non-negotiable).** Each phase lands with unit + integration tests (real Redis in CI), including reconnect-replay, consumer-group reclaim, idempotent dedupe, and **tenant isolation**. Target ≥ 80% coverage on new real code.
6. **Strict typing & async-first**, per project conventions. No `Any`.

---

## 3. Design Decisions (defaults — confirm before kickoff)

| Decision | Default | Rationale |
|----------|---------|-----------|
| Live UI delivery mode | **Tail read** (`XREAD` from last-seen id, no group) | Each browser/gRPC stream wants its *own* copy; consumer groups would load-balance and split messages across browsers. |
| Durable backend delivery mode | **Consumer group** (`XREADGROUP` + `XACK` + `XAUTOCLAIM`) | Ledger/notification each get every event once, survive restart, replay unacked. |
| Trading stream granularity | **Per account** (`lt:trading:account:{account_id}`) | Matches the ledger's per-account sharding; one write feeds UI (filtered by `session_id`) + ledger + future consumers. DRY. |
| Backtest progress granularity | **Per backtest** (`lt:backtest:progress:{backtest_id}`) | Short-lived; tailed by the watching UI; self-terminates at 100%. |
| Retention | `XADD … MAXLEN ~ N` (approximate) | Bounded memory; safe because Postgres holds the durable record. UI streams small N (~1k), durable streams larger N + lag monitoring. |
| Idempotency | Stable `Event.id` (UUID); **dedupe is the consumer's job** | Ledger already dedupes by `event_id`; at-least-once + dedupe = effective-once. |
| Serialization | `EventBus` owns it via fixed `Event.to_redis_stream`/`from_redis_stream` | Removes the fragile `.strip('{"data":')` hack. |
| Cutover | **Dual-write**, flag-gated, per channel | Zero-downtime; instant rollback by disabling the flag. |

---

## 4. The Crux: "multiple consumers" has two shapes

Redis Streams support both patterns the system needs, and the bus must expose both:

```
   ┌────────────────────────────────────────────────────────────────────────────────────┐
   │              lt:trading:account:{account_id}   ·   one durable stream              │
   ├────────────────────────────────────────────────────────────────────────────────────┤
   │ Trading producer  ─XADD·MAXLEN~N─►   e1  e2  e3  e4  e5  …                         │
   └────────────────────────────────────────────────────────────────────────────────────┘
                                              │
               ┌─────────────────────────────┬┴─────────────────────────────┐
               ▼                             ▼                              ▼
 ╭──────────────────────────╮  ╭───────────────────────────╮  ╭──────────────────────────╮
 │ TAIL · XREAD (no group)  │  │  GROUP "portfolio-ledger" │  │  GROUP "notifications"   │
 ├──────────────────────────┤  ├───────────────────────────┤  ├──────────────────────────┤
 │ live UI gRPC streams     │  │ XREADGROUP + XACK         │  │ XREADGROUP + XACK        │
 │ browser tails from its   │  │ every event exactly once, │  │ (future consumer)        │
 │ last-seen id, filters by │  │ durable; replays unacked  │  │ independent offset,      │
 │ session_id; reconnect    │  │ on restart; dedupe by     │  │ own progress; competing  │
 │ replays → no lost fills  │  │ event.id → the ledger     │  │ consumers within group   │
 ╰──────────────────────────╯  ╰───────────────────────────╯  ╰──────────────────────────╯
     independent fan-out           competing + durable            competing consumers
```

- **Tail read** = independent fan-out. N live clients each see the *full* stream (filtered client-side). Reconnect resumes from the last-seen entry id → **no lost fills on browser reconnect** (the gap pub/sub had).
- **Consumer group** = competing consumers + durability. Each *group* gets every message once; within a group, work is distributed; unacked entries are reclaimable via `XAUTOCLAIM` if a consumer dies. This is what the ledger uses.

This distinction is the whole point of the migration: pub/sub could do neither durably.

---

## 5. The `EventBus` API (`libs/common/llamatrade_common/eventbus.py`)

```python
class EventBus:
    def __init__(self, redis_url: str | None = None, *, namespace: str = "lt") -> None: ...

    async def publish(
        self, stream: str, event: Event, *, maxlen: int | None = None, approximate: bool = True
    ) -> str:
        """XADD the event (via Event.to_redis_stream). Returns the stream entry id."""

    def tail(
        self, stream: str, *, last_id: str = "$", block_ms: int = 5000, count: int = 100
    ) -> AsyncIterator[tuple[str, Event]]:
        """Independent fan-out via XREAD (no group). Yields (entry_id, event).
        Caller persists entry_id and passes it back as last_id on reconnect to replay the gap."""

    async def ensure_group(self, stream: str, group: str, *, start_id: str = "$") -> None:
        """Idempotent XGROUP CREATE … MKSTREAM (ignores BUSYGROUP)."""

    def consume(
        self, stream: str, group: str, consumer: str, *,
        block_ms: int = 5000, count: int = 10, claim_min_idle_ms: int = 60_000,
    ) -> AsyncIterator[tuple[str, Event]]:
        """Durable consumption via XREADGROUP. Periodically XAUTOCLAIM stale pending
        entries from dead consumers. Yields (entry_id, event); caller MUST ack()."""

    async def ack(self, stream: str, group: str, entry_id: str) -> None:
        """XACK a processed entry."""

    async def trim(self, stream: str, maxlen: int, *, approximate: bool = True) -> None: ...
    async def close(self) -> None: ...
```

Notes:
- `tail`/`consume` are async generators; both handle reconnect with exponential backoff + jitter (reuse the pattern already in `llamatrade_alpaca.streaming`).
- `namespace` prefixes all keys (`lt:`) for environment isolation.
- The bus is **service-agnostic** (it only depends on `Event`), mirroring the `libs/alpaca` rule.

### Fix `events.py` serialization (prerequisite)

Current `Event.to_redis_stream()` does:
```python
"data": self.model_dump_json(include={"data"}).strip('{"data":').rstrip("}"),
```
This corrupts nested/embedded JSON. Replace with explicit, symmetric JSON:
```python
"data": json.dumps(self.data),
"metadata": json.dumps(self.metadata),
```
and have `from_redis_stream` `json.loads` them. Add round-trip tests covering nested objects, unicode, and empty maps.

---

## 6. Phases

### Phase 0 — `EventBus` foundation *(no behavior change)*

**Changes**
- `libs/common/llamatrade_common/eventbus.py`: implement the API in §5.
- `libs/common/llamatrade_common/events.py`: fix `to_redis_stream`/`from_redis_stream`; ensure `EventType` covers the events we emit (`ORDER_*`, `POSITION_*`, `BACKTEST_PROGRESS` already present).
- Config: read `REDIS_URL` once via existing config; add `STREAMS_*` flags (default off).

**Tests:** publish→tail round-trip; publish→consume(group)→ack; `XAUTOCLAIM` reclaim after a simulated dead consumer; reconnect replay from a stored `last_id`; `MAXLEN` trim bound; serialization round-trip; tenant-scoped key prefixes.

**Exit:** bus is importable and fully tested; nothing in services uses it yet. **No flag enabled.**

---

### Phase 1 — Migrate trading order/position events

**Goal:** `TradingEventPublisher`/`TradingEventSubscriber` move to the bus; UI gains reconnect durability; the stream is ready for the ledger.

**Changes**
- **Producer** (`services/trading/src/streaming/publisher.py`): when `STREAMS_TRADING` on, also `bus.publish("trading:account:{account_id}", event)` for every `publish_order_*` / `publish_position_*`. Resolve `account_id` from `session_id` (cached). Keep pub/sub publish in parallel (dual-write).
  - Reuse the `OrderUpdate`/`PositionUpdate` payloads, carried in `Event.data`, tagged with `session_id`, `client_order_id`, and (when known) `sleeve_id`.
- **Consumer** (`services/trading/src/streaming/subscriber.py` + `grpc/servicer.py`): `StreamOrderUpdates`/`StreamPositionUpdates` switch to `bus.tail(stream, last_id=<from client cursor or "$">)`, filtering by `session_id`. Accept an optional client-supplied last-seen id for reconnect replay.
- **Cutover:** verify parity (every pub/sub message has a matching stream entry) → flip subscribers to Streams → remove pub/sub publish.

**Tests:** order/position fan-out to 2+ simultaneous tails; reconnect replays the gap (the key regression vs pub/sub); session filtering; dual-write parity; tenant isolation; existing trading suites stay green.

**Exit:** UI order/position streaming runs on Streams; reconnect loses nothing. Flag: `STREAMS_TRADING`.

---

### Phase 2 — Migrate backtest progress

**Goal:** progress on Streams (per your selection), with replay so a late-joining UI sees current progress immediately.

**Changes**
- **Producer** (`services/backtest/src/progress.py` + `workers/celery_tasks.py`): `bus.publish("backtest:progress:{backtest_id}", event, maxlen=256)`; keep the existing 0.5s/5% rate-limit. Dual-write under `STREAMS_BACKTEST`.
- **Consumer** (`ProgressSubscriber` + `grpc/servicer.py` `StreamBacktestProgress`): `bus.tail(stream, last_id="0")` so a client that connects mid-run replays from the start and catches up; still self-terminate at 100%.

**Tests:** late subscriber catches up via replay; terminates at 100%; rate-limit preserved; bounded `MAXLEN`.

**Exit:** progress streaming on Streams. Flag: `STREAMS_BACKTEST`.

---

### Phase 3 — Portfolio ledger fill ingestion (resolves Open Decision #2)

**Goal:** the portfolio service consumes fills durably from the trading stream — the substrate for ledger Phase 1 (shadow mode).

**Changes**
- **Portfolio service** (`services/portfolio/src/services/`): a `fill_ingestor` runs `bus.consume("trading:account:{account_id}", group="portfolio-ledger", consumer=<pod-id>)`, filters to `ORDER_FILLED`, appends to the `LedgerEvent` ledger **idempotently** (dedupe by `event.id` / `client_order_id`), then `ack`s. Unacked entries replay on restart; `XAUTOCLAIM` recovers from a crashed pod.
- **Durability story:** Trading's `trading_events` (Postgres) is the outbox/source of truth on the producer side; the Stream is low-latency transport; the ledger's `LedgerEvent` table is the destination of record. The Stream may be trimmed after ack because both ends are Postgres-durable. A periodic **outbox sweep** (compare `trading_events` vs ledger-applied) backstops any stream loss — self-healing, matching the ledger's reconcile philosophy.

**Tests:** every fill lands in the ledger exactly once under duplicate delivery; consumer restart replays unacked; `XAUTOCLAIM` after pod death; outbox-sweep recovers a deliberately dropped entry; tenant isolation; conservation invariants hold after ingest.

**Exit:** ledger shadow-mode consumes fills via the bus; Open Decision #2 = **Streams consumer group + Postgres outbox sweep**. Flag: `STREAMS_LEDGER_INGEST` (composes with the ledger's `LEDGER_SHADOW_MODE`).

---

### Phase 4 — Remove pub/sub & harden

**Changes**
- Delete dual-write pub/sub paths and the old `pubsub()` subscriber code once all consumers are on Streams and parity has held in staging.
- Observability: stream length, consumer-group lag (pending entries), reclaim count, ingest dedupe rate, tail reconnect count. Dashboards + alerts on lag/PEL growth.
- Tune `MAXLEN` per stream from observed volume; document retention.
- Load test multi-strategy account at high fill volume; verify lag bounded.

**Exit:** no pub/sub remains for migrated channels; flags removed (Streams is the default path); dashboards green under load.

---

## 7. Cross-Cutting Concerns

- **Feature flags:** `STREAMS_TRADING → STREAMS_BACKTEST → STREAMS_LEDGER_INGEST`, each gating dual-write/cutover; rollback = disable flag (pub/sub path remains until Phase 4 removal).
- **Tenancy:** stream keys are account/tenant-scoped; consumers verify `tenant_id` on each event; tenant-isolation tests per phase.
- **Idempotency:** stable `Event.id`; consumers dedupe; ledger reuses its `event_id` dedupe.
- **Backpressure/lag:** monitor pending-entries (PEL) per group; alert before `MAXLEN` would drop unacked-but-trimmed data; outbox sweep is the correctness backstop.
- **Testing:** real Redis (or `fakeredis` for unit) in CI; add a Streams integration suite under `tests/integration/`; run `./scripts/ci-local.sh --integration` before merge.
- **Service-agnostic bus:** `EventBus` must not import from any service (same rule as `libs/alpaca`). Changes here affect trading, backtest, and portfolio — run all three suites.

---

## 8. Sequencing & Dependencies

```
Phase 0 (EventBus + events.py fix)
   └─► Phase 1 (trading events → Streams)            ── reconnect durability
          ├─► Phase 2 (backtest progress → Streams)
          └─► Phase 3 (ledger fill ingestion)        ◄── resolves Open Decision #2
                 └─► Phase 4 (remove pub/sub, harden)
```

Phases 1 and 2 are independent after Phase 0. Phase 3 depends on Phase 1's account stream and aligns with ledger plan Phase 1.

---

## 9. When to revisit Kafka (explicitly deferred)

Adopt Kafka/Redpanda only if one becomes true: retention/replay beyond RAM; many *external* consumers needing the log as integration contract; aggregate throughput beyond a single Redis; or a stream-processing ecosystem need (Connect/ksqlDB). None hold today. The `EventBus` interface is the seam — swapping its backend later does not touch producers/consumers.

---

## 10. Definition of Done

- Trading order/position and backtest progress run on Redis Streams; **browser reconnect loses no events** (the pub/sub gap is closed).
- Multiple independent consumers coexist on the trading stream: live UI tails + the ledger consumer group + room for more.
- The portfolio ledger ingests fills durably (consumer group + ack + reclaim), idempotently, with a Postgres outbox sweep backstop — Open Decision #2 resolved.
- `events.py` serialization is fixed and covered; `EventBus` ≥ 80% coverage; tenant-isolation and reconnect/reclaim suites green.
- pub/sub removed for migrated channels; lag/drift observability in place.

---

## 11. To Confirm Before Kickoff

1. **Trading stream granularity** = per **account** (needs `session_id → account_id` resolution in the publisher). OK, or prefer per-session for a smaller Phase 1 blast radius (and a separate account fills stream in Phase 3)?
2. **`MAXLEN` defaults** — UI ~1k, backtest ~256, durable trading stream TBD by volume. Acceptable starting points?
3. **Outbox sweep** in Phase 3 now, or rely on consumer-group durability first and add the sweep only if observed loss warrants it?
4. **CI Redis** — real Redis service in CI vs `fakeredis` for unit + real for integration. Preference?
5. Start at **Phase 0**?
```
