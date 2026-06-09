# LlamaTrade Documentation

Documentation for the LlamaTrade algorithmic trading platform.

---

## Quick Links

| Document | Description |
|----------|-------------|
| [Architecture](architecture.md) | System design, deployment, multi-tenancy |
| [Strategy DSL](strategy-dsl.md) | S-expression DSL reference: the language, compilation, and evaluation |
| [Portfolio Ledger](portfolio-ledger.md) | How target weights become trades: sizing, sleeves, event-sourced ledger, reconciliation |
| [Trading Strategies](trading-strategies.md) | Algorithmic trading concepts and approaches |
| [Asset Classes](asset-classes.md) | Tradeable asset class reference |

---

## Services

Service-level architecture documentation.

| Service | Port | Description |
|---------|------|-------------|
| [Auth](services/auth.md) | 8810 | Authentication, JWT tokens, RBAC, Alpaca credentials |
| [Strategy](services/strategy.md) | 8820 | Strategy CRUD, DSL parsing, templates |
| [Backtest](services/backtesting.md) | 8830 | Historical backtesting, metrics calculation |
| [Market Data](services/market-data.md) | 8840 | Real-time and historical market data via Alpaca |
| [Trading](services/trading.md) | 8850 | Order execution, risk management, positions |
| [Portfolio](services/portfolio.md) | 8860 | Portfolio tracking, P&L, performance metrics |
| [Billing](services/billing.md) | 8880 | Stripe integration, subscriptions, payments |
| [Notification](services/notification.md) | 8870 | Alerts, channels (email, SMS, Slack) |

---

## Decisions

Architecture Decision Records (ADRs) for key technical choices.

| Decision | Outcome |
|----------|---------|
| [Gateway vs Direct Communication](decisions/gateway-vs-direct-communication.md) | Direct service communication via Connect protocol |
| [Tiingo vs Alpaca Market Data](decisions/tiingo-vs-alpaca-market-data.md) | Alpaca for unified trading + data |

---

## Getting Started

1. **New to LlamaTrade?** Start with [Architecture](architecture.md)
2. **Building strategies?** See [Strategy DSL](strategy-dsl.md)
3. **Running multiple strategies in one account?** See [Portfolio Ledger](portfolio-ledger.md)
4. **Understanding a service?** Check the [Services](#services) section
5. **Why a decision was made?** Check [Decisions](#decisions)
