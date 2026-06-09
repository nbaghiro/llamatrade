# Strategy DSL Reference

Complete, implementation-accurate reference for the S-expression Domain-Specific Language (DSL) used in LlamaTrade to define trading strategies.

> **Scope note.** This document describes the DSL as implemented in `libs/dsl` and `libs/compiler`. The canonical source of truth for the grammar is `libs/dsl/llamatrade_dsl/ast.py`.

---

## Table of Contents

1. [Overview & Mental Model](#overview--mental-model)
2. [Design Principles](#design-principles)
3. [Processing Pipeline](#processing-pipeline)
4. [Language Basics](#language-basics)
5. [Block Types](#block-types)
6. [Weight Methods](#weight-methods)
7. [Rebalance Frequencies](#rebalance-frequencies)
8. [Conditions](#conditions)
9. [Value Expressions](#value-expressions)
10. [Technical Indicators](#technical-indicators)
11. [Metrics](#metrics)
12. [Grammar Specification](#grammar-specification)
13. [Abstract Syntax Tree](#abstract-syntax-tree)
14. [Parser Implementation](#parser-implementation)
15. [Serialization & Storage](#serialization--storage)
16. [Validation Rules](#validation-rules)
17. [Execution Pipeline](#execution-pipeline)
18. [Multi-Strategy Execution & the Portfolio Ledger](#multi-strategy-execution--the-portfolio-ledger)
19. [Example Strategies](#example-strategies)
20. [Tips for Writing Strategies](#tips-for-writing-strategies)
21. [Related Documentation](#related-documentation)

---

## Overview & Mental Model

LlamaTrade uses a Lisp-inspired S-expression DSL to define **portfolio allocation strategies**. The single most important thing to understand:

> **The DSL is an allocation language, not a signal language.** A strategy is a *tree* that, when evaluated on a given bar, produces a set of **target portfolio weights** — e.g. `{VTI: 60%, BND: 40%}`. It never says "buy 100 shares." The execution layer compares those target weights against current holdings and generates whatever trades are needed to close the gap.

Every keyword in the language exists to do one of two things:

1. **Shape the target weight vector** — which assets are held and in what proportion (`asset`, `weight`, `group`, `filter`).
2. **Make that shape react to the market** — conditional allocation based on indicators and price (`if`/`else`, conditions, indicators).

A minimal complete strategy:

```lisp
(strategy "Dual Moving Average"
  :rebalance daily
  :benchmark SPY
  (if (> (sma SPY 50) (sma SPY 200))
    (asset VTI :weight 100)
    (else (asset BND :weight 100))))
```

This says: *every trading day, if SPY's 50-day average is above its 200-day average, hold 100% VTI; otherwise hold 100% BND.*

---

## Design Principles

1. **S-expression syntax** — parenthesized prefix notation. There is exactly one way to parse any valid expression; no operator-precedence ambiguity.
2. **Declarative** — describes *what* the allocation should be, not *how* to execute it.
3. **Composable** — blocks nest arbitrarily deep; a `weight` can contain a `group` containing an `if` containing a `filter`, and so on.
4. **Bidirectional** — lossless round-tripping between S-expression text, the typed AST, JSON, and the visual block builder. The visual builder generates DSL; DSL renders back into blocks.
5. **Single source of truth** — all input methods (visual builder, code editor, AI generation) produce the same AST. The AST is authoritative.

---

## Processing Pipeline

```
        Visual Builder            Code Editor            AI Assistant
         (React blocks)          (S-expr text)        (natural language)
               │                       │                      │
               └───────────┬───────────┴──────────────────────┘
                           ▼
                    PARSER  (libs/dsl/parser.py)
                    hand-written recursive-descent parser
                    + regex tokenizer; tracks source locations
                           │
                           ▼
                    AST  (libs/dsl/ast.py)
                    typed, frozen dataclasses
                           │
              ┌────────────┼─────────────┐
              ▼            ▼             ▼
        VALIDATOR      SERIALIZER     to_json
     (semantic check) (AST→S-expr)  (AST→JSON IR)
              │                          │
              ▼                          ▼
        ValidationResult        Stored in PostgreSQL:
                                 StrategyVersion.config_sexpr (source)
                                 StrategyVersion.config_json  (compiled IR)
                                          │
                           ┌──────────────┴───────────────┐
                           ▼                               ▼
                    COMPILER (backtest)            COMPILER (live)
              vectorized engine / bar-by-bar      bar-by-bar engine
              (libs/compiler)                     (libs/compiler)
                           │                               │
                           ▼                               ▼
                    Backtest results               Live target weights
                    (equity curve, metrics)        → Portfolio Ledger → orders
```

**Parser** (`libs/dsl/parser.py`) — a hand-written recursive-descent parser fronted by a regex tokenizer. (Note: this is *not* a Lark/EBNF grammar; the EBNF below is descriptive, not the implementation.) Every node records a `SourceLocation` (line, column, character offsets) for precise error messages.

**Validator** (`libs/dsl/validator.py`) — checks semantic correctness (valid methods/indicators, weight sums, positive parameters, etc.).

**Compiler** (`libs/compiler`) — extracts the required indicators, computes them with NumPy, and evaluates the tree into target weights. There are two execution engines that consume the **same AST**: a **bar-by-bar** engine (live trading) and a **vectorized** engine (backtesting). See [Execution Pipeline](#execution-pipeline).

---

## Language Basics

### Expressions and Lists

Everything is either an atom (number, string, symbol) or a parenthesized list. The first element of a list is the operator/keyword; the rest are arguments:

```lisp
(sma SPY 50)        ; 50-period simple moving average of SPY
(> (rsi QQQ 14) 70) ; is QQQ's 14-period RSI above 70?
```

### Data Types

| Type | Syntax | Examples | Notes |
|------|--------|----------|-------|
| Number | integer or decimal, optional minus | `14`, `0.5`, `-2.5` | **No `%` suffix** — `30` is the number thirty |
| String | double-quoted | `"My Strategy"`, `"US Equities"` | Used for `strategy`/`group` names |
| Symbol (ticker) | starts with a letter | `SPY`, `AAPL`, `BRK-B`, `BTC-USD` | May contain letters, digits, `_`, `-` |
| Keyword | colon-prefixed | `:rebalance`, `:method`, `:weight`, `:high` | Named parameters and options |

### Comments

Single-line comments start with a semicolon and run to end of line:

```lisp
;; This is a comment
(strategy "Test"        ; inline comment
  :rebalance weekly
  ...)
```

---

## Block Types

There are **six** block types. They form the structural tree of a strategy.

### 1. `strategy` — root block

The single top-level container. Exactly one per document; it must be the outermost form.

```lisp
(strategy "Name"
  [:rebalance <frequency>]
  [:benchmark <symbol>]
  [:description "<text>"]
  <child-blocks>...)
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `"Name"` | Yes | Human-readable name (first positional argument, a string) |
| `:rebalance` | No | Rebalancing frequency — see [Rebalance Frequencies](#rebalance-frequencies) |
| `:benchmark` | No | Ticker used **only for reporting** (alpha/beta/relative return); does not affect allocation |
| `:description` | No | Free-text metadata |

### 2. `asset` — a single holding (leaf)

The terminal node and the only thing that actually receives weight.

```lisp
(asset <symbol> [:weight <number>])
```

- `<symbol>` — the ticker (required).
- `:weight` — explicit percentage. **Only valid when the parent `weight` block uses `:method specified`.** Under any other method, supplying `:weight` is a validation error (the method computes the weight).

```lisp
(asset VTI)
(asset AAPL :weight 25)
```

### 3. `weight` — the allocation engine

Takes its children and assigns each a fraction of the capital flowing into the block, according to `:method`. Weights within a block are normalized to 100% of the block's share.

```lisp
(weight :method <method> [:lookback <days>] [:top <n>]
  <child-blocks>...)
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `:method` | Yes | Allocation method — see [Weight Methods](#weight-methods) |
| `:lookback` | No | Historical window (days) for dynamic methods. Must be > 0 |
| `:top` | No | Keep only the top N children by the method's ranking metric, then allocate among those N. Must be > 0 |

```lisp
;; Manual weights — must sum to ~100% within the block
(weight :method specified
  (asset VTI :weight 60)
  (asset BND :weight 40))

;; Equal weight
(weight :method equal
  (asset VTI) (asset VXUS) (asset BND))

;; Momentum, hold the strongest 3 of 5
(weight :method momentum :lookback 90 :top 3
  (asset XLK) (asset XLF) (asset XLE) (asset XLV) (asset XLI))
```

`weight` blocks compose: an outer `equal` over two inner `weight` blocks gives each inner block 50% of capital, which it then subdivides by its own method.

### 4. `group` — organization

A named container. **Transparent by default** — capital flows straight through to its children; it exists for readability and UI structure.

```lisp
(group "<name>" [:weight <number>]
  <child-blocks>...)
```

- `:weight` — like `asset`, honored **only** when the parent `weight` is `:method specified`. Lets a whole subtree carry a specified weight.

```lisp
(group "US Equities" :weight 60
  (weight :method equal
    (asset VTI) (asset VXF)))
```

### 5. `if` / `else` — conditional allocation

The only branching construct. Evaluates a condition against current market data; the subtree's allocation is the `then` block if true, else the `else` block.

```lisp
(if <condition>
  <then-block>
  [(else <else-block>)])
```

- `<then-block>` is a **single** block. To allocate across several things in a branch, wrap them in a `weight`.
- The else clause **must** be wrapped in `(else ...)` — bare juxtaposition is not allowed.
- If `else` is omitted and the condition is false, the subtree contributes nothing.

```lisp
;; Nested regimes: oversold → risk-on, overbought → risk-off, else neutral
(if (< (rsi SPY 14) 30)
  (asset SPY :weight 100)
  (else
    (if (> (rsi SPY 14) 70)
      (asset TLT :weight 100)
      (else (weight :method equal (asset SPY) (asset TLT))))))
```

> **Timing note.** Conditions are evaluated on each rebalance. With a `monthly` rebalance, an `if` is only re-checked monthly, so regime switches lag by up to the rebalance period. See [Execution Pipeline](#execution-pipeline).

### 6. `filter` — dynamic selection

Selects a subset of its candidate assets by a ranking metric *before* weighting them.

```lisp
(filter :by <criteria> :select (<direction> <N>) [:lookback <days>]
  <child-blocks>...)
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `:by` | Yes | Ranking metric: `momentum`, `volatility`, or `volume` |
| `:select` | Yes | `(top N)` or `(bottom N)` — keep the N highest/lowest ranked |
| `:lookback` | No | Window for computing the ranking metric. Must be > 0 |

`:select_count` must not exceed the number of candidate assets.

```lisp
;; Top 3 sectors by 90-day momentum, then equal-weight them
(filter :by momentum :select (top 3) :lookback 90
  (weight :method equal
    (asset XLK) (asset XLF) (asset XLE) (asset XLV) (asset XLI)))
```

---

## Weight Methods

Valid values for `:method` (source: `WEIGHT_METHODS` in `ast.py`):

| Method | Description | Requires |
|--------|-------------|----------|
| `specified` | Manual percentages set via `:weight` on each child; must sum to ~100% | `:weight` on each child |
| `equal` | Split evenly: `100/N` per child | — |
| `momentum` | Weight proportional to recent return (winners get more) | `:lookback` |
| `inverse-volatility` | Weight inversely to volatility (calmer assets get more) | `:lookback` |
| `min-variance` | Solve for the minimum-variance weight vector (covariance matrix) | `:lookback` |
| `market-cap` | Weight by market capitalization (index-like) | market-cap data |
| `risk-parity` | Equal *risk* contribution per asset (accounts for correlation) | `:lookback` |

Method names are **kebab-case** in the DSL (`inverse-volatility`, `min-variance`, `risk-parity`). The visual builder stores them internally as snake_case and converts at the DSL boundary.

### How the dynamic methods compute weights

Given the child candidates and a `:lookback` window of daily returns:

- **`equal`** — `wᵢ = 100 / N`.
- **`momentum`** — score each child by trailing return `rᵢ = priceₜ / priceₜ₋ₗₒₒₖᵦₐᶜᵏ − 1`; if `:top N` is set, keep the N highest-scoring; weight the survivors (equally, or proportional to score).
- **`inverse-volatility`** — `wᵢ ∝ 1 / σᵢ`, where `σᵢ` is the standard deviation of returns over `:lookback`; normalize to 100%. Calmer assets get more.
- **`risk-parity`** — target equal *risk contribution* per asset (accounts for correlations). Currently approximated by inverse-volatility.
- **`min-variance`** — choose the weight vector minimizing portfolio variance `wᵀΣw` over the `:lookback` covariance matrix `Σ`.
- **`market-cap`** — `wᵢ ∝ marketCapᵢ` (index-like).

All methods normalize to sum to 100% of the block's share; NaN / all-zero edge cases fall back to equal weight.

---

## Rebalance Frequencies

Valid values for `:rebalance` (source: `REBALANCE_FREQUENCIES` in `ast.py`). This is the **most behavior-defining setting** in the language — it controls how often conditions are re-evaluated and the portfolio is re-aligned to target.

| Value | Recompute target weights… |
|-------|---------------------------|
| `daily` | every trading day |
| `weekly` | once per week |
| `monthly` | once per month |
| `quarterly` | once per quarter |
| `annually` | once per year |

Higher frequency = more responsive but more turnover/cost; lower = smoother but laggier on regime changes.

### Two clocks: ticks vs. rebalances

`:rebalance` does **not** say how many times per day a strategy runs. Two separate clocks are at play:

- **Tick clock (data feed).** In live trading the runner receives **1-minute bars** and runs its per-bar loop *every minute the market is open* — appending the bar to history and checking its gates. This cadence is fixed by the feed, not the strategy.
- **Rebalance gate (`:rebalance`).** On each tick, a **date-based** check (`should_rebalance`, which also enforces *never twice on the same day*) decides whether to actually recompute target weights and trade.

So the frequency gates the minute-ticks down to actual rebalances — **at most once per day**:

| Frequency | Rebalances when… | Times per open session |
|-----------|------------------|------------------------|
| `daily` | every trading day (first qualifying bar) | **1**, then holds the rest of the day |
| `weekly` | the week changes (first trading day of the week) | 1 that day, 0 otherwise |
| `monthly` | the month changes | 1 that day, 0 otherwise |
| `quarterly` | the quarter changes | 1 that day, 0 otherwise |
| `annually` | the year changes | 1 that day, 0 otherwise |

**Evaluated** (ticked, history updated, gates checked) happens every bar; **rebalanced** (recompute target → diff vs current → trade the delta) happens only when the gate opens. A strategy is therefore a periodic loop, not a continuous one — and a single rebalance can emit **multiple orders at once** (one per symbol whose holding must change).

> **No sub-daily rebalancing (current limitation).** The finest grain is `daily` — once per day. The platform *ingests* minute bars but only *acts* daily-or-coarser; there is no "every 5 minutes" / hourly cadence yet (intraday / event-driven rebalancing is roadmap). Related caveat: a `daily` strategy referencing e.g. `(sma SPY 200)` computes that indicator over whatever bars have accumulated in the live window — the timeframe-vs-bar-resolution behavior is an open item to verify when execution is built out.

---

## Conditions

Conditions appear inside `if` blocks and evaluate to true/false against market data. Three families.

### Comparison operators

```lisp
(> left right)   (< left right)   (>= left right)   (<= left right)   (= left right)   (!= left right)
```

Compare two [value expressions](#value-expressions):

```lisp
(> (sma SPY 50) (sma SPY 200))   ; uptrend
(< (rsi QQQ 14) 30)              ; oversold
(>= (price AAPL) 150)            ; price at/above $150
```

### Crossover operators

```lisp
(crosses-above fast slow)   ; fast was ≤ slow, now fast > slow (bullish)
(crosses-below fast slow)   ; fast was ≥ slow, now fast < slow (bearish)
```

Crossovers detect a **transition**, not a persistent state, and therefore require **two bars of history** (today and the prior bar). The compiler enforces a minimum lookback of 2 for any strategy using a crossover.

```lisp
(crosses-above (sma SPY 50) (sma SPY 200))   ; golden cross
(crosses-below (ema QQQ 12) (ema QQQ 26))    ; bearish EMA cross
```

> A `>` comparison is true *every* bar the trend persists; a `crosses-above` is true only on the single bar of the cross. With infrequent rebalancing, crossovers can be missed between rebalance dates — prefer comparisons for low-frequency strategies.

### Logical operators

```lisp
(and cond1 cond2 ...)   ; all true   (≥ 2 operands)
(or  cond1 cond2 ...)   ; any true   (≥ 2 operands)
(not cond)              ; negation   (exactly 1 operand)
```

```lisp
(and (> (sma SPY 50) (sma SPY 200)) (< (rsi SPY 14) 70))   ; uptrend AND not overbought
(or  (> (rsi QQQ 14) 70) (< (rsi QQQ 14) 30))              ; overbought OR oversold
(not (> (drawdown SPY) 0.20))                              ; not in a >20% drawdown
```

---

## Value Expressions

The operands of comparisons and crossovers. Four kinds.

### Numeric literal

```lisp
50      0.30      -2.5
```

A constant. No percentage syntax — compare RSI to `30`, not `30%`.

### `price` — spot price reference

```lisp
(price <symbol> [:<field>])
```

The optional field keyword is one of `:close` (default), `:open`, `:high`, `:low`, `:volume`. **The field name *is* the keyword** — it is `(price SPY :high)`, not `(price SPY :field high)`.

```lisp
(price SPY)          ; close (default)
(price AAPL :high)   ; the bar's high
(price SPY :volume)  ; volume
```

### Indicator

A [technical indicator](#technical-indicators) call. General form:

```lisp
(<name> <symbol> <params...> [:<output>])
```

Multi-output indicators (MACD, Bollinger Bands, ADX, Stochastic) take an `:output` keyword to select which line is wanted; the default is the indicator's primary line.

### Metric

A derived statistic — see [Metrics](#metrics):

```lisp
(drawdown SPY)       ; current decline from peak
(return SPY 30)      ; 30-period return
(volatility SPY)     ; realized volatility
```

---

## Technical Indicators

The supported indicators (source: `INDICATORS` in `ast.py`; computations in `libs/compiler/pipeline.py`). General form `(<name> <symbol> <params...> [:<output>])`.

### Trend / Moving Averages

| Indicator | Syntax | Measures |
|-----------|--------|----------|
| SMA | `(sma SYM period)` | Simple moving average (trend baseline) |
| EMA | `(ema SYM period)` | Exponential moving average (faster-reacting trend) |
| MACD | `(macd SYM fast slow signal [:line\|:signal\|:histogram])` | Trend/momentum convergence; default output `:line` |
| ADX | `(adx SYM period [:value\|:plus_di\|:minus_di])` | Trend **strength** + directional indicators; default `:value` |

```lisp
(sma SPY 50)
(ema SPY 12)
(macd SPY 12 26 9 :signal)
(adx SPY 14 :plus_di)
```

### Momentum / Oscillators

| Indicator | Syntax | Measures |
|-----------|--------|----------|
| RSI | `(rsi SYM period)` | Relative Strength Index, 0–100 (overbought/oversold) |
| Stochastic | `(stoch SYM k d smooth [:k\|:d])` | Momentum vs. recent range; default `:k` |
| CCI | `(cci SYM period)` | Commodity Channel Index (deviation from mean) |
| Williams %R | `(williams-r SYM period)` | Overbought/oversold, −100 to 0 |
| MFI | `(mfi SYM period)` | Money Flow Index (volume-weighted RSI) |
| Momentum | `(momentum SYM period)` | Raw price change over N periods |

### Volatility

| Indicator | Syntax | Measures |
|-----------|--------|----------|
| Bollinger Bands | `(bbands SYM period stddev [:upper\|:middle\|:lower])` | Volatility envelope; default `:middle` |
| ATR | `(atr SYM period)` | Average True Range (absolute volatility) |
| Keltner Channels | `(keltner SYM period mult)` | ATR-based envelope |
| Std Dev | `(stddev SYM period)` | Rolling standard deviation |

### Volume / Channels

| Indicator | Syntax | Measures |
|-----------|--------|----------|
| OBV | `(obv SYM)` | On-Balance Volume (volume-flow accumulation) |
| VWAP | `(vwap SYM)` | Volume-Weighted Average Price |
| Donchian | `(donchian SYM period)` | N-period high/low channel (breakout) |

These cover the four classic families — trend, momentum, volatility, and volume.

### Default parameters

Parameters are optional; if omitted, these defaults apply (source: `compute_indicator` in `libs/compiler/pipeline.py`):

| Indicator | Default params | | Indicator | Default params |
|-----------|----------------|---|-----------|----------------|
| `sma` | period 20 | | `stoch` | k 14, d 3, smooth 3 |
| `ema` | period 20 | | `cci` | period 20 |
| `rsi` | period 14 | | `williams-r` | period 14 |
| `macd` | fast 12, slow 26, signal 9 | | `mfi` | period 14 |
| `bbands` | period 20, stddev 2.0 | | `keltner` | period 20, mult 2.0 |
| `atr` | period 14 | | `donchian` | period 20 |
| `adx` | period 14 | | `stddev` | period 20 |
| `obv` | none | | `momentum` | period 10 |
| `vwap` | none | | | |

The default `:output` for multi-output indicators is: `macd` → `:line`, `bbands` → `:middle`, `adx` → `:value`, `stoch` → `:k`.

---

## Metrics

Derived statistics (source: `METRICS` in `ast.py`). Form: `(<name> <symbol> [period])`.

| Metric | Syntax | Meaning |
|--------|--------|---------|
| `drawdown` | `(drawdown SYM)` | Current decline from the peak (e.g. `0.15` = 15% off highs) |
| `return` | `(return SYM period)` | Return over the period |
| `volatility` | `(volatility SYM [period])` | Realized volatility |

```lisp
(> (drawdown SPY) 0.15)   ; SPY is more than 15% off its peak → de-risk
```

---

## Grammar Specification

Descriptive grammar (the implementation is a hand-written recursive-descent parser, not a generated one):

```ebnf
strategy      = "(" "strategy" STRING strategy-opt* block* ")"
strategy-opt  = ":rebalance" FREQUENCY
              | ":benchmark" SYMBOL
              | ":description" STRING

block         = asset | weight | group | if | filter

asset         = "(" "asset" SYMBOL (":weight" NUMBER)? ")"
weight        = "(" "weight" ":method" METHOD (":lookback" NUMBER)? (":top" NUMBER)? block+ ")"
group         = "(" "group" STRING (":weight" NUMBER)? block+ ")"
if            = "(" "if" condition block ("(" "else" block ")")? ")"
filter        = "(" "filter" ":by" CRITERIA ":select" "(" DIRECTION NUMBER ")" (":lookback" NUMBER)? block+ ")"

condition     = comparison | crossover | logical
comparison    = "(" COMPARATOR value value ")"
crossover     = "(" ("crosses-above" | "crosses-below") value value ")"
logical       = "(" "and" condition condition+ ")"
              | "(" "or"  condition condition+ ")"
              | "(" "not" condition ")"

value         = NUMBER | price | indicator | metric
price         = "(" "price" SYMBOL (":close"|":open"|":high"|":low"|":volume")? ")"
indicator     = "(" INDICATOR SYMBOL NUMBER* (":" NAME)? ")"
metric        = "(" METRIC SYMBOL NUMBER? ")"

FREQUENCY     = "daily" | "weekly" | "monthly" | "quarterly" | "annually"
METHOD        = "specified" | "equal" | "momentum" | "inverse-volatility"
              | "min-variance" | "market-cap" | "risk-parity"
CRITERIA      = "momentum" | "volatility" | "volume"
DIRECTION     = "top" | "bottom"
COMPARATOR    = ">" | "<" | ">=" | "<=" | "=" | "!="
INDICATOR     = "sma"|"ema"|"rsi"|"macd"|"atr"|"adx"|"bbands"|"stoch"|"cci"
              | "obv"|"vwap"|"mfi"|"williams-r"|"keltner"|"donchian"|"stddev"|"momentum"
METRIC        = "drawdown" | "return" | "volatility"
SYMBOL        = letter (letter | digit | "_" | "-")*
NUMBER        = "-"? digit+ ("." digit+)?
STRING        = '"' character* '"'
```

---

## Abstract Syntax Tree

The parser produces typed, frozen dataclasses (source: `libs/dsl/llamatrade_dsl/ast.py`). Every node carries an optional `SourceLocation`.

**Blocks:** `Strategy`, `Group`, `Weight`, `Asset`, `If`, `Filter`

**Conditions:** `Comparison`, `Crossover`, `LogicalOp`

**Values:** `NumericLiteral`, `Price`, `Indicator`, `Metric`

```python
# Representative definitions (see ast.py for the full set)

@dataclass(slots=True)
class Strategy:
    name: str
    children: list[Block]
    rebalance: RebalanceFrequency | None = None   # "daily".."annually"
    benchmark: str | None = None
    description: str | None = None
    location: SourceLocation | None = None

@dataclass(slots=True)
class Weight:
    method: WeightMethod         # "specified".."risk-parity"
    children: list[Block]
    lookback: int | None = None
    top: int | None = None

@dataclass(frozen=True, slots=True)
class Asset:
    symbol: str
    weight: float | None = None

@dataclass(slots=True)
class If:
    condition: Condition
    then_block: Block
    else_block: Block | None = None

@dataclass(slots=True)
class Filter:
    by: FilterCriteria                  # "momentum"|"volatility"|"volume"
    select_direction: SelectDirection   # "top"|"bottom"
    select_count: int
    children: list[Block]
    lookback: int | None = None

@dataclass(frozen=True, slots=True)
class Indicator:
    name: str
    symbol: str
    params: tuple[int | float, ...] = ()
    output: str | None = None           # e.g. "signal", "upper", "plus_di"

@dataclass(frozen=True, slots=True)
class Price:
    symbol: str
    field: PriceField = "close"         # "close"|"open"|"high"|"low"|"volume"
```

Type unions: `Block = Strategy | Group | Weight | Asset | If | Filter`, `Condition = Comparison | Crossover | LogicalOp`, `Value = NumericLiteral | Price | Indicator | Metric`.

---

## Parser Implementation

`libs/dsl/llamatrade_dsl/parser.py` implements a two-stage parser.

**1. Tokenizer** — a single compiled regex (`TOKEN_PATTERN`) with named groups: `LPAREN`, `RPAREN`, `STRING`, `KEYWORD` (`:name`), `NUMBER`, `OPERATOR` (`>`, `<`, `>=`, `<=`, `!=`, `crosses-above`, `crosses-below`), `SYMBOL`, plus `SKIP` (whitespace) and `COMMENT` (`;` to EOL). The tokenizer tracks 1-indexed line/column and 0-indexed character offsets.

**2. Recursive-descent parser** — `Parser.parse()` returns a `Strategy`. It peeks the symbol after each `(` and dispatches to `_parse_strategy`, `_parse_block`, `_parse_weight`, `_parse_if`, `_parse_filter`, `_parse_condition`, `_parse_value`, etc. Each node captures start/end positions so errors can report `line N, col M`.

Public API:

```python
from llamatrade_dsl import parse, validate, serialize, to_json, from_json

ast = parse(source_string)        # str  -> Strategy (raises ParseError)
result = validate(ast)            # Strategy -> ValidationResult
text = serialize(ast, pretty=True)# Strategy -> str  (round-trips)
data = to_json(ast)               # Strategy -> dict (JSON IR)
ast2 = from_json(data)            # dict -> Strategy
```

---

## Serialization & Storage

A strategy is persisted on `StrategyVersion` (see `libs/db`) in **both** forms:

- **`config_sexpr`** — the original S-expression text (the canonical, human-editable source of truth used by downstream services).
- **`config_json`** — the compiled JSON IR produced by `to_json()`.

Plus extracted metadata: `symbols`, `timeframe` (derived from `:rebalance`), and `parameters` (which may carry the visual builder's `ui_state`).

### JSON IR structure

`to_json()` emits a tagged-union tree. Keys (source: `to_json.py`):

```json
{
  "type": "strategy",
  "name": "Dual Moving Average",
  "rebalance": "daily",
  "benchmark": "SPY",
  "children": [
    {
      "type": "if",
      "condition": {
        "type": "comparison",
        "operator": ">",
        "left":  {"type": "indicator", "name": "sma", "symbol": "SPY", "params": [50]},
        "right": {"type": "indicator", "name": "sma", "symbol": "SPY", "params": [200]}
      },
      "then":       {"type": "asset", "symbol": "VTI", "weight": 100},
      "else_block": {"type": "asset", "symbol": "BND", "weight": 100}
    }
  ]
}
```

Note the exact key names that downstream code depends on:
- `if` blocks use **`then`** and **`else_block`** (not `else`).
- logical conditions use `{"type": "logical", "operator": ..., "operands": [...]}`.
- indicators use `params` (a list) and optional `output`.

---

## Validation Rules

`validate()` (source: `libs/dsl/validator.py`) returns a `ValidationResult` with a `valid` flag and a list of errors (each with message, path, and source location; misspelled indicator/method names get "did you mean" suggestions). Enforced rules:

1. **Strategy** has a non-empty name and ≥ 1 child block.
2. **Weight `:method specified`** — every direct `asset`/`group` child must have a `:weight`, and they must sum to ~100% (tolerance 0.01).
3. **Weight non-`specified`** — children must **not** have `:weight` (the method computes it).
4. **Weight method** is one of the seven valid methods; `:lookback`/`:top`, if present, must be > 0; `:top` must not exceed the child count.
5. **Asset** has a non-empty symbol starting with a letter; `:weight`, if present, > 0.
6. **Filter** — `:by` is valid, `:select_count` > 0 and ≤ available assets, `:lookback` (if present) > 0, ≥ 1 child.
7. **Logical ops** — `not` takes exactly 1 operand; `and`/`or` take ≥ 2.
8. **Indicators** — name in the supported set; parameters > 0.
9. **Metrics** — name valid; period (if present) > 0.

The frontend runs an additional set of *structural* checks (no orphan blocks, no empty groups, duplicate-asset warnings) before saving; those are UI conveniences and do not replace backend validation.

---

## Execution Pipeline

How a stored strategy becomes results (backtest) or live trades.

### Compilation

`config_sexpr` → `parse()` → `validate()` → `compile_strategy()` (`libs/compiler`). Compilation:
1. **Extracts indicators** from all conditions (`extract_indicators`) into deduplicated specs.
2. Computes the **minimum bars** of history needed (max indicator lookback, floor of 2 for crossovers).
3. Produces an executable form. Two engines consume the same AST:
   - **Bar-by-bar** (`CompiledStrategy`) — stateful, processes one bar at a time. Used for **live trading**.
   - **Vectorized** (`VectorizedCompiledStrategy`) — array-based, evaluates the whole history at once via NumPy. Used for **backtesting** performance on large datasets.

### From target weights to action

On each evaluation the compiled strategy returns an **allocation**: `{symbol: weight%}`, normalized to 100%, plus a `rebalance_needed` flag and metadata.

- **Backtest** (`services/backtest`) — feeds historical bars, gets allocations, simulates the resulting trades, and accumulates an equity curve. Metrics (total/annualized return, Sharpe, Sortino, max drawdown via running peak, win rate, profit factor, and — if a `:benchmark` is set — alpha/beta) are computed from the equity curve and persisted to `BacktestResult`.
- **Live** (`services/trading`) — the runner consumes a live 1-minute bar stream, maintains a rolling per-symbol window, and on each bar (after a warmup of `min_bars + buffer`) evaluates the strategy. The strategy's `:rebalance` frequency gates *when* a new target is computed; the resulting target weights are handed to the **Portfolio Ledger**, which turns them into orders.

### Evaluation timing & gating

A strategy is not "always trading." It is a periodic loop:

```
on each wake-up (its :rebalance cadence):
    target = evaluate(conditions/indicators on the current bar)
    target_$ = target_weights × MY SLEEVE's equity      # not the whole account
    orders   = target_$ − what MY sleeve already holds   # trade only the delta
    (between wake-ups: hold)
```

Live evaluation is additionally gated by **trading-hours** checks and a per-session **circuit breaker** (consecutive losses, daily-loss %, drawdown %, error bursts). See [Portfolio Ledger](portfolio-ledger.md) and [Trading Service](services/trading.md).

---

## Multi-Strategy Execution & the Portfolio Ledger

A user has **one brokerage account** but trades flow into it from multiple sources at once: **manual** buy/sells and **one or more strategies**. The DSL deliberately says nothing about this — a strategy only ever expresses *target weights for its own slice of capital*. Coordinating multiple slices into a single commingled account is handled entirely by a layer **below** the DSL: the **Portfolio Ledger**.

In brief:

- Each running strategy is a **sleeve** with an allocated capital budget (`StrategyExecution.allocated_capital`). Its target weights are percentages **of the sleeve's equity**, not of the whole account.
- Manual trades live in a dedicated **Manual** sleeve; pre-existing or externally-traded positions live in an **Unmanaged** sleeve. A strategy can never buy or sell another sleeve's holdings.
- A single **append-only, double-entry, event-sourced ledger** is the source of truth. Per-sleeve positions, lots, cash, and P&L are **derived projections** of that ledger — so they cannot drift out of sync with one another.
- Every fill is **attributed to exactly one sleeve** at order origination (via a `client_order_id` → sleeve mapping), giving each holding a full **trade history** showing whether each buy/sell came from manual activity or a specific strategy.
- An **overlay/coordinator** turns each sleeve's target-vs-current into orders, optionally **nets** offsetting orders into block orders (allocated back at average price), submits them to the one broker account, and continuously **reconciles** the ledger's aggregate against broker truth.

The **Portfolio Service** owns this ledger — it is the **book of record** (sleeves, lots, cash, fund allocation, reconciliation). The **Trading Service** is the **execution arm**: it submits orders to the broker and emits fill events the ledger consumes.

This design follows the established **Unified Managed Account (UMA) / overlay-manager** pattern from wealth management, combined with **event-sourced double-entry accounting** to keep everything consistent at scale.

➡️ **Full architecture, data model, fund-allocation flows, and reconciliation:** see **[Portfolio Ledger & Multi-Strategy Fund Allocation](portfolio-ledger.md)**.

---

## Example Strategies

### Beginner — Classic 60/40 (static allocation)

```lisp
(strategy "Classic 60/40"
  :rebalance quarterly
  :benchmark SPY
  (weight :method specified
    (asset VTI :weight 60)
    (asset BND :weight 40)))
```

### Beginner — Equal-weight diversified

```lisp
(strategy "Equal-Weight Core"
  :rebalance monthly
  :benchmark SPY
  (weight :method equal
    (asset VTI)
    (asset VXUS)
    (asset BND)
    (asset GLD)))
```

### Intermediate — Trend regime switch

```lisp
(strategy "Trend Regime"
  :rebalance daily
  :benchmark SPY
  (if (> (sma SPY 50) (sma SPY 200))
    (weight :method specified
      (asset SPY :weight 60)
      (asset QQQ :weight 40))
    (else
      (weight :method specified
        (asset TLT :weight 50)
        (asset GLD :weight 50)))))
```

### Intermediate — RSI mean reversion

```lisp
(strategy "RSI Mean Reversion"
  :rebalance daily
  :benchmark SPY
  (if (< (rsi SPY 14) 30)
    (asset SPY :weight 100)
    (else
      (if (> (rsi SPY 14) 70)
        (asset TLT :weight 100)
        (else (weight :method equal (asset SPY) (asset TLT)))))))
```

### Advanced — All-weather risk-balanced core

```lisp
(strategy "All-Weather Core"
  :rebalance quarterly
  :benchmark SPY
  (weight :method inverse-volatility :lookback 60
    (asset SPY)
    (asset TLT)
    (asset GLD)
    (asset DBC)))
```

### Advanced — Regime-gated sector momentum rotation

```lisp
(strategy "Sector Rotation"
  :rebalance monthly
  :benchmark SPY
  (if (> (price SPY) (sma SPY 200))
    ;; Bull market: hold the top 3 sectors by momentum
    (filter :by momentum :select (top 3) :lookback 90
      (weight :method momentum :lookback 90
        (asset XLK) (asset XLF) (asset XLE) (asset XLV)
        (asset XLI) (asset XLC) (asset XLY) (asset XLP)
        (asset XLRE) (asset XLU) (asset XLB)))
    ;; Bear market: go defensive
    (else
      (weight :method equal
        (asset BND) (asset GLD)))))
```

### Advanced — Multi-condition with crossover confirmation

```lisp
(strategy "Confirmed Trend"
  :rebalance daily
  :benchmark SPY
  (if (and (crosses-above (sma SPY 50) (sma SPY 200))
           (< (rsi SPY 14) 70)
           (not (> (drawdown SPY) 0.10)))
    (weight :method specified
      (asset SPY :weight 70)
      (asset QQQ :weight 30))
    (else (asset BIL :weight 100))))   ; park in T-bills
```

---

## Tips for Writing Strategies

1. **Start static, then add logic.** Begin with a fixed `specified`/`equal` allocation; layer in `if`/`filter` once it works.
2. **Match cadence to logic.** Use comparisons (not crossovers) for low-frequency rebalances; crossovers shine on `daily`.
3. **Always set a `:benchmark`** so reporting can compute alpha/beta.
4. **Mind the warmup.** A strategy referencing `(sma SPY 200)` needs ≥ 200 bars before it produces signals.
5. **Use `group` for readability**, not allocation math (unless under `specified`).
6. **Keep nesting shallow.** Deeply nested `if`/`else` is hard to reason about — prefer a few clear regimes.
7. **Diversify the universe** for dynamic methods; momentum/inverse-volatility need several uncorrelated candidates to be meaningful.
8. **Backtest before going live**, and remember target weights apply to the strategy's **sleeve**, not your whole account — see [Portfolio Ledger](portfolio-ledger.md).

---

## Related Documentation

- [Portfolio Ledger & Multi-Strategy Fund Allocation](portfolio-ledger.md) — how target weights become trades across a shared account: sizing, sleeves, the event-sourced ledger, fund allocation, and reconciliation.
- [Strategy Service](services/strategy.md) — strategy CRUD, versioning, compile/validate endpoints.
- [Trading Service](services/trading.md) — live execution, sessions, order management.
- [Backtesting Service](services/backtesting.md) — historical simulation and metrics.
