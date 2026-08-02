"""Canonical internal-object -> proto mappers for portfolio reads.

Proto is the single source of truth for the read/wire shape (decision 1A): these
functions map the ledger read-model views and the strategy-performance compute
results straight to the generated proto messages, with no intermediate Pydantic
layer and money kept as ``Decimal`` end-to-end — emitted as
``common_pb2.Decimal(value=str(value))``.

Proto field names are authoritative: the ledger ``TransactionView`` carries
``qty``/``occurred_at`` but the proto ``Transaction`` carries ``quantity``/
``timestamp``, and the mapper resolves that here. Transaction types are a STRING
taxonomy on the read-model but an int ``TransactionType`` enum on the proto, so
they are converted through an explicit map (never int-vs-string comparison).

Nullable message fields are ``CopyFrom``-ed only when the source has a value;
scalar monetary fields the read path always populates carry ``"0"`` when the
underlying value is absent.
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from llamatrade_proto.generated import common_pb2, portfolio_pb2, trading_pb2
from llamatrade_proto.timestamps import to_proto_timestamp

from src.ledger.analytics import EquityMetrics
from src.ledger.read_model import PositionView, SummaryView, TradeStats, TransactionView

if TYPE_CHECKING:
    from src.services.strategy_performance_service import BookTotals

_ZERO = Decimal("0")

# Read-model transaction label (string taxonomy) -> proto TransactionType.
TXN_TYPE_TO_PROTO: dict[str, portfolio_pb2.TransactionType.ValueType] = {
    "buy": portfolio_pb2.TRANSACTION_TYPE_BUY,
    "sell": portfolio_pb2.TRANSACTION_TYPE_SELL,
    "deposit": portfolio_pb2.TRANSACTION_TYPE_DEPOSIT,
    "withdrawal": portfolio_pb2.TRANSACTION_TYPE_WITHDRAWAL,
    "dividend": portfolio_pb2.TRANSACTION_TYPE_DIVIDEND,
    "interest": portfolio_pb2.TRANSACTION_TYPE_INTEREST,
    "fee": portfolio_pb2.TRANSACTION_TYPE_FEE,
    "transfer_in": portfolio_pb2.TRANSACTION_TYPE_TRANSFER_IN,
    "transfer_out": portfolio_pb2.TRANSACTION_TYPE_TRANSFER_OUT,
}

_PERIOD_RETURN_KEYS = (
    "return_1d",
    "return_1w",
    "return_1m",
    "return_3m",
    "return_6m",
    "return_1y",
    "return_ytd",
    "return_all",
)


def _dec(value: Decimal | float | int | str) -> common_pb2.Decimal:
    """Proto Decimal via str, so DB Decimals keep scale and floats avoid drift."""
    return common_pb2.Decimal(value=str(value))


def position_view_to_proto(view: PositionView) -> trading_pb2.Position:
    """Map an aggregated ``PositionView`` to a proto Position.

    Aggregated holdings span sleeves/accounts, so there is no single id/session
    and no per-lot ``realized_pnl``; those (and ``available_quantity``) are left
    unset rather than blanked with a fake value.
    """
    side = (
        trading_pb2.POSITION_SIDE_LONG if view.side == "long" else trading_pb2.POSITION_SIDE_SHORT
    )
    return trading_pb2.Position(
        symbol=view.symbol,
        side=side,
        quantity=_dec(view.qty),
        cost_basis=_dec(view.cost_basis),
        average_entry_price=_dec(view.avg_entry_price),
        current_price=_dec(view.current_price),
        market_value=_dec(view.market_value),
        unrealized_pnl=_dec(view.unrealized_pnl),
        unrealized_pnl_percent=_dec(view.unrealized_pnl_percent),
    )


def transaction_view_to_proto(
    view: TransactionView, *, tenant_id: UUID, description: str = ""
) -> portfolio_pb2.Transaction:
    """Map a ``TransactionView`` to a proto Transaction (7A field names, 5A money)."""
    try:
        txn_id = UUID(view.event_id)
    except ValueError:
        txn_id = UUID(int=0)
    occurred = view.occurred_at if isinstance(view.occurred_at, datetime) else datetime.now(UTC)
    return portfolio_pb2.Transaction(
        id=str(txn_id),
        portfolio_id=str(tenant_id),
        type=TXN_TYPE_TO_PROTO.get(view.type, portfolio_pb2.TRANSACTION_TYPE_BUY),
        symbol=view.symbol or "",
        quantity=_dec(view.qty if view.qty is not None else _ZERO),
        price=_dec(view.price if view.price is not None else _ZERO),
        amount=_dec(view.amount),
        fees=_dec(view.fees),
        description=description,
        timestamp=to_proto_timestamp(occurred),
    )


def period_returns_to_proto(
    returns: Mapping[str, Decimal],
) -> portfolio_pb2.StrategyPeriodReturns:
    """Map computed period returns (present keys only) to proto; missing -> ``"0"``."""
    return portfolio_pb2.StrategyPeriodReturns(
        **{key: _dec(returns.get(key, _ZERO)) for key in _PERIOD_RETURN_KEYS}
    )


def equity_point_to_proto(
    *,
    timestamp: datetime,
    equity: Decimal,
    return_percent: Decimal | None = None,
    drawdown: Decimal | None = None,
    benchmark_value: Decimal | None = None,
) -> portfolio_pb2.StrategyEquityPoint:
    """Map one equity-curve point; nullable stats are set only when computed."""
    point = portfolio_pb2.StrategyEquityPoint(
        timestamp=to_proto_timestamp(timestamp), equity=_dec(equity)
    )
    if return_percent is not None:
        point.return_percent.CopyFrom(_dec(return_percent))
    if drawdown is not None:
        point.drawdown.CopyFrom(_dec(drawdown))
    if benchmark_value is not None:
        point.benchmark_value.CopyFrom(_dec(benchmark_value))
    return point


def benchmark_series_to_proto(
    *,
    symbol: str,
    points: list[portfolio_pb2.StrategyEquityPoint],
    total_return: Decimal | None = None,
) -> portfolio_pb2.BenchmarkData:
    """Map a rebased benchmark series to proto BenchmarkData."""
    return portfolio_pb2.BenchmarkData(
        symbol=symbol,
        name=symbol,
        equity_curve=points,
        total_return=_dec(total_return if total_return is not None else _ZERO),
    )


def strategy_summary_to_proto(
    *,
    execution_id: UUID,
    strategy_id: UUID,
    strategy_name: str,
    mode: common_pb2.ExecutionMode.ValueType,
    status: common_pb2.ExecutionStatus.ValueType,
    color: str | None,
    allocated_capital: Decimal | None,
    current_value: Decimal | None,
    positions_count: int,
    returns: portfolio_pb2.StrategyPeriodReturns,
    started_at: datetime | None,
    updated_at: datetime,
) -> portfolio_pb2.StrategyPerformanceSummary:
    """Map an assembled strategy summary to proto.

    ``mode``/``status`` are the proto enum ints straight off the execution row
    (stored proto-int via TypeDecorator) — no string round-trip. Capital fields
    carry ``"0"`` for an unfunded execution so the aggregate reads stay numeric.
    """
    summary = portfolio_pb2.StrategyPerformanceSummary(
        execution_id=str(execution_id),
        strategy_id=str(strategy_id),
        strategy_name=strategy_name,
        mode=mode,
        status=status,
        color=color or "",
        allocated_capital=_dec(allocated_capital if allocated_capital is not None else _ZERO),
        current_value=_dec(current_value if current_value is not None else _ZERO),
        positions_count=positions_count,
        returns=returns,
        updated_at=to_proto_timestamp(updated_at),
    )
    if started_at is not None:
        summary.started_at.CopyFrom(to_proto_timestamp(started_at))
    return summary


def live_metrics_to_proto(
    m: EquityMetrics | None,
    stats: TradeStats,
    *,
    starting_capital: Decimal | None,
    current_equity: Decimal | None,
    peak_equity: Decimal | None,
    current_drawdown: Decimal | None,
) -> portfolio_pb2.StrategyLiveMetrics:
    """Map realized-trade stats + equity-series metrics to proto StrategyLiveMetrics.

    Trade stats are always present (0 for no trades); return/risk metrics are set
    only when the series was long enough to derive them. ``calmar_ratio`` and the
    ``alpha``/``beta``/``correlation`` benchmark fields are not computed on the
    live path and are left unset.
    """
    metrics = portfolio_pb2.StrategyLiveMetrics(
        total_trades=stats.total_trades,
        winning_trades=stats.winning_trades,
        losing_trades=stats.losing_trades,
        win_rate=_dec(stats.win_rate),
        profit_factor=_dec(stats.profit_factor),
        average_win=_dec(stats.average_win),
        average_loss=_dec(stats.average_loss),
        total_pnl=_dec(stats.realized_pnl),
    )
    if m is not None:
        metrics.sharpe_ratio.CopyFrom(_dec(m.sharpe_ratio))
        metrics.sortino_ratio.CopyFrom(_dec(m.sortino_ratio))
        metrics.max_drawdown.CopyFrom(_dec(m.max_drawdown))
        metrics.volatility.CopyFrom(_dec(m.volatility))
    if current_drawdown is not None:
        metrics.current_drawdown.CopyFrom(_dec(current_drawdown))
    if starting_capital is not None:
        metrics.starting_capital.CopyFrom(_dec(starting_capital))
    if current_equity is not None:
        metrics.current_equity.CopyFrom(_dec(current_equity))
    if peak_equity is not None:
        metrics.peak_equity.CopyFrom(_dec(peak_equity))
    metrics.calculated_at.CopyFrom(to_proto_timestamp(datetime.now(UTC)))
    return metrics


def summary_view_to_proto(
    view: SummaryView,
    tenant_id: UUID,
    book: BookTotals | None = None,
) -> portfolio_pb2.Portfolio:
    """Map the account-wide SummaryView to a proto Portfolio.

    Equity / cash / positions value are the whole-account truth. Day and total
    return are reported on the STRATEGY-book basis (``book``) when the tenant has
    deployed strategies, so ListPortfolios reconciles with the per-strategy rows
    the UI renders; otherwise they fall back to the account figures.
    """
    if book is not None and book.has_strategies:
        total_return = book.total_return
        total_return_percent = book.total_return_percent
        day_return = book.day_pnl
        day_return_percent = book.day_pnl_percent
    else:
        total_return = view.total_unrealized_pnl + view.total_realized_pnl
        total_return_percent = view.total_pnl_percent
        day_return = view.day_pnl
        day_return_percent = view.day_pnl_percent

    return portfolio_pb2.Portfolio(
        id=str(tenant_id),
        tenant_id=str(tenant_id),
        user_id="",
        name="Main Portfolio",
        total_value=_dec(view.total_equity),
        cash_balance=_dec(view.cash),
        positions_value=_dec(view.market_value),
        total_return=_dec(total_return),
        total_return_percent=_dec(total_return_percent),
        day_return=_dec(day_return),
        day_return_percent=_dec(day_return_percent),
        updated_at=to_proto_timestamp(datetime.now(UTC)),
    )
