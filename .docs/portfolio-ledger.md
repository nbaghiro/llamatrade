# Portfolio Ledger & Multi-Strategy Fund Allocation

How LlamaTrade shares a **single brokerage account** across **multiple strategies and manual trading** while keeping exact, per-holding provenance — built on an **event-sourced, double-entry ledger** with an **overlay coordinator**.

> **Ownership:** The portfolio ledger is owned by the **Portfolio Service** (`:8860`) — it is the **book of record**. The **Trading Service** (`:8850`) is the **execution arm**: it submits orders to the broker, handles fills, and emits fill events that the portfolio ledger consumes. See [Service Ownership & Boundaries](#service-ownership--boundaries).

> **Architecture:** The ledger has its own schema — `Account`, `Sleeve`, `Lot`, `LedgerEvent`, and `SleeveSnapshot` (`libs/db/.../ledger.py`) — keyed off the trading service's deterministic `client_order_id` and `StrategyExecution.allocated_capital`. It is the **single event-sourced book of record** for trading; the trading service keeps only a thin durable order-intent record and defers accounting here (see [Service Ownership & Boundaries](#service-ownership--boundaries)). See [Mapping to Code](#mapping-to-code).

> **Single source of truth for money movement:** this document is the definitive reference for how money moves — both the conceptual model above **and** the concrete [Integration Contract](#integration-contract-trading--portfolio--strategy) between trading, portfolio, and strategy (streams, proto surface, `LedgerService` RPCs, idempotency, identity threading, sleeve close).

---

## Table of Contents

1. [The Problem](#the-problem)
2. [Core Model: Accounts, Sleeves, Lots](#core-model-accounts-sleeves-lots)
3. [Why Event-Sourced Double-Entry](#why-event-sourced-double-entry)
4. [Architecture](#architecture)
5. [Service Ownership & Boundaries](#service-ownership--boundaries)
6. [The Event Ledger](#the-event-ledger)
7. [Projections](#projections)
8. [Fund Disbursement](#fund-disbursement)
9. [Desired-State Reconciliation](#desired-state-reconciliation)
10. [Block-and-Allocate Execution](#block-and-allocate-execution)
11. [Shadow Reconciliation Against the Broker](#shadow-reconciliation-against-the-broker)
12. [Sufficient-Allocation Checks](#sufficient-allocation-checks)
13. [Multi-Tenancy & Scale](#multi-tenancy--scale)
14. [Worked Example](#worked-example)
15. [Integration Contract](#integration-contract-trading--portfolio--strategy)
16. [Mapping to Code](#mapping-to-code)
17. [Design Decisions](#design-decisions)
18. [References](#references)

---

## The Problem

A user has **one** brokerage account (one set of Alpaca credentials → one Alpaca account). Trades flow into it from multiple sources simultaneously:

- **Manual** buy/sells the user makes by hand.
- **One or more strategies**, each defined in the [Strategy DSL](strategy-dsl.md), each periodically rebalancing.

The broker only knows **aggregate** reality: one position per symbol, one cash balance. It has no idea that 70 of your 80 SPY shares belong to two different strategies and 10 to a manual buy. This creates three hard requirements:

1. **Provenance** — every holding must carry a trade history showing whether each buy/sell came from manual activity or a specific strategy.
2. **Non-interference** — one strategy must never liquidate another strategy's (or your manual) holdings, even when they hold the same symbol.
3. **Correct capital accounting** — each strategy must size positions against *its own* allocated capital, not the whole account, and must never overdraw.

The naive approach — having each strategy size against the full account and reconcile its positions against the broker aggregate — double-counts capital and causes strategies to fight over shared symbols. This document specifies the correct design.

---

## Core Model: Accounts, Sleeves, Lots

```
              ╔═════════════════════════════════════════════════════════╗
              ║                         ACCOUNT                         ║
              ╠═════════════════════════════════════════════════════════╣
              ║ 1 per broker credential set  ·  reconciliation anchor   ║
              ║ broker truth: aggregate position/symbol · cash · equity ║
              ╚═════════════════════════════════════════════════════════╝
                                           │  partitions into virtual sleeves
                                           │
       ┌────────────────┬─────────────────┬┴────────────────┬──────────────────┐
       ▼                ▼                 ▼                 ▼                  ▼
╭─────────────╮  ╭─────────────╮  ╭──────────────╮  ╭───────────────╮  ╭───────────────╮
│ Unallocated │  │    Manual   │  │  Unmanaged   │  │   Strategy A  │  │   Strategy B  │
├─────────────┤  ├─────────────┤  ├──────────────┤  ├───────────────┤  ├───────────────┤
│ free cash   │  │ hand-traded │  │ pre-existing │  │ type=strategy │  │ type=strategy │
│ pool        │  │ cash + lots │  │ + external   │  │ alloc_capital │  │ alloc_capital │
╰─────────────╯  ╰─────────────╯  ╰──────────────╯  │ cash + lots   │  │ cash + lots   │
                                                    ╰───────────────╯  ╰───────────────╯
                                                            │                  │
                                                            └────────┬─────────┘  lots
                                                                     ▼
                                                       ┌───────────────────────────┐
                                                       │ LOT  (provenance-bearing) │
                                                       ├───────────────────────────┤
                                                       │ symbol · qty · cost_basis │
                                                       │ opened_by_order           │
                                                       │ opened_at · closed_at     │
                                                       └───────────────────────────┘
```

**Account** — the unit of broker reality; the reconciliation anchor. One per Alpaca credential set.

**Sleeve** — a virtual sub-portfolio. Types:
- `strategy` — a running `StrategyExecution`, with an `allocated_capital` budget.
- `manual` — the user's hand-trading bucket.
- `unmanaged` — pre-existing holdings on first connect, plus any trades detected at the broker that we didn't originate.
- `unallocated` — free cash not yet assigned to a sleeve.

**Lot** — a provenance-bearing unit: a quantity of a symbol opened by one order in one sleeve, with its own cost basis. A user-visible "holding" in a symbol is the **sum of lots across all sleeves**; its history is the timeline of those lots' open/close events.

### Invariants (the heart of the design)

At all times, the coordinator guarantees:

```
(1) POSITIONS:  Σ over sleeves of sleeve_qty(symbol)  ==  broker_qty(symbol)   ∀ symbol
(2) CASH:       Σ over sleeves of sleeve_cash          ==  broker_cash
(3) SLEEVE:     sleeve.equity = sleeve.cash + Σ(its lots' market value)
                sleeve.allocated_capital is the budget anchor
```

Every operation (allocate, transfer, buy, sell, attribute a fill, apply a corporate action) is designed to **preserve** these invariants. A useful corollary of (2): a sleeve's free cash can never exceed the account's, so a sleeve can never spend money the account doesn't have.

---

## Why Event-Sourced Double-Entry

The danger with sleeves is "keeping N mutable ledgers in sync" — a positions table, a cash table, a lots table, each mutated imperatively and each able to drift. That rots under volume.

The fix, drawn from fintech ledger engineering (e.g. Mettle's *Write Once Double Entry*) and hedge-fund **shadow accounting**:

> **One append-only, double-entry event log is the single source of truth. Per-sleeve positions, lots, cash, and P&L are *derived projections* of that log — never independently mutated.**

This dissolves the sync problem:

- **One writer, one truth.** Projections are pure folds of the log; they *cannot* diverge from each other because none is independently mutable. Rebuilding any projection is just a replay.
- **Conservation is a checksum.** Double-entry means every movement of shares or cash has matched legs that sum to zero. Invariants (1) and (2) become *continuously assertable*, not hoped-for. Drift is detectable, never silent.
- **Crash recovery is free.** Rebuild any projection by replaying the log; the deterministic `client_order_id` plus the writer's idempotent append make redelivered fills a no-op.
- **It scales by partitioning.** Each account owns its own event stream; accounts are independent → horizontal scale. Volume means more cheap appends, not a heavier sync burden.

Conceptually this is the **Unified Managed Account (UMA) / overlay-manager** pattern from wealth management — one custodian account, independent "sleeves," a coordinating overlay — implemented on an event-sourced book. See [References](#references).

---

## Architecture

```
  STRATEGY / TRADING RUNNER        PORTFOLIO SERVICE (:8860)      TRADING SERVICE (:8850)
  ─ produces sleeve targets ─       ─── the book of record ───    ─── the execution arm ───

╭──────────────────────────╮            ╭──────────────────────────────────╮
│      SIGNAL SOURCES      │            │DESIRED-STATE RECONCILER (PLANNED)│
├──────────────────────────┤            ├──────────────────────────────────┤
│ Strategies (DSL): target │ ─desired─► │ diff( desired sleeves ) vs       │
│ weights (% of sleeve eq) │            │ ( projected actual from ledger ) │
│ Manual actions           │            │ → intended orders, by sleeve     │
╰──────────────────────────╯            ╰──────────────────────────────────╯
                                                          │  intended orders, by sleeve
                                                          └──────────────┐
                                                                         ▼
                                                    ╭────────────────────────────────────────╮
                                                    │   BLOCK-AND-ALLOCATE EXECUTOR (OMS)    │
                                                    ├────────────────────────────────────────┤
                                                    │ • order-time risk checks               │
                                                    │ • bunch intents → block order → broker │
                                                    │ • receive fills, allocate @ avg price  │
                                                    │ • emits OrderFilled + client_order_id  │
                                                    ╰────────────────────────────────────────╯
                                                                         │
    ┌─◄─ fill events (echo client_order_id) ─────────────────────────────┘
    ▼
    ╔════════════════════════════════════════════════════════════════════════════════╗
    ║                        APPEND-ONLY DOUBLE-ENTRY LEDGER                         ║
    ╠════════════════════════════════════════════════════════════════════════════════╣
    ║ every fill / cash move = a balanced double-entry event, tagged with its sleeve ║
    ║ ◄══ SINGLE SOURCE OF TRUTH                                                     ║
    ╚════════════════════════════════════════════════════════════════════════════════╝
      │
      ├──(fold)──►  per-sleeve lots / positions / cash / P&L
      ├──(fold)──►  account aggregate
      │
      ╰── SHADOW RECONCILER:  aggregate ⟷ broker truth ──► correction events
```

Three layers, cleanly separated:

- **The DSL / strategy** (in the strategy/trading runner) only ever produces *target weights for its sleeve*. It is unaware of other sleeves, the account total, or orders. (See [Strategy DSL](strategy-dsl.md).)
- **The Portfolio Service** owns the ledger and the allocation brain: budgets/fund disbursement, the desired-state diff, attribution, projections, and reconciliation. It is the **book of record**.
- **The Trading Service** is the execution arm: it takes intended orders, runs order-time risk checks, bunches and submits them to the broker, and emits **fill events** back to the ledger.

There are exactly **two sync surfaces**, both one-directional and self-healing:
1. strategy desired-state → reconciler (declarative target),
2. ledger projection ⟷ broker truth (shadow reconciliation, append corrections).

---

## Service Ownership & Boundaries

| Concern | Owner | Notes |
|---------|-------|-------|
| Accounts, **sleeves**, **lots**, cash sub-ledgers | **Portfolio (:8860)** | The book of record |
| Append-only **double-entry ledger** + projections | **Portfolio** | Single source of truth; `LedgerEvent` log + projected sleeve/lot/cash state |
| **Fund disbursement** (allocate / transfer / withdraw) | **Portfolio** | Operates on virtual cash sub-ledgers |
| **Desired-state reconciliation** (target vs actual → intended orders) | **Portfolio** | Planned; the diff library exists but is not wired into execution |
| Per-sleeve / per-strategy **P&L, provenance, holding history** | **Portfolio** | Lot-level attribution |
| **Shadow reconciliation** of ledger aggregate vs broker | **Portfolio** | Consumes broker positions/cash + activities feed |
| **Sufficient-allocation accounting** (sleeve free cash, budgets) | **Portfolio** | The sleeve-aware state the risk check reads |
| **Order execution** (submit to broker, fills, cancels) | **Trading (:8850)** | The live runner + executors |
| **Block-and-allocate** order construction & submission | **Trading** | Bunches intended orders, allocates fills @ avg price |
| Order-time **risk checks** (buying power, rate limits) | **Trading** | Reads sleeve free-cash/budget from the portfolio ledger |
| Deterministic `client_order_id` (attribution key) | **Trading** | Echoed on fills so the ledger attributes them |
| Live **market-data bar stream** → strategy evaluation | **Trading** (runner) | Produces sleeve target weights |

**The contract between them:** the portfolio service consumes *fill events* (tagged with `client_order_id`) produced by the trading service; that Trading → Portfolio fill flow is the only order flow wired today. In the target design the portfolio service also produces *intended orders* (tagged by sleeve) for the trading service to execute, but the trading runner currently sizes its own orders against sleeve equity. The portfolio ledger is authoritative for **attribution and accounting**; the broker (via the trading service) is authoritative for **aggregate reality**.

> **Why this split:** the portfolio service is the accounting layer (it owns transactions, summaries, history, P&L, and tax-lot tracking). Making it the ledger owner keeps *execution* (a broker concern) in the trading service and *book-of-record accounting* (a portfolio concern) where it belongs — a clean, single-responsibility boundary.

---

## The Event Ledger

The ledger is an append-only, ordered log of immutable events. It is the only thing that is *written*; everything else is *derived*.

### Properties

- **Append-only** — events are never edited or deleted. Corrections are new events.
- **Double-entry** — every event that moves shares or cash names a source and destination (a sleeve, the broker/market, or an external counterpart) such that the net change sums to zero. Nothing is created or destroyed within the system.
- **Sleeve-tagged** — every trade event carries the originating `sleeve_id` and `source_type` (`manual` | `strategy` | `system`), resolved deterministically via the `client_order_id → sleeve` map established at order origination.
- **Globally ordered & idempotent** — each event has a monotonic sequence number and a unique id, so replays cannot double-count.

### Event taxonomy

| Category | Events |
|----------|--------|
| Capital | `FundsDeposited`, `FundsWithdrawn`, `CapitalAllocated` (Unallocated→sleeve), `CapitalTransferred` (sleeve→sleeve) |
| Trading | `OrderIntended`, `OrderSubmitted`, `OrderAccepted`, `OrderRejected`, `OrderFilled` (partial/full), `OrderCancelled` |
| Positions | `LotOpened`, `LotIncreased`, `LotReduced`, `LotClosed` (each tagged with sleeve + realized P&L on reduce/close) |
| Cash | `CashDebited`, `CashCredited`, `DividendReceived`, `FeeCharged`, `InterestAccrued` |
| Corporate | `SplitApplied`, `SymbolChanged` |
| Reconciliation | `ExternalTradeDetected`, `DriftCorrected`, `ReconciliationAdjusted` |

Not every type above has a producer today. The emitted set covers funds deposit/withdraw, capital allocate/transfer, order submit/reject/cancel/fill, dividends, interest, fees, splits, symbol changes, external-trade detection, and sleeve freeze/close. `OrderIntended`, `OrderAccepted`, the granular `Lot*` and `Cash*` families (lot and cash state are projected from fill and capital events instead), `MergerApplied`, `DriftCorrected`, and `ReconciliationAdjusted` are catalogued but never emitted.
| Sleeve lifecycle | `SleeveOpened`, `SleeveClosed`, `SleeveFrozen`, `SleeveResumed` |

These are the `LedgerEventType` members (`libs/db/.../ledger.py`, mirrored in `ledger.proto`), spanning the capital, trading, position, cash, corporate-action, reconciliation, and sleeve-lifecycle families.

### Snapshots

To avoid replaying from genesis, the projector writes periodic **snapshots** (sleeve balances + open lots at sequence N). Recovery = load latest snapshot + replay events after N. Snapshots are an optimization; the log remains authoritative.

---

## Projections

Read models, each a deterministic fold of the ledger:

- **Sleeve positions / lots** — open lots per sleeve, with cost basis. Source of truth for **attribution**.
- **Sleeve cash** — `cash_balance`, `reserved` (earmarked for open buy orders), `free = balance − reserved`. A `settled` vs `unsettled` split exists in the projection, but settlement is not modeled yet (`unsettled` is always 0).
- **Sleeve P&L** — realized (from lot closes) and unrealized (lots × current price), per sleeve and per strategy.
- **Account aggregate** — Σ across sleeves; the value reconciled against broker truth.
- **Holding history** — for any symbol, the ordered list of lot open/close events with source labels (the user-facing "who bought/sold this" view).

Because every projection derives from the same log, they are mutually consistent by construction.

---

## Fund Disbursement

Cash management across sleeves. The broker holds one cash pool; the ledger partitions it into per-sleeve virtual balances such that invariant (2) holds.

### Operations

- **Allocate** (`Unallocated → strategy sleeve`): assigning `$X` to a strategy emits `CapitalAllocated` after checking `Unallocated.free ≥ X`. Purely virtual — no broker movement.
- **Buy / Sell**: on submit, **reserve** the buy cost from the sleeve's free cash; on fill, convert the reservation to an actual debit (`qty×price + fees`) attributed to the originating sleeve; on cancel/reject, release the reservation. Sells credit the sleeve.
- **Transfer** (`sleeve A → sleeve B`): if `A.free ≥ amount`, emit `CapitalTransferred` (virtual). Only liquid transfers are supported: if A's free cash is insufficient the transfer is rejected ("raising cash by selling positions is not yet supported"). `funds.py` can plan the FIFO raise-cash sells, but executing them needs the trading arm and is not wired.
- **Deposit / Withdraw**: deposits land in `Unallocated`. Withdrawals draw from `Unallocated` free cash only and are rejected when it is insufficient; liquidating positions to raise withdrawal cash is not implemented.
- **Dividends / interest**: broker cash credits are attributed to the **lot owner**. A dividend on a *shared* symbol is split **pro-rata by lot quantity** across the sleeves holding it.
- **Fees / commissions**: attributed to the sleeve that originated the trade.

### Settlement (a real fork)

In a **cash** account, sell proceeds are unsettled (T+1) and using them to fund a same-day buy can trip good-faith / free-ride rules. The target design tracks `settled` vs `unsettled` in the cash projection and either respects settlement (cash accounts) or relies on **margin buying power** (margin accounts, where same-day rotation is allowed). Today the projection carries the field but always reports `unsettled = 0`, and nothing gates orders on settlement; this remains an open item for cash accounts.

---

## Desired-State Reconciliation

> **Status: planned.** The diff library (`ledger/desired_state.py`) exists with tests, but no reconcile loop runs and no intended order reaches the trading service through this path; the trading runner sizes orders directly against sleeve equity today. This section describes the target design.

Strategies and manual actions declare **what the sleeve's portfolio should be**, not what orders to send. Each cycle the reconciler:

1. Reads each sleeve's **desired target** (strategy: target weights × sleeve equity; manual: the user's requested position).
2. Reads the **projected actual** sleeve holdings from the ledger.
3. Computes the **delta** per sleeve per symbol → intended orders, each tagged with its sleeve.

This is the Kubernetes-style reconcile loop: **declarative and self-healing.** If anything is off (a missed fill, a restart), the next cycle simply converges toward the desired state. There is no fragile imperative "apply this order's effect to that balance" bookkeeping — effects are events, and the desired state is the target.

### From target weights to orders (sizing)

Within a sleeve, an intended order is the **delta** between the target and the sleeve's current holdings:

```
target_value  = sleeve_equity × (target_weight / 100)     # SLEEVE equity, not account equity
target_shares = target_value / current_price
delta_shares  = target_shares − sleeve_current_shares      # vs THIS sleeve's lots only
```

A **drift tolerance** avoids churn: an order is generated only when `|delta_value| / target_value` exceeds a threshold (e.g. 5%). Sells reduce the sleeve's **own** lots (FIFO); a target weight of 0 exits the sleeve's position in that symbol. Sizing against `sleeve_equity` rather than `account_equity` is precisely what lets multiple strategies coexist without double-counting capital — it replaces the legacy account-equity sizing and the binary all-or-nothing signal logic.

A single rebalance therefore yields **one intended order per symbol whose holding changes** (sells and buys). These are submitted to the broker **immediately within the open trading window** and fill asynchronously — there is no deferred queue. The rebalance cadence itself is gated by the strategy's `:rebalance` frequency (**at most once per day**); see [Rebalance Frequencies](strategy-dsl.md#rebalance-frequencies).

---

## Block-and-Allocate Execution

> **Planned / Not implemented.** Execution today is **gross**: each sleeve's order is submitted separately, so attribution is trivially one order ↔ one sleeve. The netting / internal-cross design below is the intended graduation, not current behavior.

When multiple sleeves want to trade the same symbol in the same cycle, the coordinator does **not** fire competing orders. Following the institutional **block-and-allocate** pattern:

1. **Bunch** all sleeve intents for a symbol into a single net **block order** (e.g. A wants +5 SPY, B wants −50 → broker order −45).
2. **Submit** the block to the broker.
3. **Allocate** the fills back to sleeves at the **volume-weighted average price**, writing per-sleeve `OrderFilled` / `LotOpened|Reduced` events. Where intents offset (A buying while B sells), the overlap is an **internal cross**: shares move from B's lots to A at the fill price, with matched ledger legs — fewer broker trades, no self-competition, fair pricing.

> **Gross vs netting.** Gross execution (each sleeve's order submitted separately) makes attribution trivially 1 order ↔ 1 sleeve, with simple partial fills. Netting/internal-cross adds proportional fill-splitting on top of the proven ledger and attribution. Netting is where the subtle accounting bugs live.

---

## Shadow Reconciliation Against the Broker

The broker is the source of truth for **aggregate** reality; the ledger is the source of truth for **attribution**. Reconciliation forces the ledger's aggregate to match the broker and attributes every delta to a sleeve.

Each cycle (timer-driven, default every 300 s via `LEDGER_RECONCILE_INTERVAL_SECONDS`; there is no on-fill trigger or session/market-edge sweep today), pull broker positions + cash + the account-activities feed, and for each symbol compute `drift = broker_qty − Σ ledger_qty`, resolved **by cause**:

| Cause | Resolution |
|-------|-----------|
| Our own fill not yet booked | Match by `client_order_id` → originating sleeve → open/close that sleeve's lot. Deterministic. |
| **External trade** (user traded directly at the broker) | Unknown `client_order_id` → emit `ExternalTradeDetected` into the **Unmanaged** sleeve + alert. **Never** assigned to a strategy. |
| **Corporate action** (split, symbol change) | Detection proposes, an operator applies. The detection loop raises a proposal (a `CORPORATE_ACTION_PROPOSED` notification); nothing is booked until `ApplyCorporateAction` is called, which applies lot-by-lot (`SplitApplied`, `SymbolChanged`), preserving provenance and adjusting cost basis, then publishes `CORPORATE_ACTION_APPLIED`. Mergers are not supported. |
| **Partial fill** | Book the filled portion; remainder stays pending with cash still reserved. |
| **Fractional dust** (rounding) | Classified and reported only; no absorbing event is booked (`ReconciliationAdjusted` has no producer). |
| **Material unexplained drift** | `SleeveFrozen` on the affected sleeve + alert — do not trade on a book you can't trust. |

Because reconciliation only ever **appends** (it never rewrites a past lot), the holding history stays a faithful, ordered audit trail, and idempotency comes from the sequence numbers + deterministic order ids.

---

## Incident Alerting

`src/alerts.py` (`LedgerAlertDispatcher`) publishes alert-worthy ledger incidents onto the `lt.notifications` topic through the shared `NotificationEvents` producer; the notification service owns delivery (in-app row, email, webhooks). Dispatch uses `publish_safe`: failures are logged and swallowed, so an alerting outage never breaks a ledger operation, and deterministic dedup ids collapse re-reports of the same incident (a sleeve freeze re-detected on every pass, a quarantined fill redelivered).

| Incident kind | Notification category | Severity |
|---------------|-----------------------|----------|
| `sleeve_frozen` | `SLEEVE_FROZEN` | Critical |
| `fill_quarantined` | `FILL_QUARANTINED` | Critical |
| `dlq_backlog` | `FILL_QUARANTINED` | Critical |
| `external_trade_adopted` | `EXTERNAL_TRADE_ADOPTED` | Actionable |
| `corporate_action_proposed` | `CORPORATE_ACTION_PROPOSED` | Actionable |
| `corporate_action_applied` | `CORPORATE_ACTION_APPLIED` | Info |

---

## Sufficient-Allocation Checks

Ensuring a strategy is actually funded to trade its assets. Two checkpoints.

### At admission (when a strategy execution is created/started)

These checks exist as library code with tests but are not called from the execution-creation path yet; allocation currently enforces only `Unallocated.free` at `CapitalAllocated` time.

1. **Solvency** — `requested allocated_capital ≤ Unallocated.free`.
2. **Feasibility per asset** — for each target asset, `target_weight × allocated_capital ≥ that asset's minimum order notional`. With fractional shares this is usually fine; for non-fractionable assets a tiny target slice of a high-priced name can be untradeable — warn/reject at creation rather than failing silently each rebalance.
3. **Leverage** (not implemented) — for margin accounts, Σ sleeve leverage should stay within account margin/maintenance limits; no leverage check exists today.

### At each order (runtime)

- Size against **sleeve equity**, then verify the sleeve's **free cash** covers `qty×price + fees`.
- If insufficient, buys are **scaled down to fit** free cash regardless of gap size (correct for allocation strategies: weights are proportional, so a smaller buy preserves the intended mix). A materiality threshold with reject-and-alert is designed but not built; scaling emits no notification today.
- **Sequence sells before buys** within a rebalance so freed cash funds new buys (subject to settlement).
- Invariant (2) makes the sleeve-level check automatically account-safe.

This is the existing `RiskManager` made **sleeve-aware**: it checks the sleeve's free cash and budget, not the whole account.

---

## Multi-Tenancy & Scale

- **Tenant isolation** — every account, sleeve, lot, and event is `tenant_id`-scoped; credentials are looked up per tenant and decrypted at use.
- **Per-account stream sharding** — each account's event log is an independent stream with a single writer → no cross-account contention; accounts scale horizontally.
- **O(1) attribution** — each fill maps to its sleeve via `client_order_id`; no scanning.
- **Snapshots + incremental folds** — projections update by folding new events onto the latest snapshot, not replaying history.
- **Bounded sync** — only one reconciliation boundary (ledger ⟷ broker), and it is self-healing.

A tenant running 50 strategies is still **one** account stream; the 50 "desired target portfolios" are tiny declarative inputs. Throughput grows with appended events, which are cheap.

---

## Worked Example

Account = $100,000. Sleeves: **Manual** $20k, **Strategy A "All-Weather Core"** $40k (quarterly, inverse-vol over SPY/TLT/GLD/DBC), **Strategy B "Trend Regime"** $40k (daily, SPY/QQQ in uptrend else TLT/GLD).

- **Jan 2 (uptrend):** A buys SPY/TLT/GLD/DBC (sized to its $40k); B buys SPY 60% / QQQ 40% of its $40k.
  Broker shows `SPY = 70.83`. Ledger: `Lot(A: 20.83 @ $480)` + `Lot(B: 50.00 @ $480)`. Invariant: 20.83 + 50.00 = 70.83.
- **Feb 14:** user manually buys 10 SPY → Manual sleeve lot. Broker `SPY = 80.83`; ledger now has three SPY lots (A, B, Manual), each with its own provenance. A and B cannot touch the manual 10.
- **Apr 1 (regime flips down; A's quarter is up):** B's condition flips → it **sells its 50 SPY** (only its own lot) and buys TLT/GLD; A trims SPY slightly and adds TLT/GLD.
  Result: `TLT` and `GLD` are now each held by **both** A and B — one broker position per symbol, two attributed lots with different cost bases. SPY is now shared by A and Manual.

Holding history for TLT after the flip (the user-facing provenance view):

```
TLT — total 327.1 shares
├─ Strategy A   126.32 sh  bought Jan 2  @ $95.00   (initial all-weather)
├─ Strategy A    14.27 sh  bought Apr 1  @ $100.00  (quarterly rebalance add)
└─ Strategy B   186.50 sh  bought Apr 1  @ $100.00  (regime flip → risk-off)
```

Each row is one ledger entry, stamped with source, order id, qty, price, and time.

---

## Integration Contract (Trading ↔ Portfolio ↔ Strategy)

The concrete wire and RPC contract between the services: trading is the execution arm, portfolio is the book of record, strategy owns sleeve lifecycle (funding and close).

### Fill events (Trading → Portfolio)

**Stream.** One **global** stream `ledger:fills` (logical name `llamatrade_events.channels.LEDGER_FILLS`; Kafka topic `lt.ledger.fills`, the transport's `lt.` namespace), **keyed by `account_id`**: per-account FIFO is preserved by the partition key while the fold runs N-way parallel across accounts. Consumed by portfolio's `src/tasks/fill_ingestion.py` via the `portfolio-ledger` consumer group.

**Cardinality.** Exactly **one event per order, at terminal state** — never per partial fill (the ledger dedups on the derived event id, so per-partial publishing would drop all but the first):

- `fill` → the cumulative `filled_qty` / `filled_avg_price`.
- `canceled` / `expired` with `filled_qty > 0` → the filled portion.
- `canceled` / `rejected` / `expired` with nothing filled → publish nothing (the reservation-release event covers the cash side).

**Payload.** A proto `LedgerFill` message (`events.proto`), **envelope-encoded** onto the stream (not JSON) and discriminated by `EVENT_TYPE_LEDGER_FILL`. Built by `trading/src/ledger_events.py`, translated by `ingestion.fill_to_append` (which takes the parsed `LedgerFill`, not a JSON dict):

```protobuf
message LedgerFill {
  string tenant_id; string account_id; string sleeve_id;
  string client_order_id; string order_id;   // order_id optional
  string symbol; string side;                 // "buy" | "sell"
  string qty; string price;
  string fees;          // optional
  string cost_basis;    // optional, sells only
  string realized_pnl;  // optional, sells only
  string filled_at;     // ISO-8601
}
```

Proto3 can't distinguish unset from empty, so an empty scalar means "absent" (`fill_to_append` copies only non-empty optionals).

**Cost basis.** Optional on sells. When absent, the portfolio fill consumer computes it at ingestion via FIFO lot selection (`sizing.select_lots_fifo` via `ingestion.enrich_sell_fill`) against the account projection, inside the writer's serialized append path. A sell whose lots can't cover the qty is **quarantined** (`FillQuarantineError`), never recorded with a fabricated basis — trading reports broker facts only and never does accounting. A supplied value passes through unchanged.

**Idempotency.** Re-delivered payloads are no-ops at `LedgerWriter.append` (dedup on `event_id`). Attribution (`sleeve_id`) is fixed at order origination.

### Cash reservation events (Trading → Portfolio)

So sleeve free cash stays correct with in-flight orders, trading also publishes a proto `LedgerReservation` (`EVENT_TYPE_LEDGER_RESERVATION`, translated by `ingestion.reservation_to_append`) to the **same** global `ledger:fills` stream, carrying the same envelope keys (`tenant_id`, `account_id`, `sleeve_id`, `client_order_id`):

- **submit** (buys): `event_type: "order_submitted"`, `reserved: "<notional est.>"` → the ledger earmarks cash (`reserved_cash += amount`).
- **cancel / reject / expiry**: `event_type: "order_cancelled" | "order_rejected"` → the ledger releases the reservation.
- the terminal **fill** consumes the reservation (release + cash debit in one balanced event).

Reservation event ids derive from `sha256(client_order_id + ":" + event_type)`, so each lifecycle stage is idempotent independently. Reservation events carry no value postings of their own (they only earmark cash, tracked as the projection's derived `reserved` total); the terminal fill moves the value. A limit buy reserves exactly at its limit price; a market or stop buy reserves at the reference price plus a small buffer, since a gap-up fill can exceed it.

### Transport (Kafka)

Every fill/reservation payload is envelope-encoded and produced to the Kafka topic `lt.ledger.fills`, **keyed by `account_id`**, and consumed durably by the portfolio's `portfolio-ledger` consumer group. Every pod is a group member: Kafka assigns each account's partition to exactly one member, so per-account ordering holds while the fold runs N-way parallel across accounts, and the group coordinator handles failover. Offsets are committed manually **after** the handler persists the append (commit-after-write); a retryable failure leaves the offset uncommitted so the entry redelivers. Retention is topic config, provisioned in Terraform. Unrecordable entries (poison / quarantine) are parked on the DLQ topic (`ledger:fills:dlq` → `lt.ledger.fills.dlq`), keyed by `account_id` when the entry decoded; an operator drains them back onto the main topic idempotently with `python -m src.tasks.dlq_replay`, and a `llamatrade_ledger_fill_dlq_depth` gauge warns on new DLQ entries. Each entry's envelope id is the **full sha256 hex digest** of the payload's stable parts (`derive_event_id`), so at-least-once redelivery is a no-op on the second arrival. (This is distinct from the ledger's own 128-bit `LedgerEvent.event_id` UUID, derived as `UUID(sha256(client_order_id)[:16 bytes])`.)

### Emission paths & drift policy

Trading publishes from **two idempotent paths** (same `client_order_id` → same ledger `event_id`, so racing or double-firing never double-counts): the live trade stream (`runner.py` → `ledger_events.build_ledger_fill_payload`) and the REST-sync recovery path (`sync_order_status` / `sync_all_pending_orders` → `build_ledger_fill_payload_from_order`) that catches terminal states the stream may miss. A periodic runner loop re-publishes recently-terminal orders as a proactive drain of the crash-before-publish window.

Portfolio's drift policy (always active — the ledger is authoritative): `missing_in_ledger` → adopt into Unmanaged via `EXTERNAL_TRADE_DETECTED` at broker avg price; `missing_at_broker` / `qty_mismatch` → freeze every sleeve holding the symbol (+ `SLEEVE_FROZEN` audit event), and trading's risk check rejects all orders on a frozen sleeve. `GetOrCreateAccount` seeds the ledger from broker state (best-effort backfill).

### Proto surface & LedgerService

`trading.proto` (regenerate with `make proto`):

- `Order`: `sleeve_id = 26`, `account_id = 27`
- `Fill`: `sleeve_id = 9`, `account_id = 10`
- `TradingSession`: `account_id = 14`, `sleeve_id = 15`
- `SubmitOrderRequest`: `sleeve_id = 15` — empty ⇒ the order is attributed to the account's **Manual** sleeve (resolved server-side by trading via `LedgerService`).

`ledger.proto` — `LedgerService` is served by the **portfolio process** (`:8860`, no separate service). RPCs:

- `GetOrCreateAccount(credentials_id)` → `LedgerAccount` + base sleeves — the lazy `credentials_id → account_id` bootstrap that both strategy (funding) and trading (manual attribution) need; idempotent, and ensures the singleton Unallocated/Manual/Unmanaged sleeves.
- `AllocateCapital`, `TransferCapital`, `DepositFunds`, `WithdrawFunds` — with an empty `to_sleeve_id` and a `strategy_execution_id`, `AllocateCapital` opens (or reuses) the strategy sleeve linked to that execution and funds it atomically (open-and-fund).
- `ListSleeves`, `GetSleeve` (sleeve + open lots), `GetHoldingHistory`.
- `CloseSleeve` — retire a sleeve, re-homing its holdings (see below); the response carries the CLOSED sleeve + `already_closed` + a re-home summary (`rehomed_cash`, `RehomedPosition{symbol, qty, cost_basis}`).
- `ApplyCorporateAction` — an operator-triggered split / ticker-rename / dividend fanned across every sleeve holding the symbol, idempotently. The detection loop only proposes (publishing a `CORPORATE_ACTION_PROPOSED` notification); nothing is booked until this RPC is called, and application publishes `CORPORATE_ACTION_APPLIED`.

`Sleeve.realized_pnl` is projected from the event log, and `SleeveCash.reserved` is the **projected** reservation total, not a row column.

**LedgerClient** (`libs/proto/llamatrade_proto/clients/ledger.py`) is the async wrapper over the generated stubs (exported from `llamatrade_proto.clients`), returning typed dataclasses with `Decimal` amounts (`SleeveCashInfo.free = balance − reserved`). It speaks Connect, not raw gRPC: requests carry a minted service token and a 5000 ms read timeout, and RPC errors propagate as `connectrpc.errors.ConnectError` — fund ops are mutations, so callers handle failures explicitly. Consumers: strategy (`get_or_create_account` + `allocate_capital` on execution funding), trading (`get_sleeve` for sleeve equity / free cash, `list_sleeves` / `get_or_create_account` for Manual-sleeve resolution).

### Identity threading

- **account_id** — portfolio derives/creates one `Account` per `credentials_id` (`GetOrCreateAccount`, lazy + idempotent).
- **sleeve_id** — created when a strategy execution is funded: strategy calls `AllocateCapital`, stores the returned `sleeve_id` + `account_id` on the execution row; trading reads them when starting the runner and threads them into orders, fills, sizing, and risk. Manual orders resolve the Manual sleeve.
- **client_order_id** — deterministic (`order_executor.generate_deterministic_order_id`), reused as the attribution/idempotency key end-to-end.

### Sleeve close — re-home on stop/archive

A strategy sleeve is **retired** when its execution stops or its strategy is archived. The strategy service owns sleeve lifecycle (funds via `AllocateCapital`, closes via `CloseSleeve`). Closing is **idempotent** and **conservation-preserving** — it moves value between sleeves, never destroys it:

- open positions → the account's **Unmanaged** sleeve (carrying qty + cost basis; a re-home is not a sale, so no realized P&L);
- free cash → the **Unallocated** sleeve (immediately reusable);
- a `SLEEVE_CLOSED` event is appended and the sleeve's status becomes `CLOSED`.

The close event id is `sha256(sleeve_id + ":close")`, so a re-close is a writer no-op, and the close **refuses while the sleeve has reserved cash** (an in-flight order). The `SLEEVE_CLOSED` payload names `to_position_sleeve_id` (Unmanaged), `to_cash_sleeve_id` (Unallocated), the `positions` (`[{symbol, qty, cost_basis}]`), `cash`, and an optional `reason`; each position becomes two balanced POSITION legs (close on source, open on Unmanaged) and cash becomes two balanced CASH legs, netting to zero.

**Orchestration is decoupled and race-free** (no strategy→trading call): the strategy closes the sleeve; trading's risk check blocks orders on any non-ACTIVE sleeve (FROZEN or CLOSED); the runner self-stops on its next equity sync when its sleeve is CLOSED; and a stray/late fill for a CLOSED sleeve is re-homed to Unmanaged at ingestion (`_reroute_if_sleeve_closed`) so it can't resurrect a retired sleeve. Triggers: execution **STOPPED** closes its sleeve; strategy **ARCHIVED** cascade-stops every non-terminal execution and closes each sleeve. The close is best-effort — a stop/archive succeeds even if the ledger is unreachable (re-homed on a later close).

### Ledger authority

The ledger is the single source of truth and is **always on** — no rollout flags, no legacy fallback. Sleeve-aware behavior (sizing, risk, reservations, reconciliation handoff, fill emission) is keyed off whether an order/session carries a `sleeve_id`; unattributed/manual orders degrade gracefully to account-level behavior. The only ledger env knobs are tuning intervals (`LEDGER_RECONCILE_INTERVAL_SECONDS`, `LEDGER_SNAPSHOT_INTERVAL_SECONDS`, `LEDGER_CORPORATE_ACTIONS_INTERVAL_SECONDS`), plus trading's `TRADING_MARKET_BUY_RESERVE_BUFFER`, the safety multiplier applied when reserving cash for market buys.

---

## Mapping to Code

| Concern | Owner | Implementation |
|---------|-------|--------|
| Portfolio ledger / book of record | **Portfolio** | The append-only **double-entry event ledger** (`LedgerEvent` log, `ledger/writer.py` + `postings.py`), with the full event taxonomy (capital, trading, position, cash, corporate, reconciliation, sleeve-lifecycle families) |
| Accounts, **sleeves**, **lots** | **Portfolio** | `Account` + `Sleeve` (`type`, `strategy_execution_id`, `allocated_capital`) DB rows; open **lots** are a projection materialized into `SleeveSnapshot.lots`; Manual/Unmanaged/Unallocated base sleeves |
| Capital budget | **Portfolio** | `StrategyExecution.allocated_capital` is enforced; sizing uses **sleeve equity**, not account equity (trading `runner.py`, sleeve-aware sizing path) |
| Cash accounting | **Portfolio** | Per-sleeve cash sub-ledger projected from the log (`free = balance − reserved`) |
| Fund disbursement (allocate/transfer/withdraw) | **Portfolio** | `LedgerService` + `ledger/funds.py`; virtual cash movements from free cash (raise-cash execution not built) |
| Desired-state reconciliation | **Portfolio** | Planned; `ledger/desired_state.py` holds the diff logic but is not wired into execution |
| Shadow reconciliation vs broker | **Portfolio** | Invariant-based `ledger/reconciliation.py` + `tasks/reconciliation.py`; external deltas → Unmanaged (`EXTERNAL_TRADE_DETECTED`) |
| Incident alerting | **Portfolio** | `src/alerts.py` `LedgerAlertDispatcher`: 6 incident kinds published to `lt.notifications` (best-effort, deterministic dedup) |
| P&L / provenance / holding history | **Portfolio** | Lot-level attribution + realized P&L per sleeve (`GetHoldingHistory`), including FIFO tax-lot tracking |
| Trading session (execution) | **Trading** | `TradingSession` (one per strategy; `strategy_id` NOT NULL) is the execution session, **linked to a portfolio sleeve** |
| Order-intent record | **Trading** | Durable `Order` rows (`executor/order_executor.py`); the book of record lives **here** in the portfolio ledger, fed by fills |
| Deterministic order ids | **Trading** | `order_executor.generate_deterministic_order_id` (`lt-<hash>`) gives exactly-once submission and is the `client_order_id → sleeve` attribution key on fills |
| Order-time risk checks | **Trading** | `risk/risk_manager.py` is **sleeve-aware**, reading sleeve free-cash/status from the portfolio ledger via `LedgerClient` |
| Order netting | **Planned / Not implemented** | Execution is **gross** today — one order (and one fill event) per symbol per sleeve. Block-and-allocate bunching is designed but not built; the only `netting.py` is a pure helper in portfolio's `src/ledger/`, not wired into execution |

---

## Design Decisions

1. **Lot-selection on sells** — FIFO only (simple, tax-friendly). LIFO and specific-lot selection are not implemented.
2. **Settlement model** — the projection reserves a settled/unsettled split, but settlement is not modeled yet (`unsettled` is always 0) and same-day rotation is not gated.
3. **Capital transfers** — cash-only, from free cash. Sell-to-raise execution and in-kind lot transfers between sleeves are designed but not implemented.
4. **Unmanaged adoption** — Unmanaged lots are strictly manual-controlled; a strategy adopts pre-existing shares only via an explicit user action.
5. **Netting timing** — gross execution graduates to block-and-allocate using the internal-cross pricing rule.

---

## References

Industry patterns this design follows:

- **Unified Managed Accounts / overlay management / sleeve accounting** — one custodian account, independent sleeves, a coordinating overlay manager:
  [Vestmark UMA](https://www.vestmark.com/uma), [SS&C Advent — UMA architecture](https://www.advent.com/news-and-insights/blog/unified-managed-accounts-the-architecture-of-scalable-wealth-management/), [Envestnet UMAs](https://www.envestnet.com/wealth-management/unified-managed-accounts), [coordinated rebalancing by a master overlay manager (patent)](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/7729969).
- **Block trade allocation at average price** — bunch orders, allocate fills to sub-accounts:
  [Theorem — allocation methods](https://theorem.io/help/allocation-methods), [DriveWealth — trading for many accounts](https://developer.drivewealth.com/implementation/docs/trading-for-many-accounts-at-once), [Everysk — SMA trade allocation automation](https://everysk.com/trading/trading-sma-trade-allocation-automation/).
- **Event sourcing + double-entry (single source of truth)** — append-only log, derived balances, conservation:
  [Mettle — Double entry + event sourcing (WODE)](https://www.mettle.co.uk/blog/innovation-at-mettle-double-entry-and-event-sourcing/), [Event Stream Accounting](https://www.codeproject.com/Articles/767983/Event-Stream-Accounting).
- **Shadow accounting** — an independent book reconciled against broker/administrator truth:
  [Arcesium — shadow accounting](https://www.arcesium.com/blog/shadow-accounting-luxury-or-necessity).

## Related Documentation

- [Strategy DSL Reference](strategy-dsl.md) — the language strategies are written in; target-weight semantics, compilation, and evaluation.
- [Execution Runtime](execution-runtime.md) — the shared backtest+live runtime that produces the target weights this ledger turns into attributed trades.
- [Trading Service](services/trading.md) — live execution, sessions, order management, fill emission.
- [Portfolio Service](services/portfolio.md) — performance reporting.
