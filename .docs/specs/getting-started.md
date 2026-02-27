# Getting Started — Developer Guide

This guide covers everything you need to set up your local development environment and start contributing to LlamaTrade.

---

## Prerequisites

### Required Software

| Tool | Version | Purpose |
|------|---------|---------|
| **Python** | 3.12+ | Backend services |
| **Node.js** | 20+ | Frontend build tools |
| **Docker** | Latest | Container runtime |
| **Docker Compose** | 2.x | Local orchestration |
| **PostgreSQL** | 16 (via Docker) | Primary database |
| **Redis** | 7 (via Docker) | Cache and queues |

### Optional but Recommended

| Tool | Purpose |
|------|---------|
| **uv** | Fast Python package manager (replaces pip) |
| **Make** | Run project commands |
| **direnv** | Auto-load environment variables |

---

## Initial Setup

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/llamatrade.git
cd llamatrade
```

### 2. Run Setup Script

```bash
./scripts/setup.sh
```

This script:
- Checks prerequisites
- Creates virtual environments
- Installs Python dependencies
- Installs Node dependencies
- Copies `.env.example` files
- Generates gRPC code from proto files

### 3. Configure Environment

Copy and edit environment files:

```bash
cp .env.example .env
cp apps/web/.env.example apps/web/.env
```

**Required variables:**

```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/llamatrade

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT (generate a secure key)
JWT_SECRET=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=30

# Encryption (for Alpaca credentials)
ENCRYPTION_KEY=your-32-byte-encryption-key

# Alpaca (optional for testing)
ALPACA_API_KEY=your-paper-api-key
ALPACA_API_SECRET=your-paper-api-secret
```

---

## Running Locally

### Option 1: Docker Compose (Recommended)

Start all services:

```bash
make dev
```

This starts:
- All backend services (auth, strategy, backtest, trading, etc.)
- PostgreSQL database
- Redis
- Frontend dev server

**Access points:**
- Frontend: http://localhost:8800
- API Gateway: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Option 2: Hybrid (Infrastructure in Docker, Services Local)

Start only database and Redis:

```bash
make dev-infra
```

Then run services locally (in separate terminals or with a process manager):

```bash
# Run all services
make dev-local

# Or run individual services
cd services/auth && uvicorn src.main:app --reload --port 8810
cd services/strategy && uvicorn src.main:app --reload --port 8820
```

---

## Project Structure

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
│   ├── billing/                # Subscriptions (Stripe)
│   └── gateway/                # Kong API Gateway config
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

---

## Key Concepts

### Multi-Tenancy

Every request is scoped to a tenant:

1. JWT tokens contain `tenant_id` claim
2. Middleware extracts tenant context: `ctx = Depends(require_auth)`
3. All database queries filter by `ctx.tenant_id`
4. Service-to-service calls propagate tenant via `X-Tenant-ID` header

**Never access data without tenant filtering.**

### gRPC Communication

Services communicate via gRPC (not REST internally):

- Proto definitions: `libs/proto/llamatrade/v1/*.proto`
- Generated code: `libs/grpc/llamatrade_grpc/generated/`
- Clients: `libs/grpc/llamatrade_grpc/clients/`

Regenerate after proto changes:

```bash
cd libs/proto && buf generate
```

### Strategy DSL

Strategies are defined in an S-expression DSL:

```lisp
(strategy
  (name "RSI Mean Reversion")
  (symbols ["AAPL" "GOOGL"])
  (entry (< (rsi 14) 30))
  (exit (> (rsi 14) 70)))
```

- Parser: `libs/dsl/llamatrade_dsl/parser.py`
- Compiler: `libs/dsl/llamatrade_dsl/compiler.py`
- See: `.docs/strategy-dsl-implementation.md`

---

## Common Tasks

### Running Tests

```bash
# All tests
make test

# Single service
make test-auth
make test-strategy

# With coverage
cd services/auth && pytest --cov=src --cov-report=term-missing
```

### Linting

```bash
# All linting
make lint

# Python (ruff)
ruff check --fix services/ libs/
ruff format services/ libs/

# Frontend (ESLint)
cd apps/web && npm run lint:fix
```

### Database Migrations

```bash
# Create migration
cd services/auth
alembic revision --autogenerate -m "Add new column"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Regenerate gRPC Code

```bash
cd libs/proto
buf generate
```

---

## Service Ports

| Service | gRPC Port | HTTP Port | Description |
|---------|-----------|-----------|-------------|
| Frontend | - | 8800 | React SPA |
| Gateway | - | 8000 | Kong API Gateway |
| Auth | 8810 | - | Authentication |
| Strategy | 8820 | - | Strategy management |
| Backtest | 8830 | - | Backtesting |
| Market Data | 8840 | - | Market data |
| Trading | 8850 | - | Order execution |
| Portfolio | 8860 | - | Positions & P&L |
| Notification | 8870 | - | Alerts |
| Billing | 8880 | 8881* | Subscriptions |

*Billing has HTTP port for Stripe webhooks.

---

## Troubleshooting

### Database connection refused

```bash
# Check if PostgreSQL is running
docker ps | grep postgres

# Start infrastructure
make dev-infra
```

### gRPC import errors

```bash
# Regenerate proto files
cd libs/proto && buf generate

# Reinstall grpc lib
cd libs/grpc && pip install -e .
```

### Port already in use

```bash
# Find process using port
lsof -i :8810

# Kill process
kill -9 <PID>
```

### Redis connection errors

```bash
# Check Redis
docker ps | grep redis
redis-cli ping  # Should return PONG
```

---

## Next Steps

1. **Read the architecture docs**: `.docs/architecture.md`
2. **Understand the testing approach**: `.docs/specs/testing-guide.md`
3. **Review a service**: Start with `services/auth/` — it's the simplest
4. **Make a small change**: Fix a bug or add a test
5. **Run the full CI locally**: `./scripts/ci-local.sh`
