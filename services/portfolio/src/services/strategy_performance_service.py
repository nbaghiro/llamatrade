"""Strategy performance request/result shapes.

The read path derives per-strategy performance from the ledger projection and
maps it straight to the proto wire messages (see ``src.proto_mappers``); there is
no table-backed service here. What remains are the read filters and the
result-aggregate containers the ledger reader returns — the containers hold proto
messages (proto is the canonical read shape, 1A) plus the numeric roll-ups the
servicer needs.
"""

from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel

from llamatrade_proto.generated import portfolio_pb2

from src.ledger.read_model import PositionView


class ListPerformanceFilters(BaseModel):
    """Filters for listing strategy performance."""

    mode: int | None = None  # ExecutionMode proto value
    status: int | None = None  # ExecutionStatus proto value


@dataclass(frozen=True)
class ListPerformanceResult:
    """Result of listing strategy performance."""

    strategies: list[portfolio_pb2.StrategyPerformanceSummary]
    total_allocated: Decimal
    total_current_value: Decimal
    combined_return: Decimal | None
    total: int


@dataclass(frozen=True)
class StrategyPerformanceDetail:
    """Detailed performance for a single strategy."""

    summary: portfolio_pb2.StrategyPerformanceSummary
    metrics: portfolio_pb2.StrategyLiveMetrics
    positions: list[PositionView]


@dataclass(frozen=True)
class EquityCurveResult:
    """Equity curve data for a strategy."""

    equity_curve: list[portfolio_pb2.StrategyEquityPoint]
    benchmark: portfolio_pb2.BenchmarkData | None
    period_returns: portfolio_pb2.StrategyPeriodReturns


class BookTotals(BaseModel):
    """Strategy-book aggregate returns, matching the per-execution list.

    Lets ``ListPortfolios`` report the SAME day/total return the strategy rows
    weight-sum to (single basis), instead of the whole-account figure that also
    folds in non-strategy sleeves (idle cash, manual trades).
    """

    day_pnl: Decimal
    day_pnl_percent: Decimal
    total_return: Decimal
    total_return_percent: Decimal
    has_strategies: bool
