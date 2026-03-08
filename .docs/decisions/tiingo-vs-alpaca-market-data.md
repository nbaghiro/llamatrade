# Tiingo vs Alpaca Market Data API Comparison

> Exploration document comparing two market data providers for LlamaTrade integration.

## Overview

| Aspect                  | Tiingo                                     | Alpaca                                           |
| ----------------------- | ------------------------------------------ | ------------------------------------------------ |
| **Primary Focus**       | Historical data & backtesting              | Real-time data + trading integration             |
| **Trading Integration** | Data only (no brokerage)                   | Full brokerage + data combined                   |
| **Best For**            | Research, backtesting, historical analysis | Live trading, algo trading, real-time strategies |

---

## Data Coverage

| Data Type             | Tiingo                            | Alpaca               |
| --------------------- | --------------------------------- | -------------------- |
| **U.S. Stocks**       | 37,319 tickers                    | Full U.S. market     |
| **ETFs/Mutual Funds** | 45,149                            | Yes (via equity API) |
| **Options**           | No                                | Yes (OPRA feed)      |
| **Crypto**            | 2,100+ tickers from 40+ exchanges | Yes                  |
| **Forex**             | 40+ pairs from tier-1 banks       | No                   |
| **Chinese Stocks**    | Yes                               | No                   |
| **Historical Depth**  | **30+ years**                     | Up to 6 years        |
| **Fundamentals**      | 5-15 years                        | No                   |
| **News Feed**         | 16M+ curated articles             | No                   |

---

## Real-Time Data

| Feature                 | Tiingo                    | Alpaca                        |
| ----------------------- | ------------------------- | ----------------------------- |
| **Source**              | IEX Exchange partnership  | CTA (NYSE) + UTP (Nasdaq) SIP |
| **Market Coverage**     | ~2-3% (IEX only)          | **100%** (consolidated SIP)   |
| **WebSocket Streaming** | Yes                       | Yes                           |
| **Latency Focus**       | Moderate (NY5 datacenter) | Not HFT-suitable              |
| **Free Real-Time**      | IEX data                  | IEX data only                 |
| **Paid Real-Time**      | IEX enhanced              | Full SIP ($99/mo)             |

### SIP vs IEX Explained

- **SIP (Securities Information Processor)**: Consolidated feed from all exchanges, representing 100% of market volume. Includes National Best Bid and Offer (NBBO).
- **IEX (Investors Exchange)**: Single exchange feed representing ~2% of total market volume.

For most algorithmic trading, this difference matters less for longer-term strategies but significantly impacts short-term trading accuracy.

---

## Pricing

| Tier              | Tiingo                             | Alpaca                            |
| ----------------- | ---------------------------------- | --------------------------------- |
| **Free**          | 50 symbols/hour, 500 lookups/month | IEX real-time, 15-min delayed SIP |
| **Paid**          | Tiered plans (affordable)          | $99/mo for real-time SIP          |
| **Enterprise**    | Custom                             | Custom broker plans               |
| **Paper Trading** | N/A                                | Free with real-time data          |

---

## Technical Specifications

| Spec                   | Tiingo                              | Alpaca                             |
| ---------------------- | ----------------------------------- | ---------------------------------- |
| **API Protocol**       | REST + WebSocket                    | REST + WebSocket                   |
| **Response Format**    | JSON, CSV                           | JSON                               |
| **SDKs**               | Python (community)                  | Python, Go, Node.js, C# (official) |
| **Rate Limits (Free)** | 50 symbols/hour                     | Limited (IEX only)                 |
| **Rate Limits (Paid)** | Higher tiers                        | Unlimited (Pro)                    |
| **Data Quality**       | Proprietary error-checking, audited | Direct exchange feeds              |

---

## Infrastructure

### Tiingo

- Machine at NY5 connected directly to IEX Exchange
- Bare-metal servers <30 miles from NY5
- Optimized memory caching
- Focus on data cleanliness and redundancy

### Alpaca

- Direct feeds from CTA/NYSE and UTP/Nasdaq
- Not designed for high-frequency trading
- Commission-free trading execution
- Integrated brokerage infrastructure

---

## Use Case Recommendations

| Use Case                          | Recommendation | Rationale                  |
| --------------------------------- | -------------- | -------------------------- |
| **Backtesting with deep history** | Tiingo         | 30+ years of data          |
| **Live algorithmic trading**      | Alpaca         | Trading + data integrated  |
| **Options trading**               | Alpaca         | Only provider with options |
| **Forex strategies**              | Tiingo         | Only provider with forex   |
| **Crypto trading**                | Either         | Both support crypto        |
| **Research/academic**             | Tiingo         | Historical depth           |
| **Paper trading/prototyping**     | Alpaca         | Free paper trading         |
| **News sentiment analysis**       | Tiingo         | 16M+ articles              |
| **Chinese market access**         | Tiingo         | Only provider              |

---

## Key Tradeoffs

### Choose Tiingo if:

- You need 30+ years of historical data
- Backtesting is your primary use case
- You need forex or Chinese stock data
- You want news/sentiment data
- You're using a separate broker for execution

### Choose Alpaca if:

- You need integrated trading + data
- Real-time execution matters
- You trade options
- You want 100% market coverage (SIP)
- You prefer official SDK support
- Commission-free trading is important

---

## LlamaTrade Considerations

Given LlamaTrade's current architecture:

1. **Current State**: Already integrated with Alpaca for trading execution
2. **Backtesting Needs**: Could benefit from Tiingo's deeper historical data (30+ years vs 6 years)
3. **Hybrid Approach**: Consider using both:
   - Alpaca for live trading and real-time data
   - Tiingo for extended historical backtesting

### Potential Integration Strategy

```
┌────────────────────────────────────────────────────────────┐
│                     Market Data Service                    │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌─────────────────┐          ┌─────────────────┐          │
│  │     Alpaca      │          │     Tiingo      │          │
│  │  (Primary)      │          │  (Historical)   │          │
│  ├─────────────────┤          ├─────────────────┤          │
│  │ • Live trading  │          │ • 30+ yr history│          │
│  │ • Real-time     │          │ • Backtesting   │          │
│  │ • Options       │          │ • Forex data    │          │
│  │ • 6yr history   │          │ • News feed     │          │
│  └────────┬────────┘          └────────┬────────┘          │
│           │                            │                   │
│           └──────────┬─────────────────┘                   │
│                      │                                     │
│              ┌───────▼───────┐                             │
│              │  Data Router  │                             │
│              │  (by use case)│                             │
│              └───────────────┘                             │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

---

## Sources

- [Tiingo API Pricing](https://www.tiingo.com/about/pricing)
- [Tiingo IEX Real-time API](https://www.tiingo.com/products/iex-api)
- [Alpaca Market Data API Docs](https://docs.alpaca.markets/docs/about-market-data-api)
- [Alpaca Market Data FAQ](https://docs.alpaca.markets/docs/market-data-faq)
- [Alpaca Data Provider Info](https://alpaca.markets/support/data-provider-alpaca)
- [SIP vs IEX Comparison - Alpaca](https://alpaca.markets/learn/understanding-stock-market-data)
- [Beyond yFinance: API Comparison - Medium](https://medium.com/@trading.dude/beyond-yfinance-comparing-the-best-financial-data-apis-for-traders-and-developers-06a3b8bc07e2)
- [Best Financial Data APIs 2026](https://www.nb-data.com/p/best-financial-data-apis-in-2026)
- [QuantStart Tiingo Evaluation](https://www.quantstart.com/articles/evaluating-data-coverage-with-tiingo/)

---

_Last updated: 2026-02-27_
