# llamatrade-runtime

The **shared strategy execution core** for both backtesting and live trading.

A strategy is a pure function of `(market state, portfolio state, tick) → target orders`,
evaluated on a clock. `llamatrade_compiler.StrategySession` owns that evaluation; this library
owns the **loop around it** and the pluggable adapters that make backtest and live the *same*
engine:

| Seam | Backtest wiring | Live wiring (trading service) |
|---|---|---|
| `BarFeed` | `HistoricalBarFeed` (replayed history) | real-time stream via market-data |
| `ExecutionAdapter` | `SimulatedExecution` (slippage + commission) | Alpaca orders + `trade_updates` fills |
| `Portfolio` | in-memory book | ledger (book of record) |
| `RuntimeObserver` | live progress / partial metrics | trade + telemetry stream |

`StrategyRuntime.run(feed)` drives a `StrategySession` over a feed, applies orders through an
`ExecutionAdapter`, tracks the book in a `Portfolio`, and emits lifecycle events to a
`RuntimeObserver`. Backtest ≡ live **by construction**, because both are adapter wirings of one
runtime.

See `.docs/planning/backtest-runtime-unification-plan.md`.
