# LlamaTrade - Architecture Documentation

## Overview

LlamaTrade is a SaaS algorithmic trading platform enabling users to create custom strategies or use pre-built ones, backtest against historical data, and execute live trades via Alpaca Markets API.

**Architecture:** Microservices (Python FastAPI backend + React/TypeScript/Tailwind frontend)

---

## Services Architecture

### Core Services (10 total, all in GKE)

| Service | Port | Responsibility |
|---------|------|----------------|
| **Frontend (Web)** | 80/443 | React SPA served via nginx, CDN-backed |
| **API Gateway** | 8000 | Routing, auth validation, rate limiting |
| **Auth Service** | 8001 | Users, tenants, API keys, JWT |
| **Strategy Service** | 8002 | Strategy CRUD, versioning, templates |
| **Backtest Service** | 8003 | Historical simulation execution |
| **Market Data Service** | 8004 | Real-time + historical data from Alpaca |
| **Trading Service** | 8005 | Live order execution, risk enforcement |
| **Portfolio Service** | 8006 | Positions, P&L, performance metrics |
| **Notification Service** | 8007 | Alerts, webhooks, email/SMS |
| **Billing Service** | 8008 | Subscriptions, usage metering (Stripe) |

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
# Frontend: http://localhost:3000
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
