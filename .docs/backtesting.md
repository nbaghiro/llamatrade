# LlamaTrade Backtesting System

This document describes the backtesting subsystem—how users interact with it, what it calculates, and how it integrates with the broader LlamaTrade platform.

---

## Overview

Backtesting enables users to evaluate trading strategies against historical market data before risking real capital. The system simulates trade execution, tracks portfolio performance, and produces comprehensive metrics to assess strategy viability.

**Key Capabilities:**

- Simulate any strategy (config-based or code-based) over historical periods
- **Support arbitrarily long time ranges** (1980 to present, 45+ years)
- **Sub-minute execution** even for large universes (100+ symbols)
- Calculate industry-standard performance metrics (Sharpe, Sortino, drawdown, etc.)
- Produce equity curves and trade-by-trade breakdowns
- Run asynchronously with real-time progress streaming
- Multi-level caching for instant repeated runs

---

## Performance Architecture

A core product requirement is **speed at scale**. Users must be able to backtest strategies across decades of data without waiting minutes or hours. The system achieves this through vectorized computation, parallel processing, and intelligent caching.

### Performance Targets

| Scenario       | Symbols | Time Range          | Target Execution |
| -------------- | ------- | ------------------- | ---------------- |
| Quick test     | 1       | 1 year              | < 100ms          |
| Typical use    | 10      | 5 years             | < 2 seconds      |
| Large universe | 100     | 10 years            | < 15 seconds     |
| Maximum scale  | 100     | 45 years (1980-now) | < 45 seconds     |

### Vectorized Computation

The engine processes entire time series at once using NumPy arrays, not row-by-row iteration:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     COMPUTATION APPROACH COMPARISON                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Traditional (Row-by-row):              Vectorized (Array operations):      │
│  ───────────────────────────            ─────────────────────────────────   │
│                                                                             │
│  for date in all_dates:                 # Load all data as NumPy arrays     │
│      for symbol in symbols:             closes = load_closes()  # (N, S)    │
│          bar = get_bar(date, symbol)                                        │
│          rsi = calculate_rsi(bar)       # Compute indicators in one pass    │
│          if rsi < 30:                   rsi = vectorized_rsi(closes)        │
│              signal = BUY                                                   │
│                                         # Generate all signals at once      │
│  Time: O(days × symbols)                signals = np.where(rsi < 30, 1, 0)  │
│  45 years, 100 symbols: ~4 hours                                            │
│                                         Time: O(1) with broadcasting        │
│                                         45 years, 100 symbols: ~30 seconds  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Why vectorization matters:**

- NumPy operations run in optimized C code, not Python loops
- Modern CPUs use SIMD (Single Instruction, Multiple Data) for array operations
- Memory access is sequential and cache-friendly
- Typical speedup: **100-500x** over row-by-row iteration

### Parallelization Strategy

For large backtests, work is distributed across multiple workers:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      PARALLEL EXECUTION MODES                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Mode 1: Parallel by Symbol (large universes)                               │
│  ─────────────────────────────────────────────                              │
│                                                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐                        │
│  │ Worker 1 │ │ Worker 2 │ │ Worker 3 │ │ Worker 4 │                        │
│  │ AAPL     │ │ MSFT     │ │ GOOGL    │ │ AMZN     │  ...25 symbols each    │
│  │ 45 years │ │ 45 years │ │ 45 years │ │ 45 years │                        │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘                        │
│       └────────────┴────────────┴────────────┘                              │
│                     Merge results                                           │
│                                                                             │
│  Mode 2: Parallel by Time Chunks (single symbol, very long periods)         │
│  ───────────────────────────────────────────────────────────────            │
│                                                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │ Worker 1 │ │ Worker 2 │ │ Worker 3 │ │ Worker 4 │ │ Worker 5 │           │
│  │ 1980-89  │ │ 1990-99  │ │ 2000-09  │ │ 2010-19  │ │ 2020-25  │           │
│  │   AAPL   │ │   AAPL   │ │   AAPL   │ │   AAPL   │ │   AAPL   │           │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘           │
│       └────────────┴────────────┴────────────┴────────────┘                 │
│                  Chain equity curves sequentially                           │
│                                                                             │
│  Automatic Selection:                                                       │
│    • Universe ≥ workers → Parallel by symbol                                │
│    • Single symbol + long period → Parallel by time                         │
│    • Small job → Single worker (no overhead)                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Multi-Level Caching

Historical data rarely changes. The system caches aggressively at multiple levels:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CACHE HIERARCHY                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Level 1: In-Process LRU (per worker)                                       │
│  ─────────────────────────────────────                                      │
│  • Hot data accessed in current backtest                                    │
│  • ~100MB per worker                                                        │
│  • Latency: < 1ms                                                           │
│                                                                             │
│  Level 2: Redis (shared cluster)                                            │
│  ──────────────────────────────                                             │
│  • Pre-computed indicators                                                  │
│  • Recent backtest results                                                  │
│  • Key: bt:{symbol}:{indicator}:{params}:{date_range}                       │
│  • Latency: ~5ms                                                            │
│  • TTL: 24h for indicators, 7d for results                                  │
│                                                                             │
│  Level 3: TimescaleDB (compressed hypertables)                              │
│  ─────────────────────────────────────────────                              │
│  • Hot data: recent 5 years                                                 │
│  • Compressed chunks: 90%+ compression ratio                                │
│  • Continuous aggregates for monthly/yearly views                           │
│  • Latency: ~50ms                                                           │
│                                                                             │
│  Level 4: Cloud Storage + DuckDB (cold data)                                │
│  ────────────────────────────────────────────                               │
│  • Parquet files on GCS for 1980-2019 data                                  │
│  • DuckDB for in-process SQL on Parquet                                     │
│  • Latency: ~200ms                                                          │
│  • Cost: ~$0.02/GB/month                                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Cache Hit Scenarios:**

- Running same backtest twice: **< 100ms** (results cached)
- Same strategy, different dates: **< 1s** (indicators cached)
- First run, data in TimescaleDB: **< 10s** (compressed read)
- First run, cold data: **< 30s** (Parquet fetch + compute)

### Pre-Computed Indicators

Common indicators are computed at data ingestion time and stored alongside OHLCV:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PRE-COMPUTED INDICATOR COLUMNS                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  timestamp  symbol   open    high    low    close   volume   sma_20  rsi_14 │
│  ─────────────────────────────────────────────────────────────────────────  │
│  2024-01-02  AAPL   185.00  186.50  184.20  186.00  52M     183.45   62.3   │
│  2024-01-03  AAPL   186.20  187.80  185.50  187.50  48M     183.90   65.1   │
│  2024-01-04  AAPL   187.00  188.00  186.00  186.80  45M     184.20   58.7   │
│  ...                                                                        │
│                                                                             │
│  Pre-computed on ingest:        Computed on-demand (cached):                │
│  • SMA (20, 50, 200)            • Custom period SMAs                        │
│  • EMA (12, 26)                 • MACD (derived from EMA)                   │
│  • RSI (14)                     • Bollinger Bands                           │
│  • ATR (14)                     • Stochastic                                │
│                                                                             │
│  Storage overhead: ~40% more columns                                        │
│  Query speedup: ~5x (no computation needed)                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Historical Data Sources

Alpaca provides data from ~2016 onwards. For backtests starting in 1980, additional data sources are required:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        HISTORICAL DATA SOURCES                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Time Period          Primary Source        Coverage        Cost            │
│  ─────────────────────────────────────────────────────────────────────────  │
│  2016 - Present       Alpaca Markets        US equities     Free (included) │
│  2003 - 2015          Polygon.io            US equities     $199/mo         │
│  1998 - 2002          Tiingo                US equities     $30/mo          │
│  1980 - 1997          EOD Historical        US equities     $20/mo          │
│                                                                             │
│  Data Quality Pipeline:                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  1. Fetch raw data from source                                      │    │
│  │  2. Apply corporate actions (stock splits, dividends)               │    │
│  │  3. Validate OHLC relationships (high ≥ open,close ≥ low)           │    │
│  │  4. Fill gaps (holidays: skip, errors: interpolate)                 │    │
│  │  5. Store both adjusted and unadjusted prices                       │    │
│  │  6. Pre-compute standard indicators                                 │    │
│  │  7. Compress and partition by year                                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  Storage Requirements (100 symbols, 45 years):                              │
│  • Raw OHLCV: ~50 MB compressed                                             │
│  • With indicators: ~200 MB compressed                                      │
│  • Full 500 symbols: ~1 GB compressed                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Data Adjustments

Historical prices are adjusted for corporate actions to ensure accurate backtesting:

| Event             | Example                | Adjustment                                    |
| ----------------- | ---------------------- | --------------------------------------------- |
| **Stock Split**   | AAPL 4:1 split in 2020 | Divide pre-split prices by 4                  |
| **Reverse Split** | Stock 1:10 reverse     | Multiply pre-split prices by 10               |
| **Dividend**      | $2 dividend paid       | Reduce pre-dividend prices by dividend amount |

**Adjusted vs. Unadjusted:**

- **Adjusted prices**: Use for backtesting (shows true returns)
- **Unadjusted prices**: Use for display (shows actual historical prices)

---

## User Experience

### Initiating a Backtest

From the Strategy Builder or Strategy Detail page, users click "Run Backtest" and configure:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BACKTEST CONFIGURATION                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Strategy:     [RSI Mean Reversion - AAPL        ▼]                         │
│  Version:      [Latest (v3)                      ▼]                         │
│                                                                             │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  Date Range:   [2023-01-01] ─── to ─── [2024-01-01]                         │
│                                                                             │
│  Initial Capital:  $[ 100,000 ]                                             │
│                                                                             │
│  ─────────────────────────────────────────────────────────────────────────  │
│                                                                             │
│  Advanced Settings (optional):                                              │
│    • Commission per trade:  $[ 1.00 ]                                       │
│    • Slippage assumption:   [ 0.05 ]%                                       │
│    • Override symbols:      [ AAPL, MSFT, GOOGL ]  (leave blank for default)│
│                                                                             │
│                                    [ Cancel ]  [ Run Backtest ]             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Progress Tracking

After submission, the backtest runs asynchronously. Users see real-time progress:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BACKTEST IN PROGRESS                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Strategy: RSI Mean Reversion - AAPL                                        │
│  Status:   Running                                                          │
│                                                                             │
│  ████████████████████████████░░░░░░░░░░░░  65%                              │
│                                                                             │
│  Current step: Simulating trades for Q3 2023...                             │
│                                                                             │
│  Started:   2 minutes ago                                                   │
│  Estimated: ~1 minute remaining                                             │
│                                                                             │
│                                              [ Cancel ]                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Results Dashboard

Upon completion, users see a comprehensive results view:

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         BACKTEST RESULTS                                   │
│  RSI Mean Reversion - AAPL  •  Jan 2023 - Jan 2024  •  $100,000 initial    │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     EQUITY CURVE                                    │   │
│  │  $130k ┤                                          ╭────             │   │
│  │        │                              ╭───────────╯                 │   │
│  │  $120k ┤                    ╭─────────╯                             │   │
│  │        │          ╭─────────╯                                       │   │
│  │  $110k ┤    ╭─────╯                                                 │   │
│  │        │╭───╯                                                       │   │
│  │  $100k ┼╯                                                           │   │
│  │        └─────────────────────────────────────────────────────────   │   │
│  │         Jan    Mar    May    Jul    Sep    Nov    Jan               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                            │
│  ┌──────────────────────────┐  ┌──────────────────────────┐                │
│  │   PERFORMANCE METRICS    │  │   TRADE STATISTICS       │                │
│  ├──────────────────────────┤  ├──────────────────────────┤                │
│  │ Total Return    +28.5%   │  │ Total Trades      47     │                │
│  │ Annual Return   +28.5%   │  │ Winning Trades    29     │                │
│  │ Sharpe Ratio     1.82    │  │ Losing Trades     18     │                │
│  │ Sortino Ratio    2.41    │  │ Win Rate        61.7%    │                │
│  │ Max Drawdown    -8.3%    │  │ Profit Factor    1.64    │                │
│  │ Drawdown Days    23      │  │ Avg Win         +3.2%    │                │
│  │ Volatility      15.2%    │  │ Avg Loss        -1.9%    │                │
│  │ Beta (SPY)       0.85    │  │ Largest Win     +8.7%    │                │
│  └──────────────────────────┘  │ Largest Loss    -4.1%    │                │
│                                │ Avg Hold Time   4.2 days │                │
│                                └──────────────────────────┘                │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     MONTHLY RETURNS HEATMAP                         │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │         Jan   Feb   Mar   Apr   May   Jun   Jul   Aug   Sep   Oct   │   │
│  │  2023  +2.1% +3.4% -1.2% +4.5% +2.8% +1.9% +5.2% -0.8% +3.1% +2.4%  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     TRADE LIST (47 trades)                          │   │
│  ├────────────┬────────────┬────────┬────────┬─────────┬───────────────┤   │
│  │ Entry Date │ Exit Date  │ Symbol │ Side   │ P&L     │ P&L %         │   │
│  ├────────────┼────────────┼────────┼────────┼─────────┼───────────────┤   │
│  │ 2023-01-15 │ 2023-01-19 │ AAPL   │ Long   │ +$1,245 │ +2.1%         │   │
│  │ 2023-02-03 │ 2023-02-08 │ AAPL   │ Long   │ +$2,890 │ +4.8%         │   │
│  │ 2023-02-22 │ 2023-02-24 │ AAPL   │ Long   │ -$512   │ -0.8%         │   │
│  │ ...        │ ...        │ ...    │ ...    │ ...     │ ...           │   │
│  └────────────┴────────────┴────────┴────────┴─────────┴───────────────┘   │
│                                                                            │
│                [ Export CSV ]  [ Compare ]  [ Deploy Strategy ]            │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Performance Metrics

The backtester calculates comprehensive metrics to evaluate strategy quality:

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

**Benchmarks:**

- Sharpe > 1.0: Good
- Sharpe > 2.0: Excellent
- Sharpe > 3.0: Exceptional (verify for overfitting)

### Drawdown Metrics

| Metric                | Formula                       | Interpretation               |
| --------------------- | ----------------------------- | ---------------------------- |
| **Max Drawdown**      | `max((peak - equity) / peak)` | Worst peak-to-trough decline |
| **Drawdown Duration** | Days from peak until new high | How long recovery takes      |
| **Average Drawdown**  | Mean of all drawdown periods  | Typical underwater period    |

```
                Peak
                  │
  Equity    ──────●───────────────────────────●── New Peak (Recovery)
                  │╲                         ╱│
                  │ ╲                       ╱ │
                  │  ╲         Trough      ╱  │
                  │   ╲──────────●────────╱   │
                  │              │            │
                  ├──────────────┼────────────┤
                  │   Drawdown   │  Duration  │
                  │    -15%      │   45 days  │
```

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

The backtester simulates realistic trade execution:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EXECUTION SIMULATION                                │
└─────────────────────────────────────────────────────────────────────────────┘

For each trading day in date range:
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. LOAD BAR DATA                                                            │
│    Get OHLCV for all symbols: open, high, low, close, volume                │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. COMPUTE INDICATORS                                                       │
│    Calculate RSI, SMA, MACD, etc. using historical bars                     │
│    Note: First N bars may have NaN (warmup period)                          │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. EVALUATE CONDITIONS                                                      │
│    Check entry conditions: RSI < 30 AND price > SMA(200)                    │
│    Check exit conditions: RSI > 70 OR stop_loss_hit                         │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. GENERATE SIGNALS                                                         │
│    If entry conditions met AND no position: generate BUY signal             │
│    If exit conditions met AND has position: generate SELL signal            │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. SIMULATE EXECUTION                                                       │
│    Apply slippage:  execution_price = close × (1 + slippage_rate)           │
│    Apply commission: cost = commission_per_trade                            │
│    Check capital:   if cost > cash, skip trade                              │
│    Open/close position and record trade                                     │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 6. UPDATE PORTFOLIO                                                         │
│    cash = cash - (shares × price) - commission     (for buys)               │
│    cash = cash + (shares × price) - commission     (for sells)              │
│    equity = cash + sum(position_values)                                     │
│    Record equity point for curve                                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Slippage and Commission Modeling

Real trading incurs costs. The backtester models:

**Slippage** - Price movement between signal and execution:

```
For BUY:  execution_price = close × (1 + slippage_rate)  # Pay more
For SELL: execution_price = close × (1 - slippage_rate)  # Receive less
```

**Commission** - Broker fees per trade:

```
total_commission = entry_commission + exit_commission
trade_pnl = gross_pnl - total_commission
```

**Example:**

```
Signal: BUY AAPL at $150.00
Slippage (0.05%): Execution at $150.075
Commission: $1.00

Signal: SELL AAPL at $165.00
Slippage (0.05%): Execution at $164.9175
Commission: $1.00

Gross P&L: 100 shares × ($164.9175 - $150.075) = $1,484.25
Net P&L:   $1,484.25 - $2.00 = $1,482.25
```

---

## Strategy Interpretation

The backtester supports two strategy formats:

### Config-Based Strategies

Strategies defined via the visual builder are stored as `StrategyConfig` JSON:

```json
{
  "symbols": ["AAPL"],
  "timeframe": "1D",
  "indicators": [
    { "type": "rsi", "params": { "period": 14 }, "output_name": "rsi_14" },
    { "type": "sma", "params": { "period": 200 }, "output_name": "sma_200" }
  ],
  "entry_conditions": [
    { "left": "rsi_14", "operator": "lt", "right": 30 },
    { "left": "price", "operator": "gt", "right": "sma_200" }
  ],
  "exit_conditions": [{ "left": "rsi_14", "operator": "gt", "right": 70 }],
  "entry_action": {
    "type": "buy",
    "quantity_type": "percent",
    "quantity_value": 95
  },
  "exit_action": { "type": "sell", "quantity_type": "all" },
  "risk": {
    "stop_loss_percent": 5.0,
    "take_profit_percent": 15.0,
    "max_position_size_percent": 100
  }
}
```

The **Strategy Interpreter** converts this config into executable logic:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STRATEGY INTERPRETER                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  StrategyConfig (JSON)                                                      │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────┐        │
│  │ 1. Parse indicator definitions                                  │        │
│  │    rsi_14 = RSI(period=14)                                      │        │
│  │    sma_200 = SMA(period=200)                                    │        │
│  └─────────────────────────────────────────────────────────────────┘        │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────┐        │
│  │ 2. Compute indicators on historical bars                        │        │
│  │    rsi_values[i] = calculate_rsi(closes[:i], period=14)         │        │
│  │    sma_values[i] = calculate_sma(closes[:i], period=200)        │        │
│  └─────────────────────────────────────────────────────────────────┘        │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────┐        │
│  │ 3. Evaluate conditions for each bar                             │        │
│  │    entry = (rsi_values[i] < 30) AND (close[i] > sma_values[i])  │        │
│  │    exit = (rsi_values[i] > 70)                                  │        │
│  └─────────────────────────────────────────────────────────────────┘        │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────┐        │
│  │ 4. Generate signals                                             │        │
│  │    if entry AND no_position: return {"type": "buy", ...}        │        │
│  │    if exit AND has_position: return {"type": "sell", ...}       │        │
│  └─────────────────────────────────────────────────────────────────┘        │
│         │                                                                   │
│         ▼                                                                   │
│  Signals fed to BacktestEngine                                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

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

The interpreter also enforces risk rules:

```
For each bar while position is open:
    current_pnl_percent = (current_price - entry_price) / entry_price × 100

    # Stop loss check
    if current_pnl_percent <= -stop_loss_percent:
        generate SELL signal (reason: stop_loss)

    # Take profit check
    if current_pnl_percent >= take_profit_percent:
        generate SELL signal (reason: take_profit)

    # Trailing stop (if enabled)
    if trailing_stop_percent:
        update_trailing_stop(highest_price, current_price)
        if current_price <= trailing_stop_level:
            generate SELL signal (reason: trailing_stop)
```

---

## Data Flow

### End-to-End Request Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         USER: Clicks "Run Backtest"                         │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND                                            │
│  POST /api/backtests                                                        │
│  {                                                                          │
│    "strategy_id": "abc-123",                                                │
│    "start_date": "2023-01-01",                                              │
│    "end_date": "2024-01-01",                                                │
│    "initial_capital": 100000                                                │
│  }                                                                          │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         API GATEWAY (Kong)                                  │
│  • Validate JWT token                                                       │
│  • Extract tenant_id                                                        │
│  • Rate limit check                                                         │
│  • Route to Backtest Service                                                │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BACKTEST SERVICE :8003                              │
│                                                                             │
│  1. Validate request                                                        │
│  2. Create Backtest record in PostgreSQL (status: PENDING)                  │
│  3. Enqueue Celery task with backtest_id                                    │
│  4. Return backtest_id immediately                                          │
│                                                                             │
└──────────────┬──────────────────────────────────────────────────────────────┘
               │                                               │
               │ Response: {"id": "bt-456", "status": "pending"}
               │                                               │
               │                                               ▼
               │                              ┌───────────────────────────────┐
               │                              │  FRONTEND: Start polling      │
               │                              │  GET /api/backtests/bt-456    │
               │                              │  (or WebSocket subscription)  │
               │                              └───────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         REDIS QUEUE                                         │
│  Job: run_backtest_task(backtest_id="bt-456", tenant_id="t-789")            │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CELERY WORKER                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Step 1: Update status to RUNNING                                           │
│          └─► PostgreSQL: UPDATE backtests SET status='running'              │
│          └─► Redis pub/sub: emit progress(0%, "Starting...")                │
│                                                                             │
│  Step 2: Fetch strategy config                                              │
│          └─► HTTP: GET strategy-service:8002/strategies/{id}                │
│          └─► Returns: StrategyConfig JSON                                   │
│          └─► Redis pub/sub: emit progress(10%, "Loaded strategy")           │
│                                                                             │
│  Step 3: Fetch historical data                                              │
│          └─► Check Redis cache for bars                                     │
│          └─► If miss: HTTP: POST market-data:8004/bars                      │
│          └─► Cache result for 24 hours                                      │
│          └─► Redis pub/sub: emit progress(30%, "Fetched market data")       │
│                                                                             │
│  Step 4: Initialize interpreter                                             │
│          └─► Parse StrategyConfig                                           │
│          └─► Pre-compute indicators for all bars                            │
│          └─► Redis pub/sub: emit progress(40%, "Computed indicators")       │
│                                                                             │
│  Step 5: Run simulation                                                     │
│          └─► BacktestEngine.run(bars, strategy_fn, start, end)              │
│          └─► Emit progress every 10% of date range                          │
│          └─► Redis pub/sub: emit progress(50-90%, "Simulating...")          │
│                                                                             │
│  Step 6: Calculate metrics and save results                                 │
│          └─► Compute Sharpe, Sortino, drawdown, etc.                        │
│          └─► PostgreSQL: INSERT INTO backtest_results                       │
│          └─► Redis pub/sub: emit progress(95%, "Saving results")            │
│                                                                             │
│  Step 7: Mark complete                                                      │
│          └─► PostgreSQL: UPDATE backtests SET status='completed'            │
│          └─► Redis pub/sub: emit progress(100%, "Complete!")                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND: Receives completion event                 │
│                         Fetches GET /api/backtests/bt-456/results           │
│                         Renders results dashboard                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Service Dependencies

```
┌───────────────────────────────────────────────────────────────────────────┐
│                      BACKTEST SERVICE DEPENDENCIES                        │
└───────────────────────────────────────────────────────────────────────────┘

                           ┌─────────────────┐
                           │ Backtest Service│
                           │     :8003       │
                           └────────┬────────┘
                                    │
           ┌────────────────────────┼────────────────────────┐
           │                        │                        │
           ▼                        ▼                        ▼
  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
  │Strategy Service │     │Market Data Svc  │     │   PostgreSQL    │
  │     :8002       │     │     :8004       │     │                 │
  ├─────────────────┤     ├─────────────────┤     ├─────────────────┤
  │ GET /strategies │     │ POST /bars      │     │ backtests       │
  │   /{id}         │     │ (multi-symbol)  │     │ backtest_results│
  │                 │     │                 │     │                 │
  │ Returns:        │     │ Returns:        │     │ Stores:         │
  │ • StrategyConfig│     │ • OHLCV bars    │     │ • Config        │
  │ • Indicators    │     │ • For date range│     │ • Status        │
  │ • Conditions    │     │                 │     │ • Results       │
  └─────────────────┘     └────────┬────────┘     └─────────────────┘
                                   │
                                   ▼
                          ┌─────────────────┐
                          │   Alpaca API    │
                          │ (Data Source)   │
                          ├─────────────────┤
                          │ Historical bars │
                          │ via REST API    │
                          └─────────────────┘
```

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
    symbols         JSONB,                  -- ["AAPL", "MSFT"] or null for strategy default
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

    -- Constraints
    CONSTRAINT valid_status CHECK (status IN ('pending','running','completed','failed','cancelled')),
    CONSTRAINT valid_date_range CHECK (end_date > start_date)
);

-- Indexes for common queries
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

Historical market data rarely changes. The system caches aggressively:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CACHING ARCHITECTURE                                │
└─────────────────────────────────────────────────────────────────────────────┘

Request: Get AAPL bars, 1D timeframe, 2023-01-01 to 2024-01-01

                    ┌─────────────────────────────────────┐
                    │           Backtest Worker           │
                    └──────────────────┬──────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────┐
                    │         Redis Cache Lookup          │
                    │  Key: bars:AAPL:1D:2023-01-01:2024-01-01
                    └──────────────────┬──────────────────┘
                                       │
                        ┌──────────────┴──────────────┐
                        │                             │
                   CACHE HIT                      CACHE MISS
                        │                             │
                        ▼                             ▼
                ┌───────────────┐          ┌────────────────────┐
                │ Return cached │          │ Call Market Data   │
                │ bars (fast)   │          │ Service            │
                │ ~5ms          │          │ ~500ms-2s          │
                └───────────────┘          └─────────┬──────────┘
                                                     │
                                                     ▼
                                           ┌────────────────────┐
                                           │ Store in Redis     │
                                           │ TTL: 24 hours      │
                                           │ (data won't change)│
                                           └────────────────────┘

Cache Key Format:
    bars:{symbol}:{timeframe}:{start_date}:{end_date}

Examples:
    bars:AAPL:1D:2023-01-01:2024-01-01
    bars:MSFT:1H:2024-01-15:2024-01-20
    bars:GOOGL:5Min:2024-06-01:2024-06-07
```

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

```
Task retries: 3 attempts with exponential backoff
    Attempt 1: immediate
    Attempt 2: 60 seconds delay
    Attempt 3: 120 seconds delay
    After 3 failures: Mark FAILED with error message
```

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

- **Future performance** - Past results don't guarantee future returns
- **Execution quality** - Real fills depend on market conditions at the moment
- **Emotional factors** - Backtests don't simulate fear, greed, or fatigue
- **Regime changes** - Markets evolve; a strategy that worked in 1990 may fail today
- **Black swan events** - Rare events may not appear in historical data

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
- Few trades (< 100) - insufficient statistical significance

---

## Benchmark Comparisons

Every backtest automatically compares strategy performance against standard benchmarks:

### Built-in Benchmarks

| Benchmark           | Description                             | Use Case                           |
| ------------------- | --------------------------------------- | ---------------------------------- |
| **SPY Buy & Hold**  | S&P 500 ETF held for entire period      | "Did my strategy beat the market?" |
| **Risk-Free Rate**  | 3-month Treasury bill yield             | "Did I beat risk-free returns?"    |
| **60/40 Portfolio** | 60% SPY + 40% BND, rebalanced quarterly | "Did I beat a passive portfolio?"  |

### Benchmark Metrics

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       BENCHMARK COMPARISON REPORT                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Period: 2010-01-01 to 2024-01-01 (14 years)                                │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ Metric              │ Your Strategy │ SPY B&H │ 60/40  │ Risk-Free   │   │
│  ├─────────────────────┼───────────────┼─────────┼────────┼─────────────┤   │
│  │ Total Return        │    +285%      │  +380%  │ +180%  │   +28%      │   │
│  │ Annual Return       │    +10.2%     │ +11.8%  │  +7.6% │   +1.8%     │   │
│  │ Sharpe Ratio        │     1.45      │   0.95  │  0.82  │    N/A      │   │
│  │ Sortino Ratio       │     2.10      │   1.35  │  1.20  │    N/A      │   │
│  │ Max Drawdown        │    -18%       │  -34%   │ -22%   │    0%       │   │
│  │ Volatility (annual) │    12.5%      │  15.2%  │ 10.8%  │   0.3%      │   │
│  │ Beta (vs SPY)       │     0.65      │   1.00  │  0.60  │   0.00      │   │
│  │ Alpha (annual)      │    +3.2%      │   0.0%  │ +0.8%  │    N/A      │   │
│  └─────────────────────┴───────────────┴─────────┴────────┴─────────────┘   │
│                                                                             │
│  Interpretation:                                                            │
│  ✓ Higher Sharpe than SPY (better risk-adjusted returns)                    │
│  ✓ Lower max drawdown than SPY (less painful losses)                        │
│  ✗ Lower total return than SPY (missed some upside)                         │
│  ✓ Positive alpha (excess return beyond market exposure)                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### How Benchmarking Works

Benchmarks are computed **alongside** the strategy backtest, not as separate runs:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    BENCHMARK COMPUTATION FLOW                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  User requests backtest:                                                    │
│    Strategy: RSI Mean Reversion                                             │
│    Date Range: 2010-01-01 to 2024-01-01                                     │
│    Initial Capital: $100,000                                                │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                    PARALLEL DATA FETCHING                              │ │
│  │                                                                        │ │
│  │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐              │ │
│  │  │ Strategy     │    │ SPY          │    │ BND          │              │ │
│  │  │ Symbols      │    │ (S&P 500)    │    │ (Bonds)      │              │ │
│  │  │ AAPL, MSFT   │    │ 2010-2024    │    │ 2010-2024    │              │ │
│  │  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘              │ │
│  │         │                   │                   │                      │ │
│  │         └───────────────────┴───────────────────┘                      │ │
│  │                             │                                          │ │
│  │                    All fetched in parallel                             │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                    PARALLEL COMPUTATION                                │ │
│  │                                                                        │ │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │ │
│  │  │ Strategy Backtest                                                │  │ │
│  │  │ • Run full simulation with signals, positions, P&L               │  │ │
│  │  │ • Track equity curve day by day                                  │  │ │
│  │  │ • Calculate all metrics                                          │  │ │
│  │  └──────────────────────────────────────────────────────────────────┘  │ │
│  │                                                                        │ │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │ │
│  │  │ SPY Buy & Hold (simple)                                          │  │ │
│  │  │ • shares = initial_capital / spy_price[0]                        │  │ │
│  │  │ • equity[t] = shares × spy_price[t]                              │  │ │
│  │  │ • No trading, just price appreciation                            │  │ │
│  │  └──────────────────────────────────────────────────────────────────┘  │ │
│  │                                                                        │ │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │ │
│  │  │ 60/40 Portfolio                                                  │  │ │
│  │  │ • 60% in SPY, 40% in BND                                         │  │ │
│  │  │ • Rebalance quarterly to maintain ratio                          │  │ │
│  │  │ • Track combined equity                                          │  │ │
│  │  └──────────────────────────────────────────────────────────────────┘  │ │
│  │                                                                        │ │
│  │  ┌──────────────────────────────────────────────────────────────────┐  │ │
│  │  │ Risk-Free Rate                                                   │  │ │
│  │  │ • Fetch 3-month Treasury yield for period                        │  │ │
│  │  │ • Compound daily: equity[t] = initial × (1 + rate/252)^t         │  │ │
│  │  └──────────────────────────────────────────────────────────────────┘  │ │
│  │                                                                        │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                    COMPARISON METRICS                                  │ │
│  │                                                                        │ │
│  │  For each benchmark, compute:                                          │ │
│  │  • Total return, annual return                                         │ │
│  │  • Sharpe ratio (same risk-free rate)                                  │ │
│  │  • Max drawdown                                                        │ │
│  │  • Volatility (annualized std of daily returns)                        │ │
│  │                                                                        │ │
│  │  For strategy vs SPY specifically:                                     │ │
│  │  • Beta = cov(strategy, spy) / var(spy)                                │ │
│  │  • Alpha = strategy_return - (rf + beta × (spy_return - rf))           │ │
│  │  • Correlation = corr(strategy_daily, spy_daily)                       │ │
│  │  • Information Ratio = (strategy - spy) / tracking_error               │ │
│  │                                                                        │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Comparing Against Another Strategy

Users can compare any two backtests that share the same date range:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    STRATEGY-TO-STRATEGY COMPARISON                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Method 1: Run New Comparison                                               │
│  ───────────────────────────────                                            │
│                                                                             │
│  User has existing backtest: "RSI Mean Reversion" (2020-2024)               │
│  User wants to compare against: "MACD Crossover" strategy                   │
│                                                                             │
│  → System runs MACD backtest with SAME parameters:                          │
│    • Same date range (2020-2024)                                            │
│    • Same initial capital ($100,000)                                        │
│    • Same commission/slippage settings                                      │
│                                                                             │
│  → Returns side-by-side comparison                                          │
│                                                                             │
│  Method 2: Compare Existing Backtests                                       │
│  ─────────────────────────────────────                                      │
│                                                                             │
│  User selects from backtest history:                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  Select backtests to compare (same date range required):             │   │
│  │                                                                      │   │
│  │  ☑ RSI Mean Reversion    2020-01-01 to 2024-01-01    +45.2%          │   │
│  │  ☑ MACD Crossover        2020-01-01 to 2024-01-01    +38.7%          │   │
│  │  ☐ Bollinger Bounce      2021-01-01 to 2024-01-01    +22.1%  ⚠️      │   │
│  │                          ↑ Different date range - cannot compare     │   │
│  │                                                                      │   │
│  │                                        [ Compare Selected ]          │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Comparing Against a Custom Benchmark Asset

Users can specify any tradeable asset as a benchmark:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CUSTOM BENCHMARK CONFIGURATION                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Benchmark Settings:                                                        │
│                                                                             │
│  Built-in Benchmarks:                                                       │
│    ☑ SPY (S&P 500)                                                          │
│    ☑ 60/40 Portfolio                                                        │
│    ☑ Risk-Free Rate                                                         │
│                                                                             │
│  Custom Benchmarks:                                                         │
│    + Add Custom Benchmark                                                   │
│                                                                             │
│    ┌────────────────────────────────────────────────────────────────────┐   │
│    │  Custom Benchmark 1:                                               │   │
│    │  Symbol: [ QQQ ]  (Nasdaq 100 ETF)                                 │   │
│    │  Type:   [● Buy & Hold  ○ Equal Weight Portfolio]                  │   │
│    │                                                         [ Remove ] │   │
│    └────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│    ┌────────────────────────────────────────────────────────────────────┐   │
│    │  Custom Benchmark 2:                                               │   │
│    │  Symbols: [ XLK, XLF, XLE ]  (Sector ETFs)                         │   │
│    │  Type:   [○ Buy & Hold  ● Equal Weight Portfolio]                  │   │
│    │  Rebalance: [ Monthly ▼ ]                                          │   │
│    │                                                         [ Remove ] │   │
│    └────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Benchmark Data Availability

Different benchmarks have different historical availability:

| Benchmark | Inception | Pre-Inception Handling                       |
| --------- | --------- | -------------------------------------------- |
| SPY       | 1993      | Use S&P 500 index data (^GSPC) for 1980-1993 |
| QQQ       | 1999      | Use Nasdaq 100 index data for earlier        |
| BND       | 2007      | Use aggregate bond index proxy               |
| Risk-Free | 1980+     | 3-month T-bill yields available              |

For backtests starting before a benchmark's inception:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ⚠️  Benchmark Availability Notice                                          │
│                                                                              │
│  Your backtest period: 1985-01-01 to 2024-01-01                             │
│                                                                              │
│  SPY ETF began trading in 1993. For the period 1985-1993, we'll use:       │
│  • S&P 500 Index (^GSPC) total return data                                 │
│  • Simulated dividend reinvestment                                          │
│                                                                              │
│  This provides an accurate representation of S&P 500 performance,           │
│  but actual ETF tracking may differ slightly.                               │
│                                                                              │
│                                              [ Understood, Continue ]        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Alpha and Beta Calculation

**Beta** measures market sensitivity:

```
beta = covariance(strategy_returns, market_returns) / variance(market_returns)
```

- Beta = 1.0: Moves with market
- Beta < 1.0: Less volatile than market (defensive)
- Beta > 1.0: More volatile than market (aggressive)

**Alpha** measures excess returns:

```
alpha = strategy_return - (risk_free_rate + beta × (market_return - risk_free_rate))
```

- Alpha > 0: Strategy adds value beyond market exposure
- Alpha < 0: Strategy underperforms given its risk

### Technical Implementation

```python
# Benchmark computation happens in the backtest worker

class BenchmarkCalculator:
    """Computes benchmark returns alongside strategy backtest."""

    def __init__(self, start_date: date, end_date: date, initial_capital: float):
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital

    async def compute_buy_and_hold(
        self,
        symbol: str,
        bars: dict[str, np.ndarray]
    ) -> BenchmarkResult:
        """Compute buy-and-hold returns for a single asset."""
        closes = bars['close']

        # Buy at first close, hold until last close
        shares = self.initial_capital / closes[0]
        equity_curve = shares * closes

        daily_returns = np.diff(closes) / closes[:-1]

        return BenchmarkResult(
            name=f"{symbol} Buy & Hold",
            equity_curve=equity_curve,
            total_return=(closes[-1] - closes[0]) / closes[0],
            annual_return=self._annualize(daily_returns),
            sharpe_ratio=self._sharpe(daily_returns),
            max_drawdown=self._max_drawdown(equity_curve),
            daily_returns=daily_returns,
        )

    async def compute_portfolio(
        self,
        symbols: list[str],
        weights: list[float],
        bars_by_symbol: dict[str, dict[str, np.ndarray]],
        rebalance_frequency: str = "quarterly",
    ) -> BenchmarkResult:
        """Compute returns for a weighted portfolio with rebalancing."""
        # Implementation handles rebalancing at specified frequency
        ...

    def compute_alpha_beta(
        self,
        strategy_returns: np.ndarray,
        benchmark_returns: np.ndarray,
        risk_free_rate: float = 0.02,
    ) -> tuple[float, float]:
        """Compute alpha and beta using CAPM."""
        # Covariance of strategy with benchmark
        cov_matrix = np.cov(strategy_returns, benchmark_returns)
        beta = cov_matrix[0, 1] / cov_matrix[1, 1]

        # Alpha using CAPM formula
        strategy_annual = self._annualize(strategy_returns)
        benchmark_annual = self._annualize(benchmark_returns)
        alpha = strategy_annual - (risk_free_rate + beta * (benchmark_annual - risk_free_rate))

        return alpha, beta
```

### API Response with Benchmarks

```json
{
  "id": "bt-456",
  "strategy_name": "RSI Mean Reversion",
  "metrics": {
    "total_return": 0.452,
    "sharpe_ratio": 1.82,
    "max_drawdown": -0.12,
    "alpha": 0.085,
    "beta": 0.72
  },
  "benchmarks": {
    "spy_buy_hold": {
      "total_return": 0.385,
      "sharpe_ratio": 1.05,
      "max_drawdown": -0.34
    },
    "portfolio_60_40": {
      "total_return": 0.245,
      "sharpe_ratio": 0.95,
      "max_drawdown": -0.22
    },
    "risk_free": {
      "total_return": 0.082
    }
  },
  "vs_spy": {
    "excess_return": 0.067,
    "alpha": 0.085,
    "beta": 0.72,
    "correlation": 0.65,
    "information_ratio": 0.42
  }
}
```

---

## Walk-Forward Optimization

Walk-forward analysis prevents overfitting by simulating real-world strategy development.

### The Overfitting Problem

Traditional backtesting optimizes parameters on historical data, then tests on the same data:

```
❌ OVERFITTED APPROACH (Don't do this):

    Full History (2000-2024)
    ──────────────────────────────────────────────────────
    │  Optimize parameters: RSI period = 14, threshold = 32.7  │
    │  Test on same data: "Wow, 45% annual return!"            │
    ──────────────────────────────────────────────────────────

    Problem: Parameters are curve-fitted to past, won't work in future
```

### Walk-Forward Solution

Walk-forward repeatedly optimizes on past data and tests on unseen future data:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       WALK-FORWARD ANALYSIS                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ✓ ROBUST APPROACH:                                                         │
│                                                                             │
│  Window 1:                                                                  │
│  ├── In-Sample (optimize): 2000-2004 ──────────────────┐                    │
│  └── Out-of-Sample (test): 2005-2006 ──────────────────┼── Record results   │
│                                                                             │
│  Window 2:                                                                  │
│  ├── In-Sample (optimize): 2002-2006 ──────────────────┐                    │
│  └── Out-of-Sample (test): 2007-2008 ──────────────────┼── Record results   │
│                                                                             │
│  Window 3:                                                                  │
│  ├── In-Sample (optimize): 2004-2008 ──────────────────┐                    │
│  └── Out-of-Sample (test): 2009-2010 ──────────────────┼── Record results   │
│                                                                             │
│  ...continue rolling forward...                                             │
│                                                                             │
│  Window N:                                                                  │
│  ├── In-Sample (optimize): 2018-2022 ──────────────────┐                    │
│  └── Out-of-Sample (test): 2023-2024 ──────────────────┼── Record results   │
│                                                                             │
│  Final Performance = Average of all out-of-sample windows                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Walk-Forward Configuration

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     WALK-FORWARD SETTINGS                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  In-Sample Period:     [ 5 ] years   (how much history to optimize on)      │
│  Out-of-Sample Period: [ 1 ] year    (how far to test forward)              │
│  Step Size:            [ 1 ] year    (how often to re-optimize)             │
│                                                                             │
│  Parameters to Optimize:                                                    │
│    ☑ RSI Period         Range: [ 7 ] to [ 21 ]    Step: [ 1 ]               │
│    ☑ RSI Oversold       Range: [ 20 ] to [ 40 ]   Step: [ 5 ]               │
│    ☑ RSI Overbought     Range: [ 60 ] to [ 80 ]   Step: [ 5 ]               │
│    ☐ Stop Loss %        (fixed at 5%)                                       │
│                                                                             │
│  Optimization Target:   [ Sharpe Ratio ▼ ]                                  │
│                         (maximize this metric during in-sample)             │
│                                                                             │
│                                         [ Run Walk-Forward Analysis ]       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Walk-Forward Results

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     WALK-FORWARD RESULTS                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Windows Tested: 15                                                         │
│  Total Out-of-Sample Period: 15 years (2009-2024)                           │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ Window │ OOS Period  │ Optimal RSI │ OOS Return │ OOS Sharpe │ Status  │ │
│  ├────────┼─────────────┼─────────────┼────────────┼────────────┼─────────┤ │
│  │   1    │ 2009-2010   │ 14, 28, 72  │   +22%     │    1.45    │   ✓     │ │
│  │   2    │ 2010-2011   │ 14, 30, 70  │   +18%     │    1.32    │   ✓     │ │
│  │   3    │ 2011-2012   │ 12, 32, 68  │   -5%      │   -0.25    │   ✗     │ │
│  │   4    │ 2012-2013   │ 14, 28, 72  │   +31%     │    2.10    │   ✓     │ │
│  │  ...   │    ...      │     ...     │    ...     │    ...     │  ...    │ │
│  │  15    │ 2023-2024   │ 16, 25, 75  │   +12%     │    0.95    │   ✓     │ │
│  └────────┴─────────────┴─────────────┴────────────┴────────────┴─────────┘ │
│                                                                             │
│  Aggregate Out-of-Sample Performance:                                       │
│  • Annual Return: +11.2% (vs in-sample: +18.5%)                             │
│  • Sharpe Ratio:   1.05 (vs in-sample: 1.85)                                │
│  • Win Rate:      73% of windows profitable                                 │
│  • Efficiency:    60% (OOS Sharpe / IS Sharpe)                              │
│                                                                             │
│  ⚠️  Efficiency < 70% suggests moderate overfitting                         │
│  ✓  Strategy remains profitable out-of-sample                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Walk-Forward Efficiency

**Efficiency Ratio** = Out-of-Sample Performance / In-Sample Performance

| Efficiency | Interpretation                 |
| ---------- | ------------------------------ |
| > 80%      | Excellent - strategy is robust |
| 60-80%     | Good - acceptable degradation  |
| 40-60%     | Moderate - some overfitting    |
| < 40%      | Poor - significant overfitting |

---

## Monte Carlo Simulation

Monte Carlo simulation assesses strategy robustness by testing performance under randomized conditions.

### Why Monte Carlo?

A single backtest shows what _did_ happen. Monte Carlo shows the range of what _could_ happen:

- What if trades occurred in a different order?
- What if we started on a different date?
- What's the worst-case scenario at 95% confidence?

### Simulation Methods

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     MONTE CARLO METHODS                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Method 1: TRADE SHUFFLING                                                  │
│  ─────────────────────────                                                  │
│  Original sequence:  [+2%, -1%, +3%, -2%, +1%, +4%, -1%, +2%]               │
│  Shuffled run 1:     [-1%, +3%, +2%, +1%, -2%, +2%, +4%, -1%]               │
│  Shuffled run 2:     [+4%, -2%, +1%, -1%, +2%, +3%, -1%, +2%]               │
│  ...1000 more shuffles...                                                   │
│                                                                             │
│  Purpose: Test if strategy success depends on lucky trade ordering          │
│                                                                             │
│  Method 2: RANDOM START DATES                                               │
│  ────────────────────────────                                               │
│  Instead of starting Jan 1, 2010:                                           │
│  • Run starting Mar 15, 2010                                                │
│  • Run starting Jul 22, 2010                                                │
│  • Run starting Nov 3, 2010                                                 │
│  ...1000 random start dates...                                              │
│                                                                             │
│  Purpose: Test if strategy success depends on lucky start timing            │
│                                                                             │
│  Method 3: BOOTSTRAPPED RETURNS                                             │
│  ──────────────────────────────                                             │
│  Sample daily returns with replacement to create synthetic histories        │
│  Preserves return distribution but destroys temporal patterns               │
│                                                                             │
│  Purpose: Estimate confidence intervals for metrics                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Monte Carlo Configuration

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     MONTE CARLO SETTINGS                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Number of Simulations:  [ 1,000 ]                                          │
│                                                                             │
│  Methods to Run:                                                            │
│    ☑ Trade Shuffling      (randomize trade order)                           │
│    ☑ Random Start Dates   (vary entry timing)                               │
│    ☐ Bootstrapped Returns (resample with replacement)                       │
│                                                                             │
│  Confidence Intervals:   [ 95 ]%                                            │
│                                                                             │
│                                          [ Run Monte Carlo Analysis ]       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Monte Carlo Results

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     MONTE CARLO RESULTS                                     │
│                     1,000 Simulations                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │              EQUITY CURVE DISTRIBUTION (Trade Shuffling)            │    │
│  │                                                                     │    │
│  │  $200k ┤                                         ╭─── Best 5%       │    │
│  │        │                              ╭──────────╯                  │    │
│  │  $150k ┤                    ╭─────────┼──────── Median              │    │
│  │        │          ╭─────────┼─────────╯                             │    │
│  │  $100k ┼──────────┼─────────┼───────────────────── Worst 5%         │    │
│  │        │          ╰─────────╯                                       │    │
│  │   $50k ┤                                                            │    │
│  │        └──────────────────────────────────────────────────────────  │    │
│  │         2010      2014      2018      2022      2024                │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                METRIC DISTRIBUTIONS                                   │  │
│  ├──────────────────┬──────────┬──────────┬──────────┬───────────────────┤  │
│  │ Metric           │ Original │  Median  │   5th %  │  95th %           │  │
│  ├──────────────────┼──────────┼──────────┼──────────┼───────────────────┤  │
│  │ Total Return     │  +120%   │  +115%   │   +45%   │  +180%            │  │
│  │ Annual Return    │  +8.5%   │   +8.2%  │   +3.8%  │  +12.5%           │  │
│  │ Sharpe Ratio     │   1.25   │   1.20   │   0.65   │   1.75            │  │
│  │ Max Drawdown     │  -18%    │  -20%    │  -35%    │  -12%             │  │
│  │ Longest Drawdown │  8 mo    │  10 mo   │  22 mo   │   5 mo            │  │
│  └──────────────────┴──────────┴──────────┴──────────┴───────────────────┘  │
│                                                                             │
│  Key Insights:                                                              │
│  ✓ 95% of simulations were profitable (confidence in strategy)              │
│  ⚠ 5% worst case: -35% drawdown (plan for this psychologically)             │
│  ✓ Median close to original (strategy not dependent on trade order)         │
│  ✓ Sharpe stays > 0.65 even in worst 5% (robust risk-adjusted returns)      │
│                                                                             │
│  Risk Assessment:                                                           │
│  • Expected Annual Return: +8.2% (median)                                   │
│  • Worst-Case Annual Return: +3.8% (5th percentile)                         │
│  • 95% Confidence Drawdown: You should expect up to -35% at some point      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Interpreting Monte Carlo Results

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

### Monte Carlo + Walk-Forward Combined

For maximum confidence, run both:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     COMBINED ROBUSTNESS ANALYSIS                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. Run Walk-Forward Analysis                                               │
│     → Confirms strategy works out-of-sample (not curve-fitted)              │
│                                                                             │
│  2. Run Monte Carlo on Out-of-Sample Results                                │
│     → Confirms results aren't dependent on lucky timing/ordering            │
│                                                                             │
│  Combined Confidence Score:                                                 │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                                                                        │ │
│  │   Walk-Forward Efficiency:  68%  ───────────────┬                      │ │
│  │   Monte Carlo Win Rate:     94%  ───────────────┼─► Combined: 85/100   │ │
│  │   MC Median vs Original:    97%  ───────────────┘                      │ │
│  │                                                                        │ │
│  │   Interpretation: HIGH CONFIDENCE - Strategy is robust                 │ │
│  │                                                                        │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Comparison Feature

Users can compare multiple backtests side-by-side:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BACKTEST COMPARISON                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     EQUITY CURVES OVERLAY                           │    │
│  │  $140k ┤         ── RSI Strategy                                    │    │
│  │        │         ── MA Crossover                                    │    │
│  │  $120k ┤         ── Buy & Hold SPY                                  │    │
│  │        │                                                            │    │
│  │  $100k ┼─────────────────────────────────────────────────────────   │    │
│  │         Jan    Mar    May    Jul    Sep    Nov    Jan               │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                     METRICS COMPARISON                                │  │
│  ├──────────────────┬──────────────┬────────────────┬────────────────────┤  │
│  │ Metric           │ RSI Strategy │ MA Crossover   │ Buy & Hold SPY     │  │
│  ├──────────────────┼──────────────┼────────────────┼────────────────────┤  │
│  │ Total Return     │    +28.5%    │    +18.2%      │    +22.1%          │  │
│  │ Sharpe Ratio     │     1.82     │     1.24       │     1.45           │  │
│  │ Max Drawdown     │    -8.3%     │   -12.1%       │   -10.5%           │  │
│  │ Win Rate         │    61.7%     │    55.2%       │      N/A           │  │
│  │ Total Trades     │      47      │      23        │       1            │  │
│  └──────────────────┴──────────────┴────────────────┴────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

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
    "total_trades": 47
  },
  "equity_curve": [
    {"date": "2023-01-01", "equity": 100000, "drawdown": 0},
    {"date": "2023-01-02", "equity": 100500, "drawdown": 0},
    ...
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
    },
    ...
  ],
  "monthly_returns": {
    "2023-01": 0.021,
    "2023-02": 0.034,
    ...
  }
}
```

### Cancel Backtest

```http
DELETE /api/backtests/{id}
Authorization: Bearer {jwt_token}

Response: 200 OK
{
  "id": "uuid",
  "status": "cancelled"
}
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
// Frontend connection
const ws = new WebSocket(
  "wss://api.llamatrade.com/ws/backtests/bt-456/progress",
);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  // {
  //   "backtest_id": "bt-456",
  //   "progress": 65,
  //   "message": "Simulating Q3 2023...",
  //   "status": "running"
  // }
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
