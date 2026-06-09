# LlamaTrade — Architecture & System Guide

LlamaTrade is a multi-tenant SaaS platform for algorithmic trading. Users build (or pick) trading strategies in a visual builder, backtest them against historical market data, and run them live or in paper mode against their own brokerage account at [Alpaca Markets](https://alpaca.markets/).

This document is the **single entry point** for understanding the system. It explains the product, the end-to-end flows, and the system design, and links out to focused deep-dive docs for each area. Read it top-to-bottom for a full mental model; jump via the [Documentation Map](#documentation-map) when you need depth on one area.

---

## Table of Contents

1. [Documentation Map](#documentation-map)
2. [What LlamaTrade Is](#what-llamatrade-is)
3. [The User Journey](#the-user-journey)
4. [System Architecture](#system-architecture)
5. [How It Works — End-to-End Flows](#how-it-works--end-to-end-flows)
6. [Data Model](#data-model)
7. [Multi-Tenancy](#multi-tenancy)
8. [Service Communication (gRPC/Connect)](#service-communication)
9. [Event Sourcing](#event-sourcing)
10. [Security](#security)
11. [Technology Stack](#technology-stack)
12. [Getting Started](#getting-started)
13. [Testing](#testing)
14. [Deployment & Operations](#deployment--operations)

---

## Documentation Map

Where to go for depth on each area:

| Area | Document |
| --- | --- |
| Authentication, users, tenants, API keys | [services/auth.md](services/auth.md) |
| Strategy CRUD, versioning, templates | [services/strategy.md](services/strategy.md) |
| Strategy DSL (the strategy language) | [strategy-dsl.md](strategy-dsl.md) |
| How strategies execute (target weights → orders) | [portfolio-ledger.md](portfolio-ledger.md) |
| Backtesting engine & metrics | [services/backtesting.md](services/backtesting.md) |
| Market data (historical + real-time) | [services/market-data.md](services/market-data.md) |
| Live trading & order execution | [services/trading.md](services/trading.md) |
| Positions, P&L, performance | [services/portfolio.md](services/portfolio.md) |
| Alerts, webhooks, email/SMS | [services/notification.md](services/notification.md) |
| Subscriptions & billing (Stripe) | [services/billing.md](services/billing.md) |
| AI strategy copilot | [services/agent.md](services/agent.md) |
| Supported asset classes | [asset-classes.md](asset-classes.md) |
| Built-in strategy catalog | [trading-strategies.md](trading-strategies.md) |
| Key design decisions | [decisions/](decisions/) |
| **Alpaca** Trading API | [docs.alpaca.markets — Trading API](https://docs.alpaca.markets/docs/trading-api) |
| **Alpaca** Market Data API | [docs.alpaca.markets — Market Data](https://docs.alpaca.markets/docs/about-market-data-api) |
| **Alpaca** OAuth ("Connect with Alpaca") | [docs.alpaca.markets — OAuth](https://docs.alpaca.markets/us/docs/using-oauth2-and-trading-api) |
| **Alpaca** Broker API (embedded brokerage) | [docs.alpaca.markets — Broker API](https://docs.alpaca.markets/us/docs/about-broker-api) |

---

## What LlamaTrade Is

**The problem.** Building and running an automated trading strategy normally requires stitching together market data feeds, a backtesting engine, a broker integration, order/position bookkeeping, and risk controls — plus the infrastructure to run it reliably. That's weeks of plumbing before you can test a single idea.

**The product.** LlamaTrade gives that whole pipeline as a hosted product:

- A **visual strategy builder** that compiles to a portable strategy language (DSL).
- A **backtesting engine** to validate a strategy against years of historical data with benchmark comparison.
- **One-click deployment** to paper or live trading against the user's own Alpaca account.
- **Live monitoring** of orders, positions, P&L, and alerts.

**The core mental model.** Everything in the product follows one loop:

```
   Build / pick a Strategy  ─►  Backtest it  ─►  Deploy to Paper  ─►  Go Live
        (visual builder)         (vs SPY)         (simulated)        (real money)
```

**The brokerage relationship.** LlamaTrade never holds customer funds or securities. Each user connects **their own Alpaca brokerage account**; LlamaTrade is the automation layer that places orders on that account. Alpaca (a registered broker-dealer, member FINRA/SIPC) is the broker of record. See [Alpaca integration](#41-alpaca-integration--account-model).

**Who uses it.** Retail and semi-professional traders who want systematic strategies without building infrastructure; quant-curious users who want to test ideas; and teams (tenants) who want shared strategies under one account with role-based access.

---

## The User Journey

A typical end-to-end flow through the product:

1. **Sign up** → a `Tenant` is created with the user as `owner`; the user logs in and receives a JWT. → [auth.md](services/auth.md)
2. **Connect Alpaca** → the user adds their Alpaca API key/secret (stored encrypted), choosing paper or live. → [§4.1](#41-alpaca-integration--account-model)
3. **Build or pick a strategy** → drag-and-drop in the visual builder, start from a template, or get help from the **AI copilot**. The builder compiles to a versioned DSL strategy. → [strategy.md](services/strategy.md), [agent.md](services/agent.md)
4. **Backtest** → run the strategy over a historical window; review return, Sharpe, drawdown, win rate, and performance **vs a benchmark (S&P 500 by default)**. → [§4.5](#45-backtesting--benchmarking)
5. **Deploy to paper** → launch a live session in paper mode; the strategy trades simulated money on real-time data. → [§4.3](#43-live-trading-execution)
6. **Go live** → on a paid plan, promote the session to live trading on the user's real Alpaca account, with risk controls and a circuit breaker active.
7. **Monitor** → watch orders fill, positions update, and P&L accrue on the portfolio dashboard; receive alerts via email/SMS/webhook. → [portfolio.md](services/portfolio.md), [notification.md](services/notification.md)
8. **Subscribe** → plan tier governs live-trading access, limits, and rate limits, billed through Stripe. → [billing.md](services/billing.md)

---

## System Architecture

LlamaTrade is a set of focused microservices. The browser talks **directly** to each service over the Connect protocol (no API gateway); services talk to each other over gRPC; and asynchronous/real-time work flows through Redis.

```
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                                     USER BROWSER                                      │
└───────────────────────────────────────────┬───────────────────────────────────────────┘
                                            │
                                            ▼
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (React SPA) :8800                               │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐  │
│  │   Auth    │ │ Strategy  │ │ Backtest  │ │  Trading  │ │ Portfolio │ │  Copilot  │  │
│  │   Pages   │ │  Builder  │ │  Runner   │ │   Panel   │ │ Dashboard │ │   Chat    │  │
│  └───────────┘ └───────────┘ └───────────┘ └───────────┘ └───────────┘ └───────────┘  │
│                           Zustand + Connect Protocol Client                           │
└───────────────────────────────────────────┬───────────────────────────────────────────┘
                                            │ Connect Protocol (HTTP/1.1 + JSON)
                                            ▼
 ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
 │  Auth  │ │Strategy│ │Backtest│ │ Market │ │Trading │ │Portfol.│ │ Notif. │ │ Agent  │
 │  8810  │ │  8820  │ │  8830  │ │  8840  │ │  8850  │ │  8860  │ │  8870  │ │  8890  │
 └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘
     └──────────┴──────────┴──────────┴─gRPC┬────┴──────────┴──────────┴──────────┘
                                            │
                   ┌────────────────────────┼────────────────────────┐
                   ▼                        ▼                        ▼
           ┌──────────────┐         ┌──────────────┐         ┌──────────────┐
           │   Postgres   │         │    Redis     │         │    Alpaca    │
           │ + Timescale  │         │ Cache/Queue  │         │     API      │
           │    (RLS)     │         │   /Streams   │         │  + Streams   │
           └──────────────┘         └──────────────┘         └──────────────┘
```

### Core Services

| Service | Port | Responsibility |
| --- | --- | --- |
| **Frontend (Web)** | 8800 | React SPA (visual builder, dashboards), served via nginx/CDN |
| **Auth** | 8810 | Users, tenants, roles, API keys, JWT, encrypted Alpaca credentials |
| **Strategy** | 8820 | Strategy CRUD, versioning, compilation, templates |
| **Backtest** | 8830 | Historical simulation, metrics, benchmark comparison |
| **Market Data** | 8840 | Historical bars (stored) + real-time streaming from Alpaca |
| **Trading** | 8850 | Live/paper order execution, risk enforcement, position tracking |
| **Portfolio** | 8860 | Positions, P&L, performance metrics |
| **Notification** | 8870 | Alerts, webhooks, email/SMS |
| **Billing** | 8880 | Subscriptions, plan limits, usage metering (Stripe) |
| **Agent** | 8890 | AI copilot — natural-language strategy building & assistance |

\*Billing also exposes HTTP port 8881 for Stripe webhooks.

### Communication Patterns

- **Frontend → Services (Connect):** HTTP/1.1 + JSON; every request carries a Bearer JWT validated by each service's auth middleware. See [decisions/gateway-vs-direct-communication.md](decisions/gateway-vs-direct-communication.md).
- **Service → Service (gRPC):** HTTP/2 + binary protobuf for internal calls (e.g. Backtest → Market Data for history, Trading → Portfolio for limits).
- **Asynchronous (Celery/Redis):** long-running jobs such as backtests run on Celery workers; notifications and usage metering run as background tasks.
- **Real-Time (Connect streams / Redis Streams):** live price updates from Market Data, order/position updates from Trading, and backtest progress are delivered as server-side streams.

### Built-in Strategies

The platform ships a catalog of ready-to-use strategies (MA Crossover, RSI Mean Reversion, MACD, Bollinger Bounce, Donchian Breakout, Dual Momentum, Pairs Trading, and more). See the full catalog and parameters in [trading-strategies.md](trading-strategies.md).

---

## How It Works — End-to-End Flows

This section explains the flows that span multiple services — first in product terms, then technically.

### 4.1 Alpaca integration & account model

LlamaTrade trades on the **user's own Alpaca account** (Bring-Your-Own-Account). The user generates an API key/secret in their Alpaca dashboard and saves it in LlamaTrade; we store it **encrypted per tenant** (AES-256-GCM, `alpaca_credentials.api_key_encrypted` / `api_secret_encrypted`) with an `is_paper` flag distinguishing paper from live accounts. Each trading session and data request uses the relevant tenant's credentials, decrypted in-memory at use.

Because the user is Alpaca's direct customer, **Alpaca is the broker-dealer of record** (member FINRA/SIPC), handling custody, clearing, and account-level KYC/AML. LlamaTrade is the strategy/automation layer and never custodies funds.

- All Alpaca access — REST and WebSocket — goes through the shared `llamatrade_alpaca` library.
- For an alternative model where a platform *embeds* brokerage (opening accounts on the user's behalf), see Alpaca's [Broker API](https://docs.alpaca.markets/us/docs/about-broker-api); a scoped-token connect experience is available via [Alpaca OAuth](https://docs.alpaca.markets/us/docs/using-oauth2-and-trading-api).

→ Deep dive: [trading.md](services/trading.md), [auth.md](services/auth.md)

### 4.2 Strategy lifecycle

A user builds a strategy in the **visual builder** (or starts from a template, or describes it to the AI copilot). The builder state compiles to a **DSL** — an S-expression representation that is portable and executable. Saving a strategy creates an **immutable `StrategyVersion`** (the visual `config` JSON plus the compiled `sexpr`); editing always produces a new version, so backtests and live sessions are always pinned to an exact, reproducible definition.

```
Visual Builder ──compile──► DSL (S-expression) ──save──► StrategyVersion (immutable)
   (config JSON)                                              │
                                                   ┌──────────┴──────────┐
                                                   ▼                     ▼
                                              Backtest             Trading Session
```

→ Deep dive: [strategy.md](services/strategy.md), [strategy-dsl.md](strategy-dsl.md), [agent.md](services/agent.md)

### 4.3 Live trading execution

When a user deploys a strategy, the Trading service starts a **strategy runner** bound to that tenant's Alpaca credentials. From then on the runner drives the full loop:

```
Market Data (live bars) ─► Strategy logic ─► Signal ─► Risk checks + Circuit breaker
                                                              │ (pass)
                                                              ▼
                                                     Order Executor ─► Alpaca submit_order
                                                              │
        Position reconciliation ◄── Position update ◄── Fill (trade_updates stream)
```

1. **Session start** — preflight checks (paid plan required for live; buying power via Alpaca account); runner launches.
2. **Data in (two clocks)** — the runner consumes a real-time **bar stream** (1-minute bars) and ticks **every minute the market is open**, but a **date-based rebalance gate** (the strategy's `:rebalance` frequency, *at most once per day*) decides when it actually recomputes target weights. So a `daily` strategy is evaluated all session but rebalances **once**; coarser frequencies rebalance on the first qualifying bar of the period. See [Rebalance Frequencies](strategy-dsl.md#rebalance-frequencies).
3. **Signal → risk** — signals pass through risk limits and a **circuit breaker** (consecutive-loss / daily-loss / drawdown limits) that can halt the session.
4. **Order out** — a single rebalance can emit **multiple orders at once** (one per symbol whose holding must change — sells and buys; plus bracket children when a parent fills). The **order executor** submits them to Alpaca **immediately within the open window** (market, limit, stop, stop-limit, and bracket/OCO with attached stop-loss + take-profit); there is no deferred "place later" queue.
5. **Fills in** — a **`trade_updates` stream** delivers fills **asynchronously** (submission ≠ instant fill); **fills are the source of truth for positions** (not optimistic local state).
6. **Reconciliation** — the runner periodically reconciles local positions against the broker and corrects drift.

Durability is provided by **event sourcing** (see [§Event Sourcing](#event-sourcing)) with deterministic `client_order_id`s for idempotent submission and crash recovery.

→ Deep dive: [trading.md](services/trading.md), [portfolio-ledger.md](portfolio-ledger.md)

### 4.4 Market data & where it comes from

The **Market Data service** is the single gateway to Alpaca's data and the system of record for price history:

- **Historical bars** are ingested from Alpaca and stored in a **TimescaleDB hypertable** (`bars`), partitioned by time and shared across tenants (price history is not tenant-specific). Queries for history are served from this store, so backtests are fast and repeatable and don't re-hit Alpaca for the same window.
- **Real-time** trades/quotes/bars stream from Alpaca's WebSocket and are fanned out to subscribed clients; the hottest values are cached in **Redis** with short TTLs.
- Other services never call Alpaca for data directly — they call Market Data over gRPC.

```
Alpaca REST/WS ─► Market Data service ─┬─► TimescaleDB (bars: durable history)
                                       └─► Redis (hot cache + real-time fan-out)
                                                  ▲
   Backtest / Frontend / Trading ──gRPC──────────┘
```

→ Deep dive: [market-data.md](services/market-data.md), [decisions/tiingo-vs-alpaca-market-data.md](decisions/tiingo-vs-alpaca-market-data.md)

### 4.5 Backtesting & benchmarking

A backtest replays a strategy over a historical window and reports how it would have performed.

- The Backtest service fetches the required bars from **Market Data** (the TimescaleDB-backed store) over gRPC, then runs the compiled strategy through a **vectorized engine** that simulates orders and positions bar-by-bar.
- It computes performance metrics: total return, Sharpe, Sortino, max drawdown, win rate, profit factor, total trades, and an equity curve.
- **Benchmarking:** results are compared against a benchmark — **S&P 500 (`SPY`) by default**, or a symbol configured on the backtest request (`benchmark_symbol`). The engine computes buy-and-hold of the benchmark and derives alpha, beta, and information ratio. A strategy may also declare its own benchmark in the DSL.
- Backtests run as **Celery jobs**; progress streams to the UI via Redis pub/sub with an ETA.

→ Deep dive: [backtesting.md](services/backtesting.md)

---

## Data Model

PostgreSQL with SQLAlchemy 2.0 (async). All tenant-scoped models inherit a `tenant_id` foreign key to `tenants.id`; price `bars` are shared (no tenant scope) and stored in TimescaleDB.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                TENANT BOUNDARY                              │
│   All models below are scoped to a tenant (except Bars, which are shared)   │
└─────────────────────────────────────────────────────────────────────────────┘

                              ┌──────────────────┐
                              │     TENANT       │
                              │ id, name, slug   │
                              │ settings (JSONB) │
                              └────────┬─────────┘
        ┌──────────────┬───────────────┼───────────────┬──────────────┐
        ▼              ▼               ▼               ▼              ▼
   ┌────────┐   ┌──────────┐   ┌─────────────┐  ┌────────────┐  ┌──────────┐
   │  USER  │   │ API_KEY  │   │  ALPACA_    │  │SUBSCRIPTION│  │AUDIT_LOG │
   │ email  │   │ key_hash │   │ CREDENTIALS │  │ plan,status│  │ action   │
   │ role   │   │ scopes   │   │ enc keys    │  │ stripe_id  │  │ entity   │
   │ pw_hash │   └──────────┘   │ is_paper    │  └────────────┘  └──────────┘
   └────────┘                   └─────────────┘

                       ┌──────────────────────────┐
                       │        STRATEGY          │
                       │ name, status, version    │
                       │ created_by (→ User)      │
                       └────────────┬─────────────┘
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
 ┌─────────────────┐     ┌─────────────────────┐    ┌──────────────────┐
 │ STRATEGY_VERSION│     │  TRADING_SESSION    │    │     BACKTEST     │
 │ version, config │     │  mode: paper|live   │    │ date range,      │
 │ sexpr (compiled)│     │  status, symbols    │    │ initial_capital  │
 └─────────────────┘     └──────────┬──────────┘    └────────┬─────────┘
  immutable snapshots               │                        │ 1:1
                          ┌─────────┴─────────┐               ▼
                          ▼                   ▼      ┌──────────────────┐
                    ┌──────────┐       ┌──────────┐ │ BACKTEST_RESULT  │
                    │  ORDER   │       │ POSITION │ │ return, sharpe,  │
                    │ side,qty │       │ qty, pnl │ │ drawdown,        │
                    │ status   │       └──────────┘ │ equity_curve     │
                    └──────────┘                    └──────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                        SHARED DATA (No Tenant Scope)                        │
│   BAR (TimescaleDB hypertable): symbol+timestamp+timeframe (PK),            │
│   OHLCV; partitioned by time. Timeframes: 1Min…1Day.                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

Key relationships: a `Tenant` owns Users, API Keys, Alpaca Credentials, a Subscription, Strategies, and Audit Logs. Each `Strategy` owns immutable `StrategyVersion`s and spawns `TradingSession`s (→ Orders, Positions) and `Backtest`s (→ 1:1 Result).

→ Deep dive: the SQLAlchemy models live in `libs/db`; migrations are managed with Alembic.

---

## Multi-Tenancy

Every operation is tenant-scoped with complete isolation:

1. The **JWT** carries a `tenant_id` claim.
2. Auth middleware resolves a `TenantContext` (`ctx = Depends(require_auth)`).
3. **Every database query** filters by `ctx.tenant_id`.
4. Service-to-service calls propagate tenant via the `X-Tenant-ID` header.

Defense in depth at the database layer uses **Row-Level Security**:

```sql
ALTER TABLE strategies ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON strategies
    FOR ALL USING (tenant_id = current_setting('app.tenant_id')::uuid);
```

**Never allow cross-tenant access. When in doubt, add tenant filtering.** Tenant-isolation tests assert that one tenant cannot read another's data (and that missing rows return `NOT_FOUND`, never leaking existence).

---

## Service Communication

Services share contracts via **Protocol Buffers**:

- **Connect** — browser ↔ services (HTTP/1.1 + JSON).
- **gRPC** — service ↔ service (HTTP/2 + binary protobuf).

Proto definitions live in `libs/proto/llamatrade_proto/protos/`; generated Python and TypeScript are produced by `make proto`.

### Enums (proto is the source of truth)

Enums are defined once in proto and generated for both languages:

```
Proto definition ──► Python integer constants (+ conversion helpers for external APIs)
                 └─► TypeScript numeric enums
```

```python
from llamatrade_proto.generated import ORDER_SIDE_BUY, ORDER_STATUS_FILLED
from src.models import order_side_to_str          # int → "buy"/"sell" for Alpaca

if order.side == ORDER_SIDE_BUY:                   # integers internally
    await alpaca.submit_order(side=order_side_to_str(order.side))  # strings only at the boundary
```

Rules: proto is the source of truth (never re-define enums); use integers internally and for storage; convert to strings only at external boundaries (Alpaca, display).

### Representative endpoints (per service)

Each service exposes a Connect/gRPC API; a representative subset:

- **Auth (8810):** `Login`, `Register`, `RefreshToken`, `GetCurrentUser`, `ValidateToken`, `ValidateAPIKey`, Alpaca-credential management.
- **Strategy (8820):** strategy & version CRUD, `CompileStrategy`, `ValidateStrategy`, templates, execution lifecycle.
- **Backtest (8830):** `RunBacktest`, `GetBacktest`, `ListBacktests`, `CancelBacktest`, `CompareBacktests`, `StreamBacktestProgress`.
- **Market Data (8840):** `GetHistoricalBars`, `GetMultiBars`, `GetSnapshot`, `GetSnapshots`, `GetMarketStatus`, `StreamBars`, `StreamQuotes`, `StreamTrades`.
- **Trading (8850):** order submit/get/list/cancel, positions, `StreamOrderUpdates`, `StreamPositionUpdates`, session lifecycle.
- **Portfolio (8860):** portfolio, performance, allocation, strategy performance.
- **Notification (8870):** notifications, alerts, channels.
- **Billing (8880):** subscriptions, checkout/portal sessions (Stripe).
- **Agent (8890):** copilot chat / strategy-assist sessions.

The authoritative, complete RPC list for each service lives in its proto file and its service doc.

### Errors

Connect/gRPC status codes are used consistently (`INVALID_ARGUMENT`, `NOT_FOUND`, `PERMISSION_DENIED`, `UNAUTHENTICATED`, `INTERNAL`):

```python
raise ConnectError(Code.NOT_FOUND, f"Strategy not found: {strategy_id}")
```

---

## Event Sourcing

The Trading service uses event sourcing for durable execution, crash recovery, and a complete audit trail.

```
Strategy Runner ─► EventSourcedOrderExecutor ─► Event Store (append-only)
   Signal              1. deterministic client_order_id (SHA256)
                       2. check Alpaca for existing order (recovery)
                       3. risk checks
                       4. emit OrderSubmitted
                       5. submit to Alpaca
                       6. emit OrderAccepted / OrderRejected / OrderFilled
```

**Events** are immutable facts ordered by a global sequence, scoped to tenant + session. **Aggregates** (current state) are derived by replaying events:

```python
state = await SessionState.load(session_id, tenant_id, event_store)
state.positions["AAPL"]; state.orders[order_id]; state.realized_pnl
```

**Idempotent submission.** Orders use a deterministic `client_order_id` derived from signal parameters, so the same signal always yields the same id and Alpaca treats it as an idempotency key:

```python
data = f"{session_id}:{symbol}:{side}:{signal_timestamp.isoformat()}"
client_order_id = "lt-" + hashlib.sha256(data.encode()).hexdigest()[:16]
```

**Crash recovery.** On restart, signal replay reproduces the same `client_order_id`; the executor checks Alpaca for the order, emits any missing events, and skips re-submission.

**Event families:** signal (`signal.generated/rejected`), order (`order.submitted/accepted/rejected/filled/partially_filled/cancelled`), position (`position.opened/increased/reduced/closed`), session (`session.started/stopped/paused/resumed`), and circuit breaker (`circuit_breaker.triggered/reset`).

→ Deep dive: [trading.md](services/trading.md)

---

## Security

Multi-layered: authentication, authorization, tenant isolation, and data protection.

**Authentication.** JWT access tokens (30 min, in-memory) + refresh tokens (7 days, HttpOnly cookie):

```json
{ "sub": "user-uuid", "tenant_id": "tenant-uuid", "roles": ["admin"], "exp": 1705314000, "type": "access" }
```

API keys for programmatic access use the format `lt_<prefix>_<random>`, with only a SHA-256 hash stored, plus optional scopes and expiry. Passwords are bcrypt-hashed.

**Authorization (RBAC).**

| Role | Permissions |
| --- | --- |
| `owner` | Full access, billing, user management |
| `admin` | Everything except billing changes |
| `user` | CRUD own strategies, view portfolio |
| `viewer` | Read-only |

**Data protection.** Alpaca credentials are encrypted at rest (AES-256-GCM); all external traffic uses TLS; internal gRPC and database connections use TLS/SSL. Secrets live in GCP Secret Manager (`jwt-secret`, `encryption-key`, `stripe-api-key`).

**Audit logging.** Security-relevant events (`user.login`, `user.login_failed`, `api_key.created`, `strategy.deployed`, `order.submitted`) are recorded per tenant.

**Developer rules:** never log secrets; always parameterize queries; validate all input with Pydantic; check `tenant_id` on every query; never commit secrets.

---

## Technology Stack

**Backend:** Python 3.14, FastAPI (async) hosting Connect/gRPC ASGI apps; Celery + Redis for jobs; PostgreSQL 16 with **TimescaleDB** for time-series bars; Redis 7 for cache, pub/sub, and streams.

**Frontend:** React 18 + Vite, TypeScript, Tailwind CSS, Zustand, the Connect client (`@connectrpc/connect`), and a custom canvas-based strategy builder.

**Shared libraries (`libs/`):** `alpaca` (Alpaca REST + WebSocket clients), `proto` (contracts + generated code), `db` (SQLAlchemy models + migrations), `dsl` (strategy language), `compiler` (strategy compiler), `common` (middleware, observability, utilities).

**Infrastructure:** GCP — GKE Autopilot, Cloud SQL (PostgreSQL), Memorystore (Redis), Cloud Storage, Cloud CDN, L7 Load Balancer, Secret Manager, Cloud Monitoring/Logging; CI/CD via GitHub Actions + Cloud Build.

---

## Getting Started

```bash
# 1. Clone and configure
git clone https://github.com/your-org/llamatrade.git && cd llamatrade
cp .env.example .env && cp apps/web/.env.example apps/web/.env

# 2. Generate proto code (required after clone)
make proto

# 3. Run everything in Docker
make dev          # all services + Postgres + Redis + frontend
```

Hybrid mode (infra in Docker, services local):

```bash
make dev-infra    # Postgres + Redis only
make dev-local    # all services locally
```

Required environment variables include `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `ENCRYPTION_KEY` (for Alpaca credential encryption), and `ALPACA_API_KEY`/`ALPACA_API_SECRET` (for testing). Frontend service URLs are configured in `apps/web/.env`.

```
llamatrade/
├── apps/web/            # React frontend
├── services/           # auth, strategy, backtest, market-data, trading,
│                       #   portfolio, notification, billing, agent
├── libs/               # alpaca, proto, db, dsl, compiler, common
├── infrastructure/     # docker, k8s, terraform
└── tests/integration/  # cross-service integration tests
```

---

## Testing

> Well-tested code is non-negotiable — prefer too many tests over too few.

Priorities: business logic in the service layer; edge cases and error handling; **tenant isolation** (no cross-tenant leakage); database operations and constraints; API validation.

```bash
make test                 # full suite
make test-auth            # one service
cd services/auth && pytest --cov=src --cov-report=term-missing
```

Integration tests use `httpx.AsyncClient` + `ASGITransport`; dependencies are mocked via `app.dependency_overrides`. Target **80% coverage** for real implementations.

---

## Deployment & Operations

Production runs on **GKE Autopilot** with Cloud SQL (PostgreSQL/TimescaleDB), Memorystore (Redis), and an L7 load balancer terminating TLS.

**Environments:** staging (auto-deployed on merge to `main`) and production (tag + manual approval):

```bash
git tag v1.2.3 && git push origin v1.2.3   # then, after approval:
make deploy-prod
```

**Runtime:** each service runs ≥2 replicas with CPU/memory requests+limits, gRPC liveness probes, and Horizontal Pod Autoscaling (CPU-target 70%). Every service exposes `/health`:

```json
{ "status": "healthy", "service": "auth", "version": "1.2.3" }
```

**Observability:** Prometheus metrics (`http_requests_total`, `http_request_duration_seconds`, `db_query_duration_seconds`), structured JSON logs to Cloud Logging, and alerts on error rate, latency, and crash loops.

**Operational basics:**

```bash
kubectl logs -l app=auth -n production --tail=100      # logs
kubectl rollout undo deployment/auth -n production     # rollback
alembic downgrade -1                                   # db rollback
```

Backups: daily database snapshots (7-day retention), Redis persistence, and versioned object storage; full environments are reproducible via Terraform + `kubectl apply -k`.
