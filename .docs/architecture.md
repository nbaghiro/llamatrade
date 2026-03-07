# LlamaTrade Architecture

Complete architecture documentation for LlamaTrade, covering system design, data model, service communication, security, testing, and deployment.

---

## Table of Contents

1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Services](#services)
4. [Technology Stack](#technology-stack)
5. [Getting Started](#getting-started)
6. [Multi-Tenancy](#multi-tenancy)
7. [Data Model](#data-model)
8. [Service Communication (gRPC/Connect)](#service-communication)
9. [Event Sourcing](#event-sourcing)
10. [Security](#security)
11. [Testing](#testing)
12. [Deployment & Operations](#deployment--operations)

---

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
│                    Zustand + Connect Protocol Client                        │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │ Connect Protocol (HTTP/1.1 + JSON)
                                  │ Direct to Services (no gateway)
                                  ▼
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

**Key Points:**

- Frontend connects **directly** to each service via Connect protocol
- Each service validates JWT tokens via its own auth middleware
- No API gateway required for local development
- Services communicate with each other via internal gRPC

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
    ┌───────────┐          ┌────────────────────────┐         ┌───────────┐
    │ /         │          │ /api/v1/auth/*    →    │         │ /ws/*     │
    │ Frontend  │          │ /api/v1/strategy/* →   │         │ Connect   │
    │ (nginx)   │          │ /api/v1/trading/*  →   │         │ Streams   │
    └───────────┘          │ (path-based routing)   │         └───────────┘
                           └────────────────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
                    ▼                   ▼                   ▼
              ┌──────────┐       ┌──────────┐       ┌──────────┐
              │ Auth     │       │ Strategy │       │ Trading  │ ...
              │ Service  │       │ Service  │       │ Service  │
              └──────────┘       └──────────┘       └──────────┘
                    │                   │                   │
          ┌─────────┴───────────────────┴───────────────────┴─────────┐
          │                                                           │
          ▼                                                           ▼
    ┌───────────────┐                                        ┌───────────────┐
    │  Cloud SQL    │                                        │  Memorystore  │
    │  (PostgreSQL) │                                        │  (Redis)      │
    └───────────────┘                                        └───────────────┘
```

---

## Services

### Core Services

| Service                  | Port | Responsibility                           |
| ------------------------ | ---- | ---------------------------------------- |
| **Frontend (Web)**       | 8800 | React SPA served via nginx, CDN-backed   |
| **Auth Service**         | 8810 | Users, tenants, API keys, JWT validation |
| **Strategy Service**     | 8820 | Strategy CRUD, versioning, templates     |
| **Backtest Service**     | 8830 | Historical simulation execution          |
| **Market Data Service**  | 8840 | Real-time + historical data from Alpaca  |
| **Trading Service**      | 8850 | Live order execution, risk enforcement   |
| **Portfolio Service**    | 8860 | Positions, P&L, performance metrics      |
| **Notification Service** | 8870 | Alerts, webhooks, email/SMS              |
| **Billing Service**      | 8880 | Subscriptions, usage metering (Stripe)   |

\*Billing also exposes HTTP port 8881 for Stripe webhooks.

### Service Communication Patterns

**Frontend → Services (Connect Protocol):**

- Direct HTTP/1.1 + JSON communication via Connect protocol
- Each service validates JWT via auth middleware
- Auth interceptor in frontend adds Bearer token to requests

**Service → Service (gRPC):**

- Internal gRPC calls between services
- Examples: Backtest fetches strategy config, Trading checks portfolio limits

**Asynchronous (Redis/Celery):**

- Backtest jobs run via Celery workers
- Notifications sent via background tasks
- Usage metering aggregated periodically

**Real-Time (Connect Streams):**

- Live price updates from Market Data
- Order execution status from Trading
- Backtest progress updates

### Built-in Strategies

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
- **API Client:** Connect Protocol (@connectrpc/connect)
- **Charts:** Lightweight Charts (TradingView) or Recharts
- **Strategy Builder:** Custom Canvas (node-based visual editor)

### Infrastructure

- **Cloud Provider:** Google Cloud Platform (GCP)
- **Container Orchestration:** Docker Compose (dev), GKE Autopilot (prod)
- **CI/CD:** GitHub Actions + Cloud Build
- **Load Balancer:** GCP L7 Load Balancer (SSL termination, path routing)
- **Database:** Cloud SQL (PostgreSQL), Memorystore (Redis)
- **Storage:** Cloud Storage (backtest results, static assets)
- **CDN:** Cloud CDN (frontend assets)
- **Observability:** Cloud Monitoring + Cloud Logging
- **Secrets:** Secret Manager

---

## Getting Started

### Prerequisites

| Tool               | Version         | Purpose              |
| ------------------ | --------------- | -------------------- |
| **Python**         | 3.12+           | Backend services     |
| **Node.js**        | 20+             | Frontend build tools |
| **Docker**         | Latest          | Container runtime    |
| **Docker Compose** | 2.x             | Local orchestration  |
| **PostgreSQL**     | 16 (via Docker) | Primary database     |
| **Redis**          | 7 (via Docker)  | Cache and queues     |

**Optional but Recommended:**

- **uv** - Fast Python package manager
- **Make** - Run project commands
- **direnv** - Auto-load environment variables

### Initial Setup

```bash
# 1. Clone the repository
git clone https://github.com/your-org/llamatrade.git
cd llamatrade

# 2. Run setup script
./scripts/setup.sh

# 3. Configure environment
cp .env.example .env
cp apps/web/.env.example apps/web/.env
```

**Required Environment Variables:**

```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/llamatrade

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT
JWT_SECRET=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=30

# Encryption (for Alpaca credentials)
ENCRYPTION_KEY=your-32-byte-encryption-key

# Alpaca (optional for testing)
ALPACA_API_KEY=your-paper-api-key
ALPACA_API_SECRET=your-paper-api-secret
```

### Running Locally

**Option 1: Docker Compose (Recommended)**

```bash
make dev
```

Starts all backend services, PostgreSQL, Redis, and frontend dev server.

**Option 2: Hybrid (Infrastructure in Docker, Services Local)**

```bash
# Start only database and Redis
make dev-infra

# Run all services locally
make dev-local

# Or individual services
cd services/auth && uvicorn src.main:app --reload --port 8810
```

### Project Structure

```
llamatrade/
├── apps/
│   └── web/                    # React frontend
│       ├── src/
│       │   ├── components/     # Reusable UI components
│       │   ├── pages/          # Route-level components
│       │   ├── services/       # API clients
│       │   ├── store/          # Zustand state
│       │   └── types/          # TypeScript types
│       └── package.json
│
├── services/                   # Backend microservices
│   ├── auth/                   # Authentication & users
│   ├── strategy/               # Strategy CRUD & templates
│   ├── backtest/               # Backtesting engine
│   ├── market-data/            # Real-time & historical data
│   ├── trading/                # Live order execution
│   ├── portfolio/              # Positions & P&L
│   ├── notification/           # Alerts & webhooks
│   └── billing/                # Subscriptions (Stripe)
│
├── libs/                       # Shared libraries
│   ├── common/                 # Middleware, utilities
│   ├── db/                     # SQLAlchemy models
│   ├── dsl/                    # Strategy DSL parser/compiler
│   ├── grpc/                   # gRPC clients & generated code
│   └── proto/                  # Protocol buffer definitions
│
├── infrastructure/             # Deployment configs
│   ├── docker/                 # Docker Compose files
│   ├── k8s/                    # Kubernetes manifests
│   └── terraform/              # GCP infrastructure
│
└── tests/                      # Integration tests
    └── integration/
```

### Common Commands

```bash
# Development
make dev                    # Docker Compose (all services)
make dev-infra              # Start only Postgres + Redis
make dev-local              # Run all services locally

# Proto Generation
make proto                  # Generate Python + TypeScript from protos
make proto-lint             # Lint proto files

# Testing
make test                   # Full CI test suite
make test-auth              # Single service tests
make lint                   # All linting

# Coverage
cd services/auth && pytest --cov=src --cov-report=term-missing
```

---

## Multi-Tenancy

All operations are tenant-scoped with complete data isolation:

1. **JWT token** contains `tenant_id` claim
2. **Middleware** extracts tenant context: `ctx = Depends(require_auth)`
3. **All database queries** filter by `ctx.tenant_id`
4. **Service-to-service calls** propagate tenant via `X-Tenant-ID` header

### Database Layer (RLS)

All tenant-scoped tables include `tenant_id`:

```sql
-- Every query is filtered by tenant
SELECT * FROM strategies WHERE tenant_id = 'tenant-uuid' AND id = 'strategy-uuid';

-- Row-Level Security Policy
ALTER TABLE strategies ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON strategies
    FOR ALL
    USING (tenant_id = current_setting('app.tenant_id')::uuid);
```

### Application Layer

```python
async def require_auth(request: Request) -> TenantContext:
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(401, "Missing authentication")

    ctx = await validate_token(token)
    return ctx

# All database queries MUST use tenant_id
strategies = await db.query(Strategy).filter_by(tenant_id=ctx.tenant_id).all()
```

**Never allow cross-tenant data access. When in doubt, add tenant filtering.**

---

## Data Model

PostgreSQL database schema using SQLAlchemy 2.0 async ORM. All tenant-scoped models inherit from `TenantMixin` which adds `tenant_id` with a foreign key to `tenants.id`.

### Complete Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                    TENANT BOUNDARY                                      │
│  All models below are scoped to a tenant (except Bars which are shared)                 │
└─────────────────────────────────────────────────────────────────────────────────────────┘

                                    ┌──────────────────┐
                                    │     TENANT       │
                                    ├──────────────────┤
                                    │ id (PK)          │
                                    │ name             │
                                    │ slug (unique)    │
                                    │ is_active        │
                                    │ settings (JSONB) │
                                    └────────┬─────────┘
                                             │
           ┌─────────────────┬───────────────┼───────────────┬─────────────────┐
           │                 │               │               │                 │
           ▼                 ▼               ▼               ▼                 ▼
┌──────────────────┐ ┌──────────────┐ ┌─────────────┐ ┌─────────────┐ ┌──────────────────┐
│      USER        │ │   API_KEY    │ │  ALPACA_    │ │ SUBSCRIPTION│ │   AUDIT_LOG      │
├──────────────────┤ ├──────────────┤ │ CREDENTIALS │ ├─────────────┤ ├──────────────────┤
│ id (PK)          │ │ id (PK)      │ ├─────────────┤ │ tenant (1:1)│ │ id (PK)          │
│ tenant_id (FK)   │ │ tenant_id    │ │ id (PK)     │ │ plan        │ │ tenant_id (FK)   │
│ email            │ │ key_hash     │ │ tenant_id   │ │ status      │ │ action           │
│ password_hash    │ │ scopes       │ │ api_key_enc │ │ stripe_id   │ │ entity_type      │
│ role             │ │ expires_at   │ │ api_secret  │ └─────────────┘ │ entity_id        │
│ is_active        │ └──────────────┘ │ is_paper    │                 │ changes (JSONB)  │
│ is_verified      │                  └─────────────┘                 └──────────────────┘
└──────────────────┘


                              ┌──────────────────────────┐
                              │        STRATEGY          │
                              ├──────────────────────────┤
                              │ id (PK)                  │
                              │ tenant_id (FK)           │
                              │ name                     │
                              │ strategy_type (ENUM)     │◄─────── trend_following
                              │ status (ENUM)            │◄─────── mean_reversion
                              │ current_version          │◄─────── momentum
                              │ created_by (FK → User)   │◄─────── breakout, custom
                              └────────────┬─────────────┘
                                           │
              ┌────────────────────────────┼────────────────────────────┐
              │                            │                            │
              ▼                            ▼                            ▼
┌─────────────────────────┐  ┌─────────────────────────┐  ┌─────────────────────────┐
│    STRATEGY_VERSION     │  │    TRADING_SESSION      │  │       BACKTEST          │
├─────────────────────────┤  ├─────────────────────────┤  ├─────────────────────────┤
│ id (PK)                 │  │ id (PK)                 │  │ id (PK)                 │
│ strategy_id (FK)        │  │ tenant_id (FK)          │  │ tenant_id (FK)          │
│ version (INT)           │  │ strategy_id (FK)        │  │ strategy_id (FK)        │
│ config (JSONB)          │  │ mode: paper | live      │  │ start_date              │
│ sexpr (TEXT)            │  │ status                  │  │ end_date                │
│ created_at              │  │ symbols (JSONB)         │  │ initial_capital         │
└─────────────────────────┘  └────────────┬────────────┘  │ status                  │
                                          │               └────────────┬────────────┘
 Versions are immutable snapshots.        │                            │
 config = visual builder state            │                            │
 sexpr = compiled S-expression            ├──────────────┐             │ 1:1
                                          │              │             ▼
                                          ▼              ▼  ┌─────────────────────────┐
                              ┌───────────────────┐  ┌───────────────────┐            │
                              │      ORDER        │  │     POSITION      │            │
                              ├───────────────────┤  ├───────────────────┤            │
                              │ id (PK)           │  │ id (PK)           │            │
                              │ tenant_id (FK)    │  │ tenant_id (FK)    │            │
                              │ session_id (FK)   │  │ session_id (FK)   │            │
                              │ symbol            │  │ symbol            │            │
                              │ side: buy | sell  │  │ side: long | short│            │
                              │ order_type        │  │ qty               │            │
                              │ qty               │  │ avg_entry_price   │            │
                              │ status            │  │ unrealized_pl     │            │
                              │ filled_qty        │  └───────────────────┘            │
                              │ filled_avg_price  │                                   │
                              └───────────────────┘                                   │
                                                                                      │
                                                          ┌───────────────────────────┘
                                                          ▼
                                            ┌─────────────────────────┐
                                            │    BACKTEST_RESULT      │
                                            ├─────────────────────────┤
                                            │ backtest_id (FK, unique)│
                                            │ total_return            │
                                            │ sharpe_ratio            │
                                            │ max_drawdown            │
                                            │ total_trades            │
                                            │ win_rate                │
                                            │ equity_curve (JSONB)    │
                                            └─────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              SHARED DATA (No Tenant Scope)                              │
└─────────────────────────────────────────────────────────────────────────────────────────┘

                              ┌────────────────────────┐
                              │    BAR (TimescaleDB)   │
                              ├────────────────────────┤
                              │ symbol         ─┐      │
                              │ timestamp       ├─ PK  │  ◄── Hypertable partitioned
                              │ timeframe      ─┘      │      by timestamp (1 week)
                              │ open                   │
                              │ high                   │  Timeframes:
                              │ low                    │  • 1Min, 5Min, 15Min
                              │ close                  │  • 1Hour, 4Hour
                              │ volume                 │  • 1Day
                              └────────────────────────┘
```

### Model Details

**Auth Domain**

```
TENANT                           USER                            ALPACA_CREDENTIALS
─────────────────────────────    ─────────────────────────────   ─────────────────────────────
The root entity for multi-       Users belong to a tenant and    Encrypted broker credentials.
tenancy. Every other model       have roles for authorization.   Supports paper and live
(except Bars) belongs to                                         trading modes.
exactly one tenant.              Roles: owner, admin, user,
                                 viewer                          Uses AES-256-GCM encryption
Settings stored as JSONB for                                     for api_key and api_secret.
flexible configuration.          Password: bcrypt hashed
```

**Strategy Domain**

```
STRATEGY                         STRATEGY_VERSION
─────────────────────────────    ─────────────────────────────
The main strategy entity.        Immutable snapshots of a
                                 strategy at a point in time.
Types:
• trend_following               Contains:
• mean_reversion                • config: Visual builder JSON
• momentum                      • sexpr: Compiled S-expression
• breakout
• custom                        Versions are never modified -
                                new version created on each save.
Status lifecycle:
  draft → active → paused
            ↓
         archived
```

**Trading Domain**

```
TRADING_SESSION                  ORDER                           POSITION
─────────────────────────────    ─────────────────────────────   ─────────────────────────────
A live or paper trading run      Orders submitted through        Current holdings in a
of a strategy.                   a trading session.              trading session.

Modes: paper, live               Side: buy, sell                 Side: long, short
                                 Types: market, limit,
Status: starting, running,       stop, stop_limit                Tracks:
stopped, error                                                   • Entry price (avg)
                                 Status: pending, accepted,      • Current quantity
Symbols as JSONB array           filled, partially_filled,       • Unrealized P&L
for multi-asset strategies.      cancelled, rejected
```

**Backtest Domain**

```
BACKTEST                         BACKTEST_RESULT
─────────────────────────────    ─────────────────────────────
Historical simulation run.       Performance metrics (1:1).

Parameters:                      Metrics:
• Date range                     • total_return
• Initial capital                • sharpe_ratio
• Strategy version               • max_drawdown
                                 • win_rate
Status: pending, running,        • total_trades
completed, failed
                                 equity_curve: JSONB time series
                                 for charting performance
```

### Key Relationships

```
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│                            RELATIONSHIP SUMMARY                                            │
├────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                            │
│  Tenant ──┬── 1:N ──► Users                                                                │
│           ├── 1:N ──► API Keys                                                             │
│           ├── 1:N ──► Alpaca Credentials                                                   │
│           ├── 1:1 ──► Subscription                                                         │
│           ├── 1:N ──► Strategies ────┬── 1:N ──► Strategy Versions                         │
│           │                          ├── 1:N ──► Trading Sessions ──┬── 1:N ──► Orders     │
│           │                          │                              └── 1:N ──► Positions  │
│           │                          └── 1:N ──► Backtests ────────── 1:1 ──► Results      │
│           └── 1:N ──► Audit Logs                                                           │
│                                                                                            │
│  Bars (shared across all tenants, no tenant_id)                                            │
│                                                                                            │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow Example

```
User creates strategy in visual builder
              │
              ▼
    ┌─────────────────┐
    │    STRATEGY     │  name: "MA Crossover"
    │                 │  type: trend_following
    │                 │  status: draft
    └────────┬────────┘
             │
             ▼ save
    ┌─────────────────┐
    │ STRATEGY_VERSION│  version: 1
    │                 │  config: { blocks: [...] }
    │                 │  sexpr: "(strategy ...)"
    └────────┬────────┘
             │
    ┌────────┴────────┐
    │                 │
    ▼ backtest        ▼ deploy
┌───────────┐    ┌───────────────┐
│ BACKTEST  │    │TRADING_SESSION│  mode: paper
│           │    │               │
└─────┬─────┘    └───────┬───────┘
      │                  │
      ▼                  ├─────────────────┐
┌───────────┐            │                 │
│  RESULT   │            ▼                 ▼
│           │       ┌─────────┐       ┌──────────┐
│ sharpe    │       │  ORDER  │       │ POSITION │
│ drawdown  │       │         │       │          │
└───────────┘       └─────────┘       └──────────┘
```

### Migrations

```bash
# Create migration
cd services/auth
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

---

## Service Communication

LlamaTrade uses **Protocol Buffers** (protobuf) for service contracts:

- **Connect Protocol**: Frontend (browser) to backend services over HTTP/1.1 with JSON
- **gRPC**: Service-to-service communication over HTTP/2 with binary protobuf

**Proto definitions:** `libs/proto/llamatrade_proto/protos/`
**Generated Python code:** `libs/proto/llamatrade_proto/generated/`
**Generated TypeScript code:** `apps/web/src/generated/proto/`

### Enum Conventions (Proto as Source of Truth)

All enums used across the system are defined in proto files and generated for both Python and TypeScript. This ensures type safety and consistency across frontend and backend.

**Pattern:**

```
Proto Definition (source of truth)
        │
        ├──► Python: Integer constants + conversion helpers
        │    - ORDER_SIDE_BUY = 1
        │    - order_side_to_str(side: int) -> str
        │
        └──► TypeScript: Numeric enums
             - enum OrderSide { BUY = 1, SELL = 2 }
```

**Python Usage:**

```python
# Import proto-generated constants (single source of truth)
from llamatrade_proto.generated import (
    ORDER_SIDE_BUY,
    ORDER_SIDE_SELL,
    ORDER_STATUS_FILLED,
)

# Import conversion helpers for external APIs (e.g., Alpaca)
from src.models import (
    order_side_to_str,    # int → "buy"/"sell"
    order_status_to_str,  # int → "filled"/"cancelled"/etc.
)

# Use integer constants for comparisons and storage
if order.side == ORDER_SIDE_BUY:
    # ...

# Use conversion helpers for external API calls
await alpaca.submit_order(
    side=order_side_to_str(order.side),  # "buy" or "sell"
)
```

**TypeScript Usage:**

```typescript
// Import enums from proto-generated code
import { OrderSide, OrderStatus, StrategyStatus } from '../generated/proto/trading_pb';

// Use numeric enum values directly
if (order.side === OrderSide.BUY) {
  // ...
}

// Display helpers for UI
function getOrderSideLabel(side: OrderSide): string {
  return side === OrderSide.BUY ? 'Buy' : 'Sell';
}
```

**Database Storage:**

- Enums are stored as integers in PostgreSQL (SQLAlchemy `Integer` columns)
- No string-based enum columns — integers are more compact and consistent with proto

**Key Rules:**

1. **Proto is source of truth** — never define duplicate enums in Python/TypeScript
2. **Use integer values internally** — comparisons, storage, and cross-service calls
3. **Convert to strings only at boundaries** — external APIs (Alpaca), user display
4. **Deprecated StrEnums** — legacy StrEnum classes are kept for backward compatibility but marked DEPRECATED

### Request Flow Example

```
1. FRONTEND          LoginPage.tsx → authClient.login({ email, password })
        │
        ▼
2. CONNECT CLIENT    Serializes to JSON, adds headers
        │
        ▼
3. HTTP REQUEST      POST http://localhost:8810/llamatrade.v1.AuthService/Login
        │
        ▼
4. CONNECT ASGI      Routes to servicer method
        │
        ▼
5. SERVICER          AuthServicer.login() → business logic
        │
        ▼
6. DATABASE          SELECT * FROM users WHERE email = ?
```

### Debugging with curl

```bash
# Login request
curl -X POST http://localhost:8810/llamatrade.v1.AuthService/Login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secret"}'

# Protected endpoint (requires token)
TOKEN=$(curl -s -X POST http://localhost:8810/llamatrade.v1.AuthService/Login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secret"}' \
  | jq -r '.accessToken')

curl -X POST http://localhost:8820/llamatrade.v1.StrategyService/ListStrategies \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{}'
```

### Service Definitions

**Auth Service (8810):**

- `Login`, `Register`, `RefreshToken` (public)
- `GetCurrentUser`, `ChangePassword` (protected)
- `ValidateToken`, `ValidateAPIKey` (internal)

**Strategy Service (8820):**

- `GetStrategy`, `ListStrategies`, `CreateStrategy`, `UpdateStrategy`, `DeleteStrategy`
- `CompileStrategy`, `ValidateStrategy`

**Backtest Service (8830):**

- `RunBacktest`, `GetBacktest`, `ListBacktests`, `CancelBacktest`
- `StreamBacktestProgress` (server-side streaming)

**Market Data Service (8840):**

- `GetHistoricalBars`, `GetMultiBars`, `GetSnapshot`
- `StreamBars`, `StreamQuotes`, `StreamTrades` (streaming)

**Trading Service (8850):**

- `SubmitOrder`, `GetOrder`, `ListOrders`, `CancelOrder`
- `GetPosition`, `ListPositions`, `ClosePosition`
- `StreamOrderUpdates`, `StreamPositionUpdates` (streaming)

**Portfolio Service (8860):**

- `GetPortfolio`, `GetPerformance`, `GetAssetAllocation`

**Billing Service (8880):**

- `GetSubscription`, `CreateSubscription`, `CancelSubscription`
- `CreateCheckoutSession`, `CreatePortalSession` (Stripe)

### Error Handling

| Code | Name                | Use Case                 |
| ---- | ------------------- | ------------------------ |
| 0    | `OK`                | Success                  |
| 3    | `INVALID_ARGUMENT`  | Validation error         |
| 5    | `NOT_FOUND`         | Resource doesn't exist   |
| 7    | `PERMISSION_DENIED` | Insufficient permissions |
| 13   | `INTERNAL`          | Server error             |
| 16   | `UNAUTHENTICATED`   | Missing or invalid auth  |

```python
from connectrpc.code import Code
from connectrpc.errors import ConnectError

raise ConnectError(Code.NOT_FOUND, f"Strategy not found: {strategy_id}")
```

### Code Generation

After modifying `.proto` files:

```bash
make proto
```

Generates:

- Python: `libs/proto/llamatrade_proto/generated/*_pb2.py`, `*_connect.py`
- TypeScript: `apps/web/src/generated/proto/*_pb.ts`

---

## Event Sourcing

The trading service uses event sourcing for durable execution, crash recovery, and complete audit trails.

### Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           STRATEGY RUNNER                                   │
│   Market Data ──► Strategy Logic ──► Signal ──► EventSourcedOrderExecutor   │
└───────────────────────────────────────────────────┬─────────────────────────┘
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        EVENT SOURCED EXECUTOR                               │
│   1. Generate deterministic client_order_id (SHA256 hash)                   │
│   2. Check Alpaca for existing order (crash recovery)                       │
│   3. Run risk checks                                                        │
│   4. Emit OrderSubmitted event                                              │
│   5. Submit to Alpaca with client_order_id                                  │
│   6. Emit OrderAccepted/OrderRejected event                                 │
└───────────────────────────────────────────────────┬─────────────────────────┘
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EVENT STORE                                       │
│   trading_events table (append-only)                                        │
│   ├── sequence (auto-increment PK)                                          │
│   ├── event_id (UUID)                                                       │
│   ├── event_type (string)                                                   │
│   ├── tenant_id, session_id                                                 │
│   └── data (JSONB payload)                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Core Concepts

**Events** are immutable facts:

- Ordered by global sequence number
- Scoped to tenant + session
- Contain all data needed to understand what happened

**Aggregates** are current state derived by replaying events:

```python
state = await SessionState.load(session_id, tenant_id, event_store)
state.positions["AAPL"]  # Current position
state.orders[order_id]   # Order status
state.realized_pnl       # Total realized P&L
```

### Idempotent Order Submission

Orders use deterministic `client_order_id` based on signal parameters:

```python
def generate_deterministic_order_id(
    session_id: UUID,
    symbol: str,
    side: str,
    signal_timestamp: datetime,
) -> str:
    data = f"{session_id}:{symbol}:{side}:{signal_timestamp.isoformat()}"
    hash_digest = hashlib.sha256(data.encode()).hexdigest()[:16]
    return f"lt-{hash_digest}"
```

**Why this works:**

- Same signal always produces same `client_order_id`
- Alpaca treats `client_order_id` as idempotency key
- Crash recovery finds existing orders and skips re-submission

### Event Types

**Signal Events:**

- `signal.generated` - Strategy produced a trading signal
- `signal.rejected` - Signal failed risk checks

**Order Events:**

- `order.submitted` - Order sent to broker
- `order.accepted` - Broker accepted order
- `order.rejected` - Broker rejected order
- `order.filled` - Order completely filled
- `order.partially_filled` - Partial fill
- `order.cancelled` - Order cancelled

**Position Events:**

- `position.opened` - New position created
- `position.increased` - Added to position
- `position.reduced` - Partial close
- `position.closed` - Position fully closed

**Session Events:**

- `session.started`, `session.stopped`, `session.paused`, `session.resumed`

**Circuit Breaker Events:**

- `circuit_breaker.triggered` - Trading halted
- `circuit_breaker.reset` - Trading can resume

### Crash Recovery

The system handles crashes at any point in the order lifecycle:

**Scenario: Crash After Alpaca Submission, Before Event**

```
1. Signal generated
2. OrderSubmitted event written
3. Alpaca accepts order
4. CRASH before OrderAccepted event
```

**Recovery:**

- On restart, signal replays produce same deterministic client_order_id
- Check Alpaca: order exists with status
- Emit missing events (OrderAccepted, possibly OrderFilled)
- Skip re-submission

### Event Store API

```python
class EventStore:
    async def append(self, event: TradingEvent) -> int:
        """Append event, returns sequence number."""

    async def read_stream(
        self,
        session_id: UUID,
        from_sequence: int = 0,
        event_types: list[str] | None = None,
    ) -> AsyncIterator[TradingEvent]:
        """Read events for a session in order."""
```

---

## Security

Multi-layered security architecture for authentication, authorization, tenant isolation, and data protection.

### Authentication

**JWT Tokens:**

```json
{
  "sub": "user-uuid",
  "tenant_id": "tenant-uuid",
  "roles": ["admin"],
  "exp": 1705314000,
  "type": "access"
}
```

| Token Type    | Lifetime   | Storage         | Usage                |
| ------------- | ---------- | --------------- | -------------------- |
| Access Token  | 30 minutes | Memory only     | API requests         |
| Refresh Token | 7 days     | HttpOnly cookie | Get new access token |

**API Keys** for programmatic access:

- Format: `lt_<prefix>_<random>`
- Only SHA-256 hash stored in database
- Can have scopes and expiration

**Password Security:**

- Bcrypt hashing
- Minimum 8 characters
- Complexity requirements enforced

### Authorization (RBAC)

| Role     | Permissions                           |
| -------- | ------------------------------------- |
| `owner`  | Full access, billing, user management |
| `admin`  | All except billing changes            |
| `user`   | CRUD own strategies, view portfolio   |
| `viewer` | Read-only access                      |

```python
def require_role(allowed_roles: list[str]):
    async def check(ctx: TenantContext = Depends(require_auth)):
        if not any(role in allowed_roles for role in ctx.roles):
            raise HTTPException(403, "Insufficient permissions")
        return ctx
    return check
```

### Data Protection

**Encryption at Rest:**

- Alpaca credentials encrypted with AES-256-GCM
- Cloud SQL encrypts data at rest by default

**Encryption in Transit:**

- All external traffic uses TLS 1.3
- Internal gRPC uses TLS
- Database connections use SSL

**Secrets Management:**
Secrets stored in GCP Secret Manager:

- `jwt-secret` - JWT signing key
- `encryption-key` - Alpaca credential encryption
- `stripe-api-key` - Stripe secret key

### Network Security

**Rate Limits:**

| Plan       | Requests/minute |
| ---------- | --------------- |
| Free       | 60              |
| Pro        | 300             |
| Enterprise | Custom          |

**Firewall Rules:**

- Public access only to Load Balancer
- Services communicate on internal network only
- Database accessible only from GKE cluster

### Audit Logging

All security-relevant events are logged:

| Action              | Description               |
| ------------------- | ------------------------- |
| `user.login`        | User logged in            |
| `user.login_failed` | Failed login attempt      |
| `api_key.created`   | API key created           |
| `strategy.deployed` | Strategy deployed to live |
| `order.submitted`   | Order submitted to Alpaca |

### Security Best Practices

**For Developers:**

1. Never log sensitive data (passwords, tokens, API keys)
2. Always use parameterized queries
3. Validate all input (Pydantic models)
4. Check tenant_id on every query
5. Don't commit secrets to git

**Incident Response:**

1. Rotate affected secrets immediately
2. Invalidate all sessions (change JWT secret)
3. Review audit logs for unauthorized access
4. Notify affected tenants

---

## Testing

### Philosophy

> **Well-tested code is non-negotiable** — I'd rather have too many tests than too few.

**Priorities:**

1. Business logic in service layer
2. Edge cases and error handling
3. Tenant isolation (no cross-tenant data leakage)
4. Database operations and constraints
5. API validation and error responses

### Running Tests

```bash
# All tests
make test

# Single service
make test-auth
make test-strategy

# With coverage
cd services/auth && pytest --cov=src --cov-report=term-missing

# HTML report
pytest --cov=src --cov-report=html
```

### Test Patterns

**Async Tests:**

```python
async def test_something():
    result = await some_async_function()
    assert result is not None
```

**API Integration Tests:**

```python
from httpx import ASGITransport, AsyncClient
from src.main import app

@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as c:
        yield c

async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == 200
```

**Mocking Dependencies:**

```python
@pytest.fixture
def mock_auth_service():
    mock = MockAuthService()
    app.dependency_overrides[get_auth_service] = lambda: mock
    yield mock
    app.dependency_overrides.clear()
```

**Tenant Isolation Tests:**

```python
async def test_tenant_isolation(client, auth_headers_tenant_a, auth_headers_tenant_b):
    # Create strategy as tenant A
    response = await client.post("/strategies", headers=auth_headers_tenant_a, json={...})
    strategy_id = response.json()["id"]

    # Tenant A can access
    response = await client.get(f"/strategies/{strategy_id}", headers=auth_headers_tenant_a)
    assert response.status_code == 200

    # Tenant B cannot access
    response = await client.get(f"/strategies/{strategy_id}", headers=auth_headers_tenant_b)
    assert response.status_code == 404  # Not 403 - don't leak existence
```

### Coverage Requirements

**Target: 80% coverage** for real implementations.

**Focus Areas:**

1. **market-data** (95% real) — Full Alpaca integration
2. **auth** (60% real) — JWT, bcrypt, user creation
3. **backtest** engine (30% real) — Metrics calculations
4. **strategy** indicators (20% real) — NumPy calculations

### Common Fixtures

```python
@pytest.fixture
def tenant_id():
    return "00000000-0000-0000-0000-000000000001"

@pytest.fixture
def auth_headers(tenant_id, user_id):
    token = create_access_token(tenant_id=tenant_id, user_id=user_id, roles=["admin"])
    return {"Authorization": f"Bearer {token}"}
```

---

## Deployment & Operations

### GCP Services

| Service                 | Purpose                            |
| ----------------------- | ---------------------------------- |
| **GKE Autopilot**       | Kubernetes cluster                 |
| **Cloud SQL**           | PostgreSQL 16 database             |
| **Memorystore**         | Redis 7 for cache/queues           |
| **Cloud Storage**       | Backtest results, static assets    |
| **Cloud CDN**           | Frontend asset delivery            |
| **Cloud Load Balancer** | L7 load balancing, SSL termination |
| **Secret Manager**      | Sensitive configuration            |
| **Cloud Monitoring**    | Metrics, logging, alerting         |

### Environment Structure

```
┌─────────────────────────────────────────────────────────────────┐
│                         GCP PROJECT                             │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────┐    ┌─────────────────────┐             │
│  │      STAGING        │    │     PRODUCTION      │             │
│  │  GKE: staging       │    │  GKE: production    │             │
│  │  DB: llamatrade-stg │    │  DB: llamatrade-prod│             │
│  │  staging.llama...   │    │  app.llamatrade...  │             │
│  └─────────────────────┘    └─────────────────────┘             │
└─────────────────────────────────────────────────────────────────┘
```

### Deployment Process

**Staging (Automatic):**

```
Push to main → GitHub Actions → Build images → Deploy to staging
```

**Production (Manual Approval):**

```bash
# Create release
git tag v1.2.3
git push origin v1.2.3

# After approval
make deploy-prod
```

### Database Migrations

```bash
# Connect to Cloud SQL (via proxy)
cloud_sql_proxy -instances=project:region:instance=tcp:5432

# Run migrations
DATABASE_URL="postgresql://..." alembic upgrade head

# Rollback
alembic downgrade -1
```

### Kubernetes Resources

**Deployments:**

```yaml
apiVersion: apps/v1
kind: Deployment
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: auth
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: 500m
              memory: 512Mi
          livenessProbe:
            grpc:
              port: 8810
```

**Horizontal Pod Autoscaling:**

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
spec:
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          averageUtilization: 70
```

### Monitoring

**Health Checks:**

Every service exposes `/health`:

```json
{
  "status": "healthy",
  "service": "auth",
  "version": "1.2.3"
}
```

**Metrics (Prometheus):**

- `http_requests_total` — Request count
- `http_request_duration_seconds` — Latency histogram
- `db_query_duration_seconds` — Database query latency

**Logging:**

Structured JSON logs to stdout, collected by Cloud Logging.

**Alerts:**

| Alert           | Condition            | Severity |
| --------------- | -------------------- | -------- |
| High error rate | > 5% 5xx responses   | Critical |
| High latency    | p99 > 5s             | Warning  |
| Pod crash loop  | Restart > 3 in 10min | Critical |

### Troubleshooting

```bash
# View logs
kubectl logs -l app=auth -n production --tail=100

# Describe pod
kubectl describe pod auth-abc123 -n production

# Port forward for local debugging
kubectl port-forward svc/auth 8810:8810 -n production

# Database access
cloud_sql_proxy -instances=project:region:llamatrade-prod=tcp:5432
psql "postgresql://user:pass@localhost:5432/llamatrade"
```

### Rollback Procedures

```bash
# Kubernetes rollback
kubectl rollout undo deployment/auth -n production

# Database rollback
alembic downgrade -1
```

### Disaster Recovery

**Backups:**

- Database: Automated daily backups, 7-day retention
- Redis: Persistence enabled, hourly snapshots
- Object Storage: Versioning enabled

**Full Environment Rebuild:**

```bash
# Apply Terraform
cd infrastructure/terraform/production
terraform apply

# Deploy services
kubectl apply -k infrastructure/k8s/overlays/production

# Restore database
gcloud sql backups restore <backup-id> --restore-instance=llamatrade-prod
```
