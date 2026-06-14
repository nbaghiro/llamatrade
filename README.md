# LlamaTrade

**Open-source algorithmic trading platform** — Build strategies, backtest on historical data, and execute live trades via Alpaca Markets.

![LlamaTrade Preview](preview.png)

## Features

- **Visual Strategy Builder** — Create trading strategies without writing code using a node-based editor
- **Pre-built Strategies** — MA Crossover, RSI, MACD, Bollinger Bands, Donchian Breakout, and more
- **Backtesting Engine** — Test strategies against historical market data with detailed metrics
- **Live Trading** — Paper and live trading via Alpaca Markets API
- **Multi-tenant SaaS** — Built for scale with proper tenant isolation
- **Real-time Data** — WebSocket streaming for live market data and order updates

## Architecture

```
    🦙  LlamaTrade — strategies in, orders out
╭──────────────────────────────────────────────────────────────────────────────────╮
│                                  USER  BROWSER                                   │
│                         you · your team  (multi-tenant)                          │
╰──────────────────────────────────────────────────────────────────────────────────╯
                                          │
                                        Connect · HTTP/1.1 + JSON · JWT · no gateway
                                          ▼
╭──────────────────────────────────────────────────────────────────────────────────╮
│                            web · 8800   —   React SPA                            │
│           visual builder · backtests · trading & portfolio dashboards            │
╰──────────────────────────────────────────────────────────────────────────────────╯
                                          │
        ┬────────────────┬────────────────┴────────────────┬────────────────┬
        ▼                ▼                ▼                ▼                ▼
     sign in           build            test             live            assist
╭──────────────╮ ╭──────────────╮ ╭──────────────╮ ╭──────────────╮ ╭──────────────╮
│ auth · 8810  │ │strategy·8820 │ │backtest·8830 │ │ trading·8850 │ │ agent · 8890 │
│ JWT·tenants  │ │ parse · ver  │ │  Celery sim  │ │orders⇄Alpaca │ │   AI → DSL   │
╰──────────────╯ ╰──────────────╯ ╰──────────────╯ ╰──────────────╯ ╰──────────────╯

                 ╭──────────────╮ ╭──────────────╮ ╭──────────────╮
                 │ market-data  │ │ billing·8880 │ │ notification │
                 │ 8840 bars+WS │ │Stripe·limits │ │ 8870 alerts  │
                 ╰──────────────╯ ╰──────────────╯ ╰──────────────╯
                                          │
                                            terminal fills · exactly-once
                                          ▼
╔══════════════════════════════════════════════════════════════════════════════════╗
║               portfolio · 8860   —   THE LEDGER  ★ book of record                ║
║             sleeves · lots · double-entry events · per-strategy P&L              ║
╚══════════════════════════════════════════════════════════════════════════════════╝
                                          │
  Postgres (RLS)   ·   Redis (queues · fills · progress)   ·   Alpaca (WS + REST)   
```

## Tech Stack

| Layer              | Technology                                            |
| ------------------ | ----------------------------------------------------- |
| **Frontend**       | React 18, TypeScript, Vite, Tailwind CSS, Zustand     |
| **Backend**        | Python 3.14+, FastAPI, SQLAlchemy, Pydantic           |
| **API Protocol**   | gRPC + Connect (HTTP/1.1 JSON for browser, HTTP/2 S2S)|
| **Database**       | PostgreSQL 16, Redis 7                                |
| **Infrastructure** | Docker, Kubernetes (GKE), Terraform                   |
| **CI/CD**          | GitHub Actions                                        |

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.14+ (for local development)
- Node.js 20+ (for frontend)
- [Alpaca Markets](https://alpaca.markets/) account (free paper trading)

### 1. Clone and Configure

```bash
git clone https://github.com/your-org/llamatrade.git
cd llamatrade

# Copy environment template
cp .env.example .env

# Add your Alpaca API keys to .env
# ALPACA_API_KEY=your_paper_api_key
# ALPACA_API_SECRET=your_paper_api_secret
```

### 2. Start Development Environment

**Option A: Docker (recommended for first run)**

```bash
make dev
```

**Option B: Local Python (faster hot-reload)**

```bash
# Start infrastructure only
make dev-infra

# Run all services at once (uses honcho)
make dev-local

# Or run individual services in separate terminals
make dev-local SERVICE=auth
make dev-local SERVICE=strategy
# ... etc
```

### 3. Access the Application

| Service     | URL                   |
| ----------- | --------------------- |
| Frontend    | http://localhost:8800 |
| Auth        | http://localhost:8810 |
| Strategy    | http://localhost:8820 |

## Project Structure

```
llamatrade/
├── apps/
│   └── web/                 # React frontend
├── services/
│   ├── auth/                # Authentication & users
│   ├── strategy/            # Strategy management
│   ├── backtest/            # Backtesting engine
│   ├── market-data/         # Real-time & historical data
│   ├── trading/             # Order execution
│   ├── portfolio/           # Positions & P&L
│   ├── notification/        # Alerts & webhooks
│   └── billing/             # Subscriptions (Stripe)
├── libs/
│   ├── common/              # Shared models & utilities
│   ├── db/                  # SQLAlchemy models & migrations
│   ├── dsl/                 # Strategy DSL parser
│   ├── compiler/            # Strategy compiler
│   └── proto/               # Protocol Buffers + generated Connect code
├── infrastructure/
│   ├── docker/              # Docker Compose configs
│   ├── k8s/                 # Kubernetes manifests
│   └── terraform/           # GCP infrastructure
└── .docs/                   # Documentation
```

## Development

```bash
# Run tests
make test

# Lint & type check
make lint

# Auto-fix linting issues
make lint-fix

# See all available commands
make help
```

## Built-in Strategies

| Strategy          | Type           | Description                        |
| ----------------- | -------------- | ---------------------------------- |
| MA Crossover      | Trend          | Fast/slow moving average crossover |
| RSI Reversal      | Mean Reversion | Buy oversold, sell overbought      |
| MACD              | Momentum       | MACD line + signal line crossover  |
| Bollinger Bounce  | Mean Reversion | Trade bounces off bands            |
| Donchian Breakout | Trend          | Turtle trading channel breakout    |
| Dual Momentum     | Momentum       | Relative + absolute momentum       |
| Pairs Trading     | Arbitrage      | Cointegrated pairs spread trading  |

## Deployment

```bash
# Deploy to staging (auto on merge to main)
make deploy-staging

# Deploy to production (manual)
make deploy-prod

# Infrastructure provisioning
make tf-plan
make tf-apply
```

## Documentation

- [Architecture Guide](.docs/architecture.md)
- [gRPC/Connect Protocol Guide](.docs/specs/grpc-guide.md)
- [Alpaca API Reference](.docs/alpaca-api-guide.md)
- [Trading Strategies Guide](.docs/algorithmic-trading-strategies.md)

## Contributing

Contributions are welcome! Please read our contributing guidelines before submitting PRs.

1. Clone the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

MIT License — see [LICENSE](LICENSE) for details.
