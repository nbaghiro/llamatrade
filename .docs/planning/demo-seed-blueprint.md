# Demo-Account Seed — Blueprint

Goal: one polished, internally-consistent demo tenant (`demo@llamatrade.ai` / `demo1234`)
with realistic data across every product surface, so a visitor logging in sees a
"lived-in" account. This document is the data-model + strategy reference the seed
script (`scripts/seed_demo_account.py`) implements.

Scope rule: **demo-tenant-scoped only**. The script never touches other tenants.
No application/business logic, schema, or migration is modified — only the seed
script, its data file, the `make seed-demo` target, and this doc are added.

---

## 0. Where it runs (and why)

The ledger is the invariant-sensitive core. Its kernel (double-entry postings,
FIFO, projection/fold, equity-snapshot computation) lives in the **portfolio
service** package (`services/portfolio/src/ledger/*`, `src/tasks/equity_snapshot.py`).
To satisfy the "reuse the real kernel, don't hand-write balances" requirement the
seed **runs inside the `portfolio` container** (`WORKDIR /app`, `import src.…`
works) and imports that kernel directly.

Container capability matrix (verified):

| Need | portfolio | strategy |
|---|---|---|
| `llamatrade_db`, `llamatrade_proto`, `llamatrade_common` | ✅ | ✅ |
| ledger kernel (`src.ledger.*`, `src.tasks.equity_snapshot`) | ✅ | ❌ |
| `llamatrade_dsl` + `llamatrade_compiler` (parse/validate/to_json) | ❌ | ✅ |
| `bcrypt` | ❌ | ✅ |

Consequences:
- **Strategy DSL** is parsed/derived once in the **strategy** container from the
  real `template_service.TEMPLATES` and captured to `scripts/demo_seed_data/strategies.json`
  (sexpr + `config_json` + `symbols` + `timeframe`). The seed reads that file, so
  it never re-parses DSL and never invents tokens. Only templates that actually
  `parse_strategy → validate_strategy` clean are used (45 of 80 do; the other 35
  only pass the "starts with `(strategy`" test but fail the parser).
- **Password**: the seed hashes `demo1234` with `bcrypt.hashpw(..., gensalt())`
  if `bcrypt` is importable, else falls back to a **pre-generated valid `$2b$`
  hash constant** (bcrypt hashes are self-verifying, so `bcrypt.checkpw` in the
  auth service verifies it regardless of who produced it).

Run command:
```bash
docker cp scripts/demo_seed_data llamatrade-portfolio:/app/demo_seed_data
docker cp scripts/seed_demo_account.py llamatrade-portfolio:/app/seed_demo_account.py
docker exec -w /app llamatrade-portfolio python seed_demo_account.py
# or: make seed-demo
```

---

## 1. Auth / identity

Tables `tenants`, `users` (`libs/db/llamatrade_db/models/auth.py`). Password hashing
in auth is **bcrypt used directly** (`services/auth/src/grpc/servicer.py:375`):
`bcrypt.hashpw(request.password.encode(), bcrypt.gensalt()).decode()`; login verifies
with `bcrypt.checkpw`. No shared util, no pepper, cost 12, `$2b$`.

Login requirements (from `servicer.login`): looked up **by email only**
(`scalar_one_or_none`, so email must be globally unique), `bcrypt.checkpw` must pass,
`is_active` must be `True`. `is_verified` is **not** checked.

Seed rows:
- `Tenant(name="Alex Rivera Trading", slug="demo-llamatrade", is_active=True)` —
  slug is unique; fixed value makes the tenant findable for idempotent re-seed.
- `User(tenant_id=<tenant>, email="demo@llamatrade.ai", password_hash=<bcrypt>,
  first_name="Alex", last_name="Rivera", role="admin", is_active=True,
  is_verified=True, last_login=<recent>)`.

`AlpacaCredentials(tenant_id, name="Alpaca Paper (Demo)", api_key_encrypted,
api_secret_encrypted, is_paper=True, is_active=True)` — placeholder keys encrypted
with the real `llamatrade_common.utils.encrypt_value` (well-formed Fernet). The
`credentials_id` anchors the ledger account. Reconciliation against a live broker
with these fake keys **fails auth → the pass isolates/skips that account** (verified:
`tasks/reconciliation.py` catches `BrokerUnavailableError` and generic exceptions;
freezing only happens on a *successful* reconcile with material drift), so seeded
sleeves are never frozen.

---

## 2. Strategies

Tables `strategies`, `strategy_versions`, `strategy_executions`
(`models/strategy.py`). Enums via TypeDecorators (`models/_enum_types.py`) that
accept proto **int** constants (stored as DB enum strings).

Per strategy:
- `Strategy(tenant_id, name, description, status, is_public=False, current_version=1,
  created_by=<user>)`. `status` = `STRATEGY_STATUS_ACTIVE(2)` for live, else
  `STRATEGY_STATUS_DRAFT(1)`. `(tenant_id, name)` unique.
- `StrategyVersion(tenant_id, strategy_id, version=1, config_sexpr, config_json,
  symbols, timeframe, parameters={}, created_by)` — all four content fields come
  from `strategies.json` (real DSL + real `to_json`/`get_required_symbols`).
- **Live** strategies also get a funded `StrategyExecution(tenant_id, strategy_id,
  version=1, mode=EXECUTION_MODE_PAPER(1), status=EXECUTION_STATUS_RUNNING(2),
  started_at, allocated_capital, color, credentials_id, sleeve_id, account_id)`.
  The ledger-identity trio (migration 016) is filled after the sleeve is created.

Persona set (6, varied category/complexity; all parse+validate):

| id | name | category | live? | role in demo |
|---|---|---|---|---|
| classic-60-40 | Classic 60/40 | buy-and-hold | no | draft + backtest |
| all-weather | All-Weather Portfolio | buy-and-hold | **live** | sleeve + positions |
| risk-parity | Risk Parity | buy-and-hold | **live** | sleeve + positions |
| momentum-sectors | Momentum Sectors | factor/momentum | **live** | sleeve + positions + rebalance |
| vigilant-asset-allocation | Vigilant Asset Allocation (VAA) | trend | no (paused) | draft + backtest |
| pullback-buyer | Pullback Buyer | mean-reversion | no | draft + backtest (the underperformer) |

---

## 3. Backtests

Tables `backtests`, `backtest_results` (`models/backtest.py`). Each of the 6
strategies gets a **COMPLETED** backtest:
- `Backtest(tenant_id, strategy_id, strategy_version=1, name, status=BACKTEST_STATUS_COMPLETED(3),
  config, symbols, start_date, end_date, initial_capital=100000, started_at,
  completed_at, created_by)`.
- `BacktestResult(backtest_id, total_return, annual_return, sharpe_ratio,
  sortino_ratio, max_drawdown, max_drawdown_duration, win_rate, profit_factor,
  exposure_time, total_trades, winning_trades, losing_trades, avg_trade_return,
  final_equity, equity_curve[], trades[], daily_returns[], monthly_returns{},
  benchmark_return, benchmark_symbol="SPY", alpha, beta, information_ratio,
  benchmark_equity_curve[])`.

Metrics are hand-set per strategy to be believable and **varied, not all winners**
(Sharpe 0.55–1.55, CAGR 4.2%–12.8%, maxDD −8.9%…−21.5%, win 46%–62%). Equity and
benchmark curves + daily returns are synthesized to be consistent with those
targets (seeded RNG for reproducibility).

---

## 4. Portfolio ledger (book of record)

Tables `ledger_accounts`, `ledger_sleeves`, `ledger_events`, `ledger_sleeve_snapshots`
(`models/ledger.py`). **The event log is the single source of truth**; cash /
positions / realized-P&L are folded on read (`src/ledger/projection.py:fold`), and
the servicer's `ListSleeves`/`GetSleeve` derive lots from that projection — **nothing
reads `ledger_lots`** (it is an unbuilt "later optimization"), so the seed does not
materialize lot rows. `SleeveSnapshot` rows **do** back the equity curve
(`portfolio_read_service._daily_equity_series`, `strategy_performance_read_service`).

Seeding strategy — **replay a constructed event stream through the real kernel**:
1. `Account(tenant_id, credentials_id, base_currency="USD")`.
2. Base sleeves (identity rows, cash is projected not stored):
   `Unallocated`, `Manual`, `Unmanaged` (`SleeveType`, `SleeveStatus.ACTIVE`).
3. Strategy sleeves — one per live execution: `Sleeve(type="strategy",
   strategy_execution_id=<exec>, name, allocated_capital)`. Then back-fill the
   execution's `sleeve_id`/`account_id`/`credentials_id`.
4. Append events **chronologically** via `LedgerWriter.append` (asserts balance +
   idempotent on `event_id`; `sequence` autoincrements in append order). `occurred_at`
   is set to the historical business date of each event. Event shapes exactly match
   `build_postings` (`src/ledger/postings.py`):
   - `FUNDS_DEPOSITED` — `{sleeve_id: Unallocated, amount}` — deposit $100,000.
   - `CAPITAL_ALLOCATED` — `{from_sleeve_id: Unallocated, to_sleeve_id, amount}` —
     fund the 3 strategy sleeves + Manual.
   - `ORDER_FILLED` buy — `{sleeve_id, symbol, side:"buy", qty, price, fees,
     client_order_id, order_id}`.
   - `ORDER_FILLED` sell — same + **`cost_basis` + `realized_pnl`** computed via
     the real FIFO (`src/ledger/sizing.select_lots_fifo` over the sleeve/symbol's
     open lots — mirrors `ingestion.enrich_sell_fill`), so a basis-less sell can't
     poison the fold.
   - `DIVIDEND_RECEIVED` / `FEE_CHARGED` for flavor (balanced cash↔pnl legs).
5. `SleeveSnapshot` equity curve: for each weekly date, `fold` the events with
   `occurred_at ≤ date`, mark to a chosen price path, and call the real
   `equity_snapshot.compute_snapshot_values(projection, prices, sequence)`; persist
   each returned value as a `SleeveSnapshot(created_at=<date>, …)`.

**Invariants the stream guarantees** (all enforced by the kernel we reuse):
- Double-entry: every appended economic event's postings sum to $0 (`assert_balanced`
  in `LedgerWriter.append`).
- Conservation: deposit − allocations = Unallocated free cash; per sleeve
  cash = allocated − Σbuy_notional − fees + Σsell_proceeds + dividends ≥ 0.
- FIFO: sells consume oldest lots; realized P&L = proceeds − FIFO cost − fees.
- `Σ sleeve cash + Σ sleeve positions@mark = account equity`.
- No negative cash / negative (unopened short) positions (`check_sleeve_invariants`).

### Cash / allocation plan ($100,000 paper)
Deposit 100,000 → Unallocated. Allocations: All-Weather 35,000; Risk Parity 30,000;
Momentum Sectors 20,000; Manual 5,000 ⇒ Unallocated free ≈ 10,000. Each sleeve buys
< its allocation (small residual cash), a couple of sleeves rebalance (a sell + buy),
Manual does one closed round-trip (realized gain), one dividend + a few fees.
Net realized P&L is intentionally mixed (a small loss on a bond trim and a sector
rotation, a gain on the manual trade and a dividend).

---

## 5. Trading

Tables `trading_sessions`, `orders`, `positions` (`models/trading.py`). **There is
no separate `fills` table** — a "fill" is an `Order` at `ORDER_STATUS_FILLED`; the
same terminal fill is what publishes to the ledger. Migration 017 added
`sleeve_id`/`account_id` to sessions and orders.

For each live strategy:
- `TradingSession(tenant_id, strategy_id, strategy_version=1, credentials_id, name,
  mode=EXECUTION_MODE_PAPER, status=<ACTIVE via EXECUTION_STATUS_RUNNING>, config,
  symbols, started_at, last_heartbeat=<recent>, created_by, sleeve_id, account_id)`.
  Safe to mark ACTIVE: the trading lifespan only mounts the Connect app — runners
  start **only** via explicit RPC, there is no boot/periodic reclaim of active
  sessions (verified in `services/trading/src/main.py`).
- One `Order` per fill, `status=ORDER_STATUS_FILLED(5)`, `order_type` market/limit,
  `time_in_force=TIME_IN_FORCE_DAY`, `qty`/`filled_qty`/`filled_avg_price`,
  `submitted_at`/`filled_at`, `sleeve_id`/`account_id`, `client_order_id`
  **identical to the matching ledger `ORDER_FILLED` event's `client_order_id`** (the
  reconciliation link; ledger `event_id = sha256(client_order_id)[:16]`),
  `signal_reason`, `created_by`.
- One `Position` per open (session, symbol): `side=POSITION_SIDE_LONG`, `qty`,
  `avg_entry_price`, `cost_basis`, `current_price`/`market_value`/`unrealized_pl`
  (marked to the chosen final price so the Trading page shows P&L even without live
  market data), `realized_pl`, `is_open`, `opened_at`. Quantities/avg prices **equal
  the sleeve's folded position** (fills explain lots explain positions).

The Manual sleeve's round-trip is attributed to the Manual sleeve; its closed
position is written `is_open=False`, `closed_at`.

---

## 6. Billing

Tables `plans` (global), `subscriptions`, `payment_methods`, `invoices`
(`models/billing.py`). Plans are empty; the seed **get-or-creates** global plans by
unique `name` (not deleted on re-seed):
- `Plan(name="pro", display_name="Pro", tier=PLAN_TIER_PRO(3), price_monthly=49.00,
  price_yearly=490.00, features{}, limits{}, trial_days=14, is_active=True)`
  (+ a `free` plan for realism).
- `Subscription(tenant_id, plan_id=<pro>, status=SUBSCRIPTION_STATUS_ACTIVE(1),
  billing_cycle=BILLING_INTERVAL_MONTHLY(1), stripe_* ids (demo), current_period_start,
  current_period_end, cancel_at_period_end=False)`.
- `PaymentMethod(tenant_id, stripe_payment_method_id (demo), stripe_customer_id,
  type="card", card_brand="visa", card_last4="4242", exp, is_default=True)`.
- 1–2 paid `Invoice` rows for history.

---

## 7. Agent copilot

Tables `agent_sessions`, `agent_messages`, `agent_memory_facts`,
`agent_session_summaries` (`models/agent.py`). (`agent_memory_embeddings` needs a
1536-dim pgvector; skipped — facts drive the visible memory surface.)
- 3 `AgentSession` (user_id, title, status ACTIVE/COMPLETED, message_count,
  last_activity_at) with realistic multi-turn `AgentMessage` threads (user +
  assistant; one assistant turn carries `tool_calls_json` for a `create_strategy`
  call), e.g. "Help me build a momentum strategy", "Why did Risk Parity draw down?",
  "What is dual momentum?".
- ~5 `AgentMemoryFact` (risk tolerance, asset preference, investment goal, strategy
  decision, trading behavior) via `MemoryFactCategory`.
- `AgentSessionSummary` for the completed sessions.

---

## 8. Creation order (FK- and invariant-safe)

1. Tenant → User → AlpacaCredentials
2. Plans (get-or-create) → Subscription → PaymentMethod → Invoices
3. Strategies → StrategyVersions
4. StrategyExecutions (live) — insert to get `execution_id`
5. Ledger Account → base sleeves → strategy sleeves (link `strategy_execution_id`);
   back-fill `execution.sleeve_id/account_id/credentials_id`
6. Ledger events (deposit → allocations → fills/dividends/fees) via `LedgerWriter`
7. SleeveSnapshots (fold-per-date → `compute_snapshot_values`)
8. TradingSessions → Orders → Positions
9. Backtests → BacktestResults
10. Agent sessions → messages → memory facts → summaries

## 9. Idempotency

Re-runnable via **transactional delete-then-recreate of the demo tenant only**.
The tenant is found by fixed `slug="demo-llamatrade"`; if present, every
tenant-scoped row referencing its `tenant_id` is deleted child→parent
(`backtest_results` via its `backtests`; ledger snapshots/events/lots/sleeves/accounts;
orders/positions/sessions; executions/versions/strategies; invoices/usage/subs/
payment_methods; agent memory/messages/sessions; alpaca_credentials; api_keys; the
user), then the tenant, then everything is recreated in one transaction. Global
`plans` are get-or-created, never deleted. No other tenant is touched.

## 10. Known caveats

- **Live position marks** on the Portfolio (portfolio-service) page depend on the
  market-data service returning prices for the held symbols; with an empty store
  positions mark at cost (0 unrealized there). The **equity curve** (stored
  snapshots) and **Trading-page positions** (stored `current_price`) show P&L
  regardless. Realized P&L is fully stored in the ledger.
- `ledger_lots` and `agent_memory_embeddings` are intentionally not populated
  (nothing reads the former; the latter needs real embeddings).
- Fake Alpaca keys ⇒ background reconcile logs an isolated auth failure per pass
  (harmless; no sleeve freeze).
- **Pre-existing model/migration drift** (not fixed here): the live
  `backtest_results` table (head 021) lacks the model's `max_drawdown_duration`,
  `exposure_time`, and `monthly_returns` columns, and the model's Python-side
  default on `max_drawdown_duration` forces it into every ORM INSERT. The seed
  therefore inserts `backtest_results` via a raw parameterized SQL statement over
  the columns that actually exist. (Flagged for a follow-up migration/model
  reconciliation.)
</content>
</invoke>
