# LlamaTrade backend: architecture specification and review request

## Version history

| Field | Value |
|---|---|
| Author | Naib Baghirov |
| Status | Draft, circulating for architecture review and sign-off |
| Reviewers | _(add yourself when you start reading)_ |
| Created | 2026-07-28 |
| Scope | Backend services and shared libraries; the web and mobile clients appear only where they constrain the backend. |
| Reading guide | About 45 minutes end to end. The money path needs the most scrutiny, the worked example at the end is the fastest way to see how the pieces connect, and Accepted limitations lists what we chose not to build. |

## Introduction

This document is the design record for the LlamaTrade backend as it enters the closed paper-trading beta, written for engineers new to the codebase. The next section, Context and scope, describes the product and the external constraints that shape it. We are at the point where external testers and then real money require more people to understand and stress this architecture than have historically been inside it, and several decisions below become expensive to reverse once customer money is attached.

Each subsystem section follows the same shape: the design as built, the alternatives considered or worth proposing, and the what-if questions we asked ourselves, including the ones with unfavorable answers. The worked example at the end runs one strategy through every subsystem.

Cut scope and accepted risks are collected under Accepted limitations, each with the condition that should reopen it. Decisions that are still contestable are listed under Open questions.

### What we are asking reviewers to sign off on

Sign-off means agreement with these five decisions; push-back on any of them is equally useful review input:

1. The event-sourced double-entry ledger with virtual sleeves as the book of record for all money state (The money path).
2. The fill-ingestion design, meaning per-account ordering on the partitioned Kafka backbone, commit-after-write offsets, and quarantine over fabrication, together with its idempotency contract (The money path's fill-ingestion sections, and Eventing).
3. The shared evaluation core between backtest and live trading, and the deliberate rejection of a vectorized backtest engine (Strategy definition and evaluation).
4. The tenancy model: shared Postgres, asymmetric service identity, and enforced row-level security as defense in depth, with its blast radius stated plainly (Identity, tenancy, and the data layer).
5. The Accepted limitations list and the conditions under which each should be revisited.

## Context and scope

LlamaTrade is a multi-tenant SaaS for algorithmic trading. A user connects their own Alpaca brokerage account, builds a strategy in a visual builder, a code editor, or through an AI copilot (all three edit the same underlying language), backtests it against historical data, and deploys it to trade paper or live money on a schedule.

Three external constraints shape most of what follows.

First, we are not a broker and hold no customer funds. Alpaca is the broker of record; users bring their own API keys or connect through OAuth. This keeps us out of broker-dealer registration and, as long as money never routes through our accounts, out of money-transmitter territory. It also means the broker's view of an account is an input we reconcile against, not state we own.

Second, one brokerage account serves many strategies. Alpaca sees one position per symbol and one cash balance. Everything the product promises, per-strategy P&L, strategies that cannot touch each other's holdings, and capital budgets per strategy, has to be constructed on our side, on top of an aggregate the broker will never disaggregate for us.

Third, the platform trades US equities and ETFs only, long-only, with calendar-driven rebalancing. The strategy language can express nothing the execution layer cannot honor. This scope was chosen deliberately (see The language is an allocation language).

The platform is nine Python services plus a React SPA, in a single uv-workspace monorepo with eight shared libraries. The stack is Python 3.14, FastAPI, SQLAlchemy async, PostgreSQL, Redis, TimescaleDB for bars, Kafka for events, Connect RPC for transport, and protobuf as the single type system. The codebase is roughly 250k lines including tests.

The build-and-backtest loop is solid and heavily tested, live paper trading works end to end, and the platform deploys to GKE through CI. User-directed messaging (ledger incidents, trading alerts, billing and security email, in-app notifications) runs through a unified notification service on the event backbone (see Platform plumbing). The MVP plan gates a closed, invite-only paper beta first, with real-money trading as a separately gated milestone.

## Goals and non-goals

**Goals**

- A user's backtest must predict what the live system would have decided: same evaluation, same sizing logic, same rebalance clock. Not the same fills, since markets do not replay.
- Money state must be provably conserved. Every economic event balances to zero, every balance is derivable from the log, and drift against the broker is detected rather than silently absorbed.
- A strategy must never trade another strategy's capital or holdings, even in the same symbol in the same account.
- Tenant isolation should not depend on any single check being correct. The application filter, identity resolution, and row-level security should each have to fail independently.
- Services should degrade rather than fail when a dependency (Alpaca, Redis, the bar store) is down, except where degrading would fabricate money state. In those cases the service stops and reports the failure rather than continuing.

**Non-goals**

- Sub-daily rebalancing, shorting, options, futures, crypto, and margin modeling. The engine is long-only and acts at daily or coarser cadence, and the language refuses what the engine cannot honor.
- Custodying funds, and the Alpaca Broker API (per-customer sub-accounts, KYC). That is a separately gated legal program, and nothing in this design assumes it.
- Order netting across strategies (block-and-allocate). Designed and deliberately deferred; see What we deliberately did not build yet.
- High-frequency trading of any kind. The tick clock is one-minute bars and latency budgets are human-scale.
- Exactly-once delivery. No transport can promise it: an acknowledgment can always be lost, leaving redelivery or loss as the only choices. We choose redelivery, so money events are never dropped, and make duplicates harmless through idempotent writers, which yields exactly-once effects. That outcome is a goal and is tested. What we do not claim is that the transport itself delivers each message exactly once.

## System overview

> **Figure 1. Container view: services, state, and external systems.**
> _(insert Excalidraw export: 02-container)_

The browser talks to each service directly; there is no API gateway (see Topology decisions). Services talk to each other over the same Connect protocol with short-lived service JWTs. Asynchronous flows ride the Kafka event backbone (Eventing). Redis handles caching, the Celery broker, and coordination locks. The only queue-style workload is backtest execution on Celery.

The eight shared libraries carry most of the architectural weight, and their layering is strict by design:

- `llamatrade_proto`: protobuf definitions and generated Connect code. Proto is the single wire and read model; there is no parallel Pydantic response layer, and enums live here as the single source of truth. A CI parity test keeps the database enum bridges aligned with the proto enums.
- `llamatrade_dsl`: the strategy language (parser, validator, static analysis). Pure Python with zero dependencies; knows nothing about bars or execution.
- `llamatrade_runtime`: the evaluation engine and execution loop shared by backtest and live. Depends only on the DSL and numpy.
- `llamatrade_alpaca`: the only code in the platform allowed to speak to Alpaca, REST or WebSocket.
- `llamatrade_events`: proto-typed events over the Kafka backbone, with the broker isolated behind a one-file transport seam. The original Redis Streams transport was replaced through that same seam (Eventing).
- `llamatrade_db`: SQLAlchemy models for all services, the Alembic chain, and the RLS machinery.
- `llamatrade_common`: auth middleware, identity resolution, health checks, crypto helpers.
- `llamatrade_telemetry`: OTel-native metrics, traces, and logs with a Prometheus bridge and an enforced label-cardinality contract.

### Topology decisions: nine services, one database, no gateway

**Why microservices at all.** The failure domains genuinely differ: a backtest worker consuming CPU for thirty minutes, a WebSocket ingestor that must never scale past one replica, a fill consumer whose ordering matters, and a chat-style copilot have incompatible deployment shapes. We believe the split earns its keep on deployment shape alone. A reviewer who argues we are carrying microservice overhead at monolith scale has a point about the overhead, however; nine services times health checks, Dockerfiles, and manifests is real cost, and the build-and-deploy section shows we have not been paying it consistently.

If we had built a modular monolith instead, most of the shared-library discipline (proto as the type system, the runtime library, the events library) would survive unchanged. That is the strongest evidence the boundaries are in the right places, because they are enforced in libraries rather than by network hops. The pieces that need process isolation (Celery workers, the ingestor, the fill consumer) would become separate deployables of the same codebase, which is close to where we have ended up anyway. We would defend the current shape but do not consider it a settled question.

**One shared Postgres rather than a database per service.** Every service except market-data shares one Postgres with row-level security. The alternatives were a database per service, which is the orthodox microservices answer, or a schema per service. We chose shared because cross-service reads that would otherwise become RPC fan-outs (plan limits read from billing's tables, strategy reading execution state) remain SQL queries; because a single Alembic chain is far easier to keep coherent than nine; and because RLS provides a tenant-isolation backstop that would otherwise need to be reimplemented per store. The cost is coupling: any service can in principle touch any table, and only convention and review prevent it. The `plan_limits` module is the sanctioned example of deliberate cross-service table access. We prefer to have that named and visible rather than routed through an RPC that adds a failure mode to every order placement.

If one service's load ever swamps the shared database, the pool budget is already allocated per service (the totals are kept under Postgres `max_connections`, with a documented trigger for introducing PgBouncer), and the one workload that would actually swamp it, bar storage, already lives on its own TimescaleDB because its write pattern, retention, and failure domain are different. That split is the template for any future extraction: move a workload out when its storage behavior diverges from the shared database, rather than to match service boundaries.

**No API gateway.** This is recorded as a formal ADR. The browser reaches each service directly; Connect over HTTP/1.1 with JSON means no gRPC-web transcoding proxy is required; auth is a shared middleware library rather than a gateway concern; and GCP's L7 load balancer does path routing and TLS in production. The rejected alternative (Kong, Envoy, or similar) would have bought central rate limiting and a single egress point at the price of a single point of failure, an extra hop on streaming paths, and one more deployable. The ADR lists its own revisit triggers: a public third-party API, per-key quotas, roughly twenty services, or canary routing. We would add one more: if we ever need request-level audit for compliance, a gateway is the cheapest place to put it.

Rate limiting did not need a gateway either. Login, registration, and credential validation are throttled by a Redis-backed limiter in the shared middleware, with lockout on repeated failures, which covers the abuse cases a gateway would otherwise have been bought for.

**Connect RPC rather than raw gRPC.** Everything speaks Connect (HTTP/1.1 with JSON or binary proto), including service-to-service calls, despite `grpc` appearing in module names. The browser needs Connect anyway, so using one protocol everywhere gives us one interceptor stack, one telemetry path, and one way to inspect a service with curl. The generated gRPC servers exist but are not run. The cost is that we forgo HTTP/2 multiplexing on internal hops, which is irrelevant at our request rates, and some gRPC ecosystem tooling. A single hop can be switched to raw gRPC later if its throughput ever needs it.

---

## The money path: ledger, sleeves, and trading

This is the core of the system and the section where adversarial review helps most. It also contains some of the most carefully written code in the repository, but code that is correct against the wrong contract would still lose money, so we ask reviewers to check the contract itself, not only the invariants.

### The problem, stated precisely

One Alpaca account receives trades from N strategies plus the user's manual activity. The broker reports aggregates: one AAPL position, one cash number. We need three properties.

1. Provenance: every share is traceable to the order and strategy that bought it.
2. Non-interference: strategy A must be structurally unable to sell strategy B's shares or spend its cash, even in the same symbol.
3. Capital budgets: each strategy sizes against its own allocation and cannot overdraw it.

The naive design, in which each strategy sizes against full account equity and reconciles its own positions against the broker aggregate, double-counts capital and causes strategies to fight over shared symbols. We rejected it during design, before writing code.

### Virtual sleeves over an event-sourced double-entry log

An **account** (one per broker credential set) is partitioned into **sleeves**: virtual sub-portfolios of four types, one per running strategy execution, plus `manual`, `unmanaged` (pre-existing holdings we did not originate), and `unallocated` (free cash). Sleeves exist only in our books; Alpaca has no knowledge of them.

The risk with sleeves is that the natural implementation is a set of mutable tables (positions, cash, lots), each updated in place and each able to drift from the others. That drift is silent, and when two tables disagree there is no record of which one is wrong. For that reason all money state lives in a single append-only, double-entry event log:

- `ledger_events` is the only writable money state: a global sequence, a unique deterministic `event_id`, and a typed JSONB payload.
- Sleeve cash, positions, lots, realized P&L, and reserved cash are stored nowhere. They are computed by folding over the log, resumed from persisted checkpoints keyed by log sequence, so a restart costs the delta rather than the account's history.
- Because none of these derived views can be written independently, they cannot disagree with each other.

A checkpoint holds back a short safety window matched to the database's idle-in-transaction timeout, because a sequence is assigned at insert but its row can commit later; the two settings are coupled and must move together.

Whether the log agrees with the broker is a separate question, answered by the reconciliation pass described under Reconciliation, drift policy, and freezing.

Every economic event expands into postings across four buckets (CASH, POSITION carrying both signed shares and dollar cost, PNL, and EXTERNAL for the account boundary), and the writer asserts, before insert, that the postings sum to zero and that no position leg moves shares against its cost direction. The second check catches average-cost corruption that the dollar checksum cannot see. An unbalanced event cannot be persisted.

Three invariants define correctness and are checkable continuously:

```
(1)  sum over sleeves of sleeve_qty(symbol) == broker_qty(symbol),  per symbol
(2)  sum over sleeves of sleeve_cash       == broker_cash
(3)  sleeve.equity = sleeve.cash + market value of its lots
```

A corollary of (2) is that a sleeve can never spend money the account does not have.

We considered three alternatives:

- Mutable balance tables with careful transactions are simpler on day one, but per-strategy P&L history would have required a second bookkeeping system anyway, and table drift is undetectable after the fact.
- Treating the broker as the sole source of truth, with orders merely tagged by strategy, fails as soon as two strategies hold the same symbol, and provides no cash budgeting at all.
- Separate brokerage accounts per strategy would give the cleanest isolation, but Alpaca does not offer sub-accounts on the model we use, and most users want several strategies on one existing account.

We should also be clear about what we did not adopt: there is no CQRS framework, no projection database, and no saga orchestrator. The log is one Postgres table, projections are pure functions, and the write path is a single insert with a conflict clause. The pattern has established lineage in unified-managed-account overlay systems, fintech ledger engineering, and hedge-fund shadow accounting; we use the ordinary core of it.

*What if the log itself is corrupted, for example by a bad deploy writing wrong-but-balanced events?* Balance checks cannot catch semantically wrong events. That is why reconciliation against the broker (below) is a first-class subsystem: the broker is an independent record we continuously compare against, and that comparison catches what the checksum cannot.

*What if a user deletes their broker credentials and connects new ones?* Accounts carry the broker's own account id, learned at genesis and unique per tenant, and account resolution matches on it before creating anything, so a re-link re-points the existing book at the new credentials instead of minting a duplicate whose backfill would double-count. Pre-existing duplicates are reported by a startup sweep for operator resolution and never merged automatically, because merging two event logs is not a job to run unattended.

*What if support has to explain a balance to a user?* Every balance is a fold of events, and an operator statement tool renders any account into a readable statement: opening balances, day-grouped activity with running per-sleeve cash, closing lots with realized P&L, and the conservation identity checked at the bottom, all computed through the same fold the ledger uses, so the statement cannot disagree with the book.

### Ownership boundary: trading executes, portfolio accounts

Trading (8850) owns broker submission, order-time risk checks, the deterministic `client_order_id`, and a thin durable order-intent table. It does no accounting; it reports broker facts. Portfolio (8860) owns the ledger, all projections, reconciliation, and fund operations, and hosts a second Connect service (`LedgerService`) in the same process for sleeve reads and capital operations. The strategy service orchestrates lifecycle: it funds a sleeve when an execution starts and closes the sleeve when it stops.

The two services communicate through exactly one asynchronous channel for money facts: a single Kafka topic, `lt.ledger.fills`, keyed by `account_id`, carrying proto `LedgerFill` and `LedgerReservation` events. Synchronous calls go the other way only for reads (trading asks the ledger for sleeve equity, free cash, and status; results are cached for ten seconds and invalidated on terminal fills).

Trading's per-pod concurrency is bounded by connections rather than CPU: each live session holds its ownership lease on a dedicated database connection outside the request pool, so a pod carries on the order of ten concurrent sessions before the request path starves, and trading scales by adding pods rather than sessions per pod.

> **Figure 2. Fill ingestion: one order to balanced ledger postings, ordered per account.**
> _(insert Excalidraw export: 03-fill-ingestion)_

Trading publishes exactly one event per order, at terminal state, and never one per partial fill. The ledger deduplicates on an id derived from `client_order_id`, so per-partial publishing would silently drop all but the first partial. A cancel that partially filled publishes the filled portion; a cancel with nothing filled publishes nothing, because the reservation release covers the cash side. This cardinality rule is the most load-bearing line of the integration contract, and it is stated in the contract document, the emitter, and the ingester on purpose.

Cost basis is computed at ingestion rather than by trading. A sell's realized P&L depends on which lots it consumes, which is accounting state trading does not have and should not have. Trading leaves `cost_basis` empty; portfolio resolves it FIFO against the account projection inside the ordered consumer. A sell whose lots cannot cover it is quarantined to a dead-letter topic rather than recorded with a fabricated basis. We do not write wrong-but-balanced events; this principle (quarantine over fabrication) recurs throughout the ledger and we consider it non-negotiable.

### Idempotency and delivery semantics

Delivery is at-least-once throughout, and effective-once behavior is built on top of it through deterministic ids and idempotent writers.

- `client_order_id = "lt-" + sha256(session, symbol, side, signal_timestamp)[:16]`. Alpaca enforces uniqueness per account, so a crash retry resolves to the existing broker order instead of placing a duplicate. This one id threads the whole system: it is the broker dedup key, the event-envelope id seed, the ledger `event_id` seed, and the attribution key. The order-intent table enforces the same uniqueness with a database constraint, so concurrent submitters cannot record two intents for one logical order.
- The ledger `event_id` is `UUID(sha256(client_order_id)[:16 bytes])`, and the writer inserts with `ON CONFLICT DO NOTHING`. Redelivery collapses to one row, and so do the three independent emission paths trading runs: the live stream handler, the REST-sync recovery, and a periodic republish drain that exists to cover the window where an order reached a terminal state but the publish failed.
- Reservation events derive ids from `(client_order_id, event_type)`, so each lifecycle stage is idempotent independently.
- The same derivation scheme covers sleeve close, drift corrections, invariant freezes, and genesis backfill. Every writer to the log is deterministic.

We considered exactly-once machinery instead, for example a transactional outbox on the trading side. An outbox would remove the republish drain, at the cost of coupling order-state commits to publish semantics and adding a relay process. Since deduplication has to exist anyway (the broker's own stream can redeliver), the outbox would be additional complexity rather than a replacement. This is the best-understood part of the design.

*What if two submitters race the same order?* Both derive the same `client_order_id`. The order-intent table's unique constraint rejects the second insert before any broker call, and a duplicate that still reached Alpaca would hit its per-account uniqueness; a concurrency test asserts that five identical simultaneous submits produce exactly one broker order, with the losers surfacing as errors rather than a second fill.

*What if a trading pod crashes mid-order?* The intent row commits before the broker call, so on restart a stranded-order sweep probes Alpaca by `client_order_id`: an order the broker already has is adopted onto the existing row, one it never received is marked rejected, and a resubmit of the same signal re-derives the same id and never places a second order. One residual gap in this sweep, a lost-response-but-accepted order that gets marked rejected and so drops out of it, is tracked under Findings from the implementation read (item 5).

### Ordered fill ingestion, partitioned by account

FIFO cost basis is only correct when an account's buys are applied before the sells that consume them, so the hard requirement on fill ingestion is per-account ordering. Kafka provides this directly. Fills are keyed by `account_id`, ordering is guaranteed within a partition, and the `portfolio-ledger` consumer group therefore processes accounts in parallel while each account remains serial. Offsets are committed only after the ledger write succeeds.

Failure handling distinguishes three cases:

- Poison records (undecodable bytes, or a sell that no lots can cover) are produced to the DLQ topic, keyed like the source so a repaired record replays in account order, and committed past.
- Transient failures, such as a database outage, are not committed, so the record is redelivered until the write succeeds; we would rather retry a fill indefinitely than dead-letter it.
- Everything else commits normally.

A consumer death causes a rebalance and some redelivery, which the idempotent writer absorbs. This is also why we do not use Kafka transactions: the write target is Postgres, and the `event_id` conflict clause already makes commit-after-write effectively exactly-once.

The design history is worth keeping in the record. The first version was a single active consumer over one global Redis stream, elected by a Postgres advisory lock. Global stream order trivially gave per-account FIFO, and that was the right starting shape, because it made the ordering contract impossible to get wrong while the postings kernel was being proven. It had a ceiling (one serial writer, with O(history) FIFO enrichment inside that one loop) and an awkward failure mode (a hung but alive consumer keeps the lock, and only backlog growth reveals it). Both are retired by the group model, and consumer lag is now a standard signal rather than a hand-rolled tracker feeding a liveness probe. The ledger cutover was gated on a dual-run parity check: the parallel Kafka fold ran alongside the serial fold with the serial side authoritative, and authority flipped only after both produced identical ledger state over a soak window. We would hold any future transport change to the same gate.

The advisory lock was not removed; its scope narrowed. Reconciliation and equity-snapshot sweeps remain single-writer by lock election, because they are periodic, have no throughput problem, and double-running them corrupts the equity-curve series (drift events are protected by their deterministic ids; equity snapshot rows carry no idempotency key).

*What if the database fails over while a lock is held?* Advisory locks release with their connections, and a chaos suite now exercises this against real Postgres death and restart. It confirmed that re-election works, and also showed where the earlier assumptions were wrong: election is one-shot with no fencing token, so a torn leader that reconnects keeps sweeping alongside the new one until it notices. On the trading side a lease sweep on every pod (about every thirty seconds) detects a lost session lease and stops the local runner, so two runners overlap for at most that window and the deterministic `client_order_id` prevents a duplicate order within it. On the sweep side the exposure is real: drift events survive double-running through their deterministic ids, but equity snapshots do not, and a managed idle-in-transaction timeout can revoke a lease silently with no failover at all. Fencing the periodic sweep writers is the open item in the register; until it lands, that window is documented rather than closed.

One deliberate deviation should be flagged. The events library once shipped a generic durable consumer with a retry-counting DLQ policy, and the money path never used it, because a policy of N retries followed by DLQ is wrong for fills, where transient database failure must redeliver indefinitely. The generic consumer was deleted rather than left as unused surface area once it was clear no production path wanted its policy. This is recorded here because the retry-forever choice can look like a bug on first reading, and is deliberate.

*What if a partition's consumer stalls or dies?* The rebalance reassigns its partitions to the surviving members, uncommitted offsets are redelivered, and the writer deduplicates. Consumer-group lag is the alerting signal.

*What if we sized the partitions wrong?* This is the genuine one-way door: partition count on a keyed topic is a decide-once setting, because growing it later remaps keys and breaks per-account ordering across the boundary. `lt.ledger.fills` is provisioned at 24 partitions against a present of tens of accounts, but that number deserves an actual account-growth estimate before it becomes permanent (see Open questions). The consumer group also caps parallelism at the partition count, and portfolio autoscales to at most five pods today, so only a fraction of the twenty-four partitions are worked in parallel; the headroom is for account growth, not current throughput.

*What if a fill sits unconsumed for a long time?* Retention is time-based and long, an operational replay window rather than a length trim, so the failure class the v1 stream had, where a stalled consumer's pending entries could be trimmed away and the fill lost into reconciliation-driven mis-attribution, no longer exists. Postgres, not Kafka, remains the permanent audit store; if a longer archive is ever wanted, the plan is a topic-to-GCS sink rather than longer broker retention.

### Reconciliation, drift policy, and freezing

A background pass (lock-holder only, bounded concurrency, per-account sessions and timeouts) compares ledger projections against broker positions.

- A holding present at the broker but missing in the ledger is adopted into the Unmanaged sleeve through an `EXTERNAL_TRADE_DETECTED` event at the broker's average price. It is never assigned to a strategy.
- A holding present in the ledger but missing at the broker, or a quantity mismatch, is never auto-corrected. Every sleeve holding that symbol is frozen (a `SLEEVE_FROZEN` event and a critical log line), and trading's risk gate rejects all orders on a frozen sleeve.
- Cash drift is surfaced (a gauge, and a warning above one dollar) but never frozen, because dividends, fees, and interest legitimately move broker cash without a ledger event.
- The same invariant check runs inline after every ingested fill. Negative sleeve cash or a negative position freezes the sleeve automatically. Each event balances on its own; it is the running total across events that can become impossible.

One defensive decision here deserves explicit sign-off: a broker read failure is treated as unknown, never as empty. Reconciling against an empty broker response would classify every holding as missing at the broker and freeze every sleeve on the account. When credentials are missing or Alpaca is down, the account is skipped and retried. The skip cannot stay silent: a per-account staleness gauge alerts when an account has not reconciled within its interval. The broker adapter resolves both key-and-secret and OAuth credentials through the same resolution path trading uses, so the credential type cannot cause the skip.

*What if reconciliation runs while one of our own fills is in flight?* The broker already shows the position while the ledger has not folded the fill yet, so naive adoption would double-count, and the invariant check would then freeze the sleeve over the system's own timing. Adoption therefore defers whenever the symbol has open or recently terminal orders on the account, and the drift is retried on the next pass once the fill has folded.

*What if a dividend arrives?* A nightly poll reads the broker's corporate-announcements feed for held symbols and routes splits, renames, and dividends to the pro-rata attribution planners. The feed proposes and an operator applies; deterministic proposal ids make re-polling idempotent, and an already-applied action is never proposed again. Until the operator applies, the cash still surfaces as drift, which is the honest intermediate state.

*What if the user deletes the credentials a funded sleeve depends on?* Deletion is refused while live sessions or funded sleeves depend on the credentials: the delete call returns failed-precondition with the dependent execution ids, so the client can offer stop-and-close instead of leaving trading to hard-fail and reconciliation to go stale.

Sleeve lifecycle is designed for decoupled convergence rather than coordination. When a strategy stops: the strategy service closes the sleeve (positions are re-homed to Unmanaged at cost, with no P&L since a re-home is not a sale; free cash moves to Unallocated; the close refuses while reserved cash is nonzero); trading's risk gate independently blocks non-active sleeves; the runner stops itself on its next equity sync when it sees the sleeve closed; and a stray late fill for a closed sleeve is re-routed to Unmanaged at ingestion. That is four independent mechanisms, with no strategy-to-trading RPC and no distributed transaction. If the close fails, the sleeve id remains on the execution row as a marker and a leader-elected sweeper retries, so capital is never permanently trapped.

*What if a stop races an order still in flight?* Stop does not cancel broker orders, and the sleeve close refuses while any cash is reserved, so a stop during a rebalance waits for the in-flight orders to reach terminal state before the sleeve can close. An order that fills after the runner is gone is still reconciled: its intent row is squared by the next REST sync and its ledger fill by the republish drain, so the money lands and is attributed even with no runner listening.

*What if a sleeve freezes while the runner holds open orders?* New orders reject at the risk gate the moment the sleeve is frozen, but orders already at the broker still fill and their fills still post to the ledger, because the fill path does not re-check sleeve status; the freeze stops new risk, not the settlement of what was already committed. Only a closed sleeve stops the runner itself.

### What we deliberately did not build yet

- Netting and block-and-allocate. Execution is gross: one sleeve's order is one broker order and is trivially attributable. The netting design (bunch sleeve intents per symbol, submit the net order, allocate fills at the volume-weighted average price, cross overlapping intents internally) is written down, and a pure helper exists unwired. We deferred it because netting is where the subtle accounting bugs live, and gross execution let us prove the ledger first. It becomes worth revisiting when order volume makes the commission and market-impact savings material.
- Settlement modeling. The platform admits margin accounts only: a preflight check reads the account type from the broker and refuses cash accounts, so settled and unsettled cash never diverge in the book. Modeling settled versus unsettled balances is deferred until cash accounts are admitted, at which point it becomes a new posting family (see Accepted limitations).
- The desired-state reconciler as executor. Earlier documentation described portfolio computing intended orders from target-versus-actual state, in the style of a Kubernetes controller. The trading runner sizes and submits directly from strategy evaluation, and the portfolio-side planner was retired rather than kept as a second potential owner for sizing. If block-and-allocate netting is ever built, the question of where sizing lives reopens with it.

### Hardening from the review pass

Three weaknesses were found while preparing this document for review, and each was closed with a specific mechanism worth recording, since all three are the kind of defect that recurs if the reasoning is lost.

1. Out-of-order reservations. The `order_submitted` reservation publishes after the broker call returns, while the fill publishes from a separate task consuming `trade_updates`, so a fast market fill can reach the topic before its reservation. The projection therefore treats a reservation that arrives for an already-terminal order as a no-op: the terminal fill has already settled the cash side, and earmarking after the fact would understate free cash with no future release. This is a pure-function rule in the fold, so it holds identically on replay. The alternative, reserving before the broker call and releasing on submit failure, was rejected because it adds a failure mode to submission itself.
2. Bounded restart cost. Projection checkpoints are persisted keyed by ledger sequence, and both recovery and FIFO cost-basis enrichment seed from them, so a restart or a basis-less sell costs the delta since the last checkpoint rather than the account's full history. The checkpoints were already deterministic (the fold is a pure function of the log), so persisting them changed storage, not semantics.
3. Incident visibility. Sleeve freezes and quarantined fills are delivered to the affected tenant through the notification service (in-app, email, and any configured webhook), in addition to the operator-facing logs and metrics. An invariant violation on a user's money that only an operator can see was not an acceptable state for a beta with external users. Aggregate DLQ growth stays an operator signal on metrics rather than a tenant notification, because backlog depth is not attributable to one tenant.

---

## Strategy definition and evaluation

### The language is an allocation language

A strategy in LlamaTrade is an S-expression tree that, when evaluated on a bar, produces target portfolio weights, for example `{VTI: 60, BND: 40}`. It never expresses "buy 100 shares." Blocks shape the weight vector (`asset`, `weight`, `group`, `filter`); conditions make it react to data (`if`/`else` over comparisons, crossovers, and boolean logic across 17 indicators and 3 metrics). Sizing, the conversion of weights into orders given holdings and equity, is a separate path-dependent stage that the language cannot see.

This is the most consequential product decision in the backend, so its alternatives deserve to be spelled out. The rejected shape is the signal language most retail platforms ship: entry and exit conditions, stop-loss percentages, position counts. We had one and retired it. The allocation model won for four reasons. It composes, since a tree of weight blocks is still a weight vector, whereas entry/exit rules compose poorly. It makes multi-asset portfolios first-class rather than an addition. It maps directly onto the sleeve model, because a target vector is exactly a sleeve's desired state. And it makes backtest-versus-live parity tractable, because the deterministic part (weights) is separated from the path-dependent part (fills). The cost is expressiveness: there is no "sell half when RSI crosses 70" and there are no per-position stops. That trade sits well with the long-only, calendar-rebalanced scope, and poorly with any future that wants intraday tactics, which is why the two-clock model below is the thing to protect.

Other language decisions, briefly. S-expressions were chosen because there is exactly one way to parse any expression: no precedence table, trivial serialization, and the visual builder, the code editor, and the copilot all round-trip the same AST. The parser is hand-written recursive descent rather than generated from a grammar, which gives better error positions and keeps the DSL package at zero dependencies. Parsing is permissive and validation is strict; `market-cap` weighting parses but is rejected loudly, because silently approximating it as equal weight on a money path would be a lie. Finally, the DSL text is the only stored artifact. Versions are immutable rows holding the source string, with symbols and rebalance frequency stored as recomputed query projections, and the JSON IR derived on demand and never persisted. Storing compiled output was rejected because it turns every language change into a data migration; the proto field numbers for the retired compiled-JSON, parameters, and timeframe columns are marked `reserved` so the decision is hard to reverse casually.

Adding a new indicator family touches one vocabulary module, from which the AST set, the lookback table, and the compute dispatch all derive, and a parity test holds the proto enum to the same list. An earlier arrangement kept four hand-maintained copies, and one had already drifted, which is the kind of duplication that goes wrong without anyone noticing. There is also an open design note worth deciding deliberately: modeling moving averages as one parameterizable family rather than N separate keywords, as TradingView does. We would take that direction before the indicator count doubles.

### One engine, shared by backtest and live

> **Figure 3. One evaluation engine shared by backtest and live.**
> _(insert Excalidraw export: 04-engine)_

`StrategySession` is the unification point: one compiled strategy fed all symbols' bars together, so that cross-symbol conditions (hold TLT when RSI(SPY) is above 70) evaluate correctly; one portfolio-level rebalance clock that never fires twice in a calendar day; one sizing routine that sorts sells before buys so a rebalance funds itself, supports drift-band and binary modes, and never sells more than is held. Backtest and live both call the same `evaluate(bars, holdings, equity)`, so a backtest predicts live decisions by construction. This replaced two divergent per-service adapters. The live one evaluated per symbol and genuinely broke multi-symbol strategies, rebalancing one leg per period, before the consolidation. Both old adapters are deleted rather than deprecated.

*What if a sleeve shrinks until its orders fall below the broker minimum?* Feasibility is checked when capital is allocated, not per order, so a shrunken sleeve could otherwise emit orders the broker rejects. The sizing routine therefore skips intended orders below a configurable notional floor, counts the skips into a session metric, and re-fits the buy side so a skipped sell does not strand the buys it would have funded.

We used to have a vectorized backtest path (numpy over the whole series at once) and removed it deliberately. A vectorized engine is a second implementation of the language semantics, and any drift between it and the live evaluator produces backtests that are confidently wrong, which is the worst failure mode a trading product can have. We chose fidelity over throughput. The cost is a hot loop that recomputes indicators over accumulated history every bar, which we bound with a static analysis that caps retained history at the largest window the strategy can read (a hard cap of roughly eight trading years for period-less metrics, which is a documented approximation). A ten-year daily backtest runs in seconds. This trade would not survive tick-level simulation, which is out of scope. If vectorization is ever proposed again, the bar we would hold it to is byte-identical decision sequences against the session engine across a golden strategy corpus, enforced in CI permanently.

The loop was unified second, not first. The backtest drives `StrategyRuntime.run()` end to end, and the live runner drives `StrategyRuntime.stream()`. The swap away from the earlier hand-rolled live loop was gated on a paper-trading parity run, with the flip criterion being identical order intents over a soak window, and the hand-rolled loop was deleted once the flag flipped, so there is exactly one loop to maintain. The four adapter seams (bar feed, execution, portfolio view, observer) are plain Protocols, and the live implementations translate "fills arrive asynchronously from the broker" and "equity comes from the sleeve, not local marks" into the same interface the simulator satisfies synchronously.

Parity deliberately ends in a few documented places. Live evaluates only when every subscribed symbol has the current period's bar, so a halted symbol stalls the rebalance; backtests fill at bar close with slippage while live gets real partial fills; daily backtest bars are split-adjusted while the live stream is raw; and a daily-lookback indicator warms from preloaded daily history at session start. The resolution gap that used to follow (indicators updating on raw one-minute bars) was closed structurally: the live feed folds the intraday stream into a forming daily bar and evaluates indicators at daily resolution, so live indicator semantics match backtest by construction, with parity tests holding bars, indicator series, and orders equal over the same folded data. What remains open is timing within the day: live decides on the first complete snapshot of the day, a close-so-far reading the parity tests pin, while aligning the decision to the session close is a trade-timing product change we have deliberately not made yet.

On the halted-symbol case: no evaluation happens that period and positions stay put, which is safe but silent. A reviewer could reasonably argue for evaluating with a stale bar after a timeout. We would want that behind a per-strategy opt-in, because trading on a stale price is a worse default than doing nothing. *What if the symbol never comes back?* Session start refuses symbols that are not active and tradable at the broker. In operation, a gate that has not opened past a staleness window raises a per-tenant alert once per episode, and a delisting found by the periodic asset check marks the session degraded and puts a forced-close decision in front of the user rather than acting on their money automatically. A delisted symbol still holds the gate shut until that decision is made; evaluating around it is a product decision we have deliberately not automated.

Inside evaluation, a condition over NaN or missing data is fail-safe false, but counted, propagated to the session, and emitted as a live metric (`degraded_eval_count`), because a stale indicator that presents as a legitimate no-signal is a common way for a strategy to fail with no visible sign. The alternatives were to throw and halt the strategy, or to return false silently; we rejected both.

### Versioning and the execution lifecycle

Strategies are copy-on-write. Any source change mints an immutable new version (row locking serializes concurrent saves), so backtests and live sessions pin to an exact reproducible definition. Lifecycle is a small explicit state machine (draft to active, active to paused and back, any of those to archived, archived terminal), and archiving refuses while a live execution runs, because archiving must not release capital out from under a runner.

The execution lifecycle is where strategy touches money. Start funds the sleeve first (get-or-create account, allocate capital, persist the sleeve identity on the execution row) and only then flips to RUNNING, so a funding failure aborts go-live; the funding call is idempotent, so restarts never double-fund. Stop marks the execution stopped first, commits, then makes a best-effort call to close the sleeve, leaving the sleeve id as a needs-release marker on failure for the leader-elected sweeper. Plan limits (live-strategy count, monthly backtests) are enforced at these gates from the shared database.

The client orchestrates the two-phase deploy (create execution, start execution, start trading session), and there is deliberately no server-side saga. The safety net is trading's session rehydrator: on its periodic pass it adopts RUNNING executions that have no live session, through the same per-session advisory locks it uses for the crash case where a runner died and left its session row alive. A deploy that funded a sleeve and then failed to start a session therefore converges to a running session instead of remaining a funded orphan. The other two race cases have simpler answers: two users hitting start simultaneously are serialized by the database state transitions, and a start whose trading call times out but actually succeeded is absorbed because session start is idempotent per execution.

### The second implementation problem

The web builder contains an independent TypeScript implementation of the language (parser, emitter, validator) so the visual editor and the code pane can round-trip locally with block ids stable across reparses. It is roughly three thousand lines mirroring eighteen hundred lines of Python, and before the two were pinned together it had drifted in small ways, dropping `:benchmark` on emit and accepting keywords the Python parser rejects. Drift is now contained by a shared conformance corpus (S-expression in, canonical JSON out) that both CI lanes run, so a divergence fails the build in whichever implementation introduced it. We scoped it deliberately small; a grammar formalization or a WASM-shared parser would both be over-engineering at the current rate of language change.

---

## Eventing

All asynchronous communication is proto-typed events over a Kafka backbone (GCP Managed Service for Apache Kafka), through a five-layer library: an envelope proto, a transport (the only broker-aware file), a codec with a type registry, a bus exposing publish, tail and consume, and typed per-stream catalogs. Six logical channels map to six topics, each keyed by its natural entity: fills by `account_id`, bars by symbol, order and position updates by session, backtest progress by backtest id, and notifications by tenant. There is one topic per channel and never a topic per session; per-session UI fan-out is a key filter on an ephemeral consumer group that seeks to a recent offset. Retention is per-topic and matches intent: long for fills (an operational replay window), weeks for notifications (whose permanent store is Postgres), days for bars, hours for UI streams.

The decisions worth defending:

- The envelope is bytes plus an explicit type discriminator rather than `protobuf.Any`. It is simpler, and it is what made the transport swap invisible to every layer above it.
- There are two delivery shapes and only two. `tail` means every reader sees everything (ephemeral group, offset seek, key filter), which is right for UI streams, including the replay-from-run-start behavior backtest progress relies on. `consume` means a shared group with manual commit-after-write offsets, and it is used exactly twice: for money (fills) and for notifications, which persist their in-app row before acking for the same reason. Collapsing the two into one abstraction was considered and rejected because their failure semantics are too different to share an API honestly.
- Redis Streams came first, and Kafka replaced it through the one-file transport seam, which is why the swap was invisible to every layer above the transport. The migration is described after this list.
- We chose the GCP-managed service rather than Confluent so the backbone lives in the same cloud as everything else: VPC-native, one Terraform surface, and per-service identity done properly, with each producing or consuming service holding a GCP service account with topic-scoped IAM, bound through Workload Identity, authenticating over SASL/OAUTHBEARER with no static credentials. The costs of that choice are stated in the migration plan. Schema Registry is deferred; proto payloads are self-describing inside a closed system, and `buf` breaking-change checks run in CI (see Platform plumbing), so schema evolution is gated at build time rather than at the broker. Tiered storage is absent, which is acceptable because Postgres rather than the broker is the permanent book of record, and a topic-to-GCS sink is the archive option if one is ever needed.
- A reviewer will ask why not Pub/Sub, given the GCP-native argument. Pub/Sub has ordering keys, but the library's transport contract (consumer groups, offsets as opaque cursors, replayable tails, manual commit) was designed against Kafka's model, and the Kafka API keeps the backbone a portable protocol rather than a proprietary one. The adapter was one file for either choice, but the cost of migrating away from Pub/Sub later would be higher than from Kafka, since Kafka's API is a portable protocol.
- Trace context rides the envelope (W3C traceparent in metadata, injected on publish and extracted on consume), so producer-to-consumer spans link without any consumer effort.
- Local development runs a real broker (a single-binary Redpanda or KRaft Kafka in compose, plaintext locally, OAUTHBEARER only in GCP), and the transport passes the same contract-test suite the Redis transport did, so protocol conformance is verified rather than assumed.

The Redis-to-Kafka migration is worth keeping in the record. Redis Streams was the right first choice: partitioned ordering, long retention, and replay at scale were things launch volumes did not need, and Kafka is an entire operational subsystem. What kept it cheap to reverse was that the transport interface was designed against Kafka's shape from the beginning: the publish call always carried a partition key (Redis dropped it), cursors were opaque strings, and the claim-idle parameter was documented as ignored where failover is automatic. The migration was therefore one new transport file, threading keys the producers already had, and cutting over per stream, lowest-stakes first, with the ledger last behind the dual-run parity gate described under Ordered fill ingestion. The Redis transport, the advisory-lock fill consumer, and the per-stream Redis tests were deleted rather than kept as fallback, because a half-retired transport means maintaining two. What Kafka bought, concretely: the single-writer ledger fold became parallel by account, the length-trim loss window became time-based retention, and money events stopped sharing a Redis instance with caches. Redis keeps what it is suited for here: the market-data cache, the Celery broker, and the backtest locks and flags.

*What if thousands of browsers tail the per-session topics?* Order and position topics are low-volume, so per-viewer ephemeral groups stay cheap, and the high-volume bars topic fans out through market-data's stream manager rather than through per-browser consumers. The design holds until viewer counts justify a dedicated fan-out tier, which is a scaling addition rather than a contract change.

*What if the broker dies?* UI streams degrade; ephemeral groups reattach and re-seek. Backtest progress degrades to logging after repeated publish failures rather than failing runs, since progress is advisory and results are not (see Backtesting). Order submission proceeds, and ledger publishes fail soft (logged, never raised) because the republish drain and the REST-sync recovery converge the ledger afterward, while ledger consumption never gives up, since uncommitted offsets simply redeliver. Notification publishes take the same posture: fire-and-forget, never raised into the producing path, with the durable consumer converging delivery afterward. This asymmetry, in which money publishes never block trading and money consumption never quits, is a property of the emission and consumption design rather than the transport, and it survived the transport swap unchanged. A Redis outage now touches only caches, Celery, and the backtest locks.

---

## Market data

One library, `llamatrade_alpaca`, owns every byte to and from Alpaca. On the REST side it provides clients with a token-bucket rate limiter, a circuit breaker, and retry with backoff, composed in a fixed order (limiter, then breaker, then HTTP, then typed error mapping, with auth failures classified before retryable ones). On the WebSocket side it provides clients with shared reconnect and backoff and two deliberately different delivery models: callback fan-out for the multiplexing ingest daemon, and an async-generator for single consumers that own their backpressure, such as the live trading fill stream. Mock stream clients are first-class exports so every consumer's tests run without the network. Services are forbidden from bypassing the library, by convention and review, and the absence of any other HTTP client pointed at Alpaca is checked when the question comes up.

The market-data service is one image with two roles. The serving role handles Connect RPCs and uses Alpaca REST only, for gap fills and snapshots. The ingest role is the platform's sole Alpaca WebSocket consumer; it writes minute bars to a dedicated TimescaleDB and republishes them onto the bars topic for the serving role to fan out. The split exists because Alpaca allows one data stream per credential, the write path must be a singleton, and the read path must scale horizontally; separating them means scaling one never multiplies the other. The ingest role deploys as a single-replica Recreate workload; a second instance would be wasteful rather than incorrect, since the writes are idempotent upserts, so a leader lock was judged unnecessary.

*What if a strategy trades a symbol outside the ingest universe?* Live sessions hold their own per-tenant streams today, so they are unaffected, and the ingest universe is no longer static: it is the union of the configured baseline and the symbols of running live sessions, refreshed on an interval, with the baseline never dropped and a failed refresh keeping the current subscriptions. That derivation is the precondition for ever serving live sessions from the shared fan-out.

Storage decisions: raw unadjusted minute bars in a hypertable with 90-day retention; split-adjusted daily bars kept forever; intermediate timeframes as continuous aggregates that can never be written directly (a whitelist makes it a hard error); quotes, snapshots, and the market clock never persisted, only cached with short TTLs. Adjustment discipline lives in exactly one function (daily bars are split-adjusted, intraday bars are raw). A previous bug, raw bars written under a split-adjusted label, is the reason this is centralized.

The read path is read-through with precise semantics: serve stored bars, fetch only edge gaps from Alpaca, and persist only closed bars (the currently forming bar is served but never stored). Interior holes are the ingest gap-repairer's job, not the read path's. The failure posture is uniformly to degrade rather than fail: if Alpaca is down, serve stored bars; if the store is down, fall back to the cache path; if the clock API is down, use a full server-side NYSE calendar (holidays, early closes, DST); if no live snapshot is available, synthesize one from the last two stored daily bars so positions mark to the last close instead of cost.

Some boundaries worth knowing:

- The Alpaca request budget is enforced cluster-wide through a shared Redis token bucket, so adding replicas divides the budget rather than multiplying it.
- The bars client follows Alpaca's `next_page_token`, so long ranges paginate rather than truncating, and range limits mean the most recent N bars.
- A slow bar-stream subscriber gets drops rather than backpressure (bounded per-client queues), which is the right behavior for market data and would be wrong anywhere else.
- IEX, the free feed covering roughly three percent of consolidated volume, is the data quality we actually ship; SIP is a paid upgrade decision for later (see Accepted limitations), and user-facing accuracy claims reflect that.

---

## Identity, tenancy, and the data layer

Tenant isolation is four independent layers. The goal is that no single layer failing or being misconfigured should be sufficient for cross-tenant access.

> **Figure 4. Four independent tenant-isolation layers.**
> _(insert Excalidraw export: 05-identity)_

The middleware is pure ASGI rather than Starlette's BaseHTTPMiddleware, which runs the downstream app in a separate task and would break ContextVar propagation; this class of bug is avoided by construction rather than caught later in debugging. `resolve_identity` is the single reconciliation point between the verified token identity and the untrusted tenant context carried in request bodies. For user tokens the token always wins and a mismatched wire tenant is rejected; for service tokens the wire is trusted, which is the delegation mechanism. The forged-tenant hole that used to exist across services was closed platform-wide and verified service by service. RLS is the backstop: a fail-closed predicate under which an unset GUC yields zero rows rather than an error, `FORCE` so the table owner is also subject to policies, write-side `WITH CHECK`, and a CI test asserting exact-set equality between models that carry a tenant id and tables that carry RLS, so a new tenant table cannot ship uncovered.

Four properties of the identity plane are worth stating explicitly, because each replaced a weaker predecessor and the reasoning should not be lost.

- Tokens are signed asymmetrically. The auth service holds the signing key; every other service holds only the verify key, so a compromised service cannot mint tokens. The verify key is distributed to each service as configuration from the secret store and read once at startup, not served from a JWKS endpoint, so rotating the key means updating the secret and restarting every pod, with a mixed-key window during the rolling restart; a JWKS endpoint with overlapping keys is the planned improvement. Service tokens are short-lived and carry an audience and a service-name claim, which money-path services check against an allowlist, so a stolen service token is scoped rather than a platform-wide capability. mTLS was considered and deferred as heavier than the threat model requires; with the Kafka backbone carrying per-service accounts and topic-scoped IAM (see Eventing), both the RPC and event planes now have per-service identity. The original design was HS256 over one shared secret, a defensible simplicity trade for nine services in one trust boundary, and the thing we replaced first on the way to real money.
- RLS is enforced at runtime, not merely declared. Every deployment connects as a NOSUPERUSER application role, and each service asserts at startup that its role cannot bypass policies. Two bugs had to be fixed together with the role change, and were: trading's audit and alert paths run under tenant-scoped sessions rather than bare ones, and long-lived sessions re-establish the transaction-local tenant GUC on every transaction through a session event hook, since a commit clears it. Flipping the role without those two fixes would have broken the trading audit trail, which is why they shipped as one change.
- Revocation is supported and inexpensive. The middleware checks a Redis denylist; logout and password change insert the outstanding token ids, and refresh tokens rotate on every use with the replaced token invalidated. Access tokens last thirty minutes, so the denylist stays small and the check stays one Redis read.
- Broker credentials are envelope-encrypted at rest, behind a per-value cipher seam. The deployed default derives a per-credential key from a service secret (PBKDF2 with a random salt), so a database dump alone does not yield the secrets. A Cloud KMS cipher, in which a per-credential data key is KMS-wrapped and unwrapping requires the calling service's identity, is built and tested behind the same seam but is not yet enabled: no key is provisioned and the configuration selects the local cipher, so turning on KMS is a hardening step still to take before real money. Key derivation no longer runs on hot paths; a stored key-prefix column serves the display case that previously forced a decrypt per list call.

*What if an operator legitimately needs cross-tenant access?* `system_session` exists for exactly that, and an escape hatch that left no trace would gradually undermine defense in depth; every bypass therefore emits a structured audit line (caller, reason, tenant scope) and increments a counter metric, so the hatch stays observable.

Two constraints on future multi-user tenants are enforced rather than assumed: `resolve_identity` rejects a wire `user_id` that disagrees with the token, and per-user authorization remains deliberately unbuilt, which is safe while tenants are single-user; the roles work is scheduled with the self-serve signup milestone that ends that assumption.

*What if Redis is down for auth?* The two Redis-backed guards fail in opposite directions on purpose. The login and registration rate limiters fail closed, so an outage refuses new logins rather than lifting the brute-force ceiling; the revocation denylist fails open, so already-issued tokens keep working until their natural expiry. The pod stays serving because the Redis check is non-critical, so an outage locks out new sessions while briefly un-revoking old ones, and the middleware refuses to start at all if revocation is unconfigured in production.

*What if service clocks skew?* Token verification uses no leeway, and service tokens live five minutes and refresh a minute early, so more than about four minutes of skew between a caller and a callee makes every service-to-service call fail closed. It is a bounded, self-announcing failure rather than a silent one, but it is a real operational constraint on the fleet's clocks.

Beneath all this sits one shared Alembic chain (linear, CI-guarded), proto-int to Postgres-enum bridges with a parity test that has already caught a real silent enum divergence, and Decimal end to end for money. Proto carries decimals as strings, and floats survive only at the numpy, vendor-wire, metrics, and JSON edges, each documented.

---

## Backtesting

Backtest execution is Celery-only. The RPC validates, writes a PENDING row, enqueues, and returns; nothing simulates in the API process. This keeps API latency flat and makes worker capacity an isolated scaling knob. Configuration the engine cannot honor (shorting, position caps, parameter overrides) is rejected loudly at submission rather than accepted and ignored, because a plausible-looking but wrong backtest is the most expensive artifact this system can produce.

The design is mostly about failure modes rather than the happy path.

- Completion is a guarded terminal write: `UPDATE ... WHERE status = RUNNING`, and zero rows means a concurrent cancel won and the result is discarded. Cancellation itself has three independent mechanisms: the database status, which is authoritative; a Redis flag polled between trading dates that fails open, since a broken Redis must never abort runs; and the terminal-write guard.
- Delivery is at-least-once with compensations and no outbox. The PENDING row commits before the enqueue, and a failed enqueue marks the row FAILED so the database matches the error the caller saw. A beat-scheduled reaper covers the rest: lost workers (RUNNING past the hard time limit plus grace becomes FAILED), lost enqueues (stale PENDING is re-enqueued, and duplicate execution is tolerated because a unique one-result-per-backtest constraint makes the second writer lose), and abandoned rows. Only typed market-data failures retry; everything else is terminal.
- Datasets are content-addressed. Bar fetches are expensive and repeated, since many users run the same templates, so the worker materializes each unique request shape (symbols, range, timeframe, hashed together) into an immutable Parquet snapshot behind a Redis single-flight lock. Concurrent identical runs coalesce onto one fetch, and a warm dataset touches neither market-data nor Alpaca. That last property makes backtest load independent of market-data capacity. Older documents describe a "scale-to-zero orchestrator" here; the reality is plainer, a queue-depth gauge exported from the API process and a worker autoscaler shipped behind an operator opt-in (below).
- Metrics discipline: every annualized number is computed on a daily-resampled equity grid, because annualizing over raw intraday bars inflates Sharpe by the square root of bars per day; mathematically undefined values (profit factor with no losses, alpha and beta on degenerate variance) are None all the way to the wire rather than a fabricated zero; and the benchmark is date-joined rather than positionally aligned, restricted to the backtest window so warm-up padding cannot distort it.

Progress streams to the UI over a replayable event topic, tailed from run start so a late-joining browser sees the history. Status is published, never inferred from percentages, since failed runs also reach 100%. Publish failures degrade to logging after repeated consecutive errors rather than failing the run, since progress is advisory and results are not.

The remaining edges have answers. Two identical backtests racing the dataset lock resolve with the loser polling the store, plus a timeout fallback that materializes anyway rather than deadlocking on a dead producer. A worker dying mid-run is covered by acks-late redelivery or the reaper, and idempotent result-writing makes the duplicate harmless. The parser enforces a nesting-depth limit and reports it as an ordinary validation error, so a pathological payload cannot produce a 500. A janitor evicts dataset snapshots by last access, so the store stays bounded. A one-minute backtest timeframe is accepted while the rebalance gate still fires at most daily; the semantics are deliberate (intraday data, daily decisions) and are stated in the product documentation.

*What if a burst of submissions arrives?* The queue depth is sampled per routed queue in the API process, and a KEDA scaler for the worker deployment ships in the manifests behind an operator opt-in, with conservative scale-down and a termination grace sized to the task time limit so a scale-down never kills a mid-flight run. The opt-in is deliberate: the scaler needs KEDA and an in-cluster Prometheus, neither of which is provisioned yet, so until they are, a burst still queues and the gauge is the operator's signal. *What if the janitor evicts a dataset another run is about to read?* Snapshot writes are atomic replaces and a reader that misses falls back to a rebuild, so an eviction race costs a refetch, never a wrong result.

---

## Platform plumbing worth review attention

**Telemetry.** Metrics are created through the OpenTelemetry API with a Prometheus reader, so we get distributed tracing across the signal, risk, order, fill, ledger path without giving up Prometheus dashboards, and each service makes one `init_telemetry` call. The part we would defend hardest is the enforced cardinality contract: metric names validated against a pattern, labels validated against a bounded allow-list, a forbidden list that bans tenant, user, symbol, and order identifiers from labels outright, and histogram buckets that must be registered centrally or instrument creation fails. Per-tenant questions are deliberately routed elsewhere: business numbers to the ledger, operational drill-down to logs and traces (which do carry tenant ids), aggregate health to metrics. Enforcement is environment-aware; violations raise in development and are logged and dropped in production, because a label bug must never fail a request. Exporters are wired in every environment: services export OTLP/HTTP to the collector, which forwards to the managed tracing backend, and the endpoint is part of base configuration rather than an optional extra.

**Proto discipline.** One buf module with no package versioning, a deliberate pre-1.0 choice worth revisiting if anything external ever consumes us. Generated Python is committed to the repo, and the contributor docs say so. `buf lint` and `buf breaking` run in CI against main, which matters twice over: services deploy independently, and the Kafka schema posture (see Eventing) leans on the same gate in place of a schema registry.

**Billing.** The most complete peripheral service: real Stripe integration (checkout, portal, webhooks with signature verification and idempotent handlers), plans in the database, and a free tier that bypasses Stripe entirely. Two decisions to note. Plan enforcement is not a billing RPC; strategy, backtest, and trading read plan limits directly from the shared database, so trading availability does not depend on billing being up. A lapsed or cancelled subscription is enforced only at the next start, not against a running session: the live-strategy limit is checked when an execution starts, so a running strategy keeps trading and the tenant is blocked from starting new ones rather than stopped mid-flight. Stripe is the source of truth, with local rows as a fast cache. The webhook secret is required in production through the same `require_secret` guard the crypto keys use, handler failures in retryable classes return non-200 so Stripe retries them, and the free-tier limits have a single source, with the no-subscription fallback stricter than the catalog rather than more generous. Payment failure and trial expiry surface to the tenant through the notification service, so an account does not go past-due silently and then fail trading preflight unexplained.

**Notifications.** All user-directed messaging is one subsystem. Producers publish typed notification events onto `lt.notifications`, keyed by tenant so each tenant's notifications are ordered, and the notification service is the sole durable consumer: it persists the in-app row before committing the offset, then delivers to email and any configured webhooks with per-delivery tracking. Trading's alert surface and portfolio's ledger-incident dispatcher are thin publishers over this contract; neither delivers anything itself, so a slow webhook endpoint cannot stall a money-path task. The webhook contract is uniform across the platform: the signature covers the exact transmitted bytes, 4xx responses are not retried, and a persistently failing endpoint is disabled automatically, with the disable surfaced to the tenant as a notification of its own. Preferences are a per-category channel matrix with critical and security categories pinned on; recipients are tenant-scoped while tenants are single-user. User-defined price alerts run in the same service: event-driven conditions match inside the consumer, and market-driven conditions (price, volume, RSI) are evaluated by a leader-elected loop tailing the bars topic, with cooldowns and deterministic trigger ids so a torn leader cannot double-notify. Cross-tenant infrastructure signals (DLQ depth, consumer lag, lease loss) stay on operator metrics rather than user notifications. Auth's email flows (welcome, verification, password reset, and the password-changed and lockout security notices) deliver through the same email channel.

**The copilot** is architecturally a client, not an authority. It generates DSL, and everything it produces flows through the same validator, versioning, and execution gates as a human edit, so the agent can propose but cannot deploy something the platform would reject from a person. Side-effecting tools are draft-and-confirm: a proposed backtest halts the stream until the user approves, and approved calls execute with tool chaining disabled so one approval cannot cascade. The confirmation round-trip executes the server-persisted proposal keyed by its confirmation id, not arguments echoed by the client, so a hostile client cannot swap what was approved for something else. Memory extraction is regex-based by design, with no LLM on the write path, for cost and injection-surface control; pgvector is provisioned but unused until retrieval needs it.

---

## Build, deploy, and environments

All nine services build from one parameterized multi-stage Dockerfile pattern: repo-root context, shared libraries installed in dependency order, a non-root runtime user, a health check, and the service's real port. CI builds all nine images on every change, so a Dockerfile that does not build cannot merge. This uniformity was hard-won; an earlier generation of per-service Dockerfiles drifted until six of nine could not build at all, which is why the pattern is now single-sourced and CI-enforced rather than copied by hand.

The staging workflow builds and pushes images, applies the kustomize overlay, runs the SHA-tagged migration Job to completion (delete and re-apply, since a completed Job spec is immutable), and rolls the deployments; the production workflow promotes the same images by tag. The manifests describe the real topology: the serving deployments with HPAs, the market-data ingestor as a single-replica Recreate workload, the backtest worker and beat, the Timescale instance, and the collector. `kustomize build` for every overlay runs in CI next to the image matrix, so a manifest that does not render cannot merge either.

Terraform and the cluster agree with each other. Secrets flow from Secret Manager into the cluster through External Secrets Operator, and no Secret objects are committed. The managed Redis is the Redis the cluster uses. The Kafka cluster and its topics are Terraform-provisioned with per-service topic-scoped IAM through Workload Identity (see Eventing). The observability stack receives what services send: OTLP/HTTP to the collector on the correct port, forwarded to the managed backend, with Prometheus scraping the ports services actually listen on.

The dev compose stack remains the reference description of the topology (two Postgres instances, Timescale, Redis, a Kafka broker, the collector), and the CI end-to-end job boots the real mesh from it. CI also lints strictly (pinned ruff and pyright, a no-suppressions gate) and runs per-service tests with 80% coverage gates on the money-adjacent services. Where compose and the manifests describe the same workload, the ports and roles are kept aligned deliberately, because the failure mode of this layer is precisely two topology descriptions diverging until neither can be trusted.

*What if a migration has to be undone under load?* There is no rollback machinery, and treating Alembic downgrades as an operational plan would be dishonest; the documented convention is forward-only expand-and-contract, with downgrades reserved for local development. *What if two deploys run concurrently?* A per-environment concurrency group on the deploy workflows queues them, so two runs cannot interleave image pushes and rollouts.

---

## Accepted limitations and residual risks

Everything in this section is a deliberate scope decision or an accepted risk, stated together with the condition that should reopen it. Defects found during the production-readiness review were tracked and closed through `planning/production-readiness-gaps.md` and its implementation plan; what follows is what remains unbuilt by choice, not by oversight. A later implementation read (see Findings from the implementation read) surfaced further issues that are not yet closed; those are listed separately, so the deliberate choices here stay distinct from the open defects there.

1. Execution is gross, not netted. One sleeve order is one broker order, which keeps attribution trivial; the deferred block-and-allocate design is described under What we deliberately did not build yet. Revisit when order volume makes the commission and market-impact savings material, at which point the question of where sizing lives reopens with it.
2. Margin accounts only. A preflight check refuses cash accounts, so settled and unsettled cash never diverge in the book. Modeling settlement becomes a new posting family when cash accounts are admitted.
3. IEX market data. The free feed covers roughly three percent of consolidated volume, and user-facing accuracy claims say so. SIP is a paid upgrade decision, taken when accuracy complaints or product positioning justify the cost.
4. Long-only, daily-or-coarser rebalancing. Intraday tactics would require revisiting the two-clock model (tick feed versus rebalance gate) and are out of scope; the language refuses what the engine cannot honor.
5. One shared Postgres. The coupling is accepted and the extraction trigger is storage-behavior divergence, which is how bars earned their own TimescaleDB. The per-service-database question remains open by invitation (see Open questions).
6. Effective-once, not exactly-once. Delivery is at-least-once everywhere, with determinism and idempotent writers providing the effective-once behavior. We state this rather than claim stronger semantics the system does not have.
7. The `lt.ledger.fills` partition count is a one-way door. Growing a keyed topic remaps keys and breaks per-account ordering across the boundary, so the count is sized from an account-growth estimate and reviewed at account-count milestones (see Open questions).
8. Redis is a single replica carrying cache, the Celery broker, and coordination locks. This is acceptable because money events live on Kafka and cache loss is recoverable; revisit if any Redis-backed workload becomes money-bearing.
9. Slow bar-stream subscribers get drops, not backpressure. Correct for market data, where a stale tick is worse than a missed one, and wrong for anything else; the boundary is documented at the stream manager.
10. Two DSL implementations, pinned by a conformance corpus rather than merged into one shared parser. The corpus fails CI on divergence; a WASM-shared parser becomes worth it only if the language change rate rises substantially.
11. No mTLS. Asymmetric JWT with audience claims is the identity line on the RPC plane, and Kafka topic-scoped IAM covers the event plane. Revisit given a compliance requirement or a service count near twenty.
12. Copilot memory is heuristic extraction only, with no LLM on the write path, for cost and injection-surface control; pgvector stays idle until retrieval quality demands embeddings.

## Findings from the implementation read

A full read of the code after the production-readiness pass (2026-07-30) surfaced the issues below. Unlike the accepted limitations above, these are not deliberate choices; they are defects and risks, documented here and not yet closed. The correctness-critical money-path items (1 to 3) are also code-fix candidates.

Money path, correctness:

1. Concurrent `StartExecution` for one execution can double-allocate capital: the execution row is read without a row lock, unlike the archive path, so two starts can both fund. A `SELECT ... FOR UPDATE` on the row closes it.
2. A funding call that succeeds and then fails to commit orphans a funded sleeve no sweeper can find, because the execution row rolls back with a null sleeve id. This is the one funding path with no compensating sweep.
3. Fund operations (deposit, withdraw, allocate, transfer) double-book when the idempotency `request_id` is empty, and the RPC layer does not require it.
4. A trading fill for a known symbol but an unrecognized order id books into the strategy's sleeve; only reconciliation corrects it.
5. A broker REST failure marks an order rejected, which removes it from the stranded-order sweep, so a lost-response-but-accepted order is not re-adopted by that sweep.

Configuration and deployment:

6. Auth and billing have no `REDIS_URL` in the base manifests while the environment is production, which crash-loops the fail-closed auth middleware; the RS256 key secret is not generated by any code path.
7. Portfolio has no PodDisruptionBudget despite hosting the money-path ledger and the writer lock.

Robustness:

8. Billing's Stripe calls are synchronous inside async handlers and block the event loop; Stripe writes carry no idempotency key and the customer create is non-atomic.
9. A dropped copilot stream loses the persisted tool proposal, leaving an already-issued confirmation id unconfirmable while any side effects that already ran stand.

## Open questions for reviewers

1. Netting graduation: what order volume or cost threshold should trigger building block-and-allocate, and when it is built, does sizing move to portfolio with it? The ledger and attribution are proven; the deferral is a business-value question now, not a risk question.
2. Halted-symbol behavior: strict all-symbols gating is the shipped behavior, so a halted symbol stalls that period's rebalance. Should we offer opt-in stale-bar evaluation with a timeout, and if so, what staleness bound is acceptable on a money path?
3. SIP data upgrade: at what point do accuracy claims or user complaints justify the paid consolidated feed, and does the answer differ for backtests versus live signals?
4. Per-service databases: the case against is made under Topology decisions, and the coupling deepens over time. Is anyone willing to argue the other side before we close the question?
5. Partition-count review: who owns re-estimating the `lt.ledger.fills` sizing at account-count milestones, and what milestone triggers the first review?

## Worked example: one strategy end to end

The sections above describe subsystems; this one follows a single strategy through all of them, with concrete numbers, so the seams are visible. The example is deliberately chosen to exercise the parts that matter: a cross-symbol condition, an indicator-only symbol, both a fixed and a computed weight method, and a monthly rebalance.

```
(strategy "Recession Radar"
  :rebalance monthly
  :benchmark SPY
  (if (> (rsi SPY 14) 70)
      (weight :method specified
        (asset TLT :weight 60)
        (asset GLD :weight 40))
      (else
        (weight :method momentum :lookback 90 :top 2
          (asset VTI)
          (asset QQQ)
          (asset IWM)))))
```

In words: when the market looks overheated (RSI of SPY above 70), hold 60/40 treasuries and gold; otherwise hold the two strongest of three equity ETFs, weighted by their trailing 90-day return. SPY itself is never traded; it is a signal input and the benchmark.

> **Figure 5. One strategy through every subsystem.**
> _(insert Excalidraw export: 06-lifecycle)_

**Authoring.** All three surfaces (visual builder, code editor, copilot) produce this same S-expression; the builder round-trips it through the TypeScript implementation, and the copilot must pass it through `validate_dsl` before proposing it as a pending artifact the user commits. On save, the strategy service parses and validates the text, derives the projections (`symbols`, `rebalance: monthly`), and writes immutable version 1. Static analysis extracts one indicator series (`rsi_SPY_close_14`), the required symbol set {VTI, QQQ, IWM, TLT, GLD, SPY}, and the minimum history: the momentum lookback of 90 bars dominates the RSI's 14, so the strategy needs roughly 90 bars of warm-up and retains a history window of about 100.

**Backtesting.** The user requests a two-year daily backtest with $25,000. The RPC validates, writes a PENDING row, enqueues, and returns; a Celery worker picks it up. Warm-up padding converts 90 bars into roughly 140 calendar days, so the dataset spec covers about 27 months for all six symbols (the benchmark rides the same fetch). The spec hashes to a content address; if another user ran the same template over the same window, the Parquet snapshot is already warm and the run touches neither market-data nor Alpaca. The replay then walks dates: warm-up dates feed indicators without trading; the first evaluated date always rebalances; after that the monthly gate opens only on the first trading day of each month. On each rebalance date the RSI branch picks a side, the momentum method ranks VTI, QQQ, and IWM by trailing return and keeps two, sizing diffs targets against holdings with sells sorted before buys, and `SimulatedExecution` fills at close with slippage and a flat fee. Metrics are computed on the daily-resampled curve, the SPY benchmark is date-joined and restricted to the window, and the result row persists with a capped equity curve. The run is reproducible by construction: the same version over the same window and dataset produces identical results, because every stage from parse to fill model is deterministic.

**Deploying.** The client creates an execution ($25,000, the user's paper credentials) and starts it. Start checks the plan's live-strategy quota, then funds the sleeve: get-or-create the ledger account for those credentials, allocate $25,000 from Unallocated into a new strategy sleeve (a balanced `CAPITAL_ALLOCATED` event), persist the sleeve identity on the execution row, and only then flip to RUNNING. The client then starts the trading session. Trading's preflight checks the subscription (live mode requires a paid plan; this is paper), that the credentials belong to the tenant and match the session mode, and buying power; it resolves the ledger identity from the execution, refuses if the sleeve already has a session, preloads about 90 daily bars per symbol so the indicators are warm from the first live bar, and starts the runner loops (bar loop, equity sync, reconciliation, fill stream, republish drain). Nothing prevents the same version from also running a second execution in a different mode; each execution gets its own sleeve, which is exactly the non-interference boundary doing its job. Editing the strategy mints version 2 but changes nothing here: the runner stays pinned to version 1 until stopped and redeployed.

**A rebalance morning.** Suppose the sleeve enters November holding VTI ($13,100) and QQQ ($11,400) with $500 free cash, and RSI(SPY, 14) has climbed to 73.8.

> **Figure 6. A rebalance morning: evaluate, size, submit, fold.**
> _(insert Excalidraw export: 07-rebalance)_

The evaluation itself waits for the all-symbols gate: every one of the six symbols must have that period's bar, including SPY, which is subscribed purely as a signal input. The gate opens, evaluation runs off the event loop, and the defensive branch produces targets of TLT $15,000 and GLD $10,000 against roughly $25,000 of sleeve equity. Drift sizing emits four intended orders and sorts the sells first, so the VTI and QQQ proceeds fund the buys within the same rebalance. Each order passes the risk gate (sleeve active, buy fits free cash), gets its deterministic `client_order_id`, is persisted as intent, and goes to the broker. The buys reserve cash at the reference price plus two percent, since a market fill can gap. Fills come back on the trade stream; each order publishes exactly one `LedgerFill` at terminal state onto the account-keyed topic; the fold applies buys and sells in order, computes the sells' realized P&L from their FIFO lots, consumes the reservations, and re-checks the sleeve invariants. Within a minute the equity sync reads the new sleeve state back and the UI streams show the rotation. For the rest of the month, ticks feed indicators and the gate stays closed; degraded evaluations (a NaN from a data gap) would count into a metric rather than silently reading as false.

**When reality disagrees.** Mid-month the user manually sells some TLT in the Alpaca app. The trade has no `client_order_id` of ours, so the next reconciliation pass finds the broker short against the ledger, and quantity mismatches are never auto-corrected: every sleeve holding TLT freezes, the tenant is notified (in-app and by email, plus any configured webhook), and the risk gate rejects new orders on the frozen sleeve until the discrepancy is resolved by an explicit correction. The conservative posture is deliberate; the alternative (silently shrinking some sleeve's position to match) would corrupt exactly the provenance the ledger exists to keep.

**Retiring.** Stop marks the execution stopped, then closes the sleeve. The close refuses while any reserved cash remains (an in-flight order), so a stop during a rebalance waits for the orders to reach terminal state. On close, the TLT and GLD lots re-home to Unmanaged at cost (a re-home is not a sale, so no P&L), free cash returns to Unallocated, and the `SLEEVE_CLOSED` event's deterministic id makes a retried close a no-op. The runner notices the closed sleeve on its next equity sync and stops itself; a late fill would be re-routed to Unmanaged at ingestion. The user's capital is back in the pool, the strategy's full trading history remains queryable from the log, and deploying version 2 starts the cycle again with a fresh sleeve.

---

## References

### Repository documents

The repository documents this specification builds on, and how authority is divided between them:

- `portfolio-ledger.md`: the money contract, the most rigorous document we have. Nothing here supersedes its Integration Contract, which continues to be amended in place as the single authority on money movement.
- `execution-runtime.md`: runtime semantics and backtest-live parity.
- `strategy-dsl.md` and `signals-and-weights.md`: language semantics.
- `planning/kafka-event-backbone-migration-plan.md`: the Kafka backbone plan, with the topic map, cutover order, and the decisions the Eventing section summarizes.
- `planning/production-readiness-gaps.md` and `planning/production-readiness-plan.md`: the production-readiness register and its implementation plan, which record the review findings whose resolutions this specification's final state incorporates.
- `planning/notification-service-implementation-plan.md`: the notification subsystem plan behind the Notifications section, with the locked decisions, the full flow catalog, and the phase-by-phase test matrix.
- Per-service documents of varying freshness, and two ADRs.

This specification is the cross-cutting layer above them: decisions, alternatives, and risks in one place. Where an older document disagreed with the code (a retired language description, a mislabeled cipher, aspirational infrastructure presented as current), the stale sections were deleted in favor of this document and the subsystem contracts, so one authority remains. The subsystem documents stay the right place for contract-level detail.

The external links in the three groups below were each fetched and verified in July 2026; claims we could not verify on the page are excluded rather than cited.

### Competitor landscape

- [Composer by SoFi](https://www.composer.trade/): the closest comparable, no-code allocation strategies with backtesting and automated execution.
- [Composer API documentation](https://api.composer.trade/docs/index.html): symphonies are EDN (Clojure) nested trees of weight, condition, and filter nodes, the direct analogue of an S-expression allocation language.
- [Composer disclosures](https://www.composer.trade/legal/disclosures): Composer Securities is the broker-dealer, clearing through Alpaca and Apex; the same rail we use, one layer up.
- [SoFi acquires Composer](https://investors.sofi.com/news/news-details/2026/Introducing-Composer-by-SoFi-AI-Powered-Investing-From-Idea-to-Execution/default.aspx) (June 2026): the category's leading independent is now inside a public fintech.
- [QuantConnect](https://www.quantconnect.com/): the code-first incumbent; 500k backtests per month and an agentic assistant that can live-trade.
- [LEAN on GitHub](https://github.com/QuantConnect/Lean): the open-source reference implementation of a shared backtest and live engine, Apache-2.0.
- [Quantopian](https://en.wikipedia.org/wiki/Quantopian): 210,000 members and $48.8M raised before the 2020 shutdown; market validation and a business-model caution in one story.
- [QuantRocket on the Quantopian shutdown](https://www.quantrocket.com/blog/quantopian-shutting-down/): the diagnosis, a free community whose real customer was a fund, is the model we are not repeating.
- [QuantMage](https://quantmage.app): the closest single product shape, allocation logic on a BYO Alpaca account, with no AI surface and no per-strategy ledger.
- [Surmount SDK documentation](https://docs.surmount.ai/): strategies return a ticker-to-weight `TargetAllocation`, the same primitive as ours.
- [M1 Finance Pies](https://m1.com/invest/what-is-a-pie/): target-percentage investing at consumer scale; evidence ordinary investors think in weights.
- [Autopilot](https://www.joinautopilot.com/): per-strategy capital inside the user's own external brokerage account at $1B+ AUM, with no authoring, backtesting, or ledger accounting.
- [Robinhood opens to agents](https://robinhood.com/us/en/newsroom/robinhood-is-now-open-to-agents/) (May 2026): autonomous AI execution in ring-fenced accounts; independent convergence on capital isolation as the agent-risk primitive.
- [Alpaca OAuth partners](https://alpaca.markets/oauth): the competitive set already on the same brokerage rail.
- [Kraken acquires Capitalise.ai](https://blog.kraken.com/news/capitalise-ai) (August 2025): no-code strategy automation absorbed by a venue; the consolidation pattern in this category.
- [Horizon Trade pre-seed](https://www.calcalistech.com/ctechnews/article/r10d088vgx) (July 2026): a new entrant claiming unified backtest and live code; the positioning is now contested.

### External design precedents

- [How to Scale a Ledger, Part V](https://www.moderntreasury.com/journal/how-to-scale-a-ledger-part-v) (Modern Treasury, 2023): an immutable append-only log beneath apparently mutable balances; the shape of our ledger.
- [Stripe's Ledger](https://stripe.dev/blog/ledger-stripe-system-for-tracking-and-validating-money-movement) (2024): immutable double-entry event logging for money movement at five billion events per day.
- [Square's Books](https://developer.squareup.com/blog/books-an-immutable-double-entry-accounting-database-service/) (2019): insert-only entries with cached running balances and correction by new entries, the same read-path trade we make.
- [TigerBeetle financial accounting](https://docs.tigerbeetle.com/coding/financial-accounting/): debits and credits against typed accounts rather than signed integers.
- [Guidance on Sleeves](https://orionadvisorservices.my.site.com/OrionSupportApp/s/article/Guidance-on-Sleeves-and-Associated-Areas) (Orion): sleeve accounting as practiced in wealth management, including the same sum-of-sleeves caveat our ledger inherits.
- [UMA vs. SMA](https://www.envestnet.com/wealth-management/unified-managed-accounts/uma-vs-sma) (Envestnet, 2025): many strategies in one brokerage account with centralized administration; sleeves are standard practice, not a novel construct.
- [17 CFR 270.3a-4](https://www.law.cornell.edu/cfr/text/17/270.3a-4): the advisory-program safe harbor; the client retains rights to all securities and funds, which is why sleeves are internal accounting, not a pooled vehicle.
- [A Guide to SMAs and UMAs](https://www.smartleafam.com/news/guide-to-smas-and-umas) (Smartleaf, 2022): the strongest published objection to sleeve partitioning, cited because our alternatives sections should name real objections.
- [The rebalancing edge](https://corporate.vanguard.com/content/dam/corp/research/pdf/the_rebalancing_edge_optimizing_target_date_fund_rebalancing_through_threshold_based_strategies.pdf) (Vanguard Research, 2024): threshold-band rebalancing against calendar rebalancing; the research behind our drift-band sizing mode.
- [A guide to smart rebalancing](https://www.vanguardsouthamerica.com/content/dam/intl/americas/documents/latam/en/sa-2123766-getting-back-on-track.pdf) (Vanguard, 2019): a target allocation is a risk statement rather than an alpha statement, and no single rebalancing rule dominates.
- [Apache Kafka introduction](https://kafka.apache.org/intro): the per-key partition ordering guarantee our fill ingestion relies on.
- [Exactly-once semantics in Kafka](https://www.confluent.io/blog/exactly-once-semantics-are-possible-heres-how-apache-kafka-does-it/) (Confluent, 2017): the guarantee stops at external side effects, which is exactly why our consumers are idempotent instead.
- [Idempotent Consumer pattern](https://microservices.io/patterns/communication-style/idempotent-consumer.html) (Richardson): the effective-once construction our durable consumers implement.
- [Pseudo-Mathematics and Financial Charlatanism](https://www.davidhbailey.com/dhbpapers/backtest-pseudo.pdf) (Bailey, Borwein, Lopez de Prado, Zhu, 2014): a backtest is a statistical estimate, not evidence; the case for honest presentation of results.
- [The Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) (Bailey and Lopez de Prado, 2014): correcting reported Sharpe for selection bias and non-normality.
- [QuantConnect reconciliation](https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/reconciliation): the honest practitioner enumeration of why live diverges from backtest, and the benchmark our parity work measures against.
- [Postgres Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): the canonical statement of RLS, including FORCE and the BYPASSRLS caveat our startup asserts guard.
- [Multi-tenant isolation with RLS](https://aws.amazon.com/blogs/database/multi-tenant-data-isolation-with-postgresql-row-level-security/) (AWS, 2020): the session-variable policy pattern we use, including the pooling caveat.
- [About Connect API](https://docs.alpaca.markets/us/docs/about-connect-api) (Alpaca): the BYO-brokerage model in the vendor's own words.
- [Alpaca disclosures](https://alpaca.markets/disclosures): the registered broker-dealer holds the accounts and assets; we custody nothing.

### Market context

- [Fractional Reporting Early Findings](https://www.nyse.com/publicdocs/nyse/Q1_2026_Fractionals_Factsheet.pdf) (NYSE Research, March 2026): 9.4% of reported trades carry a fractional quantity, 18.1% for stocks over $100; direct evidence dollar-weighted allocation executes at retail scale.
- [Retail investors hold 10% of US market cap](https://finance.yahoo.com/markets/stocks/articles/retail-investors-hold-equity-assets-153500546.html) (Goldman Sachs via Yahoo Finance, May 2026): $12T in self-directed accounts and roughly 20% of equity volume, up from 15% a decade ago.
- [$5.4 trillion of retail activity in 2025](https://fortune.com/2026/02/23/what-is-retail-trading-dumb-money-stock-markets-5-4-trillion-activity-2025/) (Vanda via Fortune, February 2026): retail stock and ETF activity up 47% year over year.
- [State of the Options Industry Q3 2025](https://www.cboe.com/insights/posts/the-state-of-the-options-industry-quarter-three-2025/) (Cboe): a sixth straight record year, with retail near half of daily options volume.
- [Schwab full-year 2025 results](https://pressroom.aboutschwab.com/press-releases/press-release/2026/Schwab-Reports-Record-4Q-and-Full-Year-2025-Results/default.aspx): 38.5M active brokerage accounts and a fifth consecutive quarter above one million new accounts.
- [Robinhood 2025 results](https://www.investmentnews.com/equities/robinhood-caps-record-2025-with-q4-revenue-surge-but-shares-fall-on-investor-concerns/265225) (InvestmentNews): 27M funded customers and $324B platform assets; the self-directed cohort closest to our target user.
- [FINRA Foundation investor research](https://www.finra.org/media-center/newsreleases/2025/new-finra-foundation-research-examines-shifting-investor-behaviors) (2025): the counter-signal; new-investor formation fell to 8% from 21%, so growth is deepening engagement, not a widening funnel.
- [Retail investors and AI tools](https://www.tradersmagazine.com/xtra/nearly-two-thirds-of-retail-investors-use-ai-to-inform-investment-decisions/) (Traders Magazine, 2026): 62% of surveyed retail investors have used AI for investment decisions; a vendor-run survey, treated as directional.
- [Interactive Brokers agentic trading via Claude](https://fintech.global/2026/06/02/interactive-brokers-launches-agentic-trading-via-claude/) (June 2026): human-in-the-middle approval for every AI-generated order across 170+ markets; the emerging compliance posture.
- [Public introduces AI Agents](https://www.prnewswire.com/news-releases/public-becomes-the-first-brokerage-to-introduce-ai-agents-for-your-portfolio-302729050.html) (March 2026): natural-language intent to monitored conditional execution with pause and audit controls.
- [Alpaca raises $150M at a $1.15B valuation](https://alpaca.markets/blog/alpaca-raises-150-million-at-a-1-15b-valuation-to-build-the-global-standard-for-brokerage-infrastructure/) (January 2026): 300+ partner organizations and 9M+ brokerage accounts; the rail we build on is durable.
- [Fortune on the Alpaca round](https://fortune.com/2026/01/14/alpaca-fundraise-series-d-brokerage-infrastructure/): independent corroboration, including ARR above $100M.
- [Composer milestones](https://www.composer.trade/whats-new): $250M in assets and $1.6B traded in its highest-volume month; public traction for this exact product category.
- Category sizing, cited with caution: [Mordor Intelligence](https://www.mordorintelligence.com/industry-reports/algorithmic-trading-market) and [Fortune Business Insights](https://www.fortunebusinessinsights.com/algorithmic-trading-market-107174) publish estimates for the same algorithmic-trading market that differ by an order of magnitude; we cite them as evidence of category attention, not as sizing. The one useful datum is Mordor's finding that the retail segment is the faster-growing slice.
