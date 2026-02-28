# Strategy Builder Examples

This document contains real-world trading strategy examples that demonstrate all available block types in the LlamaTrade Strategy Builder.

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

- **Specified** - Fixed percentage allocations
- **Equal** - Split evenly across children
- **Inverse Volatility** - Risk parity weighting (requires lookback)
- **Market Cap** - Cap-weighted allocation
- **Momentum** - Momentum-weighted (requires lookback)
- **Min Variance** - Minimum variance optimization (requires lookback)

---

## Strategy 1: Risk-On/Risk-Off Tactical Allocation

**Category:** Tactical
**Difficulty:** Advanced
**Block Types Used:** Root, Group, Weight (Specified, Equal, Momentum, Inverse Volatility), Asset, If, Else

### Concept

Switch between aggressive growth positions and defensive positions based on market regime. When SPY is above its 200-day SMA (bullish), allocate to growth and high-beta assets. When below (bearish), shift to treasuries, defensive sectors, and gold.

### Structure

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

### Rationale

- **Risk-On (70% of conditional):** When markets are bullish, overweight growth (QQQ, ARKK, SMH) and high-beta momentum names (TSLA, NVDA, AMD)
- **Risk-Off (70% of conditional):** When markets turn bearish, rotate into treasuries with inverse volatility weighting (more to shorter duration), defensive sectors, and gold as a hedge
- **Always-On Core (30%):** Maintain 60/40 VTI/BND baseline regardless of market regime for stability

### Assets Used

| Ticker | Name | Exchange | Sleeve |
|--------|------|----------|--------|
| QQQ | Invesco QQQ Trust | NASDAQ | Growth Core |
| ARKK | ARK Innovation ETF | NYSEARCA | Growth Core |
| SMH | VanEck Semiconductor ETF | NYSEARCA | Growth Core |
| TSLA | Tesla Inc | NASDAQ | High Beta |
| NVDA | NVIDIA Corp | NASDAQ | High Beta |
| AMD | Advanced Micro Devices | NASDAQ | High Beta |
| TLT | iShares 20+ Year Treasury Bond ETF | NASDAQ | Treasury Safety |
| IEF | iShares 7-10 Year Treasury Bond ETF | NASDAQ | Treasury Safety |
| SHY | iShares 1-3 Year Treasury Bond ETF | NASDAQ | Treasury Safety |
| XLU | Utilities Select Sector SPDR | NYSEARCA | Defensive Equity |
| XLP | Consumer Staples Select Sector SPDR | NYSEARCA | Defensive Equity |
| GLD | SPDR Gold Shares | NYSEARCA | Safe Haven |
| VTI | Vanguard Total Stock Market ETF | NYSEARCA | Core |
| BND | Vanguard Total Bond Market ETF | NYSEARCA | Core |

---

## Strategy 2: Multi-Factor Sector Rotation

**Category:** Factor
**Difficulty:** Advanced
**Block Types Used:** Root, Group, Weight (Specified, Equal, Momentum, Inverse Volatility, Min Variance), Asset, If, Else, Filter

### Concept

Combine momentum-based stock selection with factor investing and conditional sector rotation. Uses filters to dynamically select top-performing stocks, min-variance weighting for quality value names, and conditional logic for sector ETF allocation.

### Structure

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

### Rationale

- **Momentum Leaders (30%):** Dynamically select top 10 momentum stocks from S&P 500 over 6-month lookback
- **Quality Value (30%):** Blue-chip value names weighted by minimum variance to reduce volatility
- **Sector ETFs (20%):** When tech isn't overbought (RSI < 70), weight sectors by momentum; otherwise rotate to defensive sectors
- **International (20%):** Diversify globally with inverse volatility weighting for risk parity

### Assets Used

| Ticker | Name | Exchange | Sleeve |
|--------|------|----------|--------|
| BRK.B | Berkshire Hathaway Inc | NYSE | Quality Value |
| JPM | JPMorgan Chase & Co | NYSE | Quality Value |
| JNJ | Johnson & Johnson | NYSE | Quality Value |
| PG | Procter & Gamble Co | NYSE | Quality Value |
| UNH | UnitedHealth Group Inc | NYSE | Quality Value |
| XLK | Technology Select Sector SPDR | NYSEARCA | Sector ETFs |
| XLV | Health Care Select Sector SPDR | NYSEARCA | Sector ETFs |
| XLF | Financial Select Sector SPDR | NYSEARCA | Sector ETFs |
| XLE | Energy Select Sector SPDR | NYSEARCA | Sector ETFs |
| XLP | Consumer Staples Select Sector SPDR | NYSEARCA | Sector ETFs (Defensive) |
| XLU | Utilities Select Sector SPDR | NYSEARCA | Sector ETFs (Defensive) |
| VEA | Vanguard FTSE Developed Markets ETF | NYSEARCA | International |
| VWO | Vanguard FTSE Emerging Markets ETF | NYSEARCA | International |
| EFA | iShares MSCI EAFE ETF | NYSEARCA | International |

---

## Strategy 3: All-Weather Volatility-Targeted Portfolio

**Category:** All-Weather
**Difficulty:** Intermediate
**Block Types Used:** Root, Group, Weight (Specified, Equal, Inverse Volatility, Market Cap, Min Variance), Asset, If, Else

### Concept

A Ray Dalio-inspired all-weather portfolio designed to perform in all economic environments. Uses volatility targeting across asset classes, conditional commodity exposure based on inflation signals, and alternative strategies for tail risk hedging.

### Structure

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
    │       │       ├── LQD   - iShares iBoxx $ Investment Grade Corporate Bond ETF
    │       │       └── HYG   - iShares iBoxx $ High Yield Corporate Bond ETF
    │       │
    │       └── [20%] TIP - iShares TIPS Bond ETF
    │
    ├── [15%] Group: "Real Assets"
    │   │
    │   ├── IF GLD > SMA(50) (inflation proxy)
    │   │   └── WEIGHT Specified
    │   │       ├── [40%] GLD - SPDR Gold Shares
    │   │       ├── [30%] SLV - iShares Silver Trust
    │   │       └── [30%] DBC - Invesco DB Commodity Index Tracking Fund
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

### Rationale

- **Equity Sleeve (40%):** Diversified US equity exposure with market-cap weighting for size, factor ETFs for alpha tilts, all wrapped in inverse volatility for risk parity
- **Fixed Income (30%):** Duration ladder with volatility-based allocation (more to short duration in volatile markets), credit exposure, and TIPS for inflation protection
- **Real Assets (15%):** When gold trends up (inflation signal), overweight commodities; otherwise equal weight gold and real estate
- **Alternatives (15%):** Managed futures and anti-beta for tail risk hedging, weighted by minimum variance

### Assets Used

| Ticker | Name | Exchange | Sleeve |
|--------|------|----------|--------|
| SPY | SPDR S&P 500 ETF Trust | NYSEARCA | US Large Cap |
| IWM | iShares Russell 2000 ETF | NYSEARCA | US Large Cap |
| MDY | SPDR S&P MidCap 400 ETF | NYSEARCA | US Large Cap |
| MTUM | iShares MSCI USA Momentum Factor ETF | NYSEARCA | Factor Tilt |
| QUAL | iShares MSCI USA Quality Factor ETF | NYSEARCA | Factor Tilt |
| VLUE | iShares MSCI USA Value Factor ETF | NYSEARCA | Factor Tilt |
| SHY | iShares 1-3 Year Treasury Bond ETF | NASDAQ | Duration Ladder |
| IEF | iShares 7-10 Year Treasury Bond ETF | NASDAQ | Duration Ladder |
| TLT | iShares 20+ Year Treasury Bond ETF | NASDAQ | Duration Ladder |
| LQD | iShares iBoxx $ Investment Grade Corporate Bond ETF | NYSEARCA | Credit |
| HYG | iShares iBoxx $ High Yield Corporate Bond ETF | NYSEARCA | Credit |
| TIP | iShares TIPS Bond ETF | NYSEARCA | Fixed Income |
| GLD | SPDR Gold Shares | NYSEARCA | Real Assets |
| SLV | iShares Silver Trust | NYSEARCA | Real Assets |
| DBC | Invesco DB Commodity Index Tracking Fund | NYSEARCA | Real Assets |
| VNQ | Vanguard Real Estate ETF | NYSEARCA | Real Assets |
| DBMF | iMGP DBi Managed Futures Strategy ETF | NYSEARCA | Alternatives |
| BTAL | AGFiQ US Market Neutral Anti-Beta Fund | NYSEARCA | Alternatives |

---

## Block Usage Summary

| Block Type | Strategy 1 | Strategy 2 | Strategy 3 |
|------------|:----------:|:----------:|:----------:|
| Root | ✓ | ✓ | ✓ |
| Group | ✓ | ✓ | ✓ |
| Weight (Specified) | ✓ | ✓ | ✓ |
| Weight (Equal) | ✓ | ✓ | ✓ |
| Weight (Inverse Vol) | ✓ | ✓ | ✓ |
| Weight (Momentum) | ✓ | ✓ | |
| Weight (Market Cap) | | | ✓ |
| Weight (Min Variance) | | ✓ | ✓ |
| Asset | ✓ | ✓ | ✓ |
| If/Else | ✓ | ✓ | ✓ |
| Filter | | ✓ | |

---

## Implementation

These strategies are available as templates in the Strategy Builder:

```typescript
import { getStrategyTemplate, STRATEGY_TEMPLATES } from '@/data/strategy-templates';

// Get all templates
console.log(STRATEGY_TEMPLATES);

// Load a specific template
const template = getStrategyTemplate('risk-on-off');
const tree = template.createTree();
```

See `apps/web/src/data/strategy-templates.ts` for the full implementation.
