# Technical Indicators & Weight Methods — Reference & Research Guide

A team reference for the signals and allocation methods behind LlamaTrade strategies: what exists in the DSL today, what the rest of the industry treats as table-stakes, how each piece is actually used inside strategies, and where this fits in the overall system.

> **Sourcing note.** Platform-coverage and academic claims in this doc were verified against primary sources in June 2026 (TA-Lib function list, TradingView built-in indicator docs, QuantConnect/LEAN supported-indicators docs, and the original papers for 1/N, ERC, and HRP — links in [Sources](#sources)). Indicator default parameters and classic signal rules are standard textbook conventions (Wilder, Bollinger, et al.) as shipped by those same platforms.

> **Implementation status (updated June 2026).** Every indicator below is now **numerically validated against TA-Lib** by a golden-value test suite (`libs/compiler/tests/test_indicators_golden.py`). That suite caught and fixed real bugs: ADX, Stochastic, and the MACD signal/histogram were silently returning all-NaN (so conditions using them were always false), and ATR/ADX used SMA instead of Wilder's smoothing — all corrected. On the allocation side, `risk-parity` and `min-variance` are now **real covariance-based optimizers** (previously inverse-volatility stubs), and `market-cap` is now **rejected by the validator** rather than silently falling back to equal weight. Status markers throughout reflect this current state.

---

## Table of Contents

1. [The Mental Model (start here)](#the-mental-model-start-here)
2. [How a Signal Becomes a Trade in LlamaTrade](#how-a-signal-becomes-a-trade-in-llamatrade)
3. [Indicator Catalog by Family](#indicator-catalog-by-family)
4. [Metrics](#metrics)
5. [Weight Methods (Allocation)](#weight-methods-allocation)
6. [Famous Strategy Families — the Recipes](#famous-strategy-families--the-recipes)
7. [Platform Benchmark — How Our Coverage Compares](#platform-benchmark--how-our-coverage-compares)
8. [Suggested Research Priorities](#suggested-research-priorities)
9. [Sources](#sources)

---

## The Mental Model (start here)

Every item in this document is a recipe for answering one of the same two questions every strategy must answer:

1. **"What is the market doing right now?"** → *indicators*. An indicator is a formula that crunches recent price/volume history into a single number summarizing one aspect of market behavior — is price trending (trend), moving too fast and due for a pullback (momentum/oscillators), swinging wildly (volatility), or attracting real money flow (volume). Strategies don't read charts; they read these numbers and apply rules like *"if trend is up and momentum isn't overheated, hold stocks, otherwise hold bonds."*
2. **"How much money do I put in each asset?"** → *weight methods*. Once the rules decide *which* assets to hold, a weight method decides *how much* of each — split evenly, give more to recent winners, give more to calmer assets, and so on.

None of these predict the future. They are standardized, backtestable ways of turning raw price history into decisions. The research task is figuring out which combinations have historically worked, and under what conditions.

**The simplest complete example** — and the one to learn first — is the 200-day SMA regime filter: *"if SPY's price is above its 200-day average price, hold stocks; otherwise hold bonds."* That's a real strategy funds actually run. Every other indicator on this list is the same idea with a fancier formula.

---

## How a Signal Becomes a Trade in LlamaTrade

The DSL is an **allocation language, not a signal language** (see [strategy-dsl.md](strategy-dsl.md)). A strategy never says "buy 100 shares" — it is a tree that, when evaluated, produces **target portfolio weights** like `{VTI: 60%, BND: 40%}`. Indicators influence those weights through exactly three mechanisms:

| Mechanism | DSL construct | What the indicator does |
|---|---|---|
| **Branching** | `(if <condition> ... (else ...))` | A condition built from indicators flips the subtree between two allocations |
| **Ranking/selection** | `(filter :by <criteria> :select (top N))` | A metric ranks candidate assets; only the top/bottom N receive weight |
| **Weight computation** | `(weight :method <method> ...)` | The method itself computes weights from price history (momentum, inverse-volatility, …) |

Indicators never scale a weight directly — there is no "weight SPY by its RSI." They produce **booleans** (conditions) or **rankings** (filter / method scores).

End-to-end flow:

```
1-min bars (live) / historical bars (backtest)
        │
        ▼
 Indicator computation (NumPy, libs/compiler/indicators/library.py)
        │
        ▼
 Condition evaluation (comparisons, crossovers, and/or/not)
        │
        ▼
 Tree evaluation → target weights {symbol: %}     ← gated by :rebalance frequency
        │
        ▼
 Portfolio Ledger: target % × sleeve equity → diff vs current holdings → orders
```

Two system facts that shape how signals behave in practice:

- **The rebalance gate.** Conditions are only *acted on* at the strategy's `:rebalance` cadence (daily at finest, never twice per day). A crossover that fires between rebalance dates of a `monthly` strategy is missed — prefer state comparisons (`>`) over transition detection (`crosses-above`) for low-frequency strategies.
- **Sleeves, not accounts.** Target weights apply to the strategy's *sleeve* (its allocated capital slice), not the whole brokerage account. The Portfolio Ledger coordinates multiple strategies plus manual trading in one account (see [portfolio-ledger.md](portfolio-ledger.md)).

**Condition vocabulary** (implemented): comparisons `>` `<` `>=` `<=` `=` `!=`; crossovers `crosses-above` / `crosses-below` (strict transition: fast was ≤ slow, now >); logical `and` / `or` / `not`.

---

## Indicator Catalog by Family

Legend: ✅ implemented in `libs/compiler` · 🔍 candidate to research/add. "Classic rule" = the signal convention traders actually use, as documented across TradingView/StockCharts/platform docs.

### 1. Trend / Moving Averages

*Question answered: which direction is price drifting, and how smoothly?*

| Indicator | Status | What it measures | Typical params | Classic signal rules | Used in |
|---|---|---|---|---|---|
| **SMA** — Simple Moving Average | ✅ | Plain average of last N closes; the trend baseline | 20, 50, 200 | price > SMA = uptrend; 50 crossing above 200 = "golden cross", below = "death cross" | Golden cross, 200-day regime filters, Meb Faber GTAA (10-month SMA) |
| **EMA** — Exponential MA | ✅ | Average with recency bias — reacts faster to turns | 12, 20, 26 | same rules as SMA; 12/26 EMA cross is the basis of MACD | Faster trend systems, MACD |
| **WMA / Hull MA (HMA)** | 🔍 | Lower-lag weighted averages (Hull ≈ near-zero lag) | 9–55 | direction of the HMA itself flips = trend change | Low-lag trend following |
| **DEMA / TEMA** | 🔍 | Double/triple-smoothed EMA, less lag | 20 | as EMA | Variants in trend systems |
| **KAMA** — Kaufman Adaptive MA | 🔍 | MA that speeds up in trends, flattens in chop | 10 (eff. ratio), 2/30 | price vs KAMA; KAMA slope | Adaptive trend following |
| **MACD** | ✅ | Gap between fast and slow EMA + its own signal line | 12 / 26 / 9 | MACD line crossing signal line; histogram sign flip; zero-line cross | Momentum confirmation in trend systems |
| **ADX** (+DI/−DI) | ✅ | Trend *strength* regardless of direction | 14 | ADX > 25 = trending, < 20 = chop; +DI/−DI cross gives direction | Trend filters / "should I even trend-follow now?" gates |
| **Parabolic SAR** | 🔍 | Trailing stop-and-reverse dots that flip with trend | accel 0.02, max 0.2 | price crossing the SAR dots = trend flip / exit | Trailing-stop exits in trend systems |
| **SuperTrend** | 🔍 | ATR-based trend line below/above price | 10, mult 3 | price closing across the line = trend flip | Hugely popular in retail algo trading; not in TA-Lib but built into TradingView |
| **Ichimoku Cloud** | 🔍 | Full trend system: cloud (support/resistance), Tenkan/Kijun lines | 9 / 26 / 52 | price above cloud = bull regime; Tenkan/Kijun cross = entry | Self-contained trend framework, very popular in FX/crypto |
| **Aroon** | 🔍 | How recently price made its N-period high/low (trend age) | 25 | Aroon-Up > 70 & Aroon-Down < 30 = strong uptrend; crosses = turns | Trend-exhaustion detection |
| **Vortex** | 🔍 | Paired up/down trend-flow lines | 14 | VI+ crossing VI− | Trend-start detection |

**How they're used in strategies:** moving averages are almost always used as *regime filters* — the condition in an `if` that decides risk-on vs. risk-off (e.g. the Sector Rotation example in our DSL doc gates everything on `(> (price SPY) (sma SPY 200))`). Crossover pairs (50/200, 12/26) generate entry/exit *events*. ADX/Aroon are second-order: they gate *other* signals ("only take trend trades when ADX > 25").

> **Design note (verified against TradingView):** platforms increasingly model "moving average" as one parameterizable family (type + length) rather than N separate indicators — TradingView ships a unified MA indicator with a switchable type parameter. Worth considering for the DSL instead of adding `wma`, `hma`, `dema`… as separate keywords.

### 2. Momentum / Oscillators

*Question answered: how hard has price been pushed recently — and is the move overextended?*

| Indicator | Status | What it measures | Typical params | Classic signal rules | Used in |
|---|---|---|---|---|---|
| **RSI** — Relative Strength Index | ✅ | 0–100 speedometer of recent up vs down closes | 14 (Wilder); 2 for mean reversion | > 70 overbought, < 30 oversold; divergence vs price | RSI(2) mean reversion (Connors), regime de-risking |
| **Stochastic** (%K/%D) | ✅ | Where the close sits inside the recent high-low range, 0–100 | 14 / 3 / 3 | > 80 / < 20 zones; %K crossing %D | Range-bound mean reversion |
| **Stochastic RSI** | 🔍 | Stochastic applied to RSI — more sensitive | 14 | same zones, faster | Short-term timing |
| **CCI** — Commodity Channel Index | ✅ | Deviation of price from its statistical mean | 20 | > +100 / < −100 breakout or reversion zones | Both breakout and reversion styles |
| **Williams %R** | ✅ | Inverse stochastic, −100 to 0 | 14 | > −20 overbought, < −80 oversold | Short-term reversion |
| **MFI** — Money Flow Index | ✅ | Volume-weighted RSI | 14 | > 80 / < 20; divergence | Volume-confirmed reversion |
| **Momentum** (raw) | ✅ | Price change over N periods | 10 | sign and magnitude; ranking assets | Cross-sectional momentum, our `momentum` weight method |
| **ROC** — Rate of Change | 🔍 | Same as momentum but as a % — comparable across assets | 12 | zero-line cross; ranking | Dual momentum, relative-strength rotation |
| **Ultimate Oscillator** | 🔍 | Momentum blended across 3 timeframes | 7 / 14 / 28 | 70/30 zones, divergence | Divergence trading |
| **TRIX** | 🔍 | Rate of change of a triple-smoothed EMA | 15 | zero-line / signal cross | Filtered momentum |
| **TSI** — True Strength Index | 🔍 | Double-smoothed momentum | 25 / 13 | zero/signal cross | Momentum confirmation |

**How they're used in strategies:** two opposite styles. *Mean reversion* buys oversold (`RSI < 30`) expecting a snap-back — works best on short horizons and indices. *Momentum/trend confirmation* requires the oscillator to agree with the trend signal (`and (> sma50 sma200) (< rsi 70)` — "uptrend but not overheated", exactly our Confirmed Trend example). For *rotation* strategies, ROC/momentum are computed per asset and used to **rank** (our `filter :by momentum`), not to threshold.

### 3. Volatility

*Question answered: how violent are the moves — and is price stretched relative to its own normal range?*

| Indicator | Status | What it measures | Typical params | Classic signal rules | Used in |
|---|---|---|---|---|---|
| **Bollinger Bands** | ✅ | MA ± k standard deviations — a "stretchiness" envelope | 20, 2.0σ | touch/close outside band = stretched; band squeeze = breakout brewing | Bollinger reversion, squeeze breakouts |
| **%B / Bandwidth** | 🔍 | Bollinger position (0–1) and band width as single numbers | derived | %B > 1 / < 0; bandwidth percentile lows = squeeze | Easier to threshold in conditions than raw bands |
| **ATR** — Average True Range | ✅ | Average size of a full daily swing incl. gaps (direction-blind) | 14 | not a signal itself — sizes stops (e.g. 2×ATR) and positions | Turtle position sizing, SuperTrend, Chandelier exits |
| **Keltner Channels** | ✅ | EMA ± k×ATR envelope (smoother than Bollinger) | 20, 2.0 | close outside channel = trend strength; BB-inside-KC = "TTM squeeze" | Squeeze setups, trend pullbacks |
| **Std Dev** (rolling) | ✅ | Raw return/price dispersion | 20 | input to vol-based weighting and filters | Inverse-vol weighting, vol filters |
| **Chandelier Exit** | 🔍 | Trailing stop hung k×ATR below the highest high | 22, 3×ATR | price crossing the stop = exit | Trend-following exits |
| **HV percentile / vol-of-vol** | 🔍 | Where current vol sits vs its own history | 252 | low-vol percentile = regime for breakout entries | Vol-regime gates |

**How they're used in strategies:** volatility indicators rarely generate entries alone. They (a) define *stretch* for mean reversion (Bollinger), (b) size *stops and positions* (ATR — the Turtles bet a fixed account % per ATR of risk), and (c) act as *regime detectors* (squeezes precede breakouts; high vol → de-risk). Our `inverse-volatility` weight method and `volatility` filter/metric belong to this family on the allocation side.

### 4. Volume / Money Flow

*Question answered: is real money behind this move?*

| Indicator | Status | What it measures | Typical params | Classic signal rules | Used in |
|---|---|---|---|---|---|
| **OBV** — On-Balance Volume | ✅ | Running total: +volume on up closes, −volume on down closes | — | OBV trend/divergence vs price trend = accumulation/distribution | Divergence confirmation |
| **VWAP** | ✅ | Volume-weighted average price (intraday anchor) | session | price above/below VWAP = intraday bull/bear; institutional execution benchmark | Intraday strategies, execution quality |
| **A/D Line** — Accumulation/Distribution | 🔍 | Like OBV but weighted by *where in the range* price closed | — | divergence vs price | Flow confirmation |
| **CMF** — Chaikin Money Flow | 🔍 | A/D pressure normalized over a window, −1 to +1 | 20–21 | > 0 buying pressure, < 0 selling; ±0.25 strong | Flow-confirmed entries |
| **Chaikin Oscillator** | 🔍 | MACD of the A/D line | 3 / 10 | zero-line cross | Flow momentum |
| **Force Index** | 🔍 | Price change × volume | 13 | zero cross, divergence | Elder's triple-screen |
| **RVOL / Volume SMA** | 🔍 | Today's volume vs its average | 20–50 | RVOL > 2 = unusual activity | Breakout confirmation ("breakout on volume") |
| **Ease of Movement** | 🔍 | How far price moves per unit of volume | 14 | zero cross | Confirmation |

**How they're used in strategies:** almost always as *confirmation* — a breakout or divergence "counts" only if volume agrees. Classic pattern: `and (price breaks Donchian high) (volume > 1.5 × avg volume)`. Volume is also a liquidity *filter* for universe selection (our `filter :by volume` — though note it currently reads only the last bar, not an average).

### 5. Channels / Breakout

*Question answered: is price escaping its recent range?*

| Indicator | Status | What it measures | Typical params | Classic signal rules | Used in |
|---|---|---|---|---|---|
| **Donchian Channels** | ✅ | Highest high / lowest low of last N bars | 20 (entry), 10/55 | close above upper = breakout buy; lower = exit/short | **Turtle Traders** — the most famous mechanical system ever published |
| **Keltner / Bollinger** | ✅ | (see Volatility — double as breakout channels) | | close outside = volatility breakout | Squeeze breakouts |
| **52-week high/low distance** | 🔍 | % distance from N-period (typ. 252-day) high | 252 | nearness to 52-wk high = momentum signal (George & Hwang 2004) | Academic momentum, breakout screens |
| **Pivot Points** | 🔍 | Prior-period H/L/C-derived support/resistance levels | daily/weekly | price vs pivot/R1/S1 levels | Intraday mean reversion & breakout |
| **Gap detection** | 🔍 | Open vs prior close | — | gap-up/-down continuation or fade rules | Overnight/event strategies |

**How they're used in strategies:** breakout logic is the opposite philosophy from oscillator mean reversion — instead of fading extremes, it *buys* new highs on the theory that escapes from a range start trends. The Turtle system is the canonical recipe: enter on a 20-day Donchian breakout, exit on a 10-day counter-breakout, size positions by ATR. Maps directly to our DSL: `(if (>= (price X :close) (donchian X 20 :upper)) ...)`.

### 6. Price Structure / Cross-Asset (all 🔍)

| Indicator | What it measures | Used in |
|---|---|---|
| **Rolling correlation / beta to benchmark** | Co-movement with an index | Hedging logic, pairs trading, diversification filters |
| **Relative strength ratio** (asset / benchmark) | Outperformance trend | Sector rotation ("hold what's beating SPY") |
| **Z-score of price vs MA** | Statistical stretch in σ units | Stat-arb style mean reversion; cleaner threshold than raw price-vs-MA |

---

## Metrics

Derived statistics (implemented in our DSL as the third value-expression family — usable in any condition):

| Metric | Status | Use in strategies |
|---|---|---|
| `drawdown` | ✅ | De-risking rules: `(> (drawdown SPY) 0.15)` → rotate to bonds/cash |
| `return` (N-period) | ✅ | Absolute-momentum gates (the heart of dual momentum) |
| `volatility` | ✅ | Vol-regime conditions, ranking |
| Sharpe / Sortino (windowed) | 🔍 | Rank assets by *risk-adjusted* return instead of raw return |
| Max drawdown (windowed) | 🔍 | Risk filters in universe selection |
| Downside deviation | 🔍 | Sortino-style ranking |

---

## Weight Methods (Allocation)

The second half of every strategy. The DSL's `weight :method` block answers "given these N assets, how much of each?"

### Implemented today (status — see `libs/compiler/llamatrade_compiler/evaluation/compiled.py`)

| Method | Status | What it does | Notes / gaps |
|---|---|---|---|
| `specified` | ✅ full | Manual percentages (must sum to ~100) | The 60/40 classic |
| `equal` | ✅ full | 100/N each | See research note below — this is a *strong* baseline, not a naive placeholder |
| `inverse-volatility` | ✅ full | wᵢ ∝ 1/σᵢ of daily returns over `:lookback` | Edge case: assets with missing history get a floor σ=0.0001 → they *dominate* the block instead of degrading gracefully |
| `risk-parity` | ✅ full | Equal-risk-contribution (ERC): fixed-point iteration `wᵢ ∝ 1/(Σw)ᵢ` on the return covariance matrix, long-only, normalized | Accounts for correlations (reduces to inverse-vol only when assets are uncorrelated). Falls back to inverse-vol on insufficient history |
| `min-variance` | ✅ full | Long-only minimum-variance: `w ∝ Σ⁻¹·1` via pseudo-inverse (robust to singular Σ), negatives clipped, renormalized | Estimation-error sensitive on short windows (see research note 1); falls back to inverse-vol when history is too short |
| `momentum` | ⚠️ partial | Ranks by trailing return over `:lookback`, keeps `:top N`… then **equal-weights the survivors** | Score-*proportional* weighting (winners get more) is documented but not implemented |
| `market-cap` | ❌ rejected | The validator blocks it — no fundamental-data (shares-outstanding) source | Was a silent equal-weight fallback; now a hard validation error so strategies don't get surprised |

Both `risk-parity` and `min-variance` share covariance scaffolding that builds an aligned daily-returns matrix across the candidate symbols and falls back to `inverse-volatility` when fewer than two symbols have enough history.

### What the research says (verified against the original papers)

Three results every team member researching allocation should know:

1. **Equal weight is genuinely hard to beat.** DeMiguel, Garlappi & Uppal (*Review of Financial Studies*, 2009) evaluated 14 sample-based mean-variance models across 7 datasets and found **none consistently beats 1/N** on Sharpe ratio, certainty-equivalent return, or turnover. The killer is *estimation error*: out of sample, the gains from "optimal" diversification are more than offset by errors in estimating expected returns and covariances. Their simulations suggest mean-variance needs on the order of **3,000 months of data for 25 assets** (≈250 years) to reliably win. *Takeaway: `equal` is a first-class method, and any optimizer we add must document its data appetite. (Later literature — Kirby & Ostdiek 2012, Tu & Zhou 2011 — shows some refinements do beat 1/N, so it's a high bar, not a no-go.)*

2. **Inverse-volatility is formally a special case of risk parity.** Maillard, Roncalli & Teïletche (*Journal of Portfolio Management*, 2010) proved the equal-risk-contribution (ERC) portfolio's volatility sits **between minimum-variance and equal weight** (σ_MV ≤ σ_ERC ≤ σ_1/N), and that under constant correlation ERC has the closed form wᵢ = σᵢ⁻¹ / Σσⱼ⁻¹ — *exactly* our inverse-volatility method. *Takeaway: this is why our three vol-based methods form a ladder — `inverse-volatility` (ignores correlation) → `risk-parity` (full ERC, accounts for correlation) → `min-variance` (lowest total vol). All three are now implemented; ERC and min-variance only diverge from inverse-vol when correlations differ meaningfully across the basket, and they cost a covariance estimate + a solver.*

3. **HRP is the modern covariance-only alternative.** López de Prado (*Journal of Portfolio Management*, 2016) introduced Hierarchical Risk Parity to fix three documented failures of quadratic optimizers — instability, concentration, underperformance. It clusters assets by correlation, then allocates top-down by recursive bisection. Crucially it **never inverts the covariance matrix**, so it works even when the matrix is ill-conditioned (more assets than observations — "Markowitz's curse") and needs **no expected-return estimates**. In the paper's Monte Carlo tests HRP beat CLA min-variance out of sample on variance itself, though independent replications since are mixed — treat HRP as a robust, well-motivated option, not a guaranteed winner.

### Candidate methods to research

> Already implemented (no longer candidates): **ERC risk-parity** and **minimum-variance** — see the Weight Methods table above.

| Method | What it does | Why / when | Data needs | Pitfalls |
|---|---|---|---|---|
| **Score-proportional momentum** | wᵢ ∝ trailing return | Lets winners compound; our docs already promise it | prices | Concentration; negative scores need handling |
| **Max Sharpe / mean-variance** | Markowitz tangency portfolio | The textbook optimum | returns **and** covariance | Worst estimation-error sensitivity (see DeMiguel) |
| **HRP** | Cluster + recursive bisection | Robust when many assets / short history | covariance only | Linkage-method sensitivity; mixed replication |
| **Volatility targeting** | Scale total exposure to hit target portfolio vol; rest to cash | Smooths returns; "vol-managed portfolios" literature | portfolio vol estimate | Whipsaw in vol spikes; leverage if target > realized |
| **Dual momentum** (Antonacci) | Relative momentum picks the best asset; *absolute* momentum (return > T-bill?) gates risk-on vs cash | Famous GEM strategy; composes from our existing `if` + `filter` + `return` metric | 12-mo returns | Lookback sensitivity; monthly whipsaws |
| **Kelly / fractional Kelly** | Size ∝ edge/variance | Theoretical growth-optimal sizing | win/loss estimates | Full Kelly is violently aggressive; estimates are the hard part |
| **Black-Litterman** | Blend market equilibrium with views | Institutional standard | cap weights + view model | Likely over-engineered for us now |

**Filter criteria worth adding** alongside: Sharpe ratio, distance-from-52-week-high, average dollar volume (liquidity), correlation-to-benchmark.

---

## Famous Strategy Families — the Recipes

How indicators + weight methods combine into the named strategies a researcher will encounter. All of these are expressible (or nearly so) in our DSL today:

| Strategy family | Signal recipe | Allocation recipe | DSL building blocks |
|---|---|---|---|
| **Golden cross / death cross** | SMA-50 crosses above/below SMA-200 | 100% equities ↔ 100% bonds/cash | `if` + `crosses-above`/`>` + `sma` |
| **200-day regime filter** (Faber GTAA) | price > 10-month (~200d) SMA per asset | hold asset else cash, equal across sleeves | `if` + `sma`, `weight :method equal` |
| **RSI(2) mean reversion** (Connors) | RSI(2) < 10 buy, > 90 exit, *only* above 200-day SMA | full sleeve in/out | nested `if` + `rsi` + `sma` |
| **Turtle / Donchian breakout** | 20-day Donchian breakout entry, 10-day exit | ATR-based position sizing | `if` + `donchian` (+ ATR sizing = research item) |
| **Sector momentum rotation** | rank sectors by 3–12-month return | top N, equal or momentum-weighted | `filter :by momentum` + `weight :method momentum` |
| **Dual momentum / GEM** (Antonacci) | relative: US vs intl equity 12-mo return; absolute: winner vs T-bill return | 100% in winner, else bonds | `if` + `return` metric + `filter` |
| **All-weather / risk parity** | none — pure allocation | inverse-vol or ERC across stocks/bonds/gold/commodities | `weight :method risk-parity` (or `inverse-volatility` / `min-variance`) |
| **Vol-managed portfolio** | realized vol vs target | scale equity weight by target/realized vol | needs **volatility targeting** method (research item) |
| **TTM squeeze breakout** | Bollinger inside Keltner = squeeze; breakout direction entry | full sleeve | `bbands` + `keltner` conditions |

---

## Platform Benchmark — How Our Coverage Compares

Verified June 2026 against official docs. The cross-platform **table-stakes set** — indicators shipped as built-ins by *all* of TA-Lib, TradingView, and QuantConnect/LEAN — is:

> SMA, EMA (+ WMA/Hull/KAMA variants), RSI, MACD, Stochastic, Stochastic RSI, CCI, Williams %R, Aroon, ROC, Ultimate Oscillator, ADX, Bollinger Bands, ATR, OBV, MFI, Chaikin A/D & CMF, VWAP, Parabolic SAR, Donchian, Keltner, Ichimoku, pivot points.

(Donchian/Keltner/Ichimoku/pivots/VWAP aren't TA-Lib functions but are built into both TradingView and QuantConnect; SuperTrend is TradingView-only among the three. QuantConnect ships 100+ indicators total — that's the upper-bound benchmark, not the bar.)

**Our position against the table-stakes set:**

| | Count | Items |
|---|---|---|
| ✅ We have | 14 of ~24 | SMA, EMA, RSI, MACD, Stoch, CCI, Williams %R, ADX, BBands, ATR, OBV, MFI, VWAP, Donchian, Keltner (+ stddev, momentum) |
| ❌ Missing from table-stakes | ~9 | WMA/Hull/KAMA (MA variants), Stochastic RSI, Aroon, ROC, Ultimate Oscillator, Chaikin A/D & CMF, Parabolic SAR, Ichimoku, pivot points |

On the **allocation** side, Composer (the closest product analog — also a declarative weights-based strategy builder) exposes equal, specified, inverse-volatility, and market-cap weight blocks plus threshold/rank filters; Portfolio Visualizer's tactical models cover relative-strength rotation, dual momentum, target-vol, and risk-parity style optimization. Our six usable methods (market-cap excluded) match Composer's surface and go beyond it with real **ERC risk-parity** and **minimum-variance** optimizers; the remaining gap vs Portfolio Visualizer is **dual momentum and volatility targeting**.

---

## Suggested Research Priorities

Ranked by (strategy families unlocked) ÷ (implementation effort), given the gaps above:

**Indicators**
1. **ROC** — trivial (we have `momentum`; ROC is the % form), unlocks clean cross-asset ranking and dual momentum.
2. **Parabolic SAR + SuperTrend** — the two most-used retail trend-flip signals; both ATR-adjacent, we have ATR.
3. **Stochastic RSI + Aroon** — cheap, closes most of the oscillator gap vs table-stakes.
4. **52-week-high distance + Z-score vs MA** — one-liners on existing data; unlock academic momentum and stat-arb reversion styles.
5. **Ichimoku** — bigger lift (5 lines), large retail mindshare.
6. **CMF / A-D line + RVOL** — completes the volume-confirmation family.

**Weight methods** (ERC risk-parity and min-variance are now done — see above)
1. **Score-proportional momentum** — already documented, just not implemented.
2. **Volatility targeting** — unlocks the whole vol-managed family; needs only realized vol we already compute.
3. **Dual momentum** — mostly composition of existing blocks + `return`-vs-cash-proxy comparison; huge name recognition (Antonacci GEM).
4. **HRP** — strong robustness story (no matrix inversion, no return estimates); medium effort, and a natural next step now that the covariance scaffolding exists.
5. Fix the **inverse-vol missing-data floor** (σ=0.0001 makes data-less assets dominate — should fall back to equal or exclude). Note `risk-parity`/`min-variance` inherit this via their inverse-vol fallback.

**Also worth fixing while in the area:** `filter :by volume` should average over `:lookback` instead of reading one bar. (`min-variance` is now implemented and `market-cap` now hard-fails validation, so the old "silent fallback" trap is resolved.)

---

## Sources

**Platform docs (primary, fetched June 2026)**
- TA-Lib function list — https://ta-lib.org/functions/ and https://ta-lib.github.io/ta-lib-python/funcs.html
- TradingView built-in indicators — https://www.tradingview.com/support/folders/43000587405-built-in-indicators/
- QuantConnect supported indicators — https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators
- LEAN indicator class reference — https://www.lean.io/docs/v2/lean-engine/class-reference/namespaceQuantConnect_1_1Indicators.html
- Composer weight blocks & inverse-vol — https://help.composer.trade/article/18-symphony-editor-assign-weights, https://help.composer.trade/article/26-inverse-volatility-weighting
- Portfolio Visualizer tactical models — https://www.portfoliovisualizer.com/tactical-asset-allocation-model

**Academic (primary)**
- DeMiguel, Garlappi & Uppal (2009), *Optimal Versus Naive Diversification: How Inefficient is the 1/N Portfolio Strategy?*, RFS 22(5) — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1376199
- Maillard, Roncalli & Teïletche (2010), *The Properties of Equally Weighted Risk Contribution Portfolios*, JPM 36(4) — http://www.thierry-roncalli.com/download/erc.pdf
- López de Prado (2016), *Building Diversified Portfolios that Outperform Out-of-Sample* (HRP), JPM 42(4) — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2708678

**Practitioner references (secondary)**
- StockCharts ChartSchool indicator library — https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays
- RSI(2) strategy — https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2

**Internal**
- [Strategy DSL Reference](strategy-dsl.md) — the language these signals plug into
- [Portfolio Ledger](portfolio-ledger.md) — how target weights become orders across sleeves
