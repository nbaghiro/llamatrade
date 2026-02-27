# LlamaTrade - Architecture Documentation

## Overview

LlamaTrade is a SaaS algorithmic trading platform enabling users to create custom strategies or use pre-built ones, backtest against historical data, and execute live trades via Alpaca Markets API.

**Architecture:** Microservices (Python FastAPI backend + React/TypeScript/Tailwind frontend)

---

## Services Architecture

### Core Services (10 total, all in GKE)

| Service                  | gRPC Port | HTTP Port | Responsibility                          |
| ------------------------ | --------- | --------- | --------------------------------------- |
| **Frontend (Web)**       | -         | 8800      | React SPA served via nginx, CDN-backed  |
| **API Gateway**          | -         | 8000      | gRPC-Web proxy, auth, rate limiting     |
| **Auth Service**         | 8810      | -         | Users, tenants, API keys, JWT           |
| **Strategy Service**     | 8820      | -         | Strategy CRUD, versioning, templates    |
| **Backtest Service**     | 8830      | -         | Historical simulation execution         |
| **Market Data Service**  | 8840      | -         | Real-time + historical data from Alpaca |
| **Trading Service**      | 8850      | -         | Live order execution, risk enforcement  |
| **Portfolio Service**    | 8860      | -         | Positions, P&L, performance metrics     |
| **Notification Service** | 8870      | -         | Alerts, webhooks, email/SMS             |
| **Billing Service**      | 8880      | 8881*     | Subscriptions, usage metering (Stripe)  |

*Billing requires HTTP port 8881 for Stripe webhooks (Stripe does not support gRPC).

### High-Level Request Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER BROWSER                                   │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (React SPA) :8800                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │  Auth    │  │ Strategy │  │ Backtest │  │ Trading  │  │Portfolio │       │
│  │  Pages   │  │  Builder │  │  Runner  │  │  Panel   │  │Dashboard │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
│                         Zustand + gRPC-Web Client                           │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │ gRPC-Web (HTTP/2 over HTTP/1.1)
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      API GATEWAY (Kong) :8000                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ JWT Verify  │  │ Rate Limit  │  │  gRPC-Web   │  │   Logging   │         │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘         │
└───────┬─────────────┬─────────────┬─────────────┬─────────────┬─────────────┘
        │             │             │             │             │
        ▼             ▼             ▼             ▼             ▼
   ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐
   │  Auth   │  │Strategy │  │Backtest │  │ Trading │  │Portfolio│  ...
   │ :8810   │  │ :8820   │  │ :8830   │  │ :8850   │  │ :8860   │
   └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘
        │             │             │             │             │
        └─────────────┴──────gRPC───┴─────────────┴─────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
   ┌─────────┐               ┌─────────────┐             ┌─────────┐
   │ Postgres│               │    Redis    │             │ Alpaca  │
   │   (RLS) │               │ Cache/Queue │             │   API   │
   └─────────┘               └─────────────┘             └─────────┘
```

### Service Communication Patterns

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          SYNCHRONOUS (gRPC)                                 │
│                                                                             │
│  Frontend ──► Gateway ──► Any Service  (via gRPC-Web)                       │
│  Service  ──► Service  (direct gRPC, internal calls)                        │
│                                                                             │
│  Examples:                                                                  │
│  • Auth validates JWT for all services                                      │
│  • Backtest fetches strategy config from Strategy Service                   │
│  • Trading checks portfolio limits from Portfolio Service                   │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                         ASYNCHRONOUS (Redis/Celery)                         │
│                                                                             │
│  ┌──────────┐     ┌───────────────┐     ┌──────────────┐                    │
│  │ Backtest │────►│ Redis Queue   │────►│ Celery Worker│                    │
│  │ Service  │     │ (Job Queue)   │     │ (Processing) │                    │
│  └──────────┘     └───────────────┘     └──────────────┘                    │
│                                                                             │
│  Examples:                                                                  │
│  • Backtest jobs run asynchronously                                         │
│  • Notifications sent via background tasks                                  │
│  • Usage metering aggregated periodically                                   │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                         REAL-TIME (WebSocket/SSE)                           │
│                                                                             │
│  ┌──────────┐     ┌───────────────┐     ┌──────────────┐                    │
│  │ Frontend │◄───►│ WS Gateway    │◄───►│ Market Data  │                    │
│  │          │     │               │     │ Trading Svc  │                    │
│  └──────────┘     └───────────────┘     └──────────────┘                    │
│                                                                             │
│  Examples:                                                                  │
│  • Live price updates from Market Data                                      │
│  • Order execution status from Trading                                      │
│  • Backtest progress updates                                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## GKE Deployment Architecture

```
                    ┌─────────────────────────────────────────┐
                    │           GCP Cloud CDN                 │
                    └───────────────────┬─────────────────────┘
                                        │
                    ┌───────────────────▼─────────────────────┐
                    │        GCP Load Balancer (L7)           │
                    │     (SSL termination, path routing)     │
                    └───────────────────┬─────────────────────┘
                                        │
          ┌─────────────────────────────┼─────────────────────────────┐
          │                             │                             │
          ▼                             ▼                             ▼
    ┌───────────┐               ┌───────────┐                 ┌───────────┐
    │ /         │               │ /api/*    │                 │ /ws/*     │
    │ Frontend  │               │ API GW    │                 │ WebSocket │
    │ (nginx)   │               │ (Kong)    │                 │ Gateway   │
    └───────────┘               └─────┬─────┘                 └───────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
              ┌──────────┐     ┌──────────┐     ┌──────────┐
              │ Auth     │     │ Strategy │     │ Trading  │ ...
              │ Service  │     │ Service  │     │ Service  │
              └──────────┘     └──────────┘     └──────────┘
                    │                 │                 │
          ┌─────────┴─────────────────┴─────────────────┴─────────┐
          │                                                       │
          ▼                                                       ▼
    ┌───────────────┐                                    ┌───────────────┐
    │  Cloud SQL    │                                    │  Memorystore  │
    │  (PostgreSQL) │                                    │  (Redis)      │
    └───────────────┘                                    └───────────────┘
```

---

## Technology Stack

### Backend

- **Framework:** FastAPI (async, fast, OpenAPI docs)
- **Task Queue:** Celery + Redis (backtesting jobs)
- **Database:** PostgreSQL 16 (primary), TimescaleDB (market data)
- **Cache/Queue:** Redis 7 (sessions, rate limiting, pub/sub)
- **Message Broker:** Redis Streams (real-time), Kafka (future scale)

### Frontend

- **Framework:** React 18 + Vite
- **Styling:** Tailwind CSS
- **State:** Zustand
- **Data Fetching:** TanStack Query
- **Charts:** Lightweight Charts (TradingView) or Recharts
- **Strategy Builder:** Custom Canvas (node-based visual editor)

### Infrastructure

- **Cloud Provider:** Google Cloud Platform (GCP)
- **Container Orchestration:** Docker Compose (dev), GKE Autopilot (prod)
- **CI/CD:** GitHub Actions + Cloud Build
- **API Gateway:** Traefik (dev) → Kong or GCP API Gateway (prod)
- **Database:** Cloud SQL (PostgreSQL), Memorystore (Redis)
- **Storage:** Cloud Storage (backtest results, static assets)
- **CDN:** Cloud CDN (frontend assets)
- **Observability:** Cloud Monitoring + Cloud Logging
- **Secrets:** Secret Manager

---

## Multi-Tenancy

- Row-level security (RLS) in PostgreSQL
- All tables include `tenant_id` column
- JWT contains `tenant_id` claim
- Middleware extracts and propagates tenant context

### Multi-Tenant Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              JWT TOKEN                                      │
│  {                                                                          │
│    "sub": "user-uuid",                                                      │
│    "tenant_id": "tenant-uuid",  ◄─── Extracted by middleware                │
│    "roles": ["admin"],                                                      │
│    "exp": 1234567890                                                        │
│  }                                                                          │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TENANT MIDDLEWARE                                   │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  1. Extract tenant_id from JWT                                         │ │
│  │  2. Set TenantContext for request                                      │ │
│  │  3. All database queries automatically filtered                        │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         POSTGRESQL (Row-Level Security)                     │
│                                                                             │
│  SELECT * FROM strategies WHERE tenant_id = 'tenant-uuid';                  │
│                                      ▲                                      │
│                                      │                                      │
│                          Automatically injected                             │
│                                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │  Tenant A   │  │  Tenant B   │  │  Tenant C   │  │  Tenant D   │         │
│  │  strategies │  │  strategies │  │  strategies │  │  strategies │         │
│  │  users      │  │  users      │  │  users      │  │  users      │         │
│  │  orders     │  │  orders     │  │  orders     │  │  orders     │         │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘         │
│              Complete data isolation between tenants                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Built-in Strategies

1. **MA Crossover** - Moving average crossover (fast/slow EMA)
2. **RSI Mean Reversion** - Buy oversold, sell overbought
3. **MACD** - MACD line crossover with signal line
4. **Bollinger Bands Bounce** - Mean reversion at band touches
5. **Donchian Channel Breakout** - Breakout above/below channel
6. **Dual Momentum** - Relative + absolute momentum
7. **Z-Score Mean Reversion** - Statistical mean reversion
8. **VWAP** - Volume-weighted average price strategies
9. **Pairs Trading** - Statistical arbitrage between correlated assets
10. **Stop Loss / Take Profit** - Risk management overlays

---

## User Journey Flows

### 1. Strategy Creation Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ USER: "I want to create an RSI mean reversion strategy for AAPL"            │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND: Strategy Builder                          │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  1. Select template: "RSI Mean Reversion"                              │ │
│  │  2. Configure parameters:                                              │ │
│  │     • Symbol: AAPL          • RSI Period: 14                           │ │
│  │     • Oversold: 30          • Overbought: 70                           │ │
│  │  3. Click "Save Strategy"                                              │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │ POST /api/strategies
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STRATEGY SERVICE :8820 (gRPC)                       │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  1. Validate strategy configuration                                    │ │
│  │  2. Store in PostgreSQL (tenant-scoped)                                │ │
│  │  3. Create initial version (v1)                                        │ │
│  │  4. Return strategy_id                                                 │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ RESULT: Strategy saved with ID abc-123, ready for backtesting               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2. Backtesting Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ USER: "Run backtest on my RSI strategy for last 6 months"                   │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND: Backtest Runner                           │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  1. Select strategy: "RSI Mean Reversion - AAPL"                       │ │
│  │  2. Date range: 2024-01-01 to 2024-06-30                               │ │
│  │  3. Initial capital: $10,000                                           │ │
│  │  4. Click "Run Backtest"                                               │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │ POST /api/backtests
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BACKTEST SERVICE :8830 (gRPC)                       │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  1. Queue backtest job in Redis                                        │ │
│  │  2. Return job_id immediately                                          │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    ▼                                   ▼
┌───────────────────────────────────┐   ┌───────────────────────────────────┐
│       CELERY WORKER               │   │   MARKET DATA SERVICE :8840       │
│  ┌─────────────────────────────┐  │   │  ┌─────────────────────────────┐  │
│  │ 1. Pick up job from queue   │  │   │  │ Fetch historical OHLCV data │  │
│  │ 2. Request historical data ─┼──┼──►│  │ from Alpaca API or cache    │  │
│  │ 3. Run simulation engine    │  │   │  └─────────────────────────────┘  │
│  │ 4. Calculate metrics        │  │   └───────────────────────────────────┘
│  │ 5. Store results in DB      │  │
│  │ 6. Publish completion event │  │
│  └─────────────────────────────┘  │
└───────────────────────────────────┘
                    │
                    │ WebSocket: backtest.completed
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND: Results Dashboard                         │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  Results:                                                              │ │
│  │  • Total Return: +12.5%    • Sharpe Ratio: 1.8                         │ │
│  │  • Max Drawdown: -8.2%     • Win Rate: 62%                             │ │
│  │  • Total Trades: 47        • Profit Factor: 1.6                        │ │
│  │  [Equity Curve Chart]      [Trade Distribution]                        │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3. Live Trading Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ USER: "Deploy my RSI strategy for live paper trading"                       │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND: Trading Panel                             │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  1. Select strategy: "RSI Mean Reversion - AAPL"                       │ │
│  │  2. Mode: Paper Trading (toggle)                                       │ │
│  │  3. Capital allocation: $5,000                                         │ │
│  │  4. Risk limits: Max 10% per trade                                     │ │
│  │  5. Click "Start Trading"                                              │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │ POST /api/trading/sessions
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TRADING SERVICE :8850 (gRPC)                        │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  1. Validate Alpaca credentials (from Auth Service)                    │ │
│  │  2. Create trading session                                             │ │
│  │  3. Subscribe to market data                                           │ │
│  │  4. Start strategy execution loop                                      │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │
                ┌─────────────────────┴─────────────────────┐
                ▼                                           ▼
┌───────────────────────────────────┐       ┌───────────────────────────────────┐
│   MARKET DATA SERVICE :8840       │       │         ALPACA API                │
│  ┌─────────────────────────────┐  │       │  ┌─────────────────────────────┐  │
│  │ Stream real-time quotes     │  │       │  │ Execute orders              │  │
│  │ via WebSocket               │  │       │  │ Paper: paper-api.alpaca.com │  │
│  └─────────────────────────────┘  │       │  │ Live: api.alpaca.com        │  │
└───────────────────────────────────┘       │  └─────────────────────────────┘  │
                │                           └───────────────────────────────────┘
                │ Real-time price: AAPL @ $185.50
                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TRADING SERVICE: Strategy Engine                         │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  RSI(14) = 28 < 30 (oversold threshold)                                │ │
│  │  ► SIGNAL: BUY                                                         │ │
│  │  ► Risk check: Position size OK                                        │ │
│  │  ► Submit order to Alpaca                                              │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
┌─────────────────────────┐ ┌─────────────────────────┐ ┌─────────────────────────┐
│  PORTFOLIO SVC :8860    │ │  NOTIFICATION SVC :8870 │ │  FRONTEND (WebSocket)   │
│ ┌─────────────────────┐ │ │ ┌─────────────────────┐ │ │ ┌─────────────────────┐ │
│ │ Update positions    │ │ │ │ Send alert:         │ │ │ │ Live updates:       │ │
│ │ Record transaction  │ │ │ │ "BUY AAPL @ $185.50"│ │ │ │ • Order executed    │ │
│ │ Calculate P&L       │ │ │ │ via email/SMS/push  │ │ │ │ • Position changed  │ │
│ └─────────────────────┘ │ │ └─────────────────────┘ │ │ │ • P&L updated       │ │
└─────────────────────────┘ └─────────────────────────┘ │ └─────────────────────┘ │
                                                        └─────────────────────────┘
```

---

## Database Schema

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          PostgreSQL + TimescaleDB                           │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│     TENANTS     │     │      USERS      │     │   API_KEYS      │
├─────────────────┤     ├─────────────────┤     ├─────────────────┤
│ id (PK)         │◄────│ tenant_id (FK)  │     │ tenant_id (FK)  │
│ name            │     │ id (PK)         │◄────│ user_id (FK)    │
│ plan_id         │     │ email           │     │ id (PK)         │
│ settings (JSON) │     │ password_hash   │     │ key_hash        │
│ created_at      │     │ role            │     │ scopes (JSON)   │
└─────────────────┘     │ is_active       │     │ last_used_at    │
                        └─────────────────┘     └─────────────────┘
                                │
                                │
┌─────────────────┐     ┌───────▼─────────┐     ┌─────────────────┐
│   STRATEGIES    │     │ALPACA_CREDENTIALS│    │STRATEGY_TEMPLATES│
├─────────────────┤     ├─────────────────┤     ├─────────────────┤
│ tenant_id (FK)  │     │ tenant_id (FK)  │     │ id (PK)         │
│ id (PK)         │     │ user_id (FK)    │     │ name            │
│ name            │     │ paper_key_enc   │     │ description     │
│ type            │     │ paper_secret_enc│     │ config (JSON)   │
│ config (JSON)   │     │ live_key_enc    │     │ is_builtin      │
│ is_active       │     │ live_secret_enc │     └─────────────────┘
│ version         │     └─────────────────┘
└────────┬────────┘
         │
         │
┌────────▼────────┐     ┌─────────────────┐     ┌─────────────────┐
│   BACKTESTS     │     │TRADING_SESSIONS │     │    ORDERS       │
├─────────────────┤     ├─────────────────┤     ├─────────────────┤
│ tenant_id (FK)  │     │ tenant_id (FK)  │     │ tenant_id (FK)  │
│ strategy_id(FK) │     │ strategy_id(FK) │     │ session_id (FK) │
│ id (PK)         │     │ id (PK)         │     │ id (PK)         │
│ start_date      │     │ mode (paper/live)│    │ symbol          │
│ end_date        │     │ status          │     │ side (buy/sell) │
│ initial_capital │     │ capital         │     │ quantity        │
│ status          │     │ started_at      │     │ price           │
│ results (JSON)  │     │ stopped_at      │     │ status          │
└─────────────────┘     └─────────────────┘     │ alpaca_order_id │
                                                └─────────────────┘

┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   POSITIONS     │     │  TRANSACTIONS   │     │     ALERTS      │
├─────────────────┤     ├─────────────────┤     ├─────────────────┤
│ tenant_id (FK)  │     │ tenant_id (FK)  │     │ tenant_id (FK)  │
│ session_id (FK) │     │ id (PK)         │     │ strategy_id(FK) │
│ symbol          │     │ type            │     │ id (PK)         │
│ quantity        │     │ amount          │     │ condition       │
│ avg_entry_price │     │ symbol          │     │ is_triggered    │
│ current_price   │     │ quantity        │     │ triggered_at    │
│ unrealized_pnl  │     │ price           │     │ channel         │
└─────────────────┘     │ timestamp       │     └─────────────────┘
                        └─────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                      TIMESCALEDB (Market Data - NOT tenant-scoped)          │
├─────────────────────────────────────────────────────────────────────────────┤
│  BARS (hypertable)           │  QUOTES                  │  TRADES           │
│  ───────────────────         │  ──────────────────      │  ──────────────   │
│  symbol                      │  symbol                  │  symbol           │
│  timestamp                   │  timestamp               │  timestamp        │
│  open, high, low, close      │  bid_price, ask_price    │  price            │
│  volume                      │  bid_size, ask_size      │  size             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Security

- JWT-based authentication with refresh tokens
- Password hashing with bcrypt
- Alpaca API keys encrypted at rest (AES-256)
- Row-level security in PostgreSQL
- Rate limiting at API Gateway
- CORS configured for frontend origin only
- HTTPS everywhere (TLS 1.3)
- Secret Manager for sensitive configs

---

## Local Development

```bash
# Start all services with hot-reload
make dev

# Run tests
make test

# Access services
# Frontend: http://localhost:8800
# API Gateway: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

---

## Deployment

### Staging

Automatic deployment on merge to `main` branch via GitHub Actions.

### Production

Manual approval required. Deploy via:

```bash
make deploy-prod
```
