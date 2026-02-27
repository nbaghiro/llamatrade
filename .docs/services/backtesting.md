# LlamaTrade Backtesting System

This document describes the backtesting subsystem—how users interact with it, what it calculates, and how it integrates with the broader LlamaTrade platform.

---

## Overview

Backtesting enables users to evaluate trading strategies against historical market data before risking real capital. The system simulates trade execution, tracks portfolio performance, and produces comprehensive metrics to assess strategy viability.

**Key Capabilities:**

- Simulate any strategy (config-based or code-based) over historical periods
- Support arbitrarily long time ranges (1980 to present, 45+ years)
- Sub-minute execution even for large universes (100+ symbols)
- Calculate industry-standard performance metrics (Sharpe, Sortino, drawdown, etc.)
- Produce equity curves and trade-by-trade breakdowns
- Run asynchronously with real-time progress streaming
- Multi-level caching for instant repeated runs

---

## Architecture Overview

### System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BACKTESTING SYSTEM ARCHITECTURE                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌──────────┐      ┌──────────────┐      ┌─────────────────────────────┐   │
│   │ Frontend │─────▶│ API Gateway  │─────▶│    Backtest Service :8003   │   │
│   │          │      │   (Kong)     │      │  • Request validation       │   │
│   └──────────┘      └──────────────┘      │  • Job queuing              │   │
│        ▲                                  │  • Result retrieval         │   │
│        │ WebSocket/Polling                └─────────────┬───────────────┘   │
│        │                                                │                   │
│   ┌────┴─────────────────────────────┐                  │ Celery Task       │
│   │        Progress Updates          │                  ▼                   │
│   │   Redis Pub/Sub ◀────────────────┼──────── Celery Workers (N)           │
│   └──────────────────────────────────┘          │  • Run simulations        │
│                                                 │  • Calculate metrics      │
│                                                 │  • Cache results          │
│   ┌─────────────────────────────────────────────┴───────────────────────┐   │
│   │                        DATA DEPENDENCIES                            │   │
│   │                                                                     │   │
│   │  Strategy Service ────▶ Strategy config, indicators, conditions     │   │
│   │  Market Data Service ──▶ Historical OHLCV bars                      │   │
│   │  PostgreSQL ───────────▶ Backtest records, results storage          │   │
│   │  Redis ────────────────▶ Bar cache, indicator cache, progress       │   │
│   │                                                                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Performance Architecture

A core product requirement is **speed at scale**. The system achieves sub-minute execution through:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PERFORMANCE ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  VECTORIZED COMPUTATION (100-500x speedup)                                  │
│  ─────────────────────────────────────────                                  │
│  • Process entire time series with NumPy arrays, not row-by-row loops       │
│  • 45 years × 100 symbols: ~30 seconds (vs ~4 hours row-by-row)             │
│                                                                             │
│  PARALLEL PROCESSING                                                        │
│  ───────────────────                                                        │
│  • Large universes: Split symbols across workers                            │
│  • Long periods: Split time chunks across workers                           │
│  • Auto-selection based on job characteristics                              │
│                                                                             │
│  MULTI-LEVEL CACHE                                                          │
│  ────────────────────────────────────────────────────────────────────────   │
│                                                                             │
│  L1: In-Process LRU     │ ~100MB/worker │ <1ms   │ Hot data in current run  │
│  L2: Redis Cluster      │ Shared        │ ~5ms   │ Indicators, recent runs  │
│  L3: TimescaleDB        │ 5yr hot data  │ ~50ms  │ Compressed hypertables   │
│  L4: GCS + DuckDB       │ 1980-2019     │ ~200ms │ Parquet cold storage     │
│                                                                             │
│  CACHE HIT SCENARIOS                                                        │
│  • Same backtest twice: <100ms (results cached)                             │
│  • Same strategy, different dates: <1s (indicators cached)                  │
│  • First run, recent data: <10s (TimescaleDB)                               │
│  • First run, cold data: <30s (Parquet fetch)                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Execution Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BACKTEST EXECUTION FLOW                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  USER                           SYSTEM                                      │
│  ────                           ──────                                      │
│                                                                             │
│  1. Click "Run Backtest"  ───▶  Validate request, create DB record          │
│                                 Queue Celery task, return backtest_id       │
│                                                                             │
│  2. See progress bar      ◀───  Worker: Update status to RUNNING            │
│     (polling/WebSocket)         Fetch strategy config (10%)                 │
│                                 Fetch market data, check cache (30%)        │
│                                 Compute indicators (40%)                    │
│                                 Run simulation loop (50-90%)                │
│                                 Calculate metrics (95%)                     │
│                                                                             │
│  3. View results          ◀───  Worker: Save results, mark COMPLETED        │
│                                 Return metrics, equity curve, trades        │
│                                                                             │
│  SIMULATION LOOP (for each bar):                                            │
│  ───────────────────────────────                                            │
│  Load OHLCV ─▶ Compute indicators ─▶ Evaluate conditions ─▶ Generate signal │
│       ─▶ Apply slippage/commission ─▶ Execute trade ─▶ Update portfolio     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Performance Targets

| Scenario       | Symbols | Time Range          | Target Execution |
| -------------- | ------- | ------------------- | ---------------- |
| Quick test     | 1       | 1 year              | < 100ms          |
| Typical use    | 10      | 5 years             | < 2 seconds      |
| Large universe | 100     | 10 years            | < 15 seconds     |
| Maximum scale  | 100     | 45 years (1980-now) | < 45 seconds     |

---

## Historical Data Sources

Alpaca provides data from ~2016 onwards. For backtests starting in 1980, additional sources are required:

| Time Period    | Primary Source | Coverage    | Cost            |
| -------------- | -------------- | ----------- | --------------- |
| 2016 - Present | Alpaca Markets | US equities | Free (included) |
| 2003 - 2015    | Polygon.io     | US equities | $199/mo         |
| 1998 - 2002    | Tiingo         | US equities | $30/mo          |
| 1980 - 1997    | EOD Historical | US equities | $20/mo          |

**Data Quality Pipeline:**

1. Fetch raw data from source
2. Apply corporate actions (stock splits, dividends)
3. Validate OHLC relationships (high ≥ open, close ≥ low)
4. Fill gaps (holidays: skip, errors: interpolate)
5. Store both adjusted and unadjusted prices
6. Pre-compute standard indicators (SMA 20/50/200, EMA 12/26, RSI 14, ATR 14)
7. Compress and partition by year

**Storage Requirements (100 symbols, 45 years):** ~200 MB compressed with indicators.

### Data Adjustments

| Event             | Example                | Adjustment                                    |
| ----------------- | ---------------------- | --------------------------------------------- |
| **Stock Split**   | AAPL 4:1 split in 2020 | Divide pre-split prices by 4                  |
| **Reverse Split** | Stock 1:10 reverse     | Multiply pre-split prices by 10               |
| **Dividend**      | $2 dividend paid       | Reduce pre-dividend prices by dividend amount |

Use **adjusted prices** for backtesting (true returns) and **unadjusted** for display.

---

## User Experience

### Initiating a Backtest

From the Strategy Builder or Strategy Detail page, users configure:

- **Strategy**: Select strategy and version
- **Date Range**: Start and end dates
- **Initial Capital**: Starting portfolio value (e.g., $100,000)
- **Advanced Settings** (optional): Commission per trade, slippage %, symbol overrides

### Progress Tracking

After submission, the backtest runs asynchronously. Users see:

- Progress bar with percentage complete
- Current step description (e.g., "Simulating trades for Q3 2023...")
- Start time and estimated remaining time
- Cancel button

### Results Dashboard

Upon completion, users see:

**Equity Curve**: Line chart showing portfolio value over time

**Performance Metrics Panel:**

- Total Return, Annual Return
- Sharpe Ratio, Sortino Ratio
- Max Drawdown, Drawdown Days
- Volatility, Beta (vs SPY)

**Trade Statistics Panel:**

- Total Trades, Winning/Losing Trades
- Win Rate, Profit Factor
- Average Win/Loss percentages
- Largest Win/Loss, Average Hold Time

**Monthly Returns Heatmap**: Color-coded grid of monthly performance

**Trade List**: Sortable table with entry/exit dates, symbol, side, P&L

**Actions**: Export CSV, Compare with other backtests, Deploy Strategy

---

## Performance Metrics

### Return Metrics

| Metric              | Formula                                            | Interpretation                              |
| ------------------- | -------------------------------------------------- | ------------------------------------------- |
| **Total Return**    | `(final_equity - initial_equity) / initial_equity` | Overall percentage gain/loss                |
| **Annual Return**   | `((1 + total_return) ^ (252 / trading_days)) - 1`  | Annualized return assuming 252 trading days |
| **Monthly Returns** | Return for each calendar month                     | Identifies seasonal patterns                |

### Risk-Adjusted Metrics

| Metric            | Formula                                             | Interpretation                                      |
| ----------------- | --------------------------------------------------- | --------------------------------------------------- |
| **Sharpe Ratio**  | `sqrt(252) × mean(excess_returns) / std(returns)`   | Risk-adjusted return vs. risk-free rate             |
| **Sortino Ratio** | `sqrt(252) × mean(returns) / std(downside_returns)` | Like Sharpe, but only penalizes downside volatility |
| **Calmar Ratio**  | `annual_return / max_drawdown`                      | Return relative to worst loss                       |

**Benchmarks:** Sharpe > 1.0 is good, > 2.0 is excellent, > 3.0 is exceptional (verify for overfitting).

### Drawdown Metrics

| Metric                | Formula                       | Interpretation               |
| --------------------- | ----------------------------- | ---------------------------- |
| **Max Drawdown**      | `max((peak - equity) / peak)` | Worst peak-to-trough decline |
| **Drawdown Duration** | Days from peak until new high | How long recovery takes      |
| **Average Drawdown**  | Mean of all drawdown periods  | Typical underwater period    |

### Trade Statistics

| Metric            | Formula                                              | Interpretation                  |
| ----------------- | ---------------------------------------------------- | ------------------------------- |
| **Win Rate**      | `winning_trades / total_trades`                      | Percentage of profitable trades |
| **Profit Factor** | `sum(wins) / abs(sum(losses))`                       | Gross profit vs. gross loss     |
| **Average Win**   | `mean(winning_trades.pnl_percent)`                   | Typical gain per winning trade  |
| **Average Loss**  | `mean(losing_trades.pnl_percent)`                    | Typical loss per losing trade   |
| **Expectancy**    | `(win_rate × avg_win) - ((1 - win_rate) × avg_loss)` | Expected return per trade       |

---

## Execution Model

### How Signals Become Trades

For each trading day, the backtester:

1. **Load Bar Data**: Get OHLCV for all symbols
2. **Compute Indicators**: Calculate RSI, SMA, MACD, etc. (first N bars may have NaN for warmup)
3. **Evaluate Conditions**: Check entry/exit conditions against current bar
4. **Generate Signals**: If entry conditions met and no position → BUY; if exit conditions met and has position → SELL
5. **Simulate Execution**: Apply slippage and commission, check capital availability
6. **Update Portfolio**: Adjust cash, positions, record equity point

### Slippage and Commission Modeling

**Slippage** (price movement between signal and execution):

- BUY: `execution_price = close × (1 + slippage_rate)` — pay more
- SELL: `execution_price = close × (1 - slippage_rate)` — receive less

**Commission**: Flat fee per trade, deducted from P&L.

**Example:** Buy 100 shares AAPL at $150 with 0.05% slippage and $1 commission:

- Execution at $150.075, sell later at $164.9175
- Gross P&L: $1,484.25, Net P&L: $1,482.25 (after $2 total commission)

---

## Strategy Interpretation

### Config-Based Strategies

Strategies from the visual builder are stored as JSON with:

- `symbols`: List of tickers to trade
- `timeframe`: Bar interval (e.g., "1D")
- `indicators`: List of indicator definitions with parameters
- `entry_conditions`: Conditions that trigger buy signals
- `exit_conditions`: Conditions that trigger sell signals
- `entry_action` / `exit_action`: How much to buy/sell
- `risk`: Stop loss, take profit, position sizing limits

The **Strategy Interpreter** parses this config, computes indicators on historical bars, evaluates conditions for each bar, and generates signals fed to the BacktestEngine.

### Supported Indicators

| Category       | Indicators                            | Parameters                  |
| -------------- | ------------------------------------- | --------------------------- |
| **Trend**      | SMA, EMA, MACD, ADX                   | period, fast/slow periods   |
| **Momentum**   | RSI, Stochastic, CCI, Williams %R     | period, overbought/oversold |
| **Volatility** | Bollinger Bands, ATR, Keltner Channel | period, multiplier          |
| **Volume**     | OBV, MFI, VWAP                        | period                      |
| **Channel**    | Donchian Channel                      | period                      |

### Supported Condition Operators

| Operator      | Meaning                     | Example                        |
| ------------- | --------------------------- | ------------------------------ |
| `gt`          | Greater than                | `RSI > 70`                     |
| `lt`          | Less than                   | `RSI < 30`                     |
| `gte`         | Greater or equal            | `price >= SMA`                 |
| `lte`         | Less or equal               | `price <= lower_band`          |
| `eq`          | Equal                       | `signal == 1`                  |
| `cross_above` | Crosses from below to above | `MACD cross_above signal_line` |
| `cross_below` | Crosses from above to below | `price cross_below SMA`        |

### Risk Management

The interpreter enforces risk rules on each bar while a position is open:

- **Stop Loss**: Exit if `current_pnl_percent <= -stop_loss_percent`
- **Take Profit**: Exit if `current_pnl_percent >= take_profit_percent`
- **Trailing Stop**: Update stop level based on highest price, exit if breached

---

## Database Schema

### Backtest Table

```sql
CREATE TABLE backtests (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    strategy_id     UUID NOT NULL REFERENCES strategies(id),
    strategy_version INT NOT NULL DEFAULT 1,

    -- Configuration
    name            VARCHAR(255),
    config          JSONB NOT NULL,        -- {commission, slippage, etc.}
    symbols         JSONB,                  -- ["AAPL", "MSFT"] or null for default
    start_date      DATE NOT NULL,
    end_date        DATE NOT NULL,
    initial_capital NUMERIC(18,2) NOT NULL,

    -- Execution state
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
                    -- pending, running, completed, failed, cancelled
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,

    -- Audit
    created_by      UUID NOT NULL REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT valid_status CHECK (status IN ('pending','running','completed','failed','cancelled')),
    CONSTRAINT valid_date_range CHECK (end_date > start_date)
);

CREATE INDEX idx_backtests_tenant_status ON backtests(tenant_id, status);
CREATE INDEX idx_backtests_strategy ON backtests(strategy_id);
```

### Backtest Results Table

```sql
CREATE TABLE backtest_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    backtest_id     UUID UNIQUE NOT NULL REFERENCES backtests(id) ON DELETE CASCADE,

    -- Performance metrics
    total_return    NUMERIC(10,6),
    annual_return   NUMERIC(10,6),
    sharpe_ratio    NUMERIC(10,6),
    sortino_ratio   NUMERIC(10,6),
    max_drawdown    NUMERIC(10,6),
    calmar_ratio    NUMERIC(10,6),
    volatility      NUMERIC(10,6),

    -- Trade statistics
    total_trades    INT,
    winning_trades  INT,
    losing_trades   INT,
    win_rate        NUMERIC(10,6),
    profit_factor   NUMERIC(10,6),
    avg_trade_return NUMERIC(10,6),
    final_equity    NUMERIC(18,2),

    -- Detailed data (JSONB for flexibility)
    equity_curve    JSONB,   -- [{date, equity, drawdown}, ...]
    trades          JSONB,   -- [{entry_date, exit_date, symbol, pnl, ...}, ...]
    daily_returns   JSONB,   -- [0.02, -0.01, 0.03, ...]
    monthly_returns JSONB,   -- {"2023-01": 0.05, "2023-02": 0.03, ...}

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## Caching Strategy

Historical market data rarely changes. The system caches at multiple levels:

**Cache Key Format:** `bars:{symbol}:{timeframe}:{start_date}:{end_date}`

**Lookup Flow:**

1. Check Redis for cached bars
2. On hit: Return immediately (~5ms)
3. On miss: Call Market Data Service (~500ms-2s), then cache with 24h TTL

**Pre-computed Indicators:** Common indicators (SMA 20/50/200, EMA 12/26, RSI 14, ATR 14) are computed at data ingestion time. Custom indicators are computed on-demand and cached in Redis.

---

## Error Handling

### Failure Scenarios

| Scenario                | Detection                       | Handling    | User Message                                                        |
| ----------------------- | ------------------------------- | ----------- | ------------------------------------------------------------------- |
| Strategy not found      | HTTP 404 from strategy service  | Mark FAILED | "Strategy not found. It may have been deleted."                     |
| No market data          | Empty response from market-data | Mark FAILED | "No market data available for {symbol} in the selected date range." |
| Insufficient capital    | During simulation               | Skip trade  | Visible in trade log: "Skipped: insufficient capital"               |
| Task timeout            | Celery soft time limit          | Mark FAILED | "Backtest timed out. Try a shorter date range."                     |
| Invalid strategy config | Interpreter validation          | Mark FAILED | "Invalid strategy configuration: {details}"                         |
| Service unavailable     | HTTP timeout/error              | Retry (3x)  | "Service temporarily unavailable. Retrying..."                      |

### Retry Logic

Task retries: 3 attempts with exponential backoff (immediate → 60s → 120s). After 3 failures: Mark FAILED with error message.

---

## Capabilities and Limitations

### What the Backtester Supports

| Capability         | Range               | Notes                                     |
| ------------------ | ------------------- | ----------------------------------------- |
| **Time range**     | 1980 - present      | 45+ years via multi-source data           |
| **Universe size**  | Up to 500 symbols   | Parallel processing scales linearly       |
| **Execution time** | < 1 minute typical  | For 100 symbols over 10 years             |
| **Timeframes**     | Daily bars          | Intraday planned for future               |
| **Markets**        | US equities         | Via Alpaca + historical sources           |
| **Indicators**     | 15+ built-in        | RSI, SMA, EMA, MACD, Bollinger, ATR, etc. |
| **Strategy types** | Config-based + code | Visual builder or Python classes          |

### Execution Assumptions

| Assumption             | Reality                   | Impact                         |
| ---------------------- | ------------------------- | ------------------------------ |
| Execute at close price | Real fills vary           | Slippage parameter compensates |
| Unlimited liquidity    | Large orders move markets | Suitable for < $10M portfolios |
| No partial fills       | Orders may partially fill | Not modeled                    |
| Instant execution      | Real latency exists       | Acceptable for daily timeframe |

### Data Limitations

| Limitation        | Description                     | Mitigation                             |
| ----------------- | ------------------------------- | -------------------------------------- |
| Daily bars only   | No tick or minute data          | Suitable for swing/position strategies |
| No extended hours | Pre/after-market excluded       | Most volume is regular hours           |
| US equities only  | No international, crypto, forex | Focus on most liquid market            |
| Survivorship bias | Delisted symbols missing        | Use caution with pre-2000 data         |
| Pre-1980 sparse   | Limited data availability       | Start dates < 1980 not recommended     |

### What Backtesting Cannot Tell You

- **Future performance** — Past results don't guarantee future returns
- **Execution quality** — Real fills depend on market conditions at the moment
- **Emotional factors** — Backtests don't simulate fear, greed, or fatigue
- **Regime changes** — Markets evolve; a strategy that worked in 1990 may fail today
- **Black swan events** — Rare events may not appear in historical data

### When to Trust Results

**High confidence:**

- Strategy tested over 10+ years including multiple market cycles
- Multiple symbols show consistent performance
- Sharpe ratio between 1.0-2.5 (very high ratios often indicate overfitting)
- Drawdowns align with what you could emotionally tolerate

**Exercise caution:**

- Testing only on recent bull market (post-2009)
- Sharpe ratio > 3.0 (likely overfitted)
- Strategy optimized to specific date ranges
- Few trades (< 100) — insufficient statistical significance

---

## Benchmark Comparisons

Every backtest automatically compares strategy performance against standard benchmarks.

### Built-in Benchmarks

| Benchmark           | Description                             | Use Case                           |
| ------------------- | --------------------------------------- | ---------------------------------- |
| **SPY Buy & Hold**  | S&P 500 ETF held for entire period      | "Did my strategy beat the market?" |
| **Risk-Free Rate**  | 3-month Treasury bill yield             | "Did I beat risk-free returns?"    |
| **60/40 Portfolio** | 60% SPY + 40% BND, rebalanced quarterly | "Did I beat a passive portfolio?"  |

### Benchmark Metrics Computed

For each benchmark: Total return, annual return, Sharpe ratio, max drawdown, volatility.

For strategy vs SPY specifically:

- **Beta** = `cov(strategy, spy) / var(spy)` — market sensitivity (1.0 = moves with market, <1.0 = defensive, >1.0 = aggressive)
- **Alpha** = `strategy_return - (rf + beta × (market_return - rf))` — excess return beyond market exposure
- **Correlation** and **Information Ratio**

### Custom Benchmarks

Users can add custom benchmarks:

- Single asset buy & hold (e.g., QQQ)
- Equal-weight portfolio with rebalancing (e.g., sector ETFs)

### Benchmark Data Availability

| Benchmark | Inception | Pre-Inception Handling                       |
| --------- | --------- | -------------------------------------------- |
| SPY       | 1993      | Use S&P 500 index data (^GSPC) for 1980-1993 |
| QQQ       | 1999      | Use Nasdaq 100 index data for earlier        |
| BND       | 2007      | Use aggregate bond index proxy               |
| Risk-Free | 1980+     | 3-month T-bill yields available              |

---

## Walk-Forward Optimization

Walk-forward analysis prevents overfitting by simulating real-world strategy development.

### The Overfitting Problem

Traditional backtesting optimizes parameters on historical data, then tests on the same data. This leads to curve-fitted parameters that won't work in the future.

### Walk-Forward Solution

Walk-forward repeatedly optimizes on past data and tests on unseen future data:

1. **Window 1**: Optimize on 2000-2004, test on 2005-2006 → record results
2. **Window 2**: Optimize on 2002-2006, test on 2007-2008 → record results
3. **Continue rolling forward...**
4. **Final Performance** = Average of all out-of-sample windows

### Configuration Options

- **In-Sample Period**: How much history to optimize on (e.g., 5 years)
- **Out-of-Sample Period**: How far to test forward (e.g., 1 year)
- **Step Size**: How often to re-optimize (e.g., 1 year)
- **Parameters to Optimize**: Select which strategy parameters to vary with ranges
- **Optimization Target**: Metric to maximize (e.g., Sharpe Ratio)

### Walk-Forward Efficiency

**Efficiency Ratio** = Out-of-Sample Performance / In-Sample Performance

| Efficiency | Interpretation                 |
| ---------- | ------------------------------ |
| > 80%      | Excellent — strategy is robust |
| 60-80%     | Good — acceptable degradation  |
| 40-60%     | Moderate — some overfitting    |
| < 40%      | Poor — significant overfitting |

---

## Monte Carlo Simulation

Monte Carlo simulation assesses strategy robustness by testing performance under randomized conditions.

### Why Monte Carlo?

A single backtest shows what _did_ happen. Monte Carlo shows the range of what _could_ happen:

- What if trades occurred in a different order?
- What if we started on a different date?
- What's the worst-case scenario at 95% confidence?

### Simulation Methods

1. **Trade Shuffling**: Randomize the order of trades to test if success depends on lucky sequencing
2. **Random Start Dates**: Vary entry timing to test if success depends on lucky start timing
3. **Bootstrapped Returns**: Resample daily returns with replacement to estimate confidence intervals

### Configuration Options

- **Number of Simulations**: Typically 1,000
- **Methods to Run**: Select which randomization methods
- **Confidence Intervals**: e.g., 95%

### Interpreting Results

**Strategy is ROBUST if:**

- 90%+ of simulations are profitable
- Median metrics close to original backtest
- 5th percentile Sharpe still > 0.5
- Narrow distribution (low variance across simulations)

**Strategy may be FRAGILE if:**

- < 80% of simulations profitable
- Median significantly worse than original
- 5th percentile shows losses
- Wide distribution (high variance)

### Combined Analysis

For maximum confidence, run both walk-forward and Monte Carlo:

1. Walk-forward confirms strategy works out-of-sample (not curve-fitted)
2. Monte Carlo on out-of-sample results confirms results aren't dependent on lucky timing/ordering

---

## Comparison Feature

Users can compare multiple backtests side-by-side with:

- **Equity Curves Overlay**: Multiple strategies on same chart
- **Metrics Comparison Table**: Side-by-side metrics for each strategy
- **Requirement**: Backtests must share the same date range to be comparable

---

## API Reference

### Create Backtest

```http
POST /api/backtests
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
  "strategy_id": "uuid",
  "strategy_version": 3,           // optional, defaults to latest
  "start_date": "2023-01-01",
  "end_date": "2024-01-01",
  "initial_capital": 100000,
  "symbols": ["AAPL", "MSFT"],     // optional, overrides strategy symbols
  "commission": 1.0,               // optional, default 0
  "slippage": 0.0005               // optional, default 0
}

Response: 202 Accepted
{
  "id": "uuid",
  "status": "pending",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### Get Backtest Status

```http
GET /api/backtests/{id}
Authorization: Bearer {jwt_token}

Response: 200 OK
{
  "id": "uuid",
  "strategy_id": "uuid",
  "status": "running",
  "progress": 45,
  "started_at": "2024-01-15T10:30:05Z",
  "completed_at": null
}
```

### Get Backtest Results

```http
GET /api/backtests/{id}/results
Authorization: Bearer {jwt_token}

Response: 200 OK
{
  "id": "uuid",
  "backtest_id": "uuid",
  "metrics": {
    "total_return": 0.285,
    "annual_return": 0.285,
    "sharpe_ratio": 1.82,
    "sortino_ratio": 2.41,
    "max_drawdown": 0.083,
    "win_rate": 0.617,
    "profit_factor": 1.64,
    "total_trades": 47,
    "alpha": 0.085,
    "beta": 0.72
  },
  "benchmarks": {
    "spy_buy_hold": { "total_return": 0.385, "sharpe_ratio": 1.05, "max_drawdown": -0.34 },
    "portfolio_60_40": { "total_return": 0.245, "sharpe_ratio": 0.95, "max_drawdown": -0.22 },
    "risk_free": { "total_return": 0.082 }
  },
  "equity_curve": [
    {"date": "2023-01-01", "equity": 100000, "drawdown": 0},
    {"date": "2023-01-02", "equity": 100500, "drawdown": 0}
  ],
  "trades": [
    {
      "entry_date": "2023-01-15",
      "exit_date": "2023-01-19",
      "symbol": "AAPL",
      "side": "long",
      "entry_price": 150.25,
      "exit_price": 155.80,
      "quantity": 100,
      "pnl": 555.00,
      "pnl_percent": 3.69
    }
  ],
  "monthly_returns": { "2023-01": 0.021, "2023-02": 0.034 }
}
```

### Cancel Backtest

```http
DELETE /api/backtests/{id}
Authorization: Bearer {jwt_token}

Response: 200 OK
{ "id": "uuid", "status": "cancelled" }
```

### List Backtests

```http
GET /api/backtests?strategy_id={id}&status=completed&page=1&page_size=20
Authorization: Bearer {jwt_token}

Response: 200 OK
{
  "items": [...],
  "total": 47,
  "page": 1,
  "page_size": 20
}
```

---

## WebSocket Progress (Future)

Real-time progress updates via WebSocket:

```javascript
const ws = new WebSocket(
  "wss://api.llamatrade.com/ws/backtests/bt-456/progress",
);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  // { "backtest_id": "bt-456", "progress": 65, "message": "Simulating Q3 2023...", "status": "running" }
  updateProgressBar(data.progress);
  updateStatusMessage(data.message);
};
```

---

## Glossary

| Term              | Definition                                             |
| ----------------- | ------------------------------------------------------ |
| **Backtest**      | Simulation of a strategy over historical data          |
| **Equity Curve**  | Time series of portfolio value                         |
| **Drawdown**      | Decline from peak equity to current value              |
| **Sharpe Ratio**  | Risk-adjusted return measure                           |
| **Sortino Ratio** | Like Sharpe but only penalizes downside                |
| **Win Rate**      | Percentage of trades that were profitable              |
| **Profit Factor** | Gross profits divided by gross losses                  |
| **Slippage**      | Difference between expected and actual execution price |
| **Signal**        | Trading instruction (buy, sell, etc.)                  |
| **Bar**           | OHLCV data for a single time period                    |
