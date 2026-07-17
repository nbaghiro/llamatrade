# Ledger Integration Contracts (Wave 0 — LOCKED)

The agreed interface between trading, strategy, portfolio, and web for the
portfolio ledger. Amendments vs. the original brief are marked **[AMENDED]**.

## 1. Redis fill event (Trading → Portfolio)

**Channel:** `ledger:fills:{account_id}` (`portfolio/src/ledger/ingestion.py:fill_channel`).

**Cardinality [AMENDED]:** exactly **one event per order, at terminal state** —
never per partial fill. The ledger `event_id = sha256(client_order_id)[:16]`, so
per-partial publishing would dedup all but the first partial away.

- `fill` → publish cumulative `filled_qty` / `filled_avg_price`.
- `canceled` / `expired` with `filled_qty > 0` → publish the filled portion.
- `canceled` / `rejected` / `expired` with no fill → publish nothing (the
  reservation release event covers the cash side; see §4).

**Payload (JSON)** — must match `ingestion.fill_to_append`:

```json
{
  "tenant_id": "<uuid>", "account_id": "<uuid>", "sleeve_id": "<uuid>",
  "client_order_id": "lt-<hash>", "order_id": "<uuid>",
  "symbol": "SPY", "side": "buy|sell", "qty": "50", "price": "480.00",
  "fees": "0.00",                // optional
  "cost_basis": "4800.00",       // optional, sells only [AMENDED]
  "realized_pnl": "200.00",      // optional, sells only
  "filled_at": "2026-06-11T14:30:00Z"
}
```

**Cost basis [AMENDED]:** `cost_basis` is **optional** on sells. When absent, the
portfolio fill consumer computes it at ingestion via FIFO lot selection
(`sizing.select_lots_fifo`) against the account projection, inside the writer's
serialized append path. Trading reports broker facts only and never does
accounting. (If supplied, the value passes through unchanged.)

**Idempotency:** re-delivered payloads are no-ops at `LedgerWriter.append`
(dedup on `event_id`). Attribution (`sleeve_id`) is fixed at order origination.

## 2. Proto surface

`trading.proto` (regenerate with `make proto` — TS lands in @llamatrade/core):

- `Order`: `sleeve_id = 26`, `account_id = 27`
- `Fill`: `sleeve_id = 9`, `account_id = 10`
- `TradingSession`: `account_id = 14`, `sleeve_id = 15`
- `SubmitOrderRequest`: `sleeve_id = 15` — empty ⇒ the order is attributed to
  the account's **Manual** sleeve (resolved server-side by trading via
  LedgerService).

`ledger.proto` — `LedgerService` is served by the **portfolio service process**
(port 8860, no new service). RPCs:

- `GetOrCreateAccount(credentials_id)` → `LedgerAccount` + base sleeves
  **[ADDED]** — the lazy `credentials_id → account_id` bootstrap that both
  strategy (funding) and trading (manual attribution) need; idempotent, also
  ensures the singleton Unallocated/Manual/Unmanaged sleeves.
- `AllocateCapital`, `TransferCapital`, `DepositFunds`, `WithdrawFunds`
  - `AllocateCapitalRequest` **[ADDED]**: with an empty `to_sleeve_id` and a
    `strategy_execution_id`, the portfolio opens (or reuses) the strategy
    sleeve linked to that execution and funds it atomically (open-and-fund).
- `ListSleeves`, `GetSleeve` (sleeve + open lots), `GetHoldingHistory`
- `CloseSleeve` **[ADDED]** — retire a sleeve, re-homing its holdings (§5a).
  `CloseSleeveResponse`: the CLOSED sleeve + `already_closed` + a re-home
  summary (`rehomed_cash`, `repeated RehomedPosition{symbol, qty, cost_basis}`).
- `Sleeve` message **[ADDED]**: `realized_pnl = 12` (projected from the event
  log) and `SleeveCash.reserved` is the **projected** reservation total (§4),
  not the row column.

## 3. LedgerClient (`libs/proto/llamatrade_proto/clients/ledger.py`)

Async wrapper over the generated stubs (pattern: `clients/auth.py`), exported
from `llamatrade_proto.clients`. Returns typed dataclasses with `Decimal`
amounts; `SleeveCashInfo.free = balance − reserved`. RPC errors **propagate**
(`grpc.aio.AioRpcError`) — fund ops are mutations, callers handle failures
explicitly. Consumers: strategy (`get_or_create_account` + `allocate_capital`
on execution funding), trading (`get_sleeve` for sleeve equity / free cash,
`list_sleeves`/`get_or_create_account` for Manual-sleeve resolution).

## 4. Cash reservation events (Trading → Portfolio) [ADDENDUM]

So sleeve free cash is correct with in-flight orders, trading also publishes to
the same channel (same envelope keys: `tenant_id`, `account_id`, `sleeve_id`,
`client_order_id`):

- on **submit** (buys): `event_type: "order_submitted"`, `reserved: "<notional est.>"`
  → ledger posts a reservation (`reserved_cash += amount`).
- on **cancel/reject/expiry**: `event_type: "order_cancelled" | "order_rejected"`
  → ledger releases the reservation.
- the terminal **fill** consumes the reservation (release + cash debit in one
  balanced event).

Reservation event ids derive from `sha256(client_order_id + ":" + event_type)`
so each lifecycle stage is idempotent independently. Uses the existing
`ORDER_SUBMITTED` / `ORDER_CANCELLED` / `ORDER_REJECTED` `LedgerEventType`s.
These reservation events carry no value postings of their own (they only
earmark cash, tracked as the projection's derived `reserved` total); the
terminal fill moves the value. Always active — the ledger is unconditional
(no rollout flags).

## 4a. Transport: Redis Streams [ADDED]

Under `STREAMS_LEDGER_FILLS`, every payload in §1/§4 is ALSO XADDed (flat
fields, no JSON envelope) to the global stream `lt:ledger:fills`
(`MAXLEN ~10k`), consumed durably by the portfolio's `portfolio-ledger`
consumer group (single active consumer; XAUTOCLAIM failover; per-account FIFO
preserved by global order). Pub/sub on `ledger:fills:{account_id}` remains the
primary path until staging parity, then is removed. Idempotency keys make
dual-path delivery a no-op on the second arrival.

## 4b. Emission paths and drift policy [ADDED]

Trading publishes from **three idempotent paths** (same `client_order_id` →
same ledger `event_id`, so racing or double-firing never double-counts): the
live trade stream, the REST sync recovery path (`sync_order_status` /
`sync_all_pending_orders`), and the event-sourced crash-recovery path. Market
buys reserve via the signal's `est_price`.

Portfolio's drift policy (always active — the ledger is authoritative):
`missing_in_ledger` → adopt into Unmanaged via `EXTERNAL_TRADE_DETECTED` at
broker avg price; `missing_at_broker`/`qty_mismatch` → freeze every sleeve
holding the symbol (+ `SLEEVE_FROZEN` audit event). Trading's risk check
rejects ALL orders on a frozen sleeve. Account creation
(`GetOrCreateAccount`) seeds the ledger from broker state (best-effort
backfill).

## 5. Identity threading

- **account_id**: portfolio derives/creates one `Account` per `credentials_id`
  (`GetOrCreateAccount`, lazy + idempotent).
- **sleeve_id**: created when a strategy execution is funded — strategy calls
  `AllocateCapital`, stores the returned `sleeve_id` + `account_id` on the
  execution row; trading reads them when starting the runner and threads them
  into orders, fills, sizing, and risk. Manual orders resolve the Manual sleeve.
- **client_order_id**: deterministic
  (`trading/src/executor/order_executor.py:generate_deterministic_order_id`) —
  reused as the attribution/idempotency key end-to-end.

## 5a. Sleeve close — re-home on stop/archive [ADDED]

A strategy sleeve is **retired** when its execution stops or its strategy is
archived. The strategy service owns sleeve lifecycle: it funds via
`AllocateCapital` and closes via `CloseSleeve`. Closing is **idempotent** and
**conservation-preserving** — it moves value between sleeves, never destroys it:

- open positions → the account's **Unmanaged** sleeve (carrying qty + cost
  basis; a re-home is not a sale, so no realized P&L is recognized);
- free cash → the **Unallocated** sleeve (immediately reusable);
- a `SLEEVE_CLOSED` event is appended and the sleeve's status becomes `CLOSED`.

Event id is `sha256(sleeve_id + ":close")`, so a re-close is a writer no-op. The
close **refuses while the sleeve has reserved cash** (an in-flight order): a
clean close commits no money to an open order.

`SLEEVE_CLOSED` payload (`data`): `sleeve_id`, `to_position_sleeve_id`
(Unmanaged), `to_cash_sleeve_id` (Unallocated), `positions`
(`[{symbol, qty, cost_basis}]`), `cash`, optional `reason`. Postings: each
position is two balanced POSITION legs (close on source, open on Unmanaged) and
cash is two balanced CASH legs — netting to zero (mirrors `SYMBOL_CHANGED`'s
two-leg move, but across sleeves).

**Triggers** (strategy service): execution **STOPPED** → close its sleeve;
strategy **ARCHIVED** → cascade-stop every non-terminal execution and close each
sleeve. The close is **best-effort** — a stop/archive succeeds even if the
ledger is unreachable (logged; re-homed on a later close).

**Decoupled, race-free orchestration** (no strategy→trading call): the strategy
closes the sleeve; trading's risk check blocks orders on any non-ACTIVE sleeve
(FROZEN or CLOSED); the runner self-stops on its next equity sync when the
sleeve is CLOSED; and a stray/late fill for a CLOSED sleeve is **re-homed to
Unmanaged** at ingestion (`_reroute_if_sleeve_closed`) so it can't resurrect a
retired sleeve.

## 6. Rollout

The `LEDGER_*` rollout flags were **removed (2026-06-14)**: the ledger is the
single source of truth and is always on, with no legacy fallback. Sleeve-aware
behavior (sizing, risk, reservations, reconciliation handoff, fill emission) is
keyed off whether an order/session carries a `sleeve_id` — unattributed/manual
orders degrade gracefully to account-level behavior. The only ledger env knobs
that remain are tuning intervals (`LEDGER_RECONCILE_INTERVAL_SECONDS`,
`LEDGER_SNAPSHOT_INTERVAL_SECONDS`). The Redis Streams transport flag
(`STREAMS_LEDGER_FILLS`) is a separate migration and is unaffected.
