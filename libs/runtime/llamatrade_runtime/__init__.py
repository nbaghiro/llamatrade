"""llamatrade_runtime — the shared strategy execution core for backtest and live trading.

`StrategyRuntime.run(feed)` drives a `StrategySession` over a `BarFeed`, applies its orders
through an `ExecutionAdapter` against a `Portfolio`, and emits lifecycle events to a
`RuntimeObserver`. Backtest and live are two adapter wirings of the same runtime.

The evaluation core (compile → indicators → conditions → weights → sizing) lives here too;
`libs/dsl` owns the strategy language and static AST analysis it builds on.
"""

from llamatrade_runtime.aggregation import (
    FormingBarAggregator,
    daily_period_start,
    market_timezone,
)
from llamatrade_runtime.evaluation.compiled import Allocation, CompiledStrategy, compile_strategy
from llamatrade_runtime.evaluation.conditions import (
    EvaluationError,
    evaluate_condition,
    evaluate_condition_safe,
)
from llamatrade_runtime.evaluation.state import EvaluationState
from llamatrade_runtime.execution import ExecutionAdapter, SimulatedExecution
from llamatrade_runtime.feed import (
    BarFeed,
    FormingBarFeed,
    HistoricalBarFeed,
    IntradayBarSource,
)
from llamatrade_runtime.indicators.library import (
    PriceData,
    compute_all_indicators,
    compute_indicator,
)
from llamatrade_runtime.metrics import TradeWithPnl
from llamatrade_runtime.models import ExecutionOutcome, Fill, Position, RejectedSignal, Trade
from llamatrade_runtime.observer import NullObserver, RuntimeObserver
from llamatrade_runtime.portfolio import Portfolio
from llamatrade_runtime.rebalance import should_rebalance
from llamatrade_runtime.result import RunResult, assemble_result
from llamatrade_runtime.runtime import RuntimeCancelled, StrategyRuntime
from llamatrade_runtime.session import StrategySession
from llamatrade_runtime.sizing import (
    DEFAULT_DRIFT_TOLERANCE,
    DEFAULT_MIN_ORDER_NOTIONAL,
    DEFAULT_MIN_WEIGHT_CHANGE,
    DEFAULT_SHARE_DECIMALS,
    Holding,
    IntendedOrder,
    ShareQuantization,
    SizingMode,
    SizingState,
    affordable_quantity,
    quantize_quantity,
    size_orders,
)
from llamatrade_runtime.strategy import build_session
from llamatrade_runtime.types import Bar

__all__ = [
    # Runtime loop
    "StrategyRuntime",
    "RuntimeCancelled",
    # Adapters / seams
    "BarFeed",
    "HistoricalBarFeed",
    "FormingBarFeed",
    "IntradayBarSource",
    "ExecutionAdapter",
    "SimulatedExecution",
    "Portfolio",
    "RuntimeObserver",
    "NullObserver",
    # Strategy session + build
    "StrategySession",
    "build_session",
    "should_rebalance",
    # Compiled evaluation core
    "CompiledStrategy",
    "compile_strategy",
    "Allocation",
    "EvaluationState",
    "evaluate_condition",
    "evaluate_condition_safe",
    "EvaluationError",
    # Indicators
    "PriceData",
    "compute_all_indicators",
    "compute_indicator",
    # Sizing
    "Holding",
    "IntendedOrder",
    "SizingMode",
    "SizingState",
    "ShareQuantization",
    "size_orders",
    "affordable_quantity",
    "quantize_quantity",
    "DEFAULT_DRIFT_TOLERANCE",
    "DEFAULT_MIN_WEIGHT_CHANGE",
    "DEFAULT_MIN_ORDER_NOTIONAL",
    "DEFAULT_SHARE_DECIMALS",
    # Bar type + period aggregation
    "Bar",
    "FormingBarAggregator",
    "daily_period_start",
    "market_timezone",
    # Models / results
    "Fill",
    "Trade",
    "Position",
    "RejectedSignal",
    "ExecutionOutcome",
    "RunResult",
    "assemble_result",
    "TradeWithPnl",
]
