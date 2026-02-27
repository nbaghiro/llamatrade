# LlamaTrade - Architecture Documentation

## Overview

LlamaTrade is a SaaS algorithmic trading platform enabling users to create custom strategies or use pre-built ones, backtest against historical data, and execute live trades via Alpaca Markets API.

**Architecture:** Microservices (Python FastAPI backend + React/TypeScript/Tailwind frontend)

---

## System Architecture

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

### GKE Deployment Architecture

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

## Services

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

### Service Communication Patterns

**Synchronous (gRPC):**
- Frontend → Gateway → Any Service (via gRPC-Web)
- Service → Service (direct gRPC, internal calls)
- Examples: Auth validates JWT, Backtest fetches strategy config, Trading checks portfolio limits

**Asynchronous (Redis/Celery):**
- Backtest jobs run via Celery workers
- Notifications sent via background tasks
- Usage metering aggregated periodically

**Real-Time (WebSocket/SSE):**
- Live price updates from Market Data
- Order execution status from Trading
- Backtest progress updates

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

**Data Flow:**
1. JWT token contains `tenant_id` claim
2. Tenant middleware extracts and sets TenantContext for request
3. All database queries automatically filtered by tenant_id
4. Complete data isolation between tenants

---

## User Journey Flows

### 1. Strategy Creation

1. User opens Strategy Builder
2. Selects template (e.g., "RSI Mean Reversion") or starts blank
3. Configures parameters (symbol, indicators, thresholds)
4. Clicks "Save Strategy"
5. Strategy Service validates config, stores in PostgreSQL (tenant-scoped), creates version
6. Returns strategy_id

### 2. Backtesting

1. User selects strategy and date range
2. Frontend submits backtest request to Backtest Service
3. Backtest Service queues job in Redis, returns job_id
4. Celery Worker picks up job, fetches historical data from Market Data Service
5. Worker runs simulation, calculates metrics, stores results
6. Frontend receives completion via WebSocket, displays results dashboard

### 3. Live Trading

1. User selects strategy and trading mode (Paper/Live)
2. Frontend submits session request to Trading Service
3. Trading Service validates Alpaca credentials, creates session
4. Service subscribes to real-time market data, starts strategy execution loop
5. On signals: validates risk, submits orders to Alpaca
6. Portfolio Service updates positions, Notification Service sends alerts
7. Frontend receives live updates via WebSocket

---

## Database Schema

**Core Tables (tenant-scoped):**

| Table               | Key Columns                                               |
| ------------------- | --------------------------------------------------------- |
| `tenants`           | id, name, plan_id, settings                               |
| `users`             | tenant_id, id, email, password_hash, role                 |
| `api_keys`          | tenant_id, user_id, key_hash, scopes                      |
| `alpaca_credentials`| tenant_id, user_id, paper/live keys (encrypted)           |
| `strategies`        | tenant_id, id, name, type, config, version                |
| `strategy_templates`| id, name, description, config, is_builtin                 |
| `backtests`         | tenant_id, strategy_id, dates, capital, status, results   |
| `trading_sessions`  | tenant_id, strategy_id, mode, status, capital             |
| `orders`            | tenant_id, session_id, symbol, side, qty, status          |
| `positions`         | tenant_id, session_id, symbol, qty, entry_price, pnl      |
| `transactions`      | tenant_id, type, amount, symbol, qty, price               |
| `alerts`            | tenant_id, strategy_id, condition, channel, triggered_at  |

**TimescaleDB (Market Data - NOT tenant-scoped):**

| Hypertable | Columns                              |
| ---------- | ------------------------------------ |
| `bars`     | symbol, timestamp, OHLCV             |
| `quotes`   | symbol, timestamp, bid/ask price/size|
| `trades`   | symbol, timestamp, price, size       |

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
