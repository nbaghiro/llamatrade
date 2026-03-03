# Strategy Builder Templates

A comprehensive collection of portfolio allocation templates for the LlamaTrade Strategy Builder. Templates are ordered from basic to advanced, demonstrating real-world allocation strategies using visual block-based construction.

---

## Introduction

### What is the Strategy Builder?

The Strategy Builder is a visual, no-code tool for creating portfolio allocation strategies. Unlike the S-expression DSL (used for signal-based trading strategies with entry/exit conditions), the Strategy Builder focuses on **portfolio construction and rebalancing**.

```
┌─────────────────────────────────────────────────────────────────┐
│                    STRATEGY BUILDER                             │
│                                                                 │
│  Purpose: Portfolio allocation and rebalancing                  │
│  Interface: Visual drag-and-drop blocks                         │
│  Output: Target portfolio weights                               │
│                                                                 │
│  vs S-Expression DSL:                                           │
│  ────────────────────                                           │
│  DSL: Entry/exit signals for individual trades                  │
│  Builder: Portfolio weights across multiple assets              │
└─────────────────────────────────────────────────────────────────┘
```

### Who Is This For?

- **Passive investors**: Build diversified portfolios with automatic rebalancing
- **Tactical allocators**: Create rule-based rotation strategies
- **Risk-focused investors**: Implement risk parity and volatility targeting
- **Factor investors**: Combine momentum, value, and quality tilts

### How It Works

1. **Build**: Drag blocks to create your strategy tree
2. **Configure**: Set weights, conditions, and parameters
3. **Backtest**: Validate against historical data
4. **Deploy**: Enable automatic rebalancing

---

## Block Types Reference

| Block | Description | Visual |
|-------|-------------|--------|
| **Root** | Strategy container | White card with Layers icon |
| **Group** | Named folder for organizing | White card with Layers icon |
| **Weight** | Allocation method | Green pill |
| **Asset** | Individual stock/ETF | White card with circle bullet |
| **If** | Conditional branch | Amber pill |
| **Else** | Alternative branch | Blue pill |
| **Filter** | Dynamic asset selection | Purple card |

### Weight Methods

#### Specified
Fixed percentage allocations that you define manually.
```
Example: [60%] SPY, [40%] AGG
Use when: You have specific allocation targets
```

#### Equal
Split evenly across all children.
```
Example: 5 assets → 20% each
Use when: You want to avoid concentration and market-cap bias
```

#### Inverse Volatility
Allocate more to lower-volatility assets (risk parity approach).
```
Formula: Weight_i = (1 / Vol_i) / Σ(1 / Vol_j)

Example with 60-day lookback:
  SPY volatility: 15% → Weight: 40%
  TLT volatility: 10% → Weight: 60%

Parameters:
  - Lookback period: 20-60 days typical
  - Volatility measure: Standard deviation of returns

Use when: You want equal risk contribution from each asset
```

#### Market Cap
Weight by market capitalization (like an index fund).
```
Formula: Weight_i = MarketCap_i / Σ(MarketCap_j)

Example:
  AAPL ($3T) → 50%
  MSFT ($2.5T) → 42%
  NVDA ($500B) → 8%

Use when: You want to track market-weighted exposure
```

#### Momentum
Weight by recent price performance (winners get more).
```
Formula: Weight_i = max(0, Return_i) / Σ(max(0, Return_j))

Example with 90-day lookback:
  Asset A: +20% return → Higher weight
  Asset B: +5% return → Lower weight
  Asset C: -10% return → Zero weight (negative momentum excluded)

Parameters:
  - Lookback period: 30-180 days typical
  - Return type: Total return (price + dividends)

Use when: You want to overweight recent winners
Caution: High turnover, tax-inefficient
```

#### Min Variance
Optimize for lowest portfolio volatility using mean-variance optimization.
```
Optimization:
  Minimize: Portfolio variance = w'Σw
  Subject to: Σw = 1, w ≥ 0

Parameters:
  - Lookback period: 60-252 days (longer = more stable)
  - Covariance estimation: Sample covariance matrix

Use when: You want the smoothest ride regardless of returns
Caution: Concentrated in low-vol assets, may underperform in bull markets
```

---

### Filter Blocks

Filters dynamically select assets from a universe based on ranking criteria.

```
FILTER block structure:

┌─────────────────────────────────────────────────────────────┐
│  FILTER: Top [N] by [Criteria] from [Universe]              │
└─────────────────────────────────────────────────────────────┘
```

#### Available Universes

| Universe | Description | Asset Count |
|----------|-------------|-------------|
| S&P 500 | Large-cap US stocks | 500 |
| Russell 1000 | Large + mid-cap US | 1000 |
| Russell 2000 | Small-cap US | 2000 |
| NASDAQ 100 | Large-cap tech-heavy | 100 |
| Sector ETFs | 11 GICS sectors | 11 |
| Custom | User-defined watchlist | Varies |

#### Filter Criteria

| Criteria | Description | Typical Use |
|----------|-------------|-------------|
| **Momentum (N-month)** | Total return over period | Trend following |
| **Value (P/E)** | Price-to-earnings ratio | Value investing |
| **Value (P/B)** | Price-to-book ratio | Deep value |
| **Quality** | ROE + debt/equity + earnings stability | Quality factor |
| **Low Volatility** | Historical standard deviation | Defensive |
| **Dividend Yield** | Annual dividend / price | Income |
| **Market Cap** | Total market value | Size factor |

#### Filter Example

```
FILTER: Top 10 by Momentum (6m) from S&P 500

Process:
  1. Calculate 6-month return for all 500 stocks
  2. Rank from highest to lowest
  3. Select top 10
  4. Apply weight method to selected assets

Result: 10 stocks with strongest recent performance
Rebalance: Re-run filter at each rebalance period
```

---

### Conditional Logic (IF/ELSE)

Conditional blocks allow dynamic allocation based on market conditions.

```
IF/ELSE block structure:

┌─────────────────────────────────────────────────────────────┐
│  IF [Condition]                                             │
│    └── [Allocation when TRUE]                               │
│  ELSE                                                       │
│    └── [Allocation when FALSE]                              │
└─────────────────────────────────────────────────────────────┘
```

#### Available Conditions

| Condition Type | Syntax | Example |
|----------------|--------|---------|
| **Price vs SMA** | `ASSET > SMA(N)` | `SPY > SMA(200)` |
| **SMA Crossover** | `SMA(N) > SMA(M)` | `SMA(SPY,50) > SMA(SPY,200)` |
| **RSI Level** | `RSI(ASSET,N) < X` | `RSI(SPY,14) < 30` |
| **VIX Level** | `VIX < X` | `VIX < 20` |
| **Month Range** | `MONTH >= X OR MONTH <= Y` | `MONTH >= 11 OR MONTH <= 4` |
| **Compound** | `A AND B` / `A OR B` | `SPY > SMA(200) AND VIX < 25` |

#### Evaluation Timing

```
When are conditions evaluated?

┌─────────────────────────────────────────────────────────────┐
│  REBALANCE TRIGGER                                          │
│       │                                                     │
│       ▼                                                     │
│  1. Fetch latest market data (close of prior day)           │
│       │                                                     │
│       ▼                                                     │
│  2. Calculate indicators (SMA, RSI, etc.)                   │
│       │                                                     │
│       ▼                                                     │
│  3. Evaluate all IF conditions                              │
│       │                                                     │
│       ▼                                                     │
│  4. Determine target weights                                │
│       │                                                     │
│       ▼                                                     │
│  5. Generate rebalance orders                               │
└─────────────────────────────────────────────────────────────┘

Data freshness:
  - Conditions use prior day's closing prices
  - Intraday data not used (avoids whipsaw)
  - Indicators calculated fresh at each rebalance
```

#### Lag Considerations

```
Signal lag is inherent in any rule-based system:

Day 0:  Market closes, SPY crosses below 200-day SMA
Day 1:  Rebalance runs, condition evaluated as FALSE
        Sell orders generated for next day
Day 2:  Orders execute at market open

Total lag: ~1.5 trading days from signal to execution

Mitigation:
  - Use longer-term signals (200-day vs 50-day)
  - Avoid frequent rebalancing
  - Accept lag as cost of systematic approach
```

---

### Rebalancing

#### Rebalance Frequency

| Frequency | Best For | Turnover | Tax Efficiency |
|-----------|----------|----------|----------------|
| **Daily** | High-frequency tactical | Very High | Poor |
| **Weekly** | Active tactical | High | Poor |
| **Monthly** | Most strategies | Medium | Moderate |
| **Quarterly** | Passive portfolios | Low | Good |
| **Annually** | Buy-and-hold | Very Low | Excellent |

#### Rebalance Methods

**Calendar-Based**: Rebalance on fixed schedule (1st of month, etc.)
```
Pros: Predictable, simple
Cons: May miss large drifts between dates
```

**Threshold-Based**: Rebalance when drift exceeds threshold (e.g., 5%)
```
Pros: Responds to market moves
Cons: More trading in volatile markets

Example:
  Target: SPY 60%
  Threshold: 5%
  Trigger: Rebalance if SPY drifts to <55% or >65%
```

**Hybrid**: Calendar + threshold (monthly unless drift > 10%)
```
Pros: Balance of both approaches
Cons: More complex logic
```

#### Trading Costs

```
Rebalancing incurs costs:

Direct costs:
  - Commissions: $0-5 per trade (most brokers: $0)
  - Bid-ask spread: 0.01-0.10% per trade
  - Market impact: 0.01-0.50% for large orders

Indirect costs:
  - Short-term capital gains tax (if held < 1 year)
  - Time out of market during rebalance

Rule of thumb:
  - Monthly rebalancing: ~0.5-1% annual drag
  - Quarterly rebalancing: ~0.2-0.5% annual drag
  - Annual rebalancing: ~0.1% annual drag
```

---

### Risk Warnings

#### Leveraged ETFs

Templates using leveraged ETFs (UPRO, TQQQ, SOXL, etc.) carry significant risks:

```
⚠️  LEVERAGED ETF WARNING

Volatility Decay (Beta Slippage):
  Leveraged ETFs reset daily, causing decay in volatile markets.

  Example - 2x ETF in choppy market:
    Day 1: Index +10% → ETF +20% (100 → 120)
    Day 2: Index -10% → ETF -20% (120 → 96)
    Index: 100 → 99 (-1%)
    ETF:   100 → 96 (-4%)  ← Extra 3% loss from decay

Long-term Performance:
  Over years, 3x ETFs can lose 50-90% even if index is flat
  NOT suitable for buy-and-hold

Appropriate Use:
  - Short-term tactical positions only (days to weeks)
  - With strict exit rules
  - Small position sizes (<10% of portfolio)
```

**Templates with leveraged ETFs**: #15 (RSI Mean Reversion)

#### Concentration Risk

```
High concentration = higher risk + higher potential return

Templates with concentration risk:
  - #5 (Tech Growth): 6 stocks, 100% tech sector
  - #4 (Dividend Aristocrats): 10 stocks only

Mitigation:
  - Limit single-stock positions to <10%
  - Limit single-sector exposure to <30%
  - Add diversifying assets (bonds, international)
```

#### Liquidity Considerations

```
Some ETFs have lower trading volume:

Low liquidity indicators:
  - Average daily volume < 100,000 shares
  - Bid-ask spread > 0.10%
  - Assets under management < $100M

Templates with potential liquidity concerns:
  - BTAL (Anti-Beta Fund): Lower AUM
  - DBMF (Managed Futures): Newer fund
  - Some sector ETFs during market stress

Mitigation:
  - Use limit orders, not market orders
  - Avoid trading at market open/close
  - Consider larger, more liquid alternatives
```

---

### Implementation Considerations

#### Minimum Account Sizes

| Template Type | Minimum Suggested | Why |
|---------------|-------------------|-----|
| **Simple (2-5 assets)** | $1,000 | Can buy fractional shares |
| **Moderate (5-15 assets)** | $5,000 | Meaningful positions |
| **Complex (15+ assets)** | $25,000 | Avoid tiny positions, PDT rule |
| **With Filters** | $50,000 | Individual stocks need size |

#### Tax Efficiency

| Strategy Type | Turnover | Tax Impact | Tax-Advantaged Account? |
|---------------|----------|------------|-------------------------|
| Passive (60/40) | Low | Minimal | Either |
| Factor tilts | Medium | Moderate | Prefer tax-advantaged |
| Momentum | High | Significant | Strongly prefer tax-advantaged |
| Tactical (IF/ELSE) | Variable | Can be high | Strongly prefer tax-advantaged |

#### Broker Compatibility

```
Required broker features:

Basic templates:
  ✓ ETF trading
  ✓ Fractional shares (helpful)

Advanced templates:
  ✓ ETF trading
  ✓ Options approval (for some hedged strategies)
  ✓ Extended hours (helpful for rebalancing)

Recommended brokers:
  - Alpaca (LlamaTrade native integration)
  - Interactive Brokers (comprehensive)
  - Schwab/Fidelity (for tax-advantaged accounts)
```

---

### Customization Guide

#### Adjusting Risk Tolerance

```
To REDUCE risk:
  1. Increase bond allocation (+10-20%)
  2. Add short-term treasuries (SHY)
  3. Reduce or eliminate leveraged ETFs
  4. Use Inverse Volatility weighting
  5. Add IF condition for bear markets

To INCREASE risk:
  1. Reduce bond allocation
  2. Add growth/momentum tilts
  3. Concentrate in higher-beta sectors
  4. Use Momentum weighting
  5. Add small-cap exposure (IWM)

Example - Converting template #1 (60/40) to conservative:
  Original: 60% SPY, 40% AGG
  Conservative: 40% SPY, 40% AGG, 20% SHY
```

#### Adapting for Account Size

```
Small account ($1,000-$10,000):
  - Stick to 3-5 ETF templates
  - Use Equal weighting (simpler)
  - Avoid individual stocks
  - Monthly or quarterly rebalancing

Medium account ($10,000-$100,000):
  - Can use 5-15 asset templates
  - Advanced weighting methods work well
  - Consider tax-loss harvesting

Large account ($100,000+):
  - Full template flexibility
  - Can implement Filter-based strategies
  - Direct indexing possible
  - Consider multiple sleeves for tax efficiency
```

#### Substituting Assets

```
Common substitutions:

More aggressive:
  SPY → QQQ (more tech)
  BND → HYG (high yield bonds)
  VTI → IWM (small cap)

More conservative:
  QQQ → SPY (broader market)
  TLT → IEF (shorter duration)
  HYG → LQD (investment grade)

Lower cost:
  SPY → VOO or IVV (lower expense ratio)
  AGG → BND (Vanguard alternative)

International:
  VTI → VT (includes international)
  Add VEA/VWO alongside US holdings
```

---

### Backtesting Guidelines

#### Before Deploying Any Template

```
Backtesting checklist:

1. Run backtest over multiple market regimes
   - Bull market (2010-2019)
   - Bear market (2008, 2020, 2022)
   - Sideways (2015-2016)

2. Check key metrics:
   - Total return vs benchmark
   - Maximum drawdown
   - Sharpe ratio
   - Annual turnover

3. Stress test:
   - What happens in 2008-style crash?
   - What if conditions stay triggered for months?
   - What's the worst 12-month period?

4. Sanity check:
   - Does the logic make sense?
   - Are returns realistic (not too good)?
   - Is turnover manageable?
```

#### Common Backtesting Pitfalls

```
⚠️  BACKTEST WARNINGS

Overfitting:
  - Too many parameters tuned to historical data
  - Works perfectly in backtest, fails live
  - Mitigation: Use out-of-sample testing

Survivorship Bias:
  - Backtest uses today's S&P 500 constituents
  - Ignores companies that went bankrupt
  - Mitigation: Use point-in-time data

Look-Ahead Bias:
  - Using data that wasn't available at the time
  - Example: Using final earnings vs estimates
  - Mitigation: Ensure data timestamps are correct

Unrealistic Assumptions:
  - Zero trading costs
  - Perfect execution at close prices
  - Instant rebalancing
  - Mitigation: Add realistic cost assumptions
```

---

## Beginner Templates

These templates introduce core concepts with simple structures.

---

### 1. Classic 60/40 Portfolio

**Category:** Passive | **Difficulty:** Beginner
**Block Types:** Root, Weight (Specified), Asset

The foundational portfolio allocation—60% stocks, 40% bonds. Simple, time-tested, and effective for long-term investors.

```
Root: "Classic 60/40"
└── WEIGHT Specified
    ├── [60%] SPY  - SPDR S&P 500 ETF
    └── [40%] AGG  - iShares Core US Aggregate Bond ETF
```

**Assets:**
| Ticker | Name | Allocation |
|--------|------|------------|
| SPY | SPDR S&P 500 ETF Trust | 60% |
| AGG | iShares Core US Aggregate Bond ETF | 40% |

---

### 2. Three-Fund Portfolio

**Category:** Passive | **Difficulty:** Beginner
**Block Types:** Root, Weight (Specified), Asset

The Bogleheads classic—total US market, international, and bonds. Maximum diversification with minimal complexity.

```
Root: "Three-Fund Portfolio"
└── WEIGHT Specified
    ├── [50%] VTI  - Vanguard Total Stock Market ETF
    ├── [30%] VXUS - Vanguard Total International Stock ETF
    └── [20%] BND  - Vanguard Total Bond Market ETF
```

**Assets:**
| Ticker | Name | Allocation |
|--------|------|------------|
| VTI | Vanguard Total Stock Market ETF | 50% |
| VXUS | Vanguard Total International Stock ETF | 30% |
| BND | Vanguard Total Bond Market ETF | 20% |

---

### 3. Equal Weight Sectors

**Category:** Passive | **Difficulty:** Beginner
**Block Types:** Root, Weight (Equal), Asset

Equal allocation across major market sectors. Removes market-cap bias and provides balanced sector exposure.

```
Root: "Equal Weight Sectors"
└── WEIGHT Equal
    ├── XLK  - Technology Select Sector SPDR
    ├── XLV  - Health Care Select Sector SPDR
    ├── XLF  - Financial Select Sector SPDR
    ├── XLY  - Consumer Discretionary Select Sector SPDR
    ├── XLP  - Consumer Staples Select Sector SPDR
    ├── XLE  - Energy Select Sector SPDR
    ├── XLI  - Industrial Select Sector SPDR
    ├── XLU  - Utilities Select Sector SPDR
    ├── XLB  - Materials Select Sector SPDR
    ├── XLRE - Real Estate Select Sector SPDR
    └── XLC  - Communication Services Select Sector SPDR
```

**Assets:**
| Ticker | Name | Sector |
|--------|------|--------|
| XLK | Technology Select Sector SPDR | Technology |
| XLV | Health Care Select Sector SPDR | Healthcare |
| XLF | Financial Select Sector SPDR | Financials |
| XLY | Consumer Discretionary Select Sector SPDR | Consumer Disc. |
| XLP | Consumer Staples Select Sector SPDR | Consumer Staples |
| XLE | Energy Select Sector SPDR | Energy |
| XLI | Industrial Select Sector SPDR | Industrials |
| XLU | Utilities Select Sector SPDR | Utilities |
| XLB | Materials Select Sector SPDR | Materials |
| XLRE | Real Estate Select Sector SPDR | Real Estate |
| XLC | Communication Services Select Sector SPDR | Communication |

---

### 4. Dividend Aristocrats

**Category:** Income | **Difficulty:** Beginner
**Block Types:** Root, Group, Weight (Equal), Asset

Blue-chip companies with 25+ years of consecutive dividend increases. Focus on quality and income stability.

```
Root: "Dividend Aristocrats"
└── Group: "Aristocrats"
    └── WEIGHT Equal
        ├── JNJ  - Johnson & Johnson
        ├── PG   - Procter & Gamble
        ├── KO   - Coca-Cola
        ├── PEP  - PepsiCo
        ├── MMM  - 3M Company
        ├── ABT  - Abbott Laboratories
        ├── MCD  - McDonald's
        ├── WMT  - Walmart
        ├── CL   - Colgate-Palmolive
        └── EMR  - Emerson Electric
```

**Assets:**
| Ticker | Name | Sector |
|--------|------|--------|
| JNJ | Johnson & Johnson | Healthcare |
| PG | Procter & Gamble | Consumer Staples |
| KO | Coca-Cola | Consumer Staples |
| PEP | PepsiCo | Consumer Staples |
| MMM | 3M Company | Industrials |
| ABT | Abbott Laboratories | Healthcare |
| MCD | McDonald's | Consumer Disc. |
| WMT | Walmart | Consumer Staples |
| CL | Colgate-Palmolive | Consumer Staples |
| EMR | Emerson Electric | Industrials |

---

### 5. Tech Growth Portfolio

**Category:** Growth | **Difficulty:** Beginner
**Block Types:** Root, Group, Weight (Specified), Asset

Concentrated exposure to leading technology companies with specified weights based on conviction.

```
Root: "Tech Growth"
└── WEIGHT Specified
    ├── [25%] AAPL  - Apple Inc
    ├── [20%] MSFT  - Microsoft Corp
    ├── [20%] GOOGL - Alphabet Inc
    ├── [15%] AMZN  - Amazon.com Inc
    ├── [10%] NVDA  - NVIDIA Corp
    └── [10%] META  - Meta Platforms Inc
```

**Assets:**
| Ticker | Name | Allocation |
|--------|------|------------|
| AAPL | Apple Inc | 25% |
| MSFT | Microsoft Corp | 20% |
| GOOGL | Alphabet Inc | 20% |
| AMZN | Amazon.com Inc | 15% |
| NVDA | NVIDIA Corp | 10% |
| META | Meta Platforms Inc | 10% |

---

## Intermediate Templates

These templates introduce Groups for organization and advanced weight methods.

---

### 6. Core-Satellite Portfolio

**Category:** Hybrid | **Difficulty:** Intermediate
**Block Types:** Root, Group, Weight (Specified, Equal, Inverse Volatility), Asset

Stable core of index funds combined with satellite positions in higher-conviction plays.

```
Root: "Core-Satellite"
└── WEIGHT Specified
    │
    ├── [60%] Group: "Core Holdings"
    │   └── WEIGHT Equal
    │       ├── SPY  - SPDR S&P 500 ETF
    │       └── VTI  - Vanguard Total Stock Market ETF
    │
    ├── [25%] Group: "Growth Satellites"
    │   └── WEIGHT Inverse Volatility 30d
    │       ├── QQQ  - Invesco QQQ Trust
    │       └── ARKK - ARK Innovation ETF
    │
    └── [15%] Group: "Bonds"
        └── WEIGHT Equal
            ├── BND  - Vanguard Total Bond Market ETF
            └── TLT  - iShares 20+ Year Treasury ETF
```

**Assets:**
| Ticker | Name | Sleeve | Allocation |
|--------|------|--------|------------|
| SPY | SPDR S&P 500 ETF Trust | Core | 30% |
| VTI | Vanguard Total Stock Market ETF | Core | 30% |
| QQQ | Invesco QQQ Trust | Growth | ~12.5% |
| ARKK | ARK Innovation ETF | Growth | ~12.5% |
| BND | Vanguard Total Bond Market ETF | Bonds | 7.5% |
| TLT | iShares 20+ Year Treasury ETF | Bonds | 7.5% |

---

### 7. Risk Parity Basics

**Category:** Risk Parity | **Difficulty:** Intermediate
**Block Types:** Root, Weight (Inverse Volatility), Asset

Allocate based on risk contribution rather than capital. Lower volatility assets get higher allocations.

```
Root: "Risk Parity Basics"
└── WEIGHT Inverse Volatility 60d
    ├── SPY  - SPDR S&P 500 ETF
    ├── TLT  - iShares 20+ Year Treasury ETF
    ├── GLD  - SPDR Gold Shares
    └── DBC  - Invesco DB Commodity Index Fund
```

**Assets:**
| Ticker | Name | Asset Class |
|--------|------|-------------|
| SPY | SPDR S&P 500 ETF Trust | US Equity |
| TLT | iShares 20+ Year Treasury ETF | Long Bonds |
| GLD | SPDR Gold Shares | Commodities |
| DBC | Invesco DB Commodity Index Fund | Commodities |

---

### 8. Global Asset Allocation

**Category:** Diversified | **Difficulty:** Intermediate
**Block Types:** Root, Group, Weight (Specified, Equal), Asset

Globally diversified portfolio across geographies and asset classes.

```
Root: "Global Asset Allocation"
└── WEIGHT Specified
    │
    ├── [40%] Group: "US Equities"
    │   └── WEIGHT Equal
    │       ├── VTI  - Vanguard Total Stock Market ETF
    │       └── VTV  - Vanguard Value ETF
    │
    ├── [20%] Group: "International Equities"
    │   └── WEIGHT Equal
    │       ├── VEA  - Vanguard FTSE Developed Markets ETF
    │       └── VWO  - Vanguard FTSE Emerging Markets ETF
    │
    ├── [25%] Group: "Fixed Income"
    │   └── WEIGHT Equal
    │       ├── BND  - Vanguard Total Bond Market ETF
    │       ├── BNDX - Vanguard Total International Bond ETF
    │       └── TIP  - iShares TIPS Bond ETF
    │
    └── [15%] Group: "Alternatives"
        └── WEIGHT Equal
            ├── VNQ  - Vanguard Real Estate ETF
            └── GLD  - SPDR Gold Shares
```

**Assets:**
| Ticker | Name | Sleeve |
|--------|------|--------|
| VTI | Vanguard Total Stock Market ETF | US Equities |
| VTV | Vanguard Value ETF | US Equities |
| VEA | Vanguard FTSE Developed Markets ETF | International |
| VWO | Vanguard FTSE Emerging Markets ETF | International |
| BND | Vanguard Total Bond Market ETF | Fixed Income |
| BNDX | Vanguard Total International Bond ETF | Fixed Income |
| TIP | iShares TIPS Bond ETF | Fixed Income |
| VNQ | Vanguard Real Estate ETF | Alternatives |
| GLD | SPDR Gold Shares | Alternatives |

---

### 9. Bond Ladder Duration

**Category:** Fixed Income | **Difficulty:** Intermediate
**Block Types:** Root, Group, Weight (Inverse Volatility), Asset

Treasury bond ladder weighted by inverse volatility—more allocation to stable short-duration bonds.

```
Root: "Bond Ladder"
└── Group: "Treasury Ladder"
    └── WEIGHT Inverse Volatility 30d
        ├── SHY  - iShares 1-3 Year Treasury ETF
        ├── IEI  - iShares 3-7 Year Treasury ETF
        ├── IEF  - iShares 7-10 Year Treasury ETF
        ├── TLH  - iShares 10-20 Year Treasury ETF
        └── TLT  - iShares 20+ Year Treasury ETF
```

**Assets:**
| Ticker | Name | Duration |
|--------|------|----------|
| SHY | iShares 1-3 Year Treasury ETF | Short |
| IEI | iShares 3-7 Year Treasury ETF | Short-Intermediate |
| IEF | iShares 7-10 Year Treasury ETF | Intermediate |
| TLH | iShares 10-20 Year Treasury ETF | Long-Intermediate |
| TLT | iShares 20+ Year Treasury ETF | Long |

---

### 10. Factor Tilt Portfolio

**Category:** Factor | **Difficulty:** Intermediate
**Block Types:** Root, Group, Weight (Specified, Equal), Asset

Tilt portfolio towards academically-proven factors: value, momentum, quality, and low volatility.

```
Root: "Factor Tilt"
└── WEIGHT Specified
    │
    ├── [40%] Group: "Market Beta"
    │   └── VTI  - Vanguard Total Stock Market ETF
    │
    └── [60%] Group: "Factor Tilts"
        └── WEIGHT Equal
            ├── VLUE - iShares MSCI USA Value Factor ETF
            ├── MTUM - iShares MSCI USA Momentum Factor ETF
            ├── QUAL - iShares MSCI USA Quality Factor ETF
            └── USMV - iShares MSCI USA Min Vol Factor ETF
```

**Assets:**
| Ticker | Name | Factor |
|--------|------|--------|
| VTI | Vanguard Total Stock Market ETF | Market |
| VLUE | iShares MSCI USA Value Factor ETF | Value |
| MTUM | iShares MSCI USA Momentum Factor ETF | Momentum |
| QUAL | iShares MSCI USA Quality Factor ETF | Quality |
| USMV | iShares MSCI USA Min Vol Factor ETF | Low Vol |

---

### 11. Momentum Sectors

**Category:** Momentum | **Difficulty:** Intermediate
**Block Types:** Root, Weight (Momentum), Asset

Weight sectors by recent momentum—more allocation to sectors with stronger recent performance.

```
Root: "Momentum Sectors"
└── WEIGHT Momentum 90d
    ├── XLK  - Technology Select Sector SPDR
    ├── XLV  - Health Care Select Sector SPDR
    ├── XLF  - Financial Select Sector SPDR
    ├── XLY  - Consumer Discretionary Select Sector SPDR
    ├── XLE  - Energy Select Sector SPDR
    ├── XLI  - Industrial Select Sector SPDR
    └── XLC  - Communication Services Select Sector SPDR
```

**Assets:**
| Ticker | Name | Sector |
|--------|------|--------|
| XLK | Technology Select Sector SPDR | Technology |
| XLV | Health Care Select Sector SPDR | Healthcare |
| XLF | Financial Select Sector SPDR | Financials |
| XLY | Consumer Discretionary Select Sector SPDR | Consumer Disc. |
| XLE | Energy Select Sector SPDR | Energy |
| XLI | Industrial Select Sector SPDR | Industrials |
| XLC | Communication Services Select Sector SPDR | Communication |

---

### 12. Income Focus

**Category:** Income | **Difficulty:** Intermediate
**Block Types:** Root, Group, Weight (Specified, Equal), Asset

Maximize income through dividends, REITs, and high-yield bonds.

```
Root: "Income Focus"
└── WEIGHT Specified
    │
    ├── [40%] Group: "Dividend Stocks"
    │   └── WEIGHT Equal
    │       ├── VYM  - Vanguard High Dividend Yield ETF
    │       ├── SCHD - Schwab US Dividend Equity ETF
    │       └── HDV  - iShares Core High Dividend ETF
    │
    ├── [30%] Group: "REITs"
    │   └── WEIGHT Equal
    │       ├── VNQ  - Vanguard Real Estate ETF
    │       └── VNQI - Vanguard Global ex-US Real Estate ETF
    │
    └── [30%] Group: "Bonds"
        └── WEIGHT Equal
            ├── HYG  - iShares iBoxx $ High Yield Corporate Bond ETF
            ├── LQD  - iShares iBoxx $ Investment Grade Corporate Bond ETF
            └── EMB  - iShares JP Morgan USD Emerging Markets Bond ETF
```

**Assets:**
| Ticker | Name | Sleeve |
|--------|------|--------|
| VYM | Vanguard High Dividend Yield ETF | Dividend Stocks |
| SCHD | Schwab US Dividend Equity ETF | Dividend Stocks |
| HDV | iShares Core High Dividend ETF | Dividend Stocks |
| VNQ | Vanguard Real Estate ETF | REITs |
| VNQI | Vanguard Global ex-US Real Estate ETF | REITs |
| HYG | iShares iBoxx $ High Yield Corporate Bond ETF | Bonds |
| LQD | iShares iBoxx $ Investment Grade Corporate Bond ETF | Bonds |
| EMB | iShares JP Morgan USD Emerging Markets Bond ETF | Bonds |

---

## Advanced Templates

These templates introduce conditional logic with IF/ELSE blocks.

---

### 13. Simple Trend Following

**Category:** Tactical | **Difficulty:** Advanced
**Block Types:** Root, Weight (Specified), If, Else, Asset

Basic trend following: stay invested when above the 200-day moving average, move to bonds when below.

```
Root: "Simple Trend Following"
└── WEIGHT Specified
    │
    ├── [100%] IF SPY > SMA(200)
    │   └── SPY  - SPDR S&P 500 ETF
    │
    └── [100%] ELSE
        └── SHY  - iShares 1-3 Year Treasury ETF
```

**Logic:**
- When SPY is above its 200-day SMA → 100% SPY
- When SPY is below its 200-day SMA → 100% SHY (cash equivalent)

---

### 14. Dual Moving Average

**Category:** Tactical | **Difficulty:** Advanced
**Block Types:** Root, Group, Weight (Specified), If, Else, Asset

Cross-over strategy: bullish when short-term average crosses above long-term average.

```
Root: "Dual Moving Average"
└── WEIGHT Specified
    │
    ├── [70%] Group: "Equities"
    │   ├── IF SMA(SPY, 50) > SMA(SPY, 200)
    │   │   └── WEIGHT Equal
    │   │       ├── QQQ  - Invesco QQQ Trust
    │   │       └── SPY  - SPDR S&P 500 ETF
    │   │
    │   └── ELSE
    │       └── SHY  - iShares 1-3 Year Treasury ETF
    │
    └── [30%] Group: "Bonds"
        └── WEIGHT Equal
            ├── BND  - Vanguard Total Bond Market ETF
            └── TIP  - iShares TIPS Bond ETF
```

**Logic:**
- When 50-day SMA > 200-day SMA (Golden Cross) → Risk-on equities
- When 50-day SMA < 200-day SMA (Death Cross) → Defensive cash

---

### 15. RSI Mean Reversion

**Category:** Mean Reversion | **Difficulty:** Advanced
**Block Types:** Root, Group, Weight (Specified), If, Else, Asset

Counter-trend strategy: buy oversold conditions, reduce exposure when overbought.

```
Root: "RSI Mean Reversion"
└── WEIGHT Specified
    │
    ├── [70%] Group: "Tactical Equity"
    │   ├── IF RSI(SPY, 14) < 30
    │   │   └── WEIGHT Specified
    │   │       ├── [70%] UPRO - ProShares UltraPro S&P 500 (3x)
    │   │       └── [30%] TQQQ - ProShares UltraPro QQQ (3x)
    │   │
    │   └── ELSE
    │       ├── IF RSI(SPY, 14) > 70
    │       │   └── SHY  - iShares 1-3 Year Treasury ETF
    │       │
    │       └── ELSE
    │           └── SPY  - SPDR S&P 500 ETF
    │
    └── [30%] Group: "Stable Core"
        └── WEIGHT Equal
            ├── BND  - Vanguard Total Bond Market ETF
            └── GLD  - SPDR Gold Shares
```

**Logic:**
- RSI < 30 (Oversold) → Leveraged long position
- RSI > 70 (Overbought) → Defensive cash
- RSI 30-70 (Neutral) → Standard equity exposure

---

### 16. Volatility Regime

**Category:** Tactical | **Difficulty:** Advanced
**Block Types:** Root, Weight (Specified), If, Else, Group, Asset

Adjust allocation based on VIX levels—reduce risk in high volatility environments.

```
Root: "Volatility Regime"
└── WEIGHT Specified
    │
    ├── [60%] Group: "Equity Allocation"
    │   ├── IF VIX < 20
    │   │   └── WEIGHT Momentum 30d
    │   │       ├── QQQ  - Invesco QQQ Trust
    │   │       ├── SMH  - VanEck Semiconductor ETF
    │   │       └── XLK  - Technology Select Sector SPDR
    │   │
    │   └── ELSE
    │       └── WEIGHT Inverse Volatility 30d
    │           ├── XLP  - Consumer Staples Select Sector SPDR
    │           ├── XLU  - Utilities Select Sector SPDR
    │           └── XLV  - Health Care Select Sector SPDR
    │
    └── [40%] Group: "Safe Haven"
        └── WEIGHT Equal
            ├── TLT  - iShares 20+ Year Treasury ETF
            └── GLD  - SPDR Gold Shares
```

**Logic:**
- VIX < 20 (Low Vol) → Aggressive growth with momentum weighting
- VIX >= 20 (High Vol) → Defensive sectors with inverse vol weighting

---

### 17. Seasonal Rotation

**Category:** Tactical | **Difficulty:** Advanced
**Block Types:** Root, Weight (Specified), If, Else, Asset

"Sell in May" strategy—adjust allocation based on historically strong/weak periods.

```
Root: "Seasonal Rotation"
└── WEIGHT Specified
    │
    ├── [80%] Group: "Seasonal Equity"
    │   ├── IF MONTH >= 11 OR MONTH <= 4
    │   │   └── WEIGHT Equal
    │   │       ├── SPY  - SPDR S&P 500 ETF
    │   │       ├── QQQ  - Invesco QQQ Trust
    │   │       └── IWM  - iShares Russell 2000 ETF
    │   │
    │   └── ELSE
    │       └── WEIGHT Equal
    │           ├── XLP  - Consumer Staples Select Sector SPDR
    │           └── XLU  - Utilities Select Sector SPDR
    │
    └── [20%] BND  - Vanguard Total Bond Market ETF
```

**Logic:**
- November through April → Full equity exposure (historically strong)
- May through October → Defensive sectors (historically weak)

---

### 18. Risk-On/Risk-Off Tactical

**Category:** Tactical | **Difficulty:** Advanced
**Block Types:** Root, Group, Weight (Specified, Equal, Momentum, Inverse Volatility), Asset, If, Else

Switch between aggressive growth and defensive positions based on market regime.

```
Root: "Risk-On/Risk-Off Tactical"
└── WEIGHT Specified
    │
    ├── [35%] IF SPY > SMA(200)
    │   └── WEIGHT Specified
    │       │
    │       ├── [60%] Group: "Growth Core"
    │       │   └── WEIGHT Equal
    │       │       ├── QQQ   - Invesco QQQ Trust
    │       │       ├── ARKK  - ARK Innovation ETF
    │       │       └── SMH   - VanEck Semiconductor ETF
    │       │
    │       └── [40%] Group: "High Beta"
    │           └── WEIGHT Momentum 90d
    │               ├── TSLA  - Tesla Inc
    │               ├── NVDA  - NVIDIA Corp
    │               └── AMD   - Advanced Micro Devices
    │
    ├── [35%] ELSE
    │   └── WEIGHT Specified
    │       │
    │       ├── [50%] Group: "Treasury Safety"
    │       │   └── WEIGHT Inverse Volatility 30d
    │       │       ├── TLT   - iShares 20+ Year Treasury
    │       │       ├── IEF   - iShares 7-10 Year Treasury
    │       │       └── SHY   - iShares 1-3 Year Treasury
    │       │
    │       ├── [30%] Group: "Defensive Equity"
    │       │   └── WEIGHT Equal
    │       │       ├── XLU   - Utilities Select Sector SPDR
    │       │       └── XLP   - Consumer Staples Select Sector SPDR
    │       │
    │       └── [20%] GLD - SPDR Gold Shares
    │
    └── [30%] Group: "Always-On Core"
        └── WEIGHT Equal
            ├── VTI   - Vanguard Total Stock Market ETF
            └── BND   - Vanguard Total Bond Market ETF
```

---

### 19. Inflation Hedge Dynamic

**Category:** Tactical | **Difficulty:** Advanced
**Block Types:** Root, Group, Weight (Specified, Equal), If, Else, Asset

Dynamically adjust inflation hedges based on gold trend as inflation proxy.

```
Root: "Inflation Hedge Dynamic"
└── WEIGHT Specified
    │
    ├── [50%] Group: "Equities"
    │   └── WEIGHT Equal
    │       ├── VTI  - Vanguard Total Stock Market ETF
    │       └── VEA  - Vanguard FTSE Developed Markets ETF
    │
    ├── [30%] Group: "Inflation Hedges"
    │   ├── IF GLD > SMA(50)
    │   │   └── WEIGHT Specified
    │   │       ├── [40%] GLD  - SPDR Gold Shares
    │   │       ├── [30%] SLV  - iShares Silver Trust
    │   │       └── [30%] DBC  - Invesco DB Commodity Index Fund
    │   │
    │   └── ELSE
    │       └── WEIGHT Equal
    │           ├── TIP  - iShares TIPS Bond ETF
    │           └── VNQ  - Vanguard Real Estate ETF
    │
    └── [20%] Group: "Nominal Bonds"
        └── WEIGHT Equal
            ├── BND  - Vanguard Total Bond Market ETF
            └── BNDX - Vanguard Total International Bond ETF
```

**Logic:**
- Gold trending up → Overweight commodities (inflation rising)
- Gold trending down → TIPS and REITs (stable inflation)

---

### 20. Multi-Asset Momentum

**Category:** Momentum | **Difficulty:** Advanced
**Block Types:** Root, Group, Weight (Specified, Momentum), If, Else, Asset

Apply momentum across multiple asset classes with crash protection.

```
Root: "Multi-Asset Momentum"
└── WEIGHT Specified
    │
    ├── [40%] Group: "Equity Momentum"
    │   ├── IF SPY > SMA(200)
    │   │   └── WEIGHT Momentum 60d
    │   │       ├── SPY  - SPDR S&P 500 ETF
    │   │       ├── QQQ  - Invesco QQQ Trust
    │   │       ├── IWM  - iShares Russell 2000 ETF
    │   │       └── EFA  - iShares MSCI EAFE ETF
    │   │
    │   └── ELSE
    │       └── SHY  - iShares 1-3 Year Treasury ETF
    │
    ├── [30%] Group: "Fixed Income"
    │   └── WEIGHT Momentum 30d
    │       ├── TLT  - iShares 20+ Year Treasury ETF
    │       ├── LQD  - iShares Investment Grade Corporate Bond ETF
    │       └── HYG  - iShares High Yield Corporate Bond ETF
    │
    └── [30%] Group: "Alternatives"
        └── WEIGHT Momentum 60d
            ├── GLD  - SPDR Gold Shares
            ├── DBC  - Invesco DB Commodity Index Fund
            └── VNQ  - Vanguard Real Estate ETF
```

---

## Expert Templates

These templates use advanced features including Filters for dynamic asset selection.

---

### 21. Multi-Factor Sector Rotation

**Category:** Factor | **Difficulty:** Expert
**Block Types:** Root, Group, Weight (Specified, Min Variance, Momentum, Equal, Inverse Volatility), Asset, If, Else, Filter

Combine momentum-based stock selection with factor investing and conditional sector rotation.

```
Root: "Multi-Factor Sector Rotation"
└── WEIGHT Specified
    │
    ├── [30%] Group: "Momentum Leaders"
    │   └── FILTER Top 10 by Momentum (6m) from S&P 500
    │
    ├── [30%] Group: "Quality Value"
    │   └── WEIGHT Min Variance 60d
    │       ├── BRK.B - Berkshire Hathaway Inc
    │       ├── JPM   - JPMorgan Chase & Co
    │       ├── JNJ   - Johnson & Johnson
    │       ├── PG    - Procter & Gamble Co
    │       └── UNH   - UnitedHealth Group Inc
    │
    ├── [20%] Group: "Sector ETFs"
    │   │
    │   ├── IF RSI(XLK, 14) < 70
    │   │   └── WEIGHT Momentum 30d
    │   │       ├── XLK   - Technology Select Sector SPDR
    │   │       ├── XLV   - Health Care Select Sector SPDR
    │   │       ├── XLF   - Financial Select Sector SPDR
    │   │       └── XLE   - Energy Select Sector SPDR
    │   │
    │   └── ELSE
    │       └── WEIGHT Equal
    │           ├── XLP   - Consumer Staples Select Sector SPDR
    │           └── XLU   - Utilities Select Sector SPDR
    │
    └── [20%] Group: "International"
        └── WEIGHT Inverse Volatility 30d
            ├── VEA   - Vanguard FTSE Developed Markets ETF
            ├── VWO   - Vanguard FTSE Emerging Markets ETF
            └── EFA   - iShares MSCI EAFE ETF
```

---

### 22. All-Weather Vol-Target

**Category:** All-Weather | **Difficulty:** Expert
**Block Types:** Root, Group, Weight (Specified, Equal, Inverse Volatility, Market Cap, Min Variance), Asset, If, Else

Ray Dalio-inspired portfolio with volatility targeting and conditional commodity exposure.

```
Root: "All-Weather Vol-Target"
└── WEIGHT Specified
    │
    ├── [40%] Group: "Equity Sleeve"
    │   └── WEIGHT Inverse Volatility 60d
    │       │
    │       ├── Group: "US Large Cap"
    │       │   └── WEIGHT Market Cap
    │       │       ├── SPY   - SPDR S&P 500 ETF Trust
    │       │       ├── IWM   - iShares Russell 2000 ETF
    │       │       └── MDY   - SPDR S&P MidCap 400 ETF
    │       │
    │       └── Group: "Factor Tilt"
    │           └── WEIGHT Equal
    │               ├── MTUM  - iShares MSCI USA Momentum Factor ETF
    │               ├── QUAL  - iShares MSCI USA Quality Factor ETF
    │               └── VLUE  - iShares MSCI USA Value Factor ETF
    │
    ├── [30%] Group: "Fixed Income"
    │   └── WEIGHT Specified
    │       │
    │       ├── [50%] Group: "Duration Ladder"
    │       │   └── WEIGHT Inverse Volatility 30d
    │       │       ├── SHY   - iShares 1-3 Year Treasury Bond ETF
    │       │       ├── IEF   - iShares 7-10 Year Treasury Bond ETF
    │       │       └── TLT   - iShares 20+ Year Treasury Bond ETF
    │       │
    │       ├── [30%] Group: "Credit"
    │       │   └── WEIGHT Equal
    │       │       ├── LQD   - iShares Investment Grade Corporate Bond ETF
    │       │       └── HYG   - iShares High Yield Corporate Bond ETF
    │       │
    │       └── [20%] TIP - iShares TIPS Bond ETF
    │
    ├── [15%] Group: "Real Assets"
    │   │
    │   ├── IF GLD > SMA(50)
    │   │   └── WEIGHT Specified
    │   │       ├── [40%] GLD - SPDR Gold Shares
    │   │       ├── [30%] SLV - iShares Silver Trust
    │   │       └── [30%] DBC - Invesco DB Commodity Index Fund
    │   │
    │   └── ELSE
    │       └── WEIGHT Equal
    │           ├── GLD   - SPDR Gold Shares
    │           └── VNQ   - Vanguard Real Estate ETF
    │
    └── [15%] Group: "Alternatives"
        └── WEIGHT Min Variance 90d
            ├── DBMF  - iMGP DBi Managed Futures Strategy ETF
            └── BTAL  - AGFiQ US Market Neutral Anti-Beta Fund
```

---

### 23. Quantitative Value

**Category:** Factor | **Difficulty:** Expert
**Block Types:** Root, Group, Weight (Specified, Min Variance), Filter, If, Else, Asset

Systematic value investing using filters for cheap stocks with quality metrics.

```
Root: "Quantitative Value"
└── WEIGHT Specified
    │
    ├── [40%] Group: "Deep Value"
    │   └── FILTER Top 20 by Value (P/E) from S&P 500
    │
    ├── [30%] Group: "Quality Value"
    │   └── FILTER Top 15 by Quality+Value from S&P 500
    │
    ├── [20%] Group: "Value ETFs"
    │   ├── IF SPY > SMA(200)
    │   │   └── WEIGHT Min Variance 60d
    │   │       ├── VTV  - Vanguard Value ETF
    │   │       ├── IWD  - iShares Russell 1000 Value ETF
    │   │       └── VOOV - Vanguard S&P 500 Value ETF
    │   │
    │   └── ELSE
    │       └── SHY  - iShares 1-3 Year Treasury ETF
    │
    └── [10%] BND  - Vanguard Total Bond Market ETF
```

---

### 24. Adaptive Asset Allocation

**Category:** Tactical | **Difficulty:** Expert
**Block Types:** Root, Group, Weight (Specified, Momentum, Inverse Volatility), If, Else, Asset

Dynamically adjust allocation based on multiple market regime indicators.

```
Root: "Adaptive Asset Allocation"
└── WEIGHT Specified
    │
    ├── [50%] Group: "Dynamic Equity"
    │   ├── IF SPY > SMA(200) AND VIX < 25
    │   │   └── WEIGHT Momentum 60d
    │   │       ├── QQQ   - Invesco QQQ Trust
    │   │       ├── SMH   - VanEck Semiconductor ETF
    │   │       ├── XLY   - Consumer Discretionary Select Sector SPDR
    │   │       └── IWM   - iShares Russell 2000 ETF
    │   │
    │   └── ELSE
    │       ├── IF SPY > SMA(200)
    │       │   └── WEIGHT Equal
    │       │       ├── SPY  - SPDR S&P 500 ETF
    │       │       └── XLP  - Consumer Staples Select Sector SPDR
    │       │
    │       └── ELSE
    │           └── WEIGHT Equal
    │               ├── SHY  - iShares 1-3 Year Treasury ETF
    │               └── GLD  - SPDR Gold Shares
    │
    ├── [30%] Group: "Adaptive Fixed Income"
    │   ├── IF TLT > SMA(50)
    │   │   └── WEIGHT Inverse Volatility 30d
    │   │       ├── TLT  - iShares 20+ Year Treasury ETF
    │   │       └── IEF  - iShares 7-10 Year Treasury ETF
    │   │
    │   └── ELSE
    │       └── WEIGHT Equal
    │           ├── SHY  - iShares 1-3 Year Treasury ETF
    │           └── TIP  - iShares TIPS Bond ETF
    │
    └── [20%] Group: "Tail Hedge"
        └── WEIGHT Equal
            ├── GLD   - SPDR Gold Shares
            └── DBMF  - iMGP DBi Managed Futures Strategy ETF
```

**Logic:**
- Bull market + Low volatility → Aggressive momentum
- Bull market + High volatility → Moderate equity
- Bear market → Defensive cash and gold

---

### 25. Global Tactical Asset Allocation (GTAA)

**Category:** Tactical | **Difficulty:** Expert
**Block Types:** Root, Group, Weight (Specified, Momentum, Inverse Volatility), If, Else, Asset

Meb Faber-inspired global tactical allocation with trend following across all asset classes.

```
Root: "Global Tactical (GTAA)"
└── WEIGHT Specified
    │
    ├── [25%] Group: "US Equity"
    │   ├── IF SPY > SMA(200)
    │   │   └── SPY  - SPDR S&P 500 ETF
    │   └── ELSE
    │       └── SHY  - iShares 1-3 Year Treasury ETF
    │
    ├── [25%] Group: "International Equity"
    │   ├── IF EFA > SMA(200)
    │   │   └── WEIGHT Momentum 60d
    │   │       ├── EFA  - iShares MSCI EAFE ETF
    │   │       └── VWO  - Vanguard FTSE Emerging Markets ETF
    │   └── ELSE
    │       └── SHY  - iShares 1-3 Year Treasury ETF
    │
    ├── [20%] Group: "Fixed Income"
    │   ├── IF TLT > SMA(200)
    │   │   └── WEIGHT Inverse Volatility 30d
    │   │       ├── TLT  - iShares 20+ Year Treasury ETF
    │   │       └── LQD  - iShares Investment Grade Corporate Bond ETF
    │   └── ELSE
    │       └── SHY  - iShares 1-3 Year Treasury ETF
    │
    ├── [15%] Group: "Commodities"
    │   ├── IF GLD > SMA(200)
    │   │   └── WEIGHT Equal
    │   │       ├── GLD  - SPDR Gold Shares
    │   │       └── DBC  - Invesco DB Commodity Index Fund
    │   └── ELSE
    │       └── SHY  - iShares 1-3 Year Treasury ETF
    │
    └── [15%] Group: "Real Estate"
        ├── IF VNQ > SMA(200)
        │   └── VNQ  - Vanguard Real Estate ETF
        └── ELSE
            └── SHY  - iShares 1-3 Year Treasury ETF
```

---

## Crypto Templates

These templates focus on cryptocurrency allocation. Due to crypto's high volatility and 24/7 trading, these strategies require careful risk management.

> **Note**: Crypto assets are available through Alpaca's crypto trading. These templates use crypto ETFs and direct crypto where available.

---

### 26. Crypto Core Portfolio

**Category:** Passive Crypto | **Difficulty:** Beginner
**Block Types:** Root, Weight (Specified), Asset

Simple, diversified crypto exposure weighted by market dominance.

```
Root: "Crypto Core"
└── WEIGHT Specified
    ├── [50%] BTC  - Bitcoin
    ├── [30%] ETH  - Ethereum
    └── [20%] SOL  - Solana
```

**Assets:**
| Ticker | Name | Allocation |
|--------|------|------------|
| BTC | Bitcoin | 50% |
| ETH | Ethereum | 30% |
| SOL | Solana | 20% |

**Risk Notes:**
- Extreme volatility (50%+ drawdowns common)
- 24/7 market requires stop-losses or automated management
- Consider limiting to 5-10% of total portfolio

---

### 27. Crypto with Stablecoin Buffer

**Category:** Defensive Crypto | **Difficulty:** Intermediate
**Block Types:** Root, Group, Weight (Specified, Inverse Volatility), Asset, If, Else

Crypto exposure with automatic de-risking based on Bitcoin's trend.

```
Root: "Crypto with Buffer"
└── WEIGHT Specified
    │
    ├── [70%] Group: "Crypto Allocation"
    │   ├── IF BTC > SMA(50)
    │   │   └── WEIGHT Inverse Volatility 30d
    │   │       ├── BTC  - Bitcoin
    │   │       ├── ETH  - Ethereum
    │   │       └── SOL  - Solana
    │   │
    │   └── ELSE
    │       └── WEIGHT Specified
    │           ├── [50%] BTC  - Bitcoin
    │           └── [50%] USDC - USD Coin
    │
    └── [30%] USDC - USD Coin
```

**Logic:**
- BTC above 50-day SMA → Full crypto allocation with risk parity
- BTC below 50-day SMA → 50% BTC, 50% stablecoin (defensive)
- Always maintain 30% stablecoin buffer

---

### 28. Crypto + Traditional Hybrid

**Category:** Hybrid | **Difficulty:** Intermediate
**Block Types:** Root, Group, Weight (Specified, Equal), Asset

Blend crypto with traditional assets for a balanced risk profile.

```
Root: "Crypto Hybrid"
└── WEIGHT Specified
    │
    ├── [15%] Group: "Crypto"
    │   └── WEIGHT Equal
    │       ├── BTC  - Bitcoin
    │       └── ETH  - Ethereum
    │
    ├── [50%] Group: "Equities"
    │   └── WEIGHT Equal
    │       ├── VTI  - Vanguard Total Stock Market ETF
    │       └── VXUS - Vanguard Total International Stock ETF
    │
    ├── [25%] Group: "Bonds"
    │   └── WEIGHT Equal
    │       ├── BND  - Vanguard Total Bond Market ETF
    │       └── TIP  - iShares TIPS Bond ETF
    │
    └── [10%] GLD  - SPDR Gold Shares
```

**Assets:**
| Ticker | Name | Sleeve | Allocation |
|--------|------|--------|------------|
| BTC | Bitcoin | Crypto | 7.5% |
| ETH | Ethereum | Crypto | 7.5% |
| VTI | Vanguard Total Stock Market | Equities | 25% |
| VXUS | Vanguard Total International | Equities | 25% |
| BND | Vanguard Total Bond Market | Bonds | 12.5% |
| TIP | iShares TIPS Bond ETF | Bonds | 12.5% |
| GLD | SPDR Gold Shares | Alternatives | 10% |

**Risk Notes:**
- 15% crypto exposure adds meaningful upside with contained risk
- Traditional assets provide stability during crypto drawdowns
- Rebalancing captures crypto volatility premium

---

### 29. DeFi Blue Chips

**Category:** Thematic Crypto | **Difficulty:** Advanced
**Block Types:** Root, Weight (Equal), Asset

Exposure to established DeFi protocols and infrastructure.

```
Root: "DeFi Blue Chips"
└── WEIGHT Equal
    ├── ETH   - Ethereum (base layer)
    ├── SOL   - Solana (alt L1)
    ├── AVAX  - Avalanche
    ├── LINK  - Chainlink (oracle)
    └── UNI   - Uniswap (DEX)
```

**Assets:**
| Ticker | Name | Category |
|--------|------|----------|
| ETH | Ethereum | Smart Contract Platform |
| SOL | Solana | Smart Contract Platform |
| AVAX | Avalanche | Smart Contract Platform |
| LINK | Chainlink | Oracle Network |
| UNI | Uniswap | Decentralized Exchange |

**Risk Notes:**
- Higher risk than BTC/ETH-only portfolios
- Protocol-specific risks (smart contract bugs, governance)
- Highly correlated—expect 70%+ drawdowns in bear markets

---

### 30. Crypto Trend Following

**Category:** Tactical Crypto | **Difficulty:** Expert
**Block Types:** Root, Group, Weight (Specified, Momentum), Asset, If, Else

Aggressive trend following with full exit during bear markets.

```
Root: "Crypto Trend Following"
└── WEIGHT Specified
    │
    ├── [100%] IF BTC > SMA(200) AND ETH > SMA(200)
    │   └── Group: "Risk-On Crypto"
    │       └── WEIGHT Momentum 30d
    │           ├── BTC  - Bitcoin
    │           ├── ETH  - Ethereum
    │           ├── SOL  - Solana
    │           ├── AVAX - Avalanche
    │           └── LINK - Chainlink
    │
    └── [100%] ELSE
        └── USDC - USD Coin
```

**Logic:**
- Both BTC and ETH above 200-day SMA → Full allocation to momentum-weighted crypto
- Either below 200-day SMA → 100% stablecoin (full exit)

**Historical Context:**
- This approach would have avoided most of 2022's 70% drawdown
- But misses initial rallies as trend confirmation lags
- High turnover during choppy periods

---

## Template Summary

| # | Template | Category | Difficulty | Key Blocks |
|---|----------|----------|------------|------------|
| 1 | Classic 60/40 | Passive | Beginner | Weight Specified |
| 2 | Three-Fund Portfolio | Passive | Beginner | Weight Specified |
| 3 | Equal Weight Sectors | Passive | Beginner | Weight Equal |
| 4 | Dividend Aristocrats | Income | Beginner | Group, Weight Equal |
| 5 | Tech Growth | Growth | Beginner | Weight Specified |
| 6 | Core-Satellite | Hybrid | Intermediate | Group, Weight Inverse Vol |
| 7 | Risk Parity Basics | Risk Parity | Intermediate | Weight Inverse Vol |
| 8 | Global Asset Allocation | Diversified | Intermediate | Group, Weight Specified/Equal |
| 9 | Bond Ladder | Fixed Income | Intermediate | Weight Inverse Vol |
| 10 | Factor Tilt | Factor | Intermediate | Group, Weight Equal |
| 11 | Momentum Sectors | Momentum | Intermediate | Weight Momentum |
| 12 | Income Focus | Income | Intermediate | Group, Weight Specified/Equal |
| 13 | Simple Trend Following | Tactical | Advanced | If, Else |
| 14 | Dual Moving Average | Tactical | Advanced | If, Else, Group |
| 15 | RSI Mean Reversion | Mean Reversion | Advanced | If, Else (nested) |
| 16 | Volatility Regime | Tactical | Advanced | If, Else, Weight Momentum |
| 17 | Seasonal Rotation | Tactical | Advanced | If, Else |
| 18 | Risk-On/Risk-Off | Tactical | Advanced | If, Else, Multiple Weights |
| 19 | Inflation Hedge Dynamic | Tactical | Advanced | If, Else |
| 20 | Multi-Asset Momentum | Momentum | Advanced | If, Else, Weight Momentum |
| 21 | Multi-Factor Rotation | Factor | Expert | Filter, If, Else, Min Variance |
| 22 | All-Weather Vol-Target | All-Weather | Expert | If, Else, Multiple Weights, Market Cap |
| 23 | Quantitative Value | Factor | Expert | Filter, If, Else, Min Variance |
| 24 | Adaptive Allocation | Tactical | Expert | Nested If/Else, Multiple Conditions |
| 25 | Global Tactical (GTAA) | Tactical | Expert | Multiple If/Else per asset class |
| 26 | Crypto Core | Passive Crypto | Beginner | Weight Specified |
| 27 | Crypto with Buffer | Defensive Crypto | Intermediate | If, Else, Inverse Vol |
| 28 | Crypto Hybrid | Hybrid | Intermediate | Group, Weight Equal |
| 29 | DeFi Blue Chips | Thematic Crypto | Advanced | Weight Equal |
| 30 | Crypto Trend Following | Tactical Crypto | Expert | If, Else, Weight Momentum |

---

## Block Type Coverage

| Block Type | Templates Using It |
|------------|-------------------|
| Root | All |
| Group | 4, 6, 8-12, 14-25 |
| Weight (Specified) | 1-3, 5, 6, 8, 12-25 |
| Weight (Equal) | 3, 4, 6, 8-10, 12, 14, 17-25 |
| Weight (Inverse Vol) | 6, 7, 9, 16, 19-22, 24, 25 |
| Weight (Momentum) | 11, 16, 18, 20, 21, 24, 25 |
| Weight (Market Cap) | 22 |
| Weight (Min Variance) | 18, 21-23 |
| Asset | All |
| If/Else | 13-25 |
| Filter | 21, 23 |
