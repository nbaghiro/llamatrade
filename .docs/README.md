# LlamaTrade Documentation

Documentation for the LlamaTrade algorithmic trading platform.

---

## Quick Links

| Document | Description |
|----------|-------------|
| [Architecture](architecture.md) | System design, deployment, multi-tenancy |
| [Strategy DSL](strategy-dsl.md) | S-expression DSL reference for strategies and allocations |
| [Strategy Templates](strategy-templates.md) | Visual Strategy Builder templates |
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

## Planning

Implementation roadmaps and task tracking.

| Plan | Status |
|------|--------|
| [DSL Implementation Gaps](planning/dsl-gaps.md) | In Progress |

---

## Getting Started

1. **New to LlamaTrade?** Start with [Architecture](architecture.md)
2. **Building strategies?** See [Strategy DSL](strategy-dsl.md) and [Templates](strategy-templates.md)
3. **Understanding a service?** Check the [Services](#services) section
4. **Why a decision was made?** Check [Decisions](#decisions)
